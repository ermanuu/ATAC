#!/usr/bin/env python3
"""Run the asynchronous polling load generator from the repository checkout."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.load_test import main


if __name__ == '__main__':
    raise SystemExit(main())
