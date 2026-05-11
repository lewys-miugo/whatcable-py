from __future__ import annotations

import argparse
import os
import sys
import time

from . import __version__, TAGLINE
from .formatters import cable_report, render_json, render_text
from .sysfs import snapshot


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="whatcable-py", description=f"whatcable-py {__version__} -- {TAGLINE}")
    p.add_argument("--json", action="store_true", help="Output as JSON instead of human-readable text")
    p.add_argument("--raw", action="store_true", help="Include raw Linux sysfs properties")
    p.add_argument("--watch", action="store_true", help="Continuously monitor for changes")
    p.add_argument("--report", action="store_true", help="Print cable e-marker report markdown and exit")
    p.add_argument("--version", action="store_true", help="Print version and exit")
    p.add_argument("--no-color", action="store_true", help="Disable ANSI color")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.version:
        print(__version__)
        return 0
    color_enabled = sys.stdout.isatty() and not args.no_color and "NO_COLOR" not in os.environ
    if args.watch:
        return watch(args, color_enabled=color_enabled)
    snap = snapshot()
    if args.report:
        print(cable_report(snap), end="")
    elif args.json:
        print(render_json(snap, show_raw=args.raw))
    else:
        print(render_text(snap, show_raw=args.raw, color_enabled=color_enabled), end="")
    return 0


def watch(args, *, color_enabled: bool) -> int:
    last = None
    try:
        while True:
            snap = snapshot()
            output = render_json(snap, show_raw=args.raw) if args.json else render_text(snap, show_raw=args.raw, color_enabled=color_enabled)
            if output != last:
                last = output
                if args.json:
                    print(output, flush=True)
                else:
                    print("\033[2J\033[H", end="")
                    print(time.strftime("whatcable-py --watch · %Y-%m-%d %H:%M:%S\n"))
                    print(output, end="", flush=True)
            time.sleep(1)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
