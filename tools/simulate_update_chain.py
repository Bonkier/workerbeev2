# SPDX-License-Identifier: GPL-3.0-or-later
"""Visual end-to-end simulation of three chained in-app updates.

Spawns the real WorkerBee_v2.exe in a sandbox install stamped v1.9.0 and
points it (via WORKERBEE_UPDATE_API_URL) at a localhost mock that reads
the "latest" version from `current.txt`. After each swap the watcher
bumps the mock to the next ladder entry so the relaunched exe sees a new
update: v1.9.0 -> v2.0.0 -> v2.1.0 -> v2.3.0.

    python tools/simulate_update_chain.py
"""
from __future__ import annotations

import http.server
import json
import os
import shutil
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
import zipfile


HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
for p in (PROJECT_ROOT, os.path.join(PROJECT_ROOT, "src")):
    if p not in sys.path:
        sys.path.insert(0, p)


def hr(char: str = "=") -> None:
    print(char * 68, flush=True)


def step(msg: str) -> None:
    print(f"\n[step] {msg}", flush=True)


def info(msg: str) -> None:
    print(f"   {msg}", flush=True)


def ok(msg: str) -> None:
    print(f"   [OK] {msg}", flush=True)


def fail(msg: str) -> None:
    print(f"   [FAIL] {msg}", flush=True)
    sys.exit(1)


def mock(msg: str) -> None:
    print(f"   [mock]    {msg}", flush=True)


def watch(msg: str) -> None:
    print(f"   [watcher] {msg}", flush=True)


def write_version(install_dir: str, version: str) -> None:
    internal = os.path.join(install_dir, "_internal")
    for name in ("version", "version.json"):
        with open(os.path.join(internal, name), "w", encoding="utf-8") as f:
            f.write(version)


def read_version(install_dir: str) -> str:
    internal = os.path.join(install_dir, "_internal")
    for name in ("version", "version.json"):
        path = os.path.join(internal, name)
        try:
            with open(path, "r", encoding="utf-8") as f:
                v = f.read().strip()
                if v:
                    return v
        except OSError:
            continue
    return "?"


class _ChainHandler(http.server.SimpleHTTPRequestHandler):
    """Reads `current.txt` on every API hit to decide which version to
    advertise; static file lookups (zip downloads) use the default
    SimpleHTTPRequestHandler against `serve_root`."""

    server_version = "MockGH/chain"

    current_file: str = ""
    serve_root: str = ""

    def log_message(self, *_a, **_kw):
        return

    def do_GET(self):                       # noqa: N802
        if self.path.startswith("/repos/") and self.path.endswith("/releases/latest"):
            with open(self.current_file, "r", encoding="utf-8") as f:
                v = f.read().strip() or "0.0.0"
            zip_name = f"WorkerBee_v2_{v}.zip"
            zip_path = os.path.join(self.serve_root, zip_name)
            size = os.path.getsize(zip_path) if os.path.exists(zip_path) else 0
            payload = {
                "tag_name": f"v{v}",
                "name": f"v{v}",
                "assets": [
                    {
                        "name": zip_name,
                        "browser_download_url": (
                            f"http://127.0.0.1:{self.server.server_address[1]}"
                            f"/{zip_name}"
                        ),
                        "size": size,
                    }
                ],
            }
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            mock(f"served /releases/latest  ->  v{v}  ({zip_name}, {size} B)")
            return
        return super().do_GET()


def start_mock_server(serve_root: str, current_file: str):
    _ChainHandler.serve_root = serve_root
    _ChainHandler.current_file = current_file

    def factory(*args, **kwargs):
        return _ChainHandler(*args, directory=serve_root, **kwargs)

    # Threaded so splash check + zip download don't serialise.
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), factory)
    httpd.daemon_threads = True
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd, t


def build_release_zip(dist_dir: str, serve_root: str, version: str) -> str:
    """Copy dist_dir, stamp version, zip into serve_root, drop staging copy."""
    stage = tempfile.mkdtemp(prefix=f"WB_release_stage_v{version}_")
    try:
        bundle = os.path.join(stage, "WorkerBee_v2")
        shutil.copytree(dist_dir, bundle)
        write_version(bundle, version)
        zip_path = os.path.join(serve_root, f"WorkerBee_v2_{version}.zip")
        info(f"  zipping v{version}  ->  {os.path.basename(zip_path)}")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _dirs, files in os.walk(bundle):
                for name in files:
                    abs_path = os.path.join(root, name)
                    arc = os.path.relpath(abs_path, stage)
                    zf.write(abs_path, arc)
        size = os.path.getsize(zip_path)
        info(f"   -> v{version} zip ready: {size:,} bytes")
        return zip_path
    finally:
        shutil.rmtree(stage, ignore_errors=True)


class Watcher(threading.Thread):
    """Polls install_dir/_internal/version. Each time the advertised target
    version lands, advances `current.txt` to the next ladder entry."""

    def __init__(self, install_dir: str, current_file: str, ladder: list):
        super().__init__(daemon=True)
        self.install_dir = install_dir
        self.current_file = current_file
        self.ladder = ladder            # ["2.0.0", "2.1.0", "2.3.0"]
        self.journey = ["1.9.0"]        # observed versions in order
        self.done_event = threading.Event()
        self._last_seen = "1.9.0"
        self._idx = 0

    def run(self):
        # Advertise the first entry.
        with open(self.current_file, "w", encoding="utf-8") as f:
            f.write(self.ladder[0])
        watch(f"initial mock advertises v{self.ladder[0]}")

        while not self.done_event.is_set():
            time.sleep(0.4)
            try:
                v = read_version(self.install_dir)
            except Exception:
                continue
            if v == self._last_seen:
                continue
            self._last_seen = v
            self.journey.append(v)
            watch(f"install dir is now v{v}")
            # Advance once the advertised version lands.
            if self._idx < len(self.ladder) and v == self.ladder[self._idx]:
                self._idx += 1
                if self._idx < len(self.ladder):
                    nxt = self.ladder[self._idx]
                    with open(self.current_file, "w", encoding="utf-8") as f:
                        f.write(nxt)
                    watch(f"bumped mock to advertise v{nxt}")
                else:
                    watch("ladder exhausted - chain complete")
                    self.done_event.set()
                    return


def main() -> int:
    DIST_BUILT = os.path.join(PROJECT_ROOT, "dist", "WorkerBee_v2")
    EXE_NAME = "WorkerBee_v2.exe"
    if not os.path.isdir(DIST_BUILT):
        fail(f"No built bundle at {DIST_BUILT}. Rebuild via PyInstaller first.")
    if not os.path.isfile(os.path.join(DIST_BUILT, EXE_NAME)):
        fail(f"No {EXE_NAME} in {DIST_BUILT}.")

    workdir = tempfile.mkdtemp(prefix="workerbee_chain_sim_")
    print()
    hr()
    print(" Three chained in-app updates  -  visual end-to-end demo")
    print(f" workdir: {workdir}")
    hr()

    step("1. stage local install as v1.9.0")
    install_dir = os.path.join(workdir, "install")
    shutil.copytree(DIST_BUILT, install_dir)
    write_version(install_dir, "1.9.0")
    info(f"install dir: {install_dir}")
    info(f"stamped version: v{read_version(install_dir)}")
    ok("v1.9.0 install in place")

    step("2. stage the three GitHub release zips (v2.0.0, v2.1.0, v2.3.0)")
    serve_root = os.path.join(workdir, "serve")
    os.makedirs(serve_root)
    for v in ("2.0.0", "2.1.0", "2.3.0"):
        build_release_zip(DIST_BUILT, serve_root, v)
    ok("3 release zips ready to serve")

    step("3. start mock GitHub server (port chosen by OS)")
    current_file = os.path.join(workdir, "current.txt")
    with open(current_file, "w", encoding="utf-8") as f:
        f.write("2.0.0")        # bootstrap; watcher will rewrite
    httpd, _t = start_mock_server(serve_root, current_file)
    port = httpd.server_address[1]
    api_url = f"http://127.0.0.1:{port}/repos/Bonkier/workerbeev2/releases/latest"
    info(f"mock listening at: http://127.0.0.1:{port}")
    info(f"API endpoint: {api_url}")
    info(f"control file: {current_file} (currently v2.0.0)")
    ok("mock GitHub up")

    step("4. start watcher (bumps mock to next ladder entry on each swap)")
    ladder = ["2.0.0", "2.1.0", "2.3.0"]
    watcher = Watcher(install_dir, current_file, ladder)
    watcher.start()
    info(f"ladder: {' -> '.join('v' + v for v in ladder)}")
    ok("watcher running")

    # A demo killed mid-update can leave update.lock behind, which blocks
    # the v1.9 launch with an "Update in progress" MessageBox.
    local_appdata = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
    stale_lock = os.path.join(local_appdata, "WorkerBee", "update.lock")
    try:
        os.remove(stale_lock)
        info(f"removed stale update.lock at {stale_lock}")
    except OSError:
        pass

    step("5. launch the v1.9.0 install with the env override")
    env = os.environ.copy()
    env["WORKERBEE_UPDATE_API_URL"] = api_url
    # Force every launch into update-check mode. The helper relaunches with
    # no args, so this env var must carry through the chain.
    env["WORKERBEE_FORCE_UPDATE_CHECK"] = "1"
    exe_path = os.path.join(install_dir, EXE_NAME)
    info(f"exe: {exe_path}")
    info(f"env: WORKERBEE_UPDATE_API_URL={api_url}")
    print()
    info(">>>>  WorkerBee_v2 will now appear on your screen.  <<<<")
    info(">>>>  Click 'Yes' on each 'Update available' prompt. <<<<")
    info(">>>>  After the THIRD update lands at v2.3.0, the app will be")
    info(">>>>  running normally - close it whenever you're done.")
    print()

    # Detach: exe restarts itself via the helper batches, so we follow the
    # install dir rather than the process tree.
    flags = 0
    for attr in ("DETACHED_PROCESS", "CREATE_NEW_PROCESS_GROUP"):
        flags |= getattr(subprocess, attr, 0)
    subprocess.Popen(
        [exe_path],
        cwd=install_dir,
        env=env,
        creationflags=flags,
        close_fds=True,
    )
    ok("exe spawned")

    step("6. waiting for the chain to reach v2.3.0...")
    # Each round needs a user click plus unzip + robocopy + relaunch.
    timeout = 600.0
    deadline = time.monotonic() + timeout
    while not watcher.done_event.is_set():
        if time.monotonic() > deadline:
            info(f"!! timeout after {timeout:.0f}s")
            info(f"   journey so far: {' -> '.join('v' + v for v in watcher.journey)}")
            info(f"   install currently reads: v{read_version(install_dir)}")
            break
        time.sleep(2.0)

    print()
    hr()
    print(" Chain summary")
    hr()
    print(f"   observed journey: {' -> '.join('v' + v for v in watcher.journey)}")
    print(f"   final install version (filesystem): v{read_version(install_dir)}")
    print(f"   workdir (left intact for inspection): {workdir}")
    if read_version(install_dir) == "2.3.0":
        print()
        print("   [OK] full chain landed: 1.9.0 -> 2.0.0 -> 2.1.0 -> 2.3.0")
    hr()
    print(" The launched WorkerBee_v2 process is still running.")
    print(" Close it from its window when you're done.")
    hr()

    # Keep the mock alive so the final exe can finish its "up to date"
    # splash check (mock + install both read 2.3.0).
    time.sleep(60)
    httpd.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
