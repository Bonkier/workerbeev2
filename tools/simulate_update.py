# SPDX-License-Identifier: GPL-3.0-or-later
"""End-to-end simulation of the in-app updater.

Stages a v1.9.0 install and a v2.0.0 release zip behind a localhost mock
of `releases/latest`, then drives each public updater function and
verifies the swap landed. Helper batch runs inline (not detached) so we
can wait + inspect.

    python tools/simulate_update.py
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


# Make gui_v2 / src importable regardless of cwd.
HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
for p in (PROJECT_ROOT, os.path.join(PROJECT_ROOT, "src")):
    if p not in sys.path:
        sys.path.insert(0, p)

from gui_v2 import updater   # noqa: E402  (sys.path patched above)


def step(n: int, msg: str) -> None:
    print(f"\n--- step {n}: {msg} ---", flush=True)


def info(msg: str) -> None:
    print(f"  {msg}", flush=True)


def ok(msg: str) -> None:
    print(f"  [OK] {msg}", flush=True)


def fail(msg: str) -> None:
    print(f"  [FAIL] {msg}", flush=True)
    sys.exit(1)


def write_version(install_dir: str, version: str) -> None:
    """Stamp version into _internal/{version,version.json}, matching what
    splash._read_version reads from a PyInstaller bundle."""
    internal = os.path.join(install_dir, "_internal")
    for name in ("version", "version.json"):
        with open(os.path.join(internal, name), "w", encoding="utf-8") as f:
            f.write(version)


def read_version(install_dir: str) -> str:
    """Read stamped version, matching splash._read_version's order."""
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


class _MockGitHubHandler(http.server.SimpleHTTPRequestHandler):
    """GET /repos/.../releases/latest returns canned JSON; everything else
    falls through to static file serving (trivial zip download)."""

    server_version = "MockGH/1.0"
    asset_url: str = ""        # set before serve
    asset_size: int = 0        # set before serve

    def log_message(self, *_a, **_kw):
        return  # silence per-request spam

    def do_GET(self):                       # noqa: N802
        if self.path.startswith("/repos/") and self.path.endswith("/releases/latest"):
            payload = {
                "tag_name": "v2.0.0",
                "name": "v2.0.0",
                "assets": [
                    {
                        "name": "WorkerBee_v2.zip",
                        "browser_download_url": self.asset_url,
                        "size": self.asset_size,
                    }
                ],
            }
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        return super().do_GET()


def start_mock_server(serve_root: str, asset_path: str) -> tuple[str, threading.Thread, socketserver.TCPServer]:
    """Start mock server -> (base_url, thread, server).

    Anchors the static handler at `serve_root` via the `directory` param -
    thread-safe, unlike a chdir-based override.
    """
    _MockGitHubHandler.asset_url = ""        # filled once port is bound
    _MockGitHubHandler.asset_size = os.path.getsize(asset_path)

    def factory(*args, **kwargs):
        return _MockGitHubHandler(*args, directory=serve_root, **kwargs)

    httpd = socketserver.TCPServer(("127.0.0.1", 0), factory)
    port = httpd.server_address[1]
    base = f"http://127.0.0.1:{port}"
    zip_name = os.path.basename(asset_path)
    _MockGitHubHandler.asset_url = f"{base}/{zip_name}"

    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return base, t, httpd


def main() -> int:
    DIST_BUILT = os.path.join(PROJECT_ROOT, "dist", "WorkerBee_v2")
    if not os.path.isdir(DIST_BUILT):
        fail(f"No built bundle at {DIST_BUILT!r}. "
             f"Run `python -m PyInstaller WorkerBee_v2.spec --noconfirm` first.")

    workdir = tempfile.mkdtemp(prefix="workerbee_update_sim_")
    info(f"workdir: {workdir}")

    step(1, "stage the v1.9 'local install' from the current build")
    install_dir = os.path.join(workdir, "install_v1_9")
    shutil.copytree(DIST_BUILT, install_dir)
    write_version(install_dir, "1.9.0")
    info(f"install_dir: {install_dir}")
    info(f"  version reads as: v{read_version(install_dir)}")
    ok("v1.9.0 install in place")

    step(2, "stage the v2.0 'GitHub release' zip")
    serve_root = os.path.join(workdir, "serve")
    v2_stage = os.path.join(serve_root, "WorkerBee_v2")
    os.makedirs(serve_root)
    shutil.copytree(DIST_BUILT, v2_stage)
    write_version(v2_stage, "2.0.0")
    info(f"v2.0 staged at: {v2_stage}  (version: v{read_version(v2_stage)})")

    zip_path = os.path.join(serve_root, "WorkerBee_v2.zip")
    info("zipping v2.0 -> WorkerBee_v2.zip ...")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(v2_stage):
            for name in files:
                abs_path = os.path.join(root, name)
                arc = os.path.relpath(abs_path, serve_root)
                zf.write(abs_path, arc)
    shutil.rmtree(v2_stage)
    info(f"  zip: {zip_path}  ({os.path.getsize(zip_path)} bytes)")
    ok("v2.0.0 release ready to serve")

    step(3, "spin up a localhost HTTP server pretending to be GitHub")
    base, _t, httpd = start_mock_server(serve_root, zip_path)
    info(f"mock GitHub at: {base}")
    api = f"{base}/repos/Bonkier/workerbeev2/releases/latest"
    info(f"  releases endpoint: {api}")
    ok("mock GitHub up")

    original_api = updater.GITHUB_API_LATEST
    updater.GITHUB_API_LATEST = api

    try:
        step(4, "check_latest_release() against the mock")
        info_dict = updater.check_latest_release()
        info(f"returned: {info_dict}")
        if info_dict["version"] != "2.0.0":
            fail(f"expected v2.0.0, got v{info_dict['version']}")
        if info_dict["size"] != os.path.getsize(zip_path):
            fail("size mismatch between API and on-disk zip")
        ok("remote version: v2.0.0  +  download URL  +  size")

        step(5, "is_newer(remote, local) decision")
        decision = updater.is_newer(info_dict["version"], "1.9.0")
        info(f"is_newer('2.0.0', '1.9.0') -> {decision}")
        if not decision:
            fail("comparator failed to flag the upgrade")
        ok("update is needed")

        step(6, "download_release() streams the v2.0 zip")
        downloaded = os.path.join(workdir, "downloaded_v2_0.zip")
        chunks_seen = []

        def on_progress(done: int, total: int) -> None:
            chunks_seen.append((done, total))

        updater.download_release(info_dict["download_url"],
                                 downloaded, on_progress)
        on_disk = os.path.getsize(downloaded)
        info(f"downloaded {on_disk} bytes  ({len(chunks_seen)} progress callbacks)")
        if on_disk != info_dict["size"]:
            fail("downloaded size does not match the served size")
        ok("zip downloaded intact")

        step(7, "build the install helper batch and run it INLINE")
        # Production spawns the helper detached; here we run it via
        # subprocess.run() so we can wait + inspect. EXE arg points at a
        # no-op so nothing relaunches.
        no_op_exe = os.path.join(workdir, "noop.bat")
        with open(no_op_exe, "w", encoding="utf-8") as f:
            f.write("@echo off\r\n")
        body = updater._helper_script(downloaded, install_dir, no_op_exe)

        helper_bat = os.path.join(workdir, "apply.bat")
        with open(helper_bat, "w", encoding="utf-8") as f:
            f.write(body)

        info(f"helper batch: {helper_bat}")
        info(f"install target: {install_dir}")
        info("running helper inline (waiting for it to finish)...")
        result = subprocess.run(
            ["cmd.exe", "/c", helper_bat],
            capture_output=True, text=True, timeout=90,
        )
        if result.returncode not in (0, 1, 2, 3):
            # robocopy uses 0..7 for success-ish; treat 0..3 as fine.
            info(f"stdout: {result.stdout}")
            info(f"stderr: {result.stderr}")
            fail(f"helper exited {result.returncode}")
        ok(f"helper finished (rc={result.returncode})")

        step(8, "verify the install dir is now v2.0.0")
        new_v = read_version(install_dir)
        info(f"install_dir version file reads: v{new_v}")
        if new_v != "2.0.0":
            fail("install dir did NOT pick up the new version")
        ok("install dir successfully swapped to v2.0.0")

        # Helper should have deleted the staging zip.
        if os.path.exists(downloaded):
            info(f"NOTE: helper left the zip behind at {downloaded}")
        else:
            ok("helper cleaned up the downloaded zip")

    finally:
        updater.GITHUB_API_LATEST = original_api
        httpd.shutdown()
        # Leave workdir for inspection.
        info("")
        info(f"All artefacts left under: {workdir}")

    print("\n=== simulation complete ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
