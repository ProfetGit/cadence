import argparse
import os
import sys

from . import APP_NAME, BUS_NAME, BUS_PATH, __version__

CTL_COMMANDS = (
    "play pause toggle stop next prev like dislike shuffle repeat mute volume seek show hide window mini maximize "
    "lyrics settings reload search sleep open quit status"
).split()


def _call(method, args=None):
    from . import gdbus
    return gdbus.call_sync(BUS_NAME, BUS_PATH, "org.cadence.Cadence", method, args)


def _running(activate=True) -> bool:
    try:
        _call("Activate" if activate else "Status")
        return True
    except Exception:  # noqa: BLE001
        return False


def _ctl(argv) -> int:
    from .gdbus import Variant

    ap = argparse.ArgumentParser(prog="cadence ctl", description="Control a running Cadence.")
    ap.add_argument("command", choices=CTL_COMMANDS)
    ap.add_argument("arg", nargs="?", default="")
    ap.add_argument("--json", action="store_true", help="status as JSON")
    ap.add_argument("--format", help="status format, e.g. '{artist} - {title}'")
    ns = ap.parse_args(argv)
    try:
        if ns.command == "status":
            raw = _call("Status").unpack()[0]
            import json
            d = json.loads(raw)
            if ns.format:
                print(ns.format.format_map({k: ("" if v is None else v) for k, v in d.items()}))
            elif ns.json:
                print(raw)
            else:
                print("%s: %s — %s" % (d["status"], d["title"], d["artist"]) if d["video_id"] else d["status"])
            return 0
        out = _call("Command", Variant("(ss)", (ns.command, ns.arg))).unpack()[0]
    except Exception as e:  # noqa: BLE001
        print("Cadence isn't running (%s)" % str(e).split(":")[-1].strip(), file=sys.stderr)
        return 1
    if out != "ok":
        print(out)
    return 0 if not out.startswith("error") else 2


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "ctl":
        sys.exit(_ctl(argv[1:]))

    ap = argparse.ArgumentParser(prog="cadence", description="YouTube Music for Linux.")
    ap.add_argument("url", nargs="?", help="a music.youtube.com / youtube.com / youtu.be link to open")
    ap.add_argument("--hidden", action="store_true", help="start in the tray")
    ap.add_argument("--debug", action="store_true", help="verbose log, enables the Eval/Screenshot D-Bus calls")
    ap.add_argument("--version", action="version", version="%s %s" % (APP_NAME, __version__))
    ns, qt_args = ap.parse_known_args(argv)

    if not os.environ.get("CADENCE_ALLOW_MULTI"):
        try:
            if ns.url:
                from .gdbus import Variant
                _call("Open", Variant("(s)", (ns.url,)))
                sys.exit(0)
            if _running(activate=not ns.hidden):
                sys.exit(0)
        except SystemExit:
            raise
        except Exception:  # noqa: BLE001
            pass

    from PyQt6 import QtWebEngineWidgets  # noqa: F401  (must load before QApplication)
    from PyQt6.QtWidgets import QApplication

    os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "")
    app = QApplication([sys.argv[0]] + qt_args)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setDesktopFileName("cadence")
    app.setQuitOnLastWindowClosed(False)

    from .app import CadenceApp

    ctrl = CadenceApp(app, debug=ns.debug, hidden=ns.hidden, open_url=ns.url)  # noqa: F841
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
