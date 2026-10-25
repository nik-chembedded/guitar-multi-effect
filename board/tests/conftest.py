import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
BOARD = os.path.dirname(HERE)
sys.path.insert(0, BOARD)
sys.path.insert(0, HERE)

from gme import device as gd          # noqa: E402
from gme import model as gm           # noqa: E402
from gme.store import Store           # noqa: E402

REPO = os.path.dirname(BOARD)


def make_coefs(seed=1):
    """2048 deterministic signed 18-bit coefficients including both extremes."""
    c = []
    x = seed
    for i in range(2048):
        x = (x * 1103515245 + 12345) & 0x7FFFFFFF
        c.append((x % 262144) - 131072)
    c[0], c[1], c[2047] = -131072, 131071, -1
    return c


def write_cab(dirpath, slot, name, shift, coefs):
    with open(os.path.join(str(dirpath), "cab%02d.coef" % slot), "w") as f:
        f.write("%s\n%d\n" % (name, shift))
        f.write("\n".join(str(c) for c in coefs))
        f.write("\n")


@pytest.fixture
def cabdir(tmp_path):
    d = tmp_path / "cab"
    d.mkdir()
    write_cab(d, 0, "Default", 3, make_coefs(1))
    write_cab(d, 1, "Marshall 4x12", 5, make_coefs(2))
    return d


@pytest.fixture
def mock():
    return gd.Mock(version=0x0205)


@pytest.fixture
def model(mock, tmp_path, cabdir):
    return gm.Model(mock, store=Store(str(tmp_path / "data")), cab_dir=str(cabdir))
