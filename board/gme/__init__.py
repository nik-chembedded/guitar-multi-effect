"""gme - control library for the guitar multi-effect FPGA image (Python 2.7 and 3)."""
from __future__ import print_function, division

from .device import DevMem, Mock, DeviceError, WrongImage
from .model import (Model, Table, Param, ParamError, CabinetError, NotEditable, FactoryPreset,
                    PresetExists, load_table, open_device)
from .store import Store, StoreError

__version__ = "0.1"
