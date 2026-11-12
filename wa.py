#!/usr/bin/env python3
"""Entry point: python3 wa.py <command>  (same as ./wa or wa.cmd)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from autopilot.cli import main  # noqa: E402

sys.exit(main())
