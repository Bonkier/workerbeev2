# Automation Backend Attribution

The code under `src/wbcore/` is ported from **Charge-Grinder** by
Walpth (a.k.a. AlexWalp), licensed under **GNU General Public License v3**.

- Upstream: https://github.com/Walpth/Charge-Grinder
- Mouse-movement model trainer: https://github.com/Walpth/ideal-mouse-movements
- License: GPL v3 (see LICENSE in repo root)

WorkerBee as a whole is distributed under GPL v3 as a consequence of
incorporating these files.

## Imported modules

- `automation/{battle,event,grab,lux,move,pack,shop,teams}.py` from `source/`
- `automation/utils/{utils,params,paths,profiles,os_windows_backend,os_x11_backend,log_config}.py` from `source/utils/`
- `automation/utils/movement/{builder,generator,inertia,pointer_gain}.py` and `model.npz` from `source/utils/movement/`
- `automation/bot.py` from upstream `Bot.py`
- `automation/stats.py` from upstream `stats.py`

Local modifications:
- Charge-Grinder absolute imports (`from source.X import Y`) rewritten as
  package-relative (`from .X import Y`) so the tree fits under WorkerBee's
  `src/wbcore/`.
- GUI couplings (`p.APP`, direct `QMetaObject.invokeMethod` calls) are
  replaced with a callback interface so the WorkerBee v2 GUI can drive
  the bot without Charge-Grinder's own widgets.
