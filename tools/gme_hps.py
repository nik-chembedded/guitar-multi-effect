#!/usr/bin/env python
"""Compatibility wrapper: the control tool now lives in board/gme_hps.py (library in board/gme/).

    python tools/gme_hps.py status        is the same as        python board/gme_hps.py status

On the board, copy the whole board/ directory and run board/gme_hps.py directly.
Works with Python 2.7 and 3.
"""
from __future__ import print_function

import os
import runpy
import sys

target = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "board", "gme_hps.py")
if not os.path.isfile(target):
    sys.exit("board/gme_hps.py not found next to tools/ (expected %s)" % os.path.normpath(target))
sys.argv[0] = os.path.normpath(target)
runpy.run_path(os.path.normpath(target), run_name="__main__")
