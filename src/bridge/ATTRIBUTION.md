# Bridge Attribution

The files in this directory (`bridge.dll`, `bridge.py`) are derived from
Charge-Grinder by AlexWalp (Walpth), licensed under GNU General Public
License v3.

- Upstream: https://github.com/Walpth/Charge-Grinder
  (moved from the retired https://github.com/AlexWalp/Mirror-Dungeon-Bot)
- Vendored from commit 2ff48811 (2026-07-16, "windows upgrade": the
  DLL checks the driver version on the device as well as G Hub's
  installed version, accepts the Logicool branding, and renames the
  exports z0..z16 to electric_sheep_*; the "U.T.B." diagnose() stays)
- License: GPL v3 (see LICENSE in repo root)

WorkerBee as a whole is distributed under GPL v3 as a consequence of
incorporating these files.
