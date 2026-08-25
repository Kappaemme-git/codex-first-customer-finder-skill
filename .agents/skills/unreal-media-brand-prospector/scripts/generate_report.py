#!/usr/bin/env python3
"""Delegate UMG report rendering to the canonical shared Phase 1 core."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path


def renderer() -> Path:
    here = Path(__file__).resolve()
    candidates = [
        here.parents[4] / "shared/prospecting-core/scripts/render_report.py",
        here.parents[2] / "unreal-prospecting-core/scripts/render_report.py",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise SystemExit("Shared prospecting core is unavailable. Install the Unreal skill with scripts/install-unreal.js.")


if __name__ == "__main__":
    target = renderer()
    sys.path.insert(0, str(target.parent))
    runpy.run_path(str(target), run_name="__main__")
