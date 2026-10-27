"""The page: files are served, reference only local files, and the parameter table has every
field the page's JavaScript reads (the page is generated from it).  No browser here: the page
was run in a real browser separately (see the report)."""
import os
import re
from html.parser import HTMLParser

import pytest

from conftest import BOARD
from test_api import api, start        # noqa: F401  (fixtures)

WWW = os.path.join(BOARD, "www")


class Refs(HTMLParser):
    def __init__(self):
        HTMLParser.__init__(self)
        self.refs = []
        self.ids = set()

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a:
            self.ids.add(a["id"])
        for k in ("src", "href"):
            if k in a and tag in ("script", "link", "img", "a", "source", "iframe"):
                self.refs.append((tag, a[k]))


def test_page_files_served_and_local(api):
    s, body = api.call("GET", "/")
    assert s == 200
    p = Refs()
    p.feed(body.decode("utf-8"))
    files = [r for t, r in p.refs if t in ("script", "link")]
    assert {"app.js", "icons.js", "app.css"} <= set(files)
    for tag, ref in p.refs:
        assert not re.match(r"^(\w+:)?//|^\w+:", ref), "external reference %s" % ref
        assert not ref.startswith("/") or ref.startswith("/api/"), ref
    for f in files:
        s, data = api.call("GET", "/" + f)
        assert s == 200 and len(data) > 100, f
        assert data == open(os.path.join(WWW, f), "rb").read()


@pytest.mark.parametrize("name", ["index.html", "app.js", "util.js", "controls.js", "icons.js", "app.css"])
def test_no_external_resources(name):
    text = open(os.path.join(WWW, name), encoding="utf-8").read()
    assert not re.search(r"https?://", text), name
    assert not re.search(r"@import|import\(|\beval\(|document\.write", text), name
    if name.endswith(".js"):
        assert "XMLHttpRequest" not in text


def test_js_files_referenced_exist_and_balanced():
    for name in ("util.js", "controls.js", "icons.js", "app.js"):
        t = open(os.path.join(WWW, name), encoding="utf-8").read()
        # cheap structural check without a JS engine: brackets balance outside strings/comments
        t = re.sub(r"/\*.*?\*/", "", t, flags=re.S)
        t = re.sub(r"//[^\n]*", "", t)
        t = re.sub(r'"(\\.|[^"\\\n])*"|\'(\\.|[^\'\\\n])*\'', '""', t)
        t = re.sub(r"/(\\.|\[[^\]]*\]|[^/\\\n])+/[gimsuy]*(?=[.,;)\s])", "0", t)
        for a, b in ("()", "[]", "{}"):
            assert t.count(a) == t.count(b), (name, a)


def test_ids_used_by_js_exist_in_html(api):
    html = open(os.path.join(WWW, "index.html"), encoding="utf-8").read()
    p = Refs()
    p.feed(html)
    js = open(os.path.join(WWW, "app.js"), encoding="utf-8").read()
    for m in re.finditer(r'getElementById\("([\w-]+)"\)', js):
        i = m.group(1)
        # ids created by the script itself
        if i in ("cabbody", "preset-sel", "preset-name", "raw-reg", "raw-val", "gr-bar", "gr-text", "preset-dirty"):
            continue
        assert i in p.ids, i
    for t in ("board", "settings", "expert"):
        assert "tab-" + t in p.ids


ICONS = re.findall(r"^    (\w+): '", open(os.path.join(WWW, "icons.js"), encoding="utf-8").read(), re.M)
KINDS = re.findall(r"\.k-(\w+) \{", open(os.path.join(WWW, "app.css"), encoding="utf-8").read())


PARAM_FIELDS = ["id", "name", "group", "reg", "lsb", "width", "type", "min", "max", "default", "unit",
                "mul", "div", "decimals", "help", "min_version", "available"]


def test_info_has_what_the_page_needs(api):
    s, info = api.get("/api/info")
    effects = dict((e["id"], e) for e in info["effects"])
    ids = [p["id"] for p in info["params"]]
    assert len(ids) == len(set(ids))
    for p in info["params"]:
        for f in PARAM_FIELDS:
            assert f in p, (p["id"], f)
        assert p["type"] in ("int", "signed", "bool", "enum")
        assert p["help"].strip() and p["name"].strip()
        assert p["div"] > 0 and p["mul"] > 0 and isinstance(p["decimals"], int)
        if p["type"] == "enum":
            assert p["enum"] and all("value" in e and "label" in e for e in p["enum"])
            assert any(not e.get("alias") for e in p["enum"])
            assert len(set(e["label"] for e in p["enum"])) == len(p["enum"])
        if "gui_min" in p or "gui_max" in p:
            assert p["min"] <= p["gui_min"] < p["gui_max"] <= p["max"]
        assert p["group"] in effects or p["group"] == "system", p["id"]
    for e in info["effects"]:
        for f in ("id", "name", "short", "enable", "min_version"):
            assert f in e
        assert e["short"].strip() and len(e["short"]) <= 5      # the tile in the signal chain strip
        assert e["icon"] in ICONS, e["id"]                       # drawn in icons.js
        assert e["kind"] in KINDS, e["id"]                       # colour class .k-<kind> in app.css
        en = [p for p in info["params"] if p["id"] == e["enable"]][0]
        assert en["type"] == "bool" and en["group"] == e["id"]
    s, ch = api.get("/api/chain")
    assert set(ch["order"]) <= set(effects)
    assert [x["id"] for x in ch["effects"]] == ch["order"]
    for x in ch["effects"]:
        assert set(x) == {"id", "name", "enable", "on", "member"}
    s, st = api.get("/api/state")
    avail = [p["id"] for p in info["params"] if p["available"]]
    assert sorted(st["values"]) == sorted(avail) == sorted(st["raw"])
    for k in ("version", "codec_init_done", "codec_nak", "pll_locked", "mute"):
        assert k in st["status"]
    for k in ("available", "slot", "slots", "active_bank", "enabled"):
        assert k in st["cab"]
    s, lv = api.get("/api/levels")
    for k in ("in", "out", "in_db", "out_db"):
        assert k in lv
    s, raw = api.get("/api/raw")
    assert all(set(r) >= {"reg", "name", "rw", "value"} for r in raw["registers"])


def test_every_param_belongs_to_a_card_or_settings(api):
    """Every available parameter is shown: in the card of its effect or in Settings (group system)."""
    s, info = api.get("/api/info")
    s, ch = api.get("/api/chain")
    cards = set(e["id"] for e in ch["effects"])
    for p in info["params"]:
        if p["available"]:
            assert p["group"] in cards or p["group"] == "system", p["id"]


def test_controls_are_labelled():
    js = open(os.path.join(WWW, "controls.js"), encoding="utf-8").read()
    assert '"for": "c-" + p.id' in js and js.count('"aria-label": p.name') >= 3 and "aria-valuetext" in js
    app = open(os.path.join(WWW, "app.js"), encoding="utf-8").read()
    assert "fpga_version.toString(16)" not in app            # versions are printed as 4 hex digits
    css = open(os.path.join(WWW, "app.css"), encoding="utf-8").read()
    sizes = [int(x) for x in re.findall(r"font-size:\s*(\d+)px", css)]
    assert min(sizes) >= 11
    assert re.search(r"\.ctl-name \{[^}]*font-size: 1[3-9]px", css)
