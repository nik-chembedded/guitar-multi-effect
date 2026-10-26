#!/usr/bin/env python
"""
gme_web.py - web server and JSON API for the guitar multi-effect v2 (runs on the board).

    python gme_web.py                    (port 8080, needs root for /dev/mem)
    python gme_web.py --port 8081 --mock (no board: in-memory register file)

Serves the page in www/ and the JSON API under /api (see docs/web_ui_design.md):

    GET  /api/info                  version, FPGA VERSION, parameter table, effects
    GET  /api/state                 all parameter values (display units + raw), status, chain, cabinet
    POST /api/params                {id: value, ...}  values in display units (number, "320ms", label, bool)
    GET  /api/levels                input / output level, dynamics gain reduction in dB
    GET  /api/levels/stream         server-sent events, ~15 Hz (?hz=N, ?max=N events)
    GET  /api/presets               factory + user presets
    GET  /api/presets/<name>        one preset
    POST /api/presets               {name, overwrite?}  save the current state as a user preset
    POST /api/presets/<name>        load (apply) a preset
    DELETE /api/presets/<name>      delete a user preset
    GET  /api/cab                   cabinet slots, active bank
    POST /api/cab                   {slot: n} load cabinet n / {enabled: bool}
    GET/POST /api/codec             {reg|name, value}  WM8731 register write
    GET/POST /api/chain             {order: [ids], editable}  409 while the order is fixed
    GET/POST /api/raw[/<reg>]       raw register access {value}

Errors are JSON {"error": text} with a 4xx status (502 when the hardware fails).
All hardware access goes through one lock. The server refuses to start when VERSION
does not read 0x02xx. Python 2.7 and 3, standard library only.
"""
from __future__ import print_function, division

import argparse
import json
import mimetypes
import os
import sys
import threading
import time

try:
    from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
    from SocketServer import ThreadingMixIn
    from urlparse import urlsplit, parse_qs
    from urllib import unquote
except ImportError:                                           # Python 3
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from socketserver import ThreadingMixIn
    from urllib.parse import urlsplit, parse_qs, unquote

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import gme                                                    # noqa: E402
from gme import model as gm                                   # noqa: E402
from gme import device as gd                                  # noqa: E402
from gme.store import Store, StoreError                       # noqa: E402

MAX_BODY = 1 << 20
SPAN_WORDS = gd.NWORDS


class HttpError(Exception):
    def __init__(self, status, message):
        Exception.__init__(self, message)
        self.status = status
        self.message = message


def is_int(x):
    return isinstance(x, int) and not isinstance(x, bool)


def need_dict(body):
    if not isinstance(body, dict):
        raise HttpError(400, "JSON object expected")
    return body


class Api(object):
    """The endpoints, independent of the HTTP plumbing: handle(method, path, query, body) -> (status, obj)."""

    def __init__(self, model):
        self.m = model

    def handle(self, method, parts, query, body):
        if not parts:
            raise HttpError(404, "see /api/info")
        name = parts[0]
        fn = getattr(self, "ep_" + name, None)
        if fn is None:
            raise HttpError(404, "unknown endpoint /api/%s" % "/".join(parts))
        try:
            return fn(method, parts[1:], query, body)
        except HttpError:
            raise
        except gm.ParamError as e:
            raise HttpError(400, str(e))
        except StoreError as e:
            raise HttpError(400, str(e))
        except gm.FactoryPreset as e:
            raise HttpError(403, str(e))
        except (gm.PresetExists, gm.NotEditable, gm.CabinetError) as e:
            raise HttpError(409, str(e))
        except KeyError as e:
            raise HttpError(404, "not found: %s" % (e.args[0] if e.args else ""))
        except gd.DeviceError as e:
            raise HttpError(502, "hardware: %s" % e)

    @staticmethod
    def _methods(method, allowed):
        if method not in allowed:
            raise HttpError(405, "method %s not allowed here (use %s)" % (method, "/".join(allowed)))

    # ------------------------------------------------------------------ info / state
    def ep_info(self, method, rest, query, body):
        self._methods(method, ("GET",))
        m = self.m
        params = []
        for p in m.table.params:
            d = p.public()
            d["available"] = m.available(p)
            params.append(d)
        return 200, {"name": "gme", "software_version": gme.__version__,
                     "fpga_version": m.version, "fpga_version_hex": "0x%04X" % m.version,
                     "mock": bool(getattr(m.dev, "mock", False)),
                     "capabilities": {"cab": m.cab_available(), "eq": m.eq_available(), "dyn": m.eq_available(),
                                      "chain_editable": m.chain_editable()},
                     "params": params, "effects": m.table.effects, "chain_default": m.table.chain_default,
                     "registers": m.table.registers, "codec_registers": m.table.data["codec"]["registers"],
                     "span_registers": SPAN_WORDS}

    def ep_state(self, method, rest, query, body):
        self._methods(method, ("GET",))
        return 200, self.m.state()

    # ------------------------------------------------------------------ params
    def ep_params(self, method, rest, query, body):
        self._methods(method, ("POST",))
        need_dict(body)
        if not body:
            raise HttpError(400, "no parameters given")
        for v in body.values():
            if isinstance(v, (dict, list)) or v is None:
                raise HttpError(400, "values must be numbers, strings or booleans")
        values = self.m.set(body)
        return 200, {"ok": True, "values": values}

    # ------------------------------------------------------------------ levels
    def ep_levels(self, method, rest, query, body):
        self._methods(method, ("GET",))
        if rest:
            raise HttpError(404, "unknown endpoint /api/levels/%s" % "/".join(rest))
        return 200, self.m.levels()

    # ------------------------------------------------------------------ presets
    def ep_presets(self, method, rest, query, body):
        m = self.m
        if not rest:
            if method == "GET":
                return 200, {"presets": m.preset_list()}
            self._methods(method, ("GET", "POST"))
            need_dict(body)
            name = body.get("name")
            if not isinstance(name, type(u"")) and not isinstance(name, str):
                raise HttpError(400, "name required")
            ow = body.get("overwrite", False)
            if not isinstance(ow, bool):
                raise HttpError(400, "overwrite must be true or false")
            m.save_preset(name, overwrite=ow)
            return 201, {"ok": True, "saved": name}
        name = unquote(rest[0])
        if len(rest) > 1:
            raise HttpError(404, "unknown endpoint")
        if method == "GET":
            return 200, m.get_preset(name)
        if method == "POST":
            warnings = m.apply_preset(name)
            return 200, {"ok": True, "loaded": name, "warnings": warnings, "values": m.state()["values"]}
        self._methods(method, ("GET", "POST", "DELETE"))
        m.delete_preset(name)
        return 200, {"ok": True, "deleted": name}

    # ------------------------------------------------------------------ cabinet
    def ep_cab(self, method, rest, query, body):
        m = self.m
        if method == "GET":
            return 200, m.cab_status()
        self._methods(method, ("GET", "POST"))
        need_dict(body)
        if "slot" not in body and "enabled" not in body:
            raise HttpError(400, "give slot and/or enabled")
        out = {"ok": True}
        with m.lock:
            if "slot" in body:
                if not is_int(body["slot"]) or not 0 <= body["slot"] <= 99:
                    raise HttpError(400, "slot must be an integer 0..99")
                out["loaded"] = m.cab_load(body["slot"])
            if "enabled" in body:
                if not isinstance(body["enabled"], bool):
                    raise HttpError(400, "enabled must be true or false")
                m.cab_enable(body["enabled"])
        out["cab"] = m.cab_status()
        return 200, out

    # ------------------------------------------------------------------ codec
    def ep_codec(self, method, rest, query, body):
        m = self.m
        if method == "GET":
            return 200, {"registers": m.table.data["codec"]["registers"],
                         "busy": bool(m.read(gd.REG_CODEC) & 1)}
        self._methods(method, ("GET", "POST"))
        need_dict(body)
        ref = body.get("reg", body.get("name"))
        val = body.get("value")
        if ref is None or val is None:
            raise HttpError(400, "give reg (or name) and value")
        if isinstance(ref, bool) or isinstance(val, bool) or not is_int(val):
            raise HttpError(400, "value must be an integer 0..511")
        reg = m.codec_reg(ref)
        m.codec_write(reg, val)
        return 200, {"ok": True, "reg": reg, "value": val}

    # ------------------------------------------------------------------ chain
    def ep_chain(self, method, rest, query, body):
        m = self.m
        if method == "GET":
            return 200, m.chain()
        self._methods(method, ("GET", "POST"))
        need_dict(body)
        order = body.get("order")
        if not isinstance(order, list):
            raise HttpError(400, "order: list of effect ids required")
        return 200, m.set_chain(order)

    # ------------------------------------------------------------------ raw
    def ep_raw(self, method, rest, query, body):
        m = self.m
        if not rest:
            self._methods(method, ("GET",))
            regs = [r for r in m.table.registers if m.version >= r["min_version"]]
            return 200, {"registers": [{"reg": r["reg"], "name": r["name"], "rw": r["rw"],
                                        "value": m.read(r["reg"])} for r in regs]}
        if len(rest) > 1:
            raise HttpError(404, "unknown endpoint")
        try:
            reg = m.table.register(unquote(rest[0]))
        except gm.ParamError as e:
            raise HttpError(400, str(e))
        if not 0 <= reg < SPAN_WORDS:
            raise HttpError(400, "register 0..%d" % (SPAN_WORDS - 1))
        if method == "POST":
            need_dict(body)
            v = body.get("value")
            if not is_int(v) or not 0 <= v <= 0xFFFF:
                raise HttpError(400, "value must be an integer 0..65535")
            m.write(reg, v)
        else:
            self._methods(method, ("GET", "POST"))
        val = m.read(reg)
        return 200, {"reg": reg, "value": val, "hex": "0x%04X" % val}


class Handler(BaseHTTPRequestHandler):
    server_version = "gme/" + gme.__version__

    def log_message(self, fmt, *args):
        if getattr(self.server, "verbose", False):
            sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))

    # -- plumbing ---------------------------------------------------------
    def _send(self, status, data, ctype, extra=None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or []):
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _json(self, status, obj):
        self._send(status, json.dumps(obj).encode("utf-8"), "application/json; charset=utf-8")

    def _read_body(self):
        n = self.headers.get("Content-Length")
        if not n:
            return {}
        try:
            n = int(n)
        except ValueError:
            raise HttpError(400, "bad Content-Length")
        if n > MAX_BODY:
            raise HttpError(413, "body too large")
        raw = self.rfile.read(n)
        if not raw.strip():
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except ValueError:
            raise HttpError(400, "invalid JSON body")

    def _dispatch(self):
        try:
            u = urlsplit(self.path)
            parts = [p for p in u.path.split("/") if p]
            if parts and parts[0] == "api":
                query = parse_qs(u.query)
                if parts[1:2] == ["levels"] and parts[2:] == ["stream"]:
                    if self.command != "GET":
                        raise HttpError(405, "GET only")
                    return self._stream(query)
                body = self._read_body() if self.command in ("POST", "PUT") else {}
                status, obj = self.server.api.handle(self.command, parts[1:], query, body)
                return self._json(status, obj)
            if self.command not in ("GET", "HEAD"):
                raise HttpError(405, "method not allowed")
            return self._static(u.path)
        except HttpError as e:
            self._json(e.status, {"error": e.message})
        except (IOError, OSError) as e:
            if getattr(e, "errno", None) in (32, 104, 10053, 10054):   # client went away
                return
            self._json(500, {"error": "internal error: %s" % e})
        except Exception as e:                                          # keep the server alive
            self._json(500, {"error": "internal error: %s: %s" % (e.__class__.__name__, e)})

    do_GET = do_POST = do_DELETE = do_PUT = do_HEAD = _dispatch

    # -- static files -------------------------------------------------------
    def _static(self, urlpath):
        root = os.path.realpath(self.server.www_dir)
        rel = unquote(urlpath).lstrip("/") or "index.html"
        path = os.path.realpath(os.path.join(root, rel))
        if os.path.isdir(path):
            path = os.path.join(path, "index.html")
        if not (path == root or path.startswith(root + os.sep)) or not os.path.isfile(path):
            raise HttpError(404, "not found")
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        with open(path, "rb") as f:
            data = f.read()
        self._send(200, data, ctype)

    # -- server-sent events ---------------------------------------------------
    def _stream(self, query):
        try:
            hz = float(query.get("hz", ["15"])[0])
            limit = int(query.get("max", ["0"])[0])
        except ValueError:
            raise HttpError(400, "hz / max must be numbers")
        hz = min(max(hz, 1.0), 30.0)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        n = 0
        try:
            while not self.server.stopping.is_set():
                ev = self.server.api.m.levels()
                ev["t"] = round(time.time(), 3)
                self.wfile.write(("data: %s\n\n" % json.dumps(ev)).encode("utf-8"))
                self.wfile.flush()
                n += 1
                if limit and n >= limit:
                    break
                time.sleep(1.0 / hz)
        except (IOError, OSError):
            pass


class Server(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, addr, model, www_dir, verbose=False):
        HTTPServer.__init__(self, addr, Handler)
        self.api = Api(model)
        self.www_dir = www_dir
        self.verbose = verbose
        self.stopping = threading.Event()

    def stop(self):
        self.stopping.set()
        self.shutdown()
        self.server_close()


def create_server(model, host="127.0.0.1", port=0, www_dir=None, verbose=False):
    return Server((host, port), model, www_dir or os.path.join(HERE, "www"), verbose)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--mock", action="store_true", help="in-memory register file instead of /dev/mem")
    ap.add_argument("--mock-version", type=lambda s: int(s, 0), default=0x0208)
    ap.add_argument("--mock-state", default=None, metavar="FILE",
                    help="with --mock: share the mock registers with other processes through this JSON file "
                         "(e.g. the same file as gme_hps.py --mock --mock-state)")
    ap.add_argument("--no-check", action="store_true", help="skip the VERSION check")
    ap.add_argument("--data-dir", default=None, help="presets/ and settings.json (default: next to this script)")
    ap.add_argument("--cab-dir", default=None, help="cabNN.coef files (default: <data-dir>/cab; with --mock ../ir/build if it has cabinet files)")
    ap.add_argument("--www", default=None, help="static files (default: www/ next to this script)")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)
    try:
        dev = gm.open_device(mock=a.mock, mock_version=a.mock_version, check=not a.no_check,
                                state_file=os.path.expanduser(a.mock_state) if a.mock_state else None)
    except gd.WrongImage as e:
        raise SystemExit(str(e))
    except (IOError, OSError) as e:
        raise SystemExit("cannot open /dev/mem (run as root on the board; --mock to test): %s" % e)
    data_dir = a.data_dir or HERE
    model = gm.Model(dev, store=Store(data_dir), cab_dir=a.cab_dir or gm.default_cab_dir(data_dir, a.mock))
    try:
        if model.eq_resync():                      # the FPGA forgot the EQ coefficients (they cannot be read back)
            print("EQ coefficients restored from settings.json")
    except gm.ParamError as e:
        print("EQ: %s" % e)
    srv = create_server(model, a.host, a.port, a.www, a.verbose)
    print("gme web UI: http://%s:%d/  (FPGA VERSION 0x%04X%s)" % (
        a.host if a.host != "0.0.0.0" else "<board address>", srv.server_address[1], model.version,
        ", MOCK" if a.mock else ""))
    sys.stdout.flush()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("")
    finally:
        srv.server_close()


if __name__ == "__main__":
    sys.exit(main())
