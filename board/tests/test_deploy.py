"""Deployment scripts, tested locally: the init script against a temporary directory with the mock
server, the autostart installer against a fake root, deploy_board.sh / board_smoke.sh with a fake
`ssh` that runs the remote command locally.  Nothing here touches a board."""
import json
import os
import shutil
import socket
import stat
import subprocess
import sys
import time
import urllib.request

import pytest

from conftest import BOARD, REPO

SH = shutil.which("sh")
BASH = shutil.which("bash")
pytestmark = pytest.mark.skipif(not (SH and BASH) or os.name == "nt", reason="needs a POSIX shell")

TOOLS = os.path.join(REPO, "tools")


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def board_copy(dst):
    shutil.copytree(BOARD, str(dst), ignore=shutil.ignore_patterns("tests", "__pycache__", "*.pyc", ".pytest_cache"))
    return str(dst)


def get(port, path):
    return json.loads(urllib.request.urlopen("http://127.0.0.1:%d%s" % (port, path), timeout=5).read().decode())


@pytest.fixture
def initenv(tmp_path):
    d = board_copy(tmp_path / "gme")
    port = free_port()
    env = dict(os.environ, GME_DIR=d, GME_PORT=str(port), GME_PIDFILE=str(tmp_path / "pid"),
               GME_LOG=str(tmp_path / "log"), GME_PY=sys.executable,
               GME_ARGS="--mock --host 127.0.0.1 --mock-state %s --data-dir %s" % (tmp_path / "st.json", tmp_path / "data"))
    yield d, port, env, tmp_path
    subprocess.run([SH, os.path.join(d, "gme_web.init"), "stop"], env=env, capture_output=True)


def init(d, env, cmd):
    return subprocess.run([SH, os.path.join(d, "gme_web.init"), cmd], env=env, capture_output=True, text=True, timeout=60)


def test_init_start_status_stop(initenv):
    d, port, env, tmp = initenv
    assert init(d, env, "status").returncode == 3
    r = init(d, env, "start")
    assert r.returncode == 0, r.stderr
    assert "started" in r.stdout
    assert get(port, "/api/info")["fpga_version"] == 0x0209
    assert init(d, env, "status").returncode == 0
    assert "already running" in init(d, env, "start").stdout
    pid = int(open(str(tmp / "pid")).read())
    r = init(d, env, "restart")
    assert r.returncode == 0
    assert int(open(str(tmp / "pid")).read()) != pid
    assert get(port, "/api/state")["status"]["version"] == 0x0209
    assert init(d, env, "stop").returncode == 0
    assert init(d, env, "status").returncode == 3
    assert not os.path.exists(str(tmp / "pid"))
    with pytest.raises(Exception):
        get(port, "/api/info")
    assert "starting gme_web.py" in open(str(tmp / "log")).read()
    assert init(d, env, "bogus").returncode == 2


def test_init_wrong_fpga_image_does_not_loop(initenv):
    d, port, env, tmp = initenv
    env["GME_ARGS"] += " --mock-version 0x0100"
    r = init(d, env, "start")
    assert r.returncode == 1
    assert "exited at start-up" in r.stderr
    assert "0x02xx" in open(str(tmp / "log")).read()
    assert not os.path.exists(str(tmp / "pid"))
    time.sleep(1.5)
    assert init(d, env, "status").returncode == 3                 # nothing restarted it


def test_init_missing_files(initenv):
    d, port, env, tmp = initenv
    os.remove(os.path.join(d, "gme_web.py"))
    r = init(d, env, "start")
    assert r.returncode == 1 and "not found" in r.stderr


# ---- autostart installer -------------------------------------------------------------------------------

def installer(tmp_path, root, extra_env=None, tools=("sh", "ls", "grep", "awk", "cat", "ln", "mkdir", "chmod", "rm", "printf",
                                                    "dirname", "mktemp", "sed")):
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    for t in tools:
        src = shutil.which(t)
        if src and not (bindir / t).exists():
            os.symlink(src, str(bindir / t))
    env = dict(os.environ, PATH=str(bindir), GME_ROOT=str(root), GME_DIR="/home/root/gme")
    env.update(extra_env or {})
    return env


def run_inst(env, cmd):
    return subprocess.run([SH, os.path.join(BOARD, "install_init.sh"), cmd], env=env, capture_output=True, text=True)


def test_install_detect_and_systemd(tmp_path):
    root = tmp_path / "root"
    (root / "run" / "systemd" / "system").mkdir(parents=True)
    env = installer(tmp_path, root)
    assert run_inst(env, "detect").stdout.strip() == "systemd"
    r = run_inst(env, "install")
    assert r.returncode == 0 and "init system found: systemd" in r.stdout
    unit = (root / "etc" / "systemd" / "system" / "gme_web.service").read_text()
    assert "--port 8080" in unit and "/home/root/gme/gme_web.py" in unit and "Restart=no" in unit
    assert run_inst(env, "uninstall").returncode == 0
    assert not (root / "etc" / "systemd" / "system" / "gme_web.service").exists()


def test_install_sysv_update_rc(tmp_path):
    root = tmp_path / "root"
    (root / "etc" / "init.d").mkdir(parents=True)
    stub = tmp_path / "stub"
    stub.mkdir()
    (stub / "update-rc.d").write_text("#!/bin/sh\necho \"$@\" >> %s\n" % (tmp_path / "urc.log"))
    (stub / "update-rc.d").chmod(0o755)
    env = installer(tmp_path, root)
    env["PATH"] = str(stub) + os.pathsep + env["PATH"]
    assert run_inst(env, "detect").stdout.strip() == "sysv-update-rc"
    r = run_inst(env, "install")
    assert r.returncode == 0 and "sysv-update-rc" in r.stdout
    assert os.readlink(str(root / "etc" / "init.d" / "gme_web")) == "/home/root/gme/gme_web.init"
    assert open(str(tmp_path / "urc.log")).read().strip() == "gme_web defaults 90 10"


def test_install_sysv_links_without_update_rc(tmp_path):
    root = tmp_path / "root"
    for n in "0123456":
        (root / "etc" / ("rc%s.d" % n)).mkdir(parents=True)
    (root / "etc" / "init.d").mkdir()
    env = installer(tmp_path, root)
    assert run_inst(env, "detect").stdout.strip() == "sysv-links"
    assert run_inst(env, "install").returncode == 0
    for n in "2345":
        assert (root / "etc" / ("rc%s.d" % n) / "S90gme_web").is_symlink()
    for n in "016":
        assert (root / "etc" / ("rc%s.d" % n) / "K10gme_web").is_symlink()
    assert run_inst(env, "uninstall").returncode == 0
    assert not (root / "etc" / "rc2.d" / "S90gme_web").is_symlink() and not (root / "etc" / "init.d" / "gme_web").is_symlink()


def test_install_upstart(tmp_path):
    root = tmp_path / "root"
    (root / "etc" / "init").mkdir(parents=True)
    env = installer(tmp_path, root)
    assert run_inst(env, "detect").stdout.strip() == "upstart"
    assert run_inst(env, "install").returncode == 0
    conf = (root / "etc" / "init" / "gme_web.conf").read_text()
    assert "exec /bin/sh /home/root/gme/gme_web.init start" in conf


def test_install_rc_local_fallback(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    env = installer(tmp_path, root)
    assert run_inst(env, "detect").stdout.strip() == "rc.local"
    for _ in range(2):                                          # idempotent
        assert run_inst(env, "install").returncode == 0
    lines = (root / "etc" / "rc.local").read_text().splitlines()
    assert lines[0] == "#!/bin/sh" and lines[-1] == "exit 0"
    assert [l for l in lines if "gme_web" in l] == ["/bin/sh /home/root/gme/gme_web.init start # gme_web"]
    assert lines.index("exit 0") > [i for i, l in enumerate(lines) if "gme_web" in l][0]
    assert run_inst(env, "uninstall").returncode == 0
    assert "gme_web" not in (root / "etc" / "rc.local").read_text()
    # an existing rc.local keeps its other lines
    (root / "etc" / "rc.local").write_text("#!/bin/sh\necho hello\nexit 0\n")
    run_inst(env, "install")
    t = (root / "etc" / "rc.local").read_text().splitlines()
    assert t[:2] == ["#!/bin/sh", "echo hello"] and t[-1] == "exit 0" and len(t) == 4


def test_install_forced_system_and_unknown(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    env = installer(tmp_path, root, {"GME_INIT_SYSTEM": "upstart"})
    assert run_inst(env, "detect").stdout.strip() == "upstart"
    env["GME_INIT_SYSTEM"] = "bogus"
    assert run_inst(env, "install").returncode == 1
    assert run_inst(env, "nonsense").returncode == 2


# ---- deploy_board.sh / board_smoke.sh with a fake ssh ---------------------------------------------------------

@pytest.fixture
def fakessh(tmp_path):
    p = tmp_path / "fakessh"
    p.write_text('#!/bin/sh\n# fake ssh: skip "-o X", skip the target, run the rest locally\n'
                 'while [ "$1" = "-o" ]; do shift 2; done\nshift\nexec sh -c "$*"\n')
    p.chmod(0o755)
    return str(p)


def deploy(args, env, **kw):
    return subprocess.run([BASH, os.path.join(TOOLS, "deploy_board.sh")] + args, env=env, capture_output=True, text=True,
                          timeout=120, **kw)


def test_deploy_dry_run(tmp_path):
    env = dict(os.environ, GME_SSH="false")                      # would fail if it were called
    cab = tmp_path / "c"
    cab.mkdir()
    (cab / "cab00.coef").write_text("x\n0\n")
    r = deploy(["--dry-run", "--install", "--cab", str(cab), "--host", "10.0.0.9"], env)
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert "root@10.0.0.9:/home/root/gme" in out and "[dry-run] nothing was changed" in out
    assert "install_init.sh' install" in out and "gme_web.init' restart" in out and "board_smoke.sh" in out
    assert "rm -rf gme www" in out and "/home/root/gme" in out
    assert "rm -rf /" not in out
    r = deploy(["--dry-run", "--no-restart"], env)
    assert "gme_web.init' restart" not in r.stdout and "board_smoke" not in r.stdout
    assert deploy(["--bogus"], env).returncode == 2
    assert deploy(["--cab", str(tmp_path)], env).returncode == 1          # no cab files there
    r = subprocess.run([BASH, os.path.join(TOOLS, "board_smoke.sh"), "--dry-run", "10.0.0.9", "--port", "9"],
                       env=env, capture_output=True, text=True)
    assert r.returncode == 0 and "gme_smoke.py --port '9'" in r.stdout and "curl" in r.stdout


def test_deploy_and_smoke_with_fake_ssh(tmp_path, fakessh):
    remote = tmp_path / "remote"
    (remote / "presets").mkdir(parents=True)
    (remote / "presets" / "mine.json").write_text("{}")
    (remote / "settings.json").write_text("{}")
    (remote / "www").mkdir()
    (remote / "www" / "stale.js").write_text("old")
    (remote / "cab").mkdir()
    (remote / "cab" / "keep.coef").write_text("k")
    outside = tmp_path / "outside.txt"
    outside.write_text("untouched")
    cab = tmp_path / "cabsrc"
    cab.mkdir()
    (cab / "cab00.coef").write_text("n\n0\n")
    (cab / "notes.txt").write_text("not copied")
    port = free_port()
    env = dict(os.environ, GME_SSH=fakessh, GME_PY=sys.executable, GME_PIDFILE=str(tmp_path / "pid"),
               GME_LOG=str(tmp_path / "log"),
               GME_ARGS="--mock --host 127.0.0.1 --mock-state %s --data-dir %s" % (tmp_path / "st.json", tmp_path / "data"),
               GME_HPS_ARGS="--mock --mock-state %s --data-dir %s" % (tmp_path / "st.json", tmp_path / "data"))
    try:
        r = deploy(["--host", "127.0.0.1", "--remote-dir", str(remote), "--port", str(port), "--cab", str(cab)], env)
        assert r.returncode == 0, r.stdout + r.stderr
        for f in ("gme/model.py", "gme/params.json", "gme_hps.py", "gme_web.py", "gme_smoke.py", "gme_web.init",
                  "install_init.sh", "www/index.html", "www/app.js", "README.md", "cab/cab00.coef"):
            assert (remote / f).is_file(), f
        assert not (remote / "tests").exists()
        assert not (remote / "www" / "stale.js").exists()                  # old code replaced
        assert (remote / "presets" / "mine.json").exists() and (remote / "settings.json").exists()
        assert (remote / "cab" / "keep.coef").exists() and not (remote / "cab" / "notes.txt").exists()
        assert outside.read_text() == "untouched"
        assert os.access(str(remote / "gme_web.init"), os.X_OK)
        assert "ALL CHECKS PASSED" in r.stdout and "FAIL" not in r.stdout
        assert r.stdout.count("PASS set/read back/restore") == 9
        assert "PASS GET /api/info" in r.stdout and "PASS PC -> board" in r.stdout
        assert get(port, "/api/info")["mock"] is True
        # the smoke test restored the values it changed
        st = get(port, "/api/state")
        assert all(v == 0 for k, v in st["raw"].items() if k.endswith("_on"))
        # smoke test alone, and a failing one (server stopped)
        s = subprocess.run([BASH, os.path.join(TOOLS, "board_smoke.sh"), "127.0.0.1", "--port", str(port),
                            "--remote-dir", str(remote)], env=env, capture_output=True, text=True, timeout=60)
        assert s.returncode == 0, s.stdout
        subprocess.run([SH, str(remote / "gme_web.init"), "stop"], env=dict(env, GME_DIR=str(remote)), capture_output=True)
        s = subprocess.run([BASH, os.path.join(TOOLS, "board_smoke.sh"), "127.0.0.1", "--port", str(port),
                            "--remote-dir", str(remote)], env=dict(env, GME_SMOKE_WAIT="1"), capture_output=True, text=True, timeout=90)
        assert s.returncode == 1 and "FAIL" in s.stdout and "SOME CHECKS FAILED" in s.stdout
    finally:
        subprocess.run([SH, str(remote / "gme_web.init"), "stop"], env=dict(env, GME_DIR=str(remote)), capture_output=True)


def test_deploy_install_with_fake_ssh_uses_remote_dir(tmp_path, fakessh):
    """--install runs install_init.sh with the remote dir; the fake root keeps /etc untouched."""
    remote = tmp_path / "remote"
    root = tmp_path / "root"
    root.mkdir()
    env = dict(os.environ, GME_SSH=fakessh, GME_ROOT=str(root), GME_INIT_SYSTEM="rc.local",
               GME_PY=sys.executable, GME_PIDFILE=str(tmp_path / "pid"), GME_LOG=str(tmp_path / "log"),
               GME_ARGS="--mock --host 127.0.0.1 --mock-state %s --data-dir %s" % (tmp_path / "st.json", tmp_path / "data"))
    port = free_port()
    try:
        r = deploy(["--host", "127.0.0.1", "--remote-dir", str(remote), "--port", str(port), "--install", "--no-smoke"], env)
        assert r.returncode == 0, r.stdout + r.stderr
        assert "init system found: rc.local" in r.stdout
        assert ("%s/gme_web.init start" % remote) in (root / "etc" / "rc.local").read_text()
    finally:
        subprocess.run([SH, str(remote / "gme_web.init"), "stop"], env=dict(env, GME_DIR=str(remote)), capture_output=True)


def test_gme_smoke_py_directly(tmp_path):
    import threading
    import gme_web
    import gme_smoke
    from gme import device as gd, model as gm
    from gme.store import Store
    m = gm.Model(gd.Mock(), store=Store(str(tmp_path)))
    srv = gme_web.create_server(m, "127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()
    try:
        before = m.read_all()
        assert gme_smoke.main(["--port", str(srv.server_address[1])]) == 0
        assert m.read_all() == before                              # everything restored
    finally:
        srv.stop()
    gme_smoke.RESULTS[:] = []
    assert gme_smoke.main(["--port", str(free_port()), "--wait", "0.5"]) == 1
