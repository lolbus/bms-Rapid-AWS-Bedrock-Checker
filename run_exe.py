#!/usr/bin/env python
"""bedrock_checker_wins -- PyInstaller entry point (from the portable-exe-packing
skill's run_exe template, placeholders substituted).

Why this file exists (skill section 3): a frozen Windows app cannot get these
wrong --
* UTF-8 stdout/stderr before anything prints (cp1252 kills on one box-drawing char)
* sys.frozen -> APP_DIR = dirname(sys.executable); never use __file__ for runtime data
* runtime data (config.json, logs/, exports/) lives BESIDE the exe
* multiprocessing.freeze_support() first in __main__
* crash-hold input() with DXCPACK_NO_HOLD escape (isatty() lies under Start-Process)
* windowed build: sys.stdout is None; reopen fd 1/2 when the parent passed pipes

APP_IMPORT is imported BY STRING below, so PyInstaller's graph never sees it.
It and everything it reaches are listed in the spec's hiddenimports.
"""

import io
import os
import sys

APP_NAME = "bedrock_checker_wins"
APP_VERSION = "0.1.0"
APP_IMPORT = "bedrock_checker.app"
APP_CALLABLE = "main"
DATA_DIRS = ["logs", "exports"]
GUI = True
SELFTEST_FLAG = "--selftest"


def _force_utf8_streams():
    """Make stdout/stderr UTF-8 tolerant -- and present -- before any print()."""
    writable = False
    for name, fd in (("stdout", 1), ("stderr", 2)):
        stream = getattr(sys, name, None)
        if stream is not None:
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                try:
                    setattr(sys, name, io.TextIOWrapper(
                        stream.buffer, encoding="utf-8", errors="replace",
                        line_buffering=True))
                except Exception:
                    pass
            writable = True
            continue
        try:
            # closefd=False: fd 1/2 belong to the process, not to this wrapper.
            raw = open(fd, "wb", buffering=0, closefd=False)
            setattr(sys, name, io.TextIOWrapper(
                raw, encoding="utf-8", errors="replace", line_buffering=True))
            writable = True
        except OSError:
            # No console and no pipe: keep print() harmless.
            setattr(sys, name, io.StringIO())
    return writable


def app_dir():
    """Directory that owns runtime data: the exe's folder when frozen."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _prepare_runtime(base):
    os.chdir(base)
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ["APP_DIR"] = base
    for rel in DATA_DIRS:
        os.makedirs(os.path.join(base, rel), exist_ok=True)


def _load_entry():
    # Imported by string: invisible to PyInstaller's static graph. APP_IMPORT
    # must appear in the spec's hiddenimports.
    import importlib

    module = importlib.import_module(APP_IMPORT)
    func = getattr(module, APP_CALLABLE, None)
    if not callable(func):
        raise RuntimeError(
            "%s.%s is missing or not callable" % (APP_IMPORT, APP_CALLABLE))
    return func


def _selftest(base):
    """Import-and-teardown smoke test for verify_release.py on a clean machine."""
    print("selftest: app_dir=%s" % base)
    _load_entry()
    print("selftest: imports ok")
    if GUI:
        import tkinter

        root = tkinter.Tk()
        root.withdraw()
        root.update_idletasks()
        root.destroy()
        print("tk: ok")
    for rel in DATA_DIRS:
        target = os.path.join(base, rel)
        if not os.path.isdir(target):
            raise RuntimeError("data dir not created: %s" % target)
    print("selftest: ok")
    return 0


def _hold_console():
    if os.environ.get("DXCPACK_NO_HOLD"):
        return
    try:
        if not sys.stdin or not sys.stdin.isatty():
            return
        print("Press Enter to exit...")
        input()
    except Exception:
        pass


def main(argv=None):
    _force_utf8_streams()
    argv = list(sys.argv[1:] if argv is None else argv)
    base = app_dir()
    print("%s v%s" % (APP_NAME, APP_VERSION))
    try:
        _prepare_runtime(base)
        if SELFTEST_FLAG and SELFTEST_FLAG in argv:
            return _selftest(base)
        return _load_entry()() or 0
    except KeyboardInterrupt:
        print("\n%s stopped by user (Ctrl+C)" % APP_NAME)
        return 0
    except SystemExit as exc:
        return int(exc.code or 0)
    except Exception as exc:
        import traceback

        print()
        print("=" * 60)
        print("ERROR: %s failed to start" % APP_NAME)
        print("=" * 60)
        print("%s: %s" % (type(exc).__name__, exc))
        print()
        traceback.print_exc()
        print()
        _hold_console()
        return 1


if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()
    sys.exit(main())
