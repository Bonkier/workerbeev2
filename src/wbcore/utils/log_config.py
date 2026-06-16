import logging, sys, os


def _is_onefile_temp_path(path: str) -> bool:
    normalized = os.path.normcase(os.path.abspath(path))
    return "\\appdata\\local\\temp\\onefil" in normalized


def _launched_executable_dir():
    argv0 = os.path.abspath(sys.argv[0]) if sys.argv else ""
    exe = os.path.abspath(sys.executable)

    if argv0 and os.path.isfile(argv0) and not _is_onefile_temp_path(argv0):
        return os.path.dirname(argv0)

    if exe and os.path.isfile(exe) and not _is_onefile_temp_path(exe):
        return os.path.dirname(exe)

    if argv0:
        return os.path.dirname(argv0)

    return os.path.dirname(exe)


def _runtime_base_path():
    appimage_path = os.environ.get("APPIMAGE")
    if appimage_path:
        return os.path.dirname(appimage_path)

    if "__compiled__" in globals():
        return _launched_executable_dir()

    return os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

class _PipeFormatter(logging.Formatter):
    """Pipe-separated format; logs page splits on ' | ' for color coding."""

    def formatTime(self, record, datefmt=None):
        import time
        return time.strftime('%d/%m/%Y %H:%M:%S', time.localtime(record.created))


def setup_logging(enable_logging: bool = True, log_file: str = "game.log", log_level=logging.INFO):
    if not enable_logging:
        logging.disable(logging.CRITICAL)
        return

    base_path = _runtime_base_path()

    log_path = os.path.join(base_path, log_file)
    print(f"Logging enabled. Log file: {log_path}")

    formatter = _PipeFormatter(
        fmt='%(asctime)s | %(name)s | %(levelname)s | %(funcName)s:%(lineno)d | %(message)s',
    )
    handler = logging.FileHandler(str(log_path), encoding='utf-8')
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(log_level)
    # Idempotent on relaunch.
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(handler)

    original_excepthook = sys.excepthook

    def log_uncaught_exceptions(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        logging.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))
        original_excepthook(exc_type, exc_value, exc_traceback)

    sys.excepthook = log_uncaught_exceptions