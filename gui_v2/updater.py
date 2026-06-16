# SPDX-License-Identifier: GPL-3.0-or-later
"""
GitHub-release-based in-app updater.

User flow (the only flow):

    1. User clicks "Update now" (Help page).
    2. We hit the GitHub API for the latest release of the configured
       repo. If our embedded `version`/`version.json` is already at-or-
       above the tag, we tell the user they're up to date and stop.
    3. Otherwise we download the release's `.zip` asset to a temp file,
       streaming progress callbacks back to the UI.
    4. We write a small `.bat` helper to %TEMP%, spawn it detached, and
       quit Qt. The helper:
         * waits 2 s for the running exe to release file locks,
         * extracts the zip to a sibling staging dir,
         * mirrors the staging dir into the install directory with
           robocopy /MIR,
         * deletes the staging dir + the downloaded zip,
         * relaunches the (now-updated) exe,
         * self-deletes.

Configs are safe by construction: the bundled exe stores settings under
`%LOCALAPPDATA%\\WorkerBee\\config\\`, which lives outside the install
directory. robocopy /MIR only touches files inside the install dir.

If anything in steps 2-3 fails, we surface a clear error and the user's
install is untouched. If extraction in the helper fails, the helper
deletes the staging dir + the zip and exits without restarting; the
user is left with the working old install.

Source-tree (`python v2_launcher.py`) runs cannot self-update - they
don't have a frozen exe to swap. We detect that and tell the user.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
import subprocess
from typing import Callable, Optional
import urllib.error
import urllib.request


# ---------------------------------------------------------------------------
# Repo target. The user owns the GitHub account and the release pipeline.
# Edit this constant to point at a different repo; the rest of the module
# uses GITHUB_API_LATEST derived from it.
# ---------------------------------------------------------------------------
GITHUB_REPO = "Bonkier/workerbeev2"
GITHUB_API_LATEST = (
    f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
)

_USER_AGENT = "WorkerBee-Updater"
_DEFAULT_TIMEOUT = 15


_log = logging.getLogger(__name__)


class UpdateError(RuntimeError):
    """Raised when any updater stage fails. The message is user-facing,
    so keep it short and readable in a status line."""


# ---------------------------------------------------------------------------
# GitHub API
# ---------------------------------------------------------------------------

def _http_open(url: str, timeout: float = _DEFAULT_TIMEOUT):
    """Open `url` with the GitHub API headers. Caller closes."""
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": _USER_AGENT,
        },
    )
    return urllib.request.urlopen(req, timeout=timeout)


def check_latest_release() -> dict:
    """Query GitHub for the latest published release of `GITHUB_REPO`.

    Returns a dict with keys:
        version        - tag_name, lowercased + 'v' stripped (e.g. '2.0.1')
        download_url   - direct-link URL to the .zip asset
        size           - bytes (int, 0 if GitHub didn't report it)

    Raises `UpdateError` if the repo is missing, no releases exist, the
    release has no .zip asset, or the network is unreachable.

    The endpoint can be overridden at call time with the
    `WORKERBEE_UPDATE_API_URL` env var. This is used by the simulation
    harness to point at a localhost mock server - production runs leave
    it unset and hit GitHub directly.
    """
    api_url = os.environ.get("WORKERBEE_UPDATE_API_URL") or GITHUB_API_LATEST
    try:
        with _http_open(api_url) as r:
            payload = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise UpdateError(
                f"No releases on {GITHUB_REPO} yet."
            ) from exc
        raise UpdateError(
            f"GitHub returned HTTP {exc.code}."
        ) from exc
    except urllib.error.URLError as exc:
        raise UpdateError(
            f"Could not reach GitHub: {exc.reason}"
        ) from exc
    except Exception as exc:                # JSON decode, socket weirdness
        raise UpdateError(
            f"Update check failed: {exc}"
        ) from exc

    tag = (payload.get("tag_name") or payload.get("name") or "0.0.0")
    tag = tag.lstrip("v").lstrip("V")

    # Find the .zip asset. There should be exactly one for our build
    # pipeline; if there are multiple, prefer one whose name contains
    # 'WorkerBee_v2'.
    candidates = []
    for asset in payload.get("assets") or []:
        name = str(asset.get("name", "")).lower()
        if name.endswith(".zip"):
            candidates.append(asset)
    if not candidates:
        raise UpdateError(
            "Latest release has no .zip asset to download."
        )
    candidates.sort(
        key=lambda a: "workerbee_v2" in str(a.get("name", "")).lower(),
        reverse=True,
    )
    pick = candidates[0]
    return {
        "version": tag,
        "download_url": pick["browser_download_url"],
        "size": int(pick.get("size") or 0),
    }


def _parse_version(v: str) -> tuple:
    """`'2.0.1'` -> `(2, 0, 1)`. Non-numeric chunks become 0 so weird
    tags compare sensibly without raising."""
    out = []
    for chunk in str(v).lstrip("v").lstrip("V").split("."):
        try:
            out.append(int(chunk))
        except ValueError:
            out.append(0)
    return tuple(out)


def is_newer(remote: str, current: str) -> bool:
    """True if `remote` is strictly greater than `current`."""
    return _parse_version(remote) > _parse_version(current)


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

ProgressFn = Callable[[int, int], None]


def download_release(url: str, dest_path: str,
                     on_progress: Optional[ProgressFn] = None,
                     chunk_size: int = 256 * 1024) -> None:
    """Stream `url` to `dest_path`, invoking `on_progress(done, total)`
    after each chunk. `total` is 0 when the server didn't send a
    Content-Length header. On any error the partial file is deleted and
    `UpdateError` is raised."""
    if on_progress is None:
        on_progress = lambda d, t: None
    try:
        with _http_open(url, timeout=60) as resp:
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            on_progress(done, total)
            with open(dest_path, "wb") as f:
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    on_progress(done, total)
    except Exception as exc:
        try:
            os.remove(dest_path)
        except OSError:
            pass
        raise UpdateError(f"Download failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Install + restart
# ---------------------------------------------------------------------------

def is_frozen() -> bool:
    """True iff we're running from the PyInstaller bundle."""
    return bool(getattr(sys, "frozen", False))


def install_dir() -> Optional[str]:
    """Directory the running exe lives in, when frozen. None when running
    from source (no install dir to swap)."""
    if not is_frozen():
        return None
    return os.path.dirname(os.path.abspath(sys.executable))


def exe_path() -> Optional[str]:
    """Absolute path to the running .exe, or None when not frozen."""
    return os.path.abspath(sys.executable) if is_frozen() else None


def _helper_script(zip_path: str, dest_dir: str, exe_to_launch: str) -> str:
    """Return the .bat body that performs the swap + restart. Inlined
    here so we don't have to ship a separate file."""
    # Note: %~2 etc. are 1-indexed batch positional args; we hardcode the
    # paths here rather than passing them as args so the helper survives
    # spaces and ampersands without needing complex quoting. Single
    # backslashes in the source produce single backslashes on disk
    # because this is a normal Python str literal, not raw.
    return (
        "@echo off\r\n"
        "REM Wait for the parent exe to release file locks. PySide6 +\r\n"
        "REM the Qt event loop can hold handles a moment after the\r\n"
        "REM main window closes, so we give them 5s rather than 2s.\r\n"
        "timeout /t 5 /nobreak >NUL\r\n"
        "\r\n"
        f'set "ZIP={zip_path}"\r\n'
        f'set "INSTALL={dest_dir}"\r\n'
        f'set "EXE={exe_to_launch}"\r\n'
        'set "STAGE=%TEMP%\\WorkerBee_update_stage_%RANDOM%%RANDOM%"\r\n'
        '\r\n'
        'mkdir "%STAGE%" 2>NUL\r\n'
        'powershell -NoLogo -NoProfile -Command '
        '"try { Expand-Archive -Force -Path \'%ZIP%\' -DestinationPath \'%STAGE%\'; exit 0 } '
        'catch { exit 1 }"\r\n'
        'if errorlevel 1 (\r\n'
        '    rmdir /S /Q "%STAGE%" 2>NUL\r\n'
        '    del "%ZIP%" 2>NUL\r\n'
        '    exit /b 1\r\n'
        ')\r\n'
        '\r\n'
        'REM Some zips wrap their contents in a WorkerBee_v2\\ folder; some don\'t.\r\n'
        'REM Pick the right source root so robocopy mirrors the actual install layout.\r\n'
        'if exist "%STAGE%\\WorkerBee_v2\\WorkerBee_v2.exe" (\r\n'
        '    set "SRC=%STAGE%\\WorkerBee_v2"\r\n'
        ') else (\r\n'
        '    set "SRC=%STAGE%"\r\n'
        ')\r\n'
        '\r\n'
        'REM Mirror new contents into the install dir. Configs live under\r\n'
        'REM %LOCALAPPDATA%\\WorkerBee\\config\\ which is outside the install\r\n'
        'REM dir, so /MIR does NOT touch them.\r\n'
        'REM /R:10 /W:3 gives 30s of retry budget so a slow parent exit\r\n'
        'REM never wedges the swap. The version file mirror itself is\r\n'
        'REM 5 bytes; retries cost nothing if the lock clears fast.\r\n'
        'robocopy "%SRC%" "%INSTALL%" /MIR /R:10 /W:3 /NFL /NDL /NJH /NJS /nc /ns >NUL\r\n'
        '\r\n'
        'rmdir /S /Q "%STAGE%" 2>NUL\r\n'
        'del "%ZIP%" 2>NUL\r\n'
        'REM Pass --post-update so v2_launcher clears the in-progress\r\n'
        'REM marker file. Any unrelated double-launch during this window\r\n'
        'REM would not have the flag and gets blocked at startup.\r\n'
        'start "" "%EXE%" --post-update\r\n'
        'del "%~f0" 2>NUL\r\n'
    )


def apply_update_and_restart(zip_path: str) -> None:
    """Spawn the Windows helper that swaps files and restarts the exe.
    This function returns immediately - the caller must then quit Qt
    so the helper can take over file locks.

    Raises UpdateError when called from a source-tree run (no install
    dir to swap) or when the helper can't be spawned."""
    dest_dir = install_dir()
    exe = exe_path()
    if not dest_dir or not exe:
        raise UpdateError(
            "Source-tree runs can't self-update. "
            "Rebuild via PyInstaller for in-app updates."
        )

    # Drop the in-progress marker BEFORE spawning the helper. If we wrote
    # it after, there'd be a tiny window where the helper was running and
    # the lock didn't exist yet - a fast double-click could squeeze in.
    write_update_lock()

    helper_path = os.path.join(
        tempfile.gettempdir(),
        f"WorkerBee_apply_{os.getpid()}.bat",
    )
    body = _helper_script(zip_path, dest_dir, exe)
    try:
        with open(helper_path, "w", encoding="utf-8") as f:
            f.write(body)
    except OSError as exc:
        raise UpdateError(
            f"Couldn't write installer helper: {exc}"
        ) from exc

    flags = 0
    for attr in ("DETACHED_PROCESS", "CREATE_NO_WINDOW",
                 "CREATE_NEW_PROCESS_GROUP"):
        flags |= getattr(subprocess, attr, 0)
    try:
        # `cmd /c start "" /min` makes Windows release the parent's
        # console handle so this exe can exit before the helper does
        # its work. /min keeps the brief flash off the foreground.
        subprocess.Popen(
            ["cmd.exe", "/c", "start", "", "/min",
             "cmd.exe", "/c", helper_path],
            creationflags=flags,
            close_fds=True,
        )
    except OSError as exc:
        raise UpdateError(
            f"Couldn't spawn installer helper: {exc}"
        ) from exc

    _log.info("update: helper spawned (%s); exe will restart shortly",
              helper_path)


# ---------------------------------------------------------------------------
# Convenience: one-shot orchestration
# ---------------------------------------------------------------------------

def staging_zip_path(version: str) -> str:
    """Stable temp path for the downloaded zip."""
    return os.path.join(
        tempfile.gettempdir(),
        f"WorkerBee_v2_update_{version}.zip",
    )


# ---------------------------------------------------------------------------
# Update-in-progress lock
#
# When a swap is in flight there's a ~25 s window between the parent exe
# exiting and the freshly-installed exe coming up - the helper batch is
# extracting + robocopying detached, and no WorkerBee window is on screen.
# If the user double-clicks the shortcut during that window we'd start a
# second instance racing with the swap and the user would probably end up
# with a half-mirrored install.
#
# The lock file at %LOCALAPPDATA%\WorkerBee\update.lock papers over this:
#   - written by apply_update_and_restart() just before spawning the helper
#   - the helper passes `--post-update` to the relaunched exe, which clears
#     the lock at startup
#   - any OTHER startup within ~90 s of the lock's mtime is treated as a
#     mid-swap relaunch attempt and refused with a friendly message
#   - stale locks (older than 90 s, e.g. from a crashed update) are
#     silently cleaned up
# ---------------------------------------------------------------------------

def _lock_file_path() -> str:
    """%LOCALAPPDATA%\\WorkerBee\\update.lock (or a temp-dir fallback if
    LOCALAPPDATA is somehow unset, which doesn't happen on real Windows)."""
    base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
    return os.path.join(base, "WorkerBee", "update.lock")


def write_update_lock() -> None:
    """Drop the in-progress marker. Best-effort: a failure to write the
    lock just means the next launch loses the guardrail, not that the
    update itself broke."""
    import time as _time
    path = _lock_file_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(str(_time.time()))
    except OSError as exc:
        _log.warning("update lock write failed: %s", exc)


def clear_update_lock() -> None:
    """Remove the marker. Called by the post-update relaunch as soon as
    it knows the new exe is healthy."""
    try:
        os.remove(_lock_file_path())
    except OSError:
        pass


def is_update_in_progress(max_age_seconds: float = 90.0) -> bool:
    """True if there's a fresh marker file. Stale markers (older than
    `max_age_seconds`) are removed and treated as not-in-progress so a
    crashed update never permanently blocks future launches."""
    import time as _time
    path = _lock_file_path()
    try:
        mtime = os.path.getmtime(path)
        if _time.time() - mtime < max_age_seconds:
            return True
        os.remove(path)              # stale, clean it
    except OSError:
        pass
    return False


__all__ = [
    "GITHUB_REPO",
    "UpdateError",
    "check_latest_release",
    "is_newer",
    "download_release",
    "is_frozen",
    "install_dir",
    "exe_path",
    "apply_update_and_restart",
    "staging_zip_path",
    "is_update_in_progress",
    "write_update_lock",
    "clear_update_lock",
]
