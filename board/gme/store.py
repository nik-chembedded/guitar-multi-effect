"""User presets and settings as JSON files in a directory.

    <root>/presets/<name>.json     one user preset
    <root>/settings.json           misc settings (chain order, loaded cabinet slot, ...)

Python 2.7 and 3 compatible, standard library only.
"""
from __future__ import print_function, division

import json
import os
import re
import threading

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.\-]{0,39}$")


class StoreError(ValueError):
    pass


def _replace(src, dst):
    rep = getattr(os, "replace", None)
    if rep is not None:
        rep(src, dst)
        return
    try:                                  # Python 2 on Windows cannot rename over a file
        os.rename(src, dst)
    except OSError:
        os.remove(dst)
        os.rename(src, dst)


def _write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=1, sort_keys=True)
        f.write("\n")
    _replace(tmp, path)


class Store(object):
    def __init__(self, root):
        self.root = root
        self.preset_dir = os.path.join(root, "presets")
        self.settings_path = os.path.join(root, "settings.json")
        self.lock = threading.Lock()

    @staticmethod
    def valid_name(name):
        return bool(NAME_RE.match(name or ""))

    def _path(self, name):
        if not NAME_RE.match(name or ""):
            raise StoreError("invalid preset name (letters, digits, space, _ . -; max 40 characters)")
        return os.path.join(self.preset_dir, name + ".json")

    def list_presets(self):
        if not os.path.isdir(self.preset_dir):
            return []
        names = []
        for fn in os.listdir(self.preset_dir):
            if fn.endswith(".json") and NAME_RE.match(fn[:-5]):
                names.append(fn[:-5])
        return sorted(names, key=lambda s: s.lower())

    def exists(self, name):
        return os.path.isfile(self._path(name))

    def load_preset(self, name):
        path = self._path(name)
        if not os.path.isfile(path):
            raise KeyError(name)
        with open(path) as f:
            return json.load(f)

    def save_preset(self, name, preset):
        path = self._path(name)
        with self.lock:
            if not os.path.isdir(self.preset_dir):
                os.makedirs(self.preset_dir)
            _write_json(path, preset)

    def delete_preset(self, name):
        path = self._path(name)
        with self.lock:
            if not os.path.isfile(path):
                raise KeyError(name)
            os.remove(path)

    def settings(self):
        try:
            with open(self.settings_path) as f:
                return json.load(f)
        except (IOError, OSError, ValueError):
            return {}

    def update_settings(self, **kw):
        with self.lock:
            cur = self.settings()
            cur.update(kw)
            if not os.path.isdir(self.root):
                os.makedirs(self.root)
            _write_json(self.settings_path, cur)
            return cur
