"""JSON API tests: the real server on a free port with the Mock backend."""
import http.client
import json
import threading
import time

import pytest

import gme_web
from conftest import make_coefs, write_cab
from gme import device as gd
from gme import model as gm
from gme.store import Store


class Client(object):
    def __init__(self, port):
        self.port = port

    def call(self, method, path, body=None, raw=None, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            data = raw if raw is not None else (json.dumps(body) if body is not None else None)
            h = dict(headers or {})
            if data is not None:
                h["Content-Type"] = "application/json"
            c.request(method, path, body=data, headers=h)
            r = c.getresponse()
            payload = r.read()
            ctype = r.getheader("Content-Type") or ""
            obj = json.loads(payload.decode("utf-8")) if "json" in ctype else payload
            return r.status, obj
        finally:
            c.close()

    def get(self, p):
        return self.call("GET", p)

    def post(self, p, b=None):
        return self.call("POST", p, b if b is not None else {})

    def delete(self, p):
        return self.call("DELETE", p)


def start(version, tmp_path, cabdir, **mockkw):
    dev = gd.Mock(version=version, **mockkw)
    model = gm.Model(dev, store=Store(str(tmp_path / "data")), cab_dir=str(cabdir))
    srv = gme_web.create_server(model, "127.0.0.1", 0)
    t = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.02})
    t.daemon = True
    t.start()
    return srv, dev, model, Client(srv.server_address[1])


@pytest.fixture
def api(tmp_path, cabdir):
    srv, dev, model, cl = start(0x0205, tmp_path, cabdir)
    cl.dev, cl.model = dev, model
    yield cl
    srv.stop()


@pytest.fixture
def old_api(tmp_path, cabdir):
    srv, dev, model, cl = start(0x0204, tmp_path, cabdir)
    cl.dev, cl.model = dev, model
    yield cl
    srv.stop()


def err(resp, status):
    s, j = resp
    assert s == status, (s, j)
    assert isinstance(j, dict) and isinstance(j["error"], str) and j["error"]


# ---- info / state ---------------------------------------------------------------------------

def test_info(api):
    s, j = api.get("/api/info")
    assert s == 200
    assert j["fpga_version"] == 0x0205 and j["fpga_version_hex"] == "0x0205" and j["mock"] is True
    assert j["capabilities"] == {"cab": True, "chain_editable": False}
    assert len(j["params"]) == 29 and all(p["available"] for p in j["params"])
    p = [x for x in j["params"] if x["id"] == "echo_time"][0]
    assert p["unit"] == "ms" and p["reg"] == 5 and p["min_version"] == 0x0201
    assert [e["id"] for e in j["effects"]] == ["od", "dist", "cab", "mod", "trem", "echo", "reverb"]
    assert any(r["name"] == "cab_data_hi" for r in j["registers"])


def test_info_old_image(old_api):
    s, j = old_api.get("/api/info")
    assert j["capabilities"]["cab"] is False
    assert [x["id"] for x in j["params"] if not x["available"]] == ["cab_on", "cab_bank", "cab_shift0", "cab_shift1"]


def test_state(api):
    s, j = api.get("/api/state")
    assert s == 200
    assert set(j) == {"values", "raw", "status", "chain", "cab"}
    assert len(j["values"]) == 29 and j["values"]["echo_on"] is False
    assert j["status"]["pll_locked"] is True and j["status"]["codec_init_done"] is True
    assert j["chain"]["editable"] is False and j["cab"]["available"] is True


# ---- params -----------------------------------------------------------------------------------

def test_set_params(api):
    s, j = api.post("/api/params", {"echo_time": "320ms", "trem_rate": 6.5, "echo_on": True,
                                    "dist_type": "Heavy", "reverb_type": 2, "mod_fb": -50, "od_drive": 3000})
    assert s == 200 and j["ok"] is True
    assert j["values"]["echo_time"] == 320 and j["values"]["dist_type"] == "Heavy"
    d = api.dev
    assert d.regs[5] == 15360 and d.regs[0x16] == 650 and d.regs[0] == 4 and d.regs[9] == 2
    assert d.regs[14] == 2 and d.regs[1] == 3000 and d.regs[0x19] == (-16383 & 0xFFFF)
    s, j = api.get("/api/state")
    assert j["values"]["echo_time"] == 320 and j["raw"]["echo_time"] == 15360
    assert j["values"]["echo_on"] is True and abs(j["values"]["mod_fb"] + 50) < 0.01
    api.post("/api/params", {"echo_on": False, "od_on": True})
    assert d.regs[0] == 1


def test_set_params_errors(api):
    n = len(api.dev.log)
    err(api.post("/api/params", {"nope": 1}), 400)
    err(api.post("/api/params", {"echo_time": "5Hz"}), 400)
    err(api.post("/api/params", {"echo_time": 9999}), 400)
    err(api.post("/api/params", {"od_gain": -1}), 400)
    err(api.post("/api/params", {"dist_type": "zzz"}), 400)
    err(api.post("/api/params", {"echo_on": "maybe"}), 400)
    err(api.post("/api/params", {"echo_time": None}), 400)
    err(api.post("/api/params", {"echo_time": [1]}), 400)
    err(api.post("/api/params", {"od_gain": True}), 400)
    err(api.post("/api/params", {}), 400)
    err(api.call("POST", "/api/params", raw="[1,2]"), 400)
    err(api.call("POST", "/api/params", raw="{not json"), 400)
    err(api.post("/api/params", {"od_drive": 1000, "echo_time": 9999}), 400)    # nothing applied
    assert len(api.dev.log) == n
    err(api.get("/api/params"), 405)


def test_param_not_in_image(old_api):
    err(old_api.post("/api/params", {"cab_on": True}), 400)


# ---- levels ---------------------------------------------------------------------------------------

def test_levels(api):
    s, j = api.get("/api/levels")
    assert s == 200 and set(j) == {"in", "out", "in_db", "out_db", "gain_reduction"}
    assert 0 <= j["in"] <= 32767


def read_events(port, n, query=""):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    c.request("GET", "/api/levels/stream" + query)
    r = c.getresponse()
    assert r.status == 200 and r.getheader("Content-Type") == "text/event-stream"
    ev, t = [], []
    while len(ev) < n:
        line = r.fp.readline().decode("utf-8")
        if not line:
            break
        if line.startswith("data: "):
            ev.append(json.loads(line[6:]))
            t.append(time.time())
    c.close()
    return ev, t


def test_sse_stream(api):
    ev, t = read_events(api.port, 8)
    assert len(ev) == 8 and all("in" in e and "out" in e and "t" in e for e in ev)
    rate = (len(ev) - 1) / (t[-1] - t[0])
    assert 8 <= rate <= 25, rate                                  # ~15 Hz
    assert len(set(e["in"] for e in ev)) > 1                       # levels move
    ev, _ = read_events(api.port, 100, "?max=3&hz=30")
    assert len(ev) == 3
    # abandoning a stream does not stop the server
    ev, _ = read_events(api.port, 2)
    assert api.get("/api/info")[0] == 200
    err(api.call("POST", "/api/levels/stream"), 405)
    err(api.get("/api/levels/stream?hz=x"), 400)


# ---- presets ------------------------------------------------------------------------------------------

def test_presets_lifecycle(api):
    s, j = api.get("/api/presets")
    names = [p["name"] for p in j["presets"]]
    assert s == 200 and names[:3] == ["clean", "crunch", "lead"] and all(p["factory"] for p in j["presets"])
    s, j = api.get("/api/presets/flanger")
    assert j["factory"] is True and j["params"]["mod_fb"] == 26000 and j["fx"] == ["mod"]
    s, j = api.post("/api/presets/flanger")
    assert s == 200 and j["loaded"] == "flanger" and j["warnings"] == []
    assert api.dev.regs[0] == 16 and api.dev.regs[0x19] == 26000 and j["values"]["mod_shape"] == "Triangle"
    api.post("/api/params", {"echo_time": "250ms", "echo_on": True})
    s, j = api.post("/api/presets", {"name": "mine"})
    assert s == 201 and j["saved"] == "mine"
    err(api.post("/api/presets", {"name": "mine"}), 409)
    assert api.post("/api/presets", {"name": "mine", "overwrite": True})[0] == 201
    err(api.post("/api/presets", {"name": "clean", "overwrite": True}), 403)
    err(api.post("/api/presets", {"name": "../evil"}), 400)
    err(api.post("/api/presets", {}), 400)
    err(api.post("/api/presets", {"name": "x", "overwrite": "yes"}), 400)
    api.post("/api/presets/clean")
    assert api.dev.regs[0] == 0
    s, j = api.get("/api/presets/mine")
    assert s == 200 and j["factory"] is False and j["params"]["echo_time"] == 12000 and j["fx"] == ["mod", "echo"]
    api.post("/api/presets/mine")
    assert api.dev.regs[5] == 12000 and api.dev.regs[0] == 0x14
    assert ("mine", False) in [(p["name"], p["factory"]) for p in api.get("/api/presets")[1]["presets"]]
    err(api.get("/api/presets/nope"), 404)
    err(api.post("/api/presets/nope"), 404)
    err(api.delete("/api/presets/nope"), 404)
    err(api.delete("/api/presets/crunch"), 403)
    s, j = api.delete("/api/presets/mine")
    assert s == 200 and j["deleted"] == "mine"
    err(api.get("/api/presets/mine"), 404)
    err(api.call("PUT", "/api/presets/mine", {}), 405)


def test_preset_name_with_space_is_url_decoded(api):
    api.post("/api/presets", {"name": "my lead"})
    assert api.get("/api/presets/my%20lead")[0] == 200
    assert api.delete("/api/presets/my%20lead")[0] == 200


# ---- cabinet --------------------------------------------------------------------------------------------

def test_cab(api, cabdir):
    s, j = api.get("/api/cab")
    assert j["available"] and [c["name"] for c in j["slots"]] == ["Default", "Marshall 4x12"]
    assert j["active_bank"] == 0 and j["slot"] is None
    s, j = api.post("/api/cab", {"slot": 1})
    assert s == 200 and j["loaded"]["name"] == "Marshall 4x12" and j["cab"]["active_bank"] == 1
    assert api.dev.cab_coef(1, 0) == -131072 and api.dev.cab_coef(1, 1) == 131071
    assert j["cab"]["slot"] == 1
    s, j = api.post("/api/cab", {"slot": 0, "enabled": True})
    assert j["cab"]["enabled"] is True and j["cab"]["active_bank"] == 0 and api.dev.regs[0] == 0x40
    api.post("/api/cab", {"enabled": False})
    assert api.dev.regs[0] == 0
    err(api.post("/api/cab", {}), 400)
    err(api.post("/api/cab", {"slot": "1"}), 400)
    err(api.post("/api/cab", {"slot": -1}), 400)
    err(api.post("/api/cab", {"slot": True}), 400)
    err(api.post("/api/cab", {"enabled": "yes"}), 400)
    err(api.post("/api/cab", {"slot": 7}), 409)
    write_cab(cabdir, 5, "broken", 1, [1, 2])
    err(api.post("/api/cab", {"slot": 5}), 409)


def test_cab_old_image(old_api):
    s, j = old_api.get("/api/cab")
    assert s == 200 and j["available"] is False
    err(old_api.post("/api/cab", {"slot": 0}), 409)
    err(old_api.post("/api/cab", {"enabled": True}), 409)


# ---- codec ------------------------------------------------------------------------------------------------

def test_codec(api):
    s, j = api.post("/api/codec", {"reg": 2, "value": 0x79})
    assert s == 200 and j["ok"]
    assert api.post("/api/codec", {"name": "left_headphone_out", "value": 0x7F})[0] == 200
    assert api.dev.codec_log == [(2, 0x79), (2, 0x7F)]
    assert api.get("/api/codec")[1]["registers"][0]["name"] == "left_line_in"
    err(api.post("/api/codec", {"reg": 2}), 400)
    err(api.post("/api/codec", {"value": 2}), 400)
    err(api.post("/api/codec", {"reg": 2, "value": 600}), 400)
    err(api.post("/api/codec", {"reg": 200, "value": 1}), 400)
    err(api.post("/api/codec", {"reg": "bogus", "value": 1}), 400)
    err(api.post("/api/codec", {"reg": 2, "value": "1"}), 400)


def test_codec_nak_is_502(tmp_path, cabdir):
    srv, dev, model, cl = start(0x0205, tmp_path, cabdir, nak=True)
    try:
        err(cl.post("/api/codec", {"reg": 2, "value": 1}), 502)
    finally:
        srv.stop()


# ---- chain ---------------------------------------------------------------------------------------------------

def test_chain_fixed(api):
    s, j = api.get("/api/chain")
    assert s == 200 and j["editable"] is False
    assert j["order"] == ["od", "dist", "cab", "mod", "trem", "echo", "reverb"]
    assert j["effects"][0] == {"id": "od", "name": "Overdrive", "enable": "od_on", "on": False}
    err(api.post("/api/chain", {"order": j["order"]}), 409)
    err(api.post("/api/chain", {}), 400)
    err(api.post("/api/chain", {"order": "od"}), 400)


def test_chain_editable(api, monkeypatch):
    monkeypatch.setattr(gm, "ROUTING_VERSION", 0x0205)
    assert api.get("/api/chain")[1]["editable"] is True
    new = ["echo", "od", "dist", "cab", "mod", "trem", "reverb"]
    s, j = api.post("/api/chain", {"order": new})
    assert s == 200 and j["order"] == new
    assert api.get("/api/chain")[1]["order"] == new
    assert api.get("/api/state")[1]["chain"]["order"] == new
    err(api.post("/api/chain", {"order": new[:-1]}), 400)


# ---- raw -------------------------------------------------------------------------------------------------------

def test_raw(api):
    assert api.get("/api/raw/0x10")[1] == {"reg": 16, "value": 0x0205, "hex": "0x0205"}
    assert api.get("/api/raw/16")[1]["value"] == 0x0205
    assert api.get("/api/raw/version")[1]["value"] == 0x0205
    s, j = api.post("/api/raw/0x03", {"value": 0x0005})
    assert s == 200 and j["value"] == 5 and api.dev.regs[3] == 5
    api.post("/api/raw/effects_enable", {"value": 12})
    assert api.dev.regs[0] == 12
    assert api.post("/api/raw/0x10", {"value": 1})[1]["value"] == 0x0205       # read-only: ignored
    assert api.get("/api/raw/0x30")[1]["value"] == 0
    s, j = api.get("/api/raw")
    assert s == 200 and any(r["name"] == "version" and r["value"] == 0x0205 for r in j["registers"])
    err(api.get("/api/raw/64"), 400)
    err(api.get("/api/raw/zzz"), 400)
    err(api.post("/api/raw/3", {"value": 70000}), 400)
    err(api.post("/api/raw/3", {"value": "5"}), 400)
    err(api.post("/api/raw/3", {}), 400)
    err(api.call("DELETE", "/api/raw/3"), 405)
    err(api.get("/api/raw/1/2"), 404)


# ---- misc ---------------------------------------------------------------------------------------------------------

def test_unknown_and_static(api):
    err(api.get("/api/nothing"), 404)
    err(api.get("/api"), 404)
    err(api.call("DELETE", "/api/info"), 405)
    s, body = api.call("GET", "/")
    assert s == 200 and b"<title>" in body
    assert api.call("GET", "/index.html")[0] == 200
    assert api.call("GET", "/nothing.js")[0] == 404
    assert api.call("GET", "/../gme_web.py")[0] == 404
    assert api.call("GET", "/%2e%2e/gme_web.py")[0] == 404
    assert api.call("GET", "/..%2fgme_web.py")[0] == 404
    assert api.call("POST", "/index.html", {})[0] == 405


def test_wrong_image_refused_by_server():
    with pytest.raises(SystemExit) as e:
        gme_web.main(["--mock", "--mock-version", "0x0100", "--port", "0"])
    assert "0x02xx" in str(e.value)


# ---- concurrency ------------------------------------------------------------------------------------------------------

def test_concurrent_posts_are_serialised(tmp_path, cabdir):
    srv, dev, model, cl = start(0x0205, tmp_path, cabdir, write_delay=0.0003)
    try:
        A = {"od_drive": 1000, "od_gain": 1, "echo_time": "100ms", "echo_on": True, "dist_mix": "10%"}
        B = {"od_drive": 2000, "od_gain": 2, "echo_time": "200ms", "echo_on": False, "dist_mix": "20%"}
        snapshots, errors = [], []

        def poster(i):
            try:
                for k in range(6):
                    s, j = cl.post("/api/params", A if (i + k) % 2 == 0 else B)
                    if s != 200:
                        errors.append((s, j))
            except Exception as e:                                    # pragma: no cover
                errors.append(e)

        def reader():
            try:
                for k in range(6):
                    s, j = cl.get("/api/state")
                    v = j["raw"]
                    snapshots.append((v["od_drive"], v["od_gain"], v["echo_time"], v["echo_on"], v["dist_mix"]))
            except Exception as e:                                    # pragma: no cover
                errors.append(e)

        ts = [threading.Thread(target=poster, args=(i,)) for i in range(8)] + \
             [threading.Thread(target=reader) for _ in range(3)]
        for t in ts:
            t.start()
        for t in ts:
            t.join(60)
        assert not errors, errors
        assert dev.max_concurrent == 1                                  # one register port
        okA = (1000, 1, 4800, 1, 26)
        okB = (2000, 2, 9600, 0, 51)
        # a POST changes several registers; readers must never see a mixture
        assert snapshots and all(s in (okA, okB, (0, 0, 0, 0, 0)) for s in snapshots), snapshots
        s, j = cl.get("/api/state")
        v = j["raw"]
        assert (v["od_drive"], v["od_gain"], v["echo_time"], v["echo_on"], v["dist_mix"]) in (okA, okB)
    finally:
        srv.stop()


def test_concurrent_cab_load_and_params(tmp_path, cabdir):
    srv, dev, model, cl = start(0x0205, tmp_path, cabdir, write_delay=0.00005)
    try:
        res = []
        t1 = threading.Thread(target=lambda: res.append(cl.post("/api/cab", {"slot": 0})))
        t2 = threading.Thread(target=lambda: [res.append(cl.post("/api/params", {"od_gain": i % 5 + 1}))
                                              for i in range(10)])
        t1.start()
        t2.start()
        t1.join(60)
        t2.join(60)
        assert all(r[0] == 200 for r in res), res
        assert dev.max_concurrent == 1 and dev.cab_ignored_writes == 0
        assert dev.cab_coef(1, 1) == 131071 and dev.regs[0x1B] & 1 == 1
    finally:
        srv.stop()
