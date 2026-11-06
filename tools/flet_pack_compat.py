"""Run ``flet pack`` with a fix for a flet-cli bug on Windows (experiments only).

    python tools/flet_pack_compat.py app.py --onedir ...   (same arguments as ``flet pack``)

flet-cli 1.0.5 and 1.1.0 restore the executable overlay after updating its
version resource with ``open(exe_path, "ab", encoding="utf-8")``. Binary mode
takes no encoding, so ``flet pack`` stops with ``ValueError: binary mode
doesn't take an encoding argument`` whenever the overlay has to be restored.
This wrapper gives that one module an ``open`` that drops the encoding in
binary mode and then runs the unchanged flet CLI. It is used only by the
packaging experiment that compares ``flet pack`` with ``flet build``; the
released build uses ``flet build`` and does not need it.
"""

from __future__ import annotations

import builtins
import sys


def _binary_safe_open(file, mode="r", *args, **kwargs):
    if "b" in mode:
        kwargs.pop("encoding", None)
    return builtins.open(file, mode, *args, **kwargs)


def main(argv: list[str] | None = None) -> int:
    from flet_cli.__pyinstaller import win_utils  # Windows-only module of flet-cli
    from flet_cli.cli import main as flet_main

    win_utils.open = _binary_safe_open
    sys.argv = ["flet", "pack", *(sys.argv[1:] if argv is None else argv)]
    flet_main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
