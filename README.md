# WorkerBee v2

Automated assistant for **Limbus Company**. Runs Mirror Dungeon, EXP & Thread
Luxcavation, plus a task scheduler that strings them together.

Download page: https://bonkier.github.io/workerbeev2/
Latest release: https://github.com/Bonkier/workerbeev2/releases/latest
Community: Discord, DM `@bnkir` for an invite.

---

## Requirements

- Windows 10/11
- Limbus Company in **1920x1080** windowed mode on the primary monitor
- If you're building from source: Python **3.11 / 3.12 / 3.13** and the
  Microsoft Build Tools (SDK + Desktop C++ + MSVC 14.x):
  https://visualstudio.microsoft.com/downloads/?q=build+tools

## Install (released build)

1. Download `WorkerBee_v2.zip` from the
   [latest release](https://github.com/Bonkier/workerbeev2/releases/latest).
2. Extract anywhere on disk.
3. Run `WorkerBee_v2.exe`. Settings live in `%LOCALAPPDATA%\WorkerBee\` and
   survive updates.

## Build from source

```
git clone https://github.com/Bonkier/workerbeev2.git
cd workerbeev2
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python v2_launcher.py
```

To produce a distributable bundle:

```
pyinstaller WorkerBee_v2.spec
```

The build drops at `dist/WorkerBee_v2/`.

## Attribution

The automation backend is derived from **[Charge-Grinder](https://github.com/Walpth/Charge-Grinder)**
by **Walpth**, used under the terms of the GNU General Public License v3.0.
The Qt user interface, scheduler, in-app updater, theming system, build
pipeline, and image set are original work on top of that backend.

This project is distributed under the GNU GPL v3 (see [LICENSE](LICENSE)).
That means the source must remain open and any redistribution, modified or
not, must preserve the same license.

## Disclaimer

WorkerBee automates input against the live Limbus Company client. Project
Moon has not endorsed it. The license imposes no warranty; use of any game
automation tool may violate the game's Terms of Service. Use it on accounts
you accept the risk of losing.
