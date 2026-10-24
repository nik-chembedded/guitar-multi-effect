"""
test_runner.py - builds the design with GHDL and runs the cocotb tests.

    cd sim/cocotb && pytest -v            # all tests
    pytest -v -k overdrive                # select tests (by test name)
"""
import os
import shutil
from pathlib import Path

from cocotb_tools.runner import get_runner

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
RTL = ROOT / "fpga" / "rtl"
MODELS = ROOT / "sim" / "models"
BUILD = Path(os.environ.get("GME_BUILD", HERE / "sim_build"))

IP_MODELS = [MODELS / "sim_rom.vhd", MODELS / "sim_dpram.vhd", MODELS / "sim_dcfifo.vhd",
             *sorted((MODELS / "ip").glob("*.vhd"))]
FX_RTL = [RTL / f for f in ("fx_pkg.vhd", "overdrive.vhd", "distortion.vhd", "chorus.vhd",
                            "tremolo_v2.vhd", "echo.vhd", "comb_filter.vhd",
                            "allpass_filter.vhd", "reverbe.vhd", "FX_chain.vhd")]
GHDL_ARGS = ["--std=08", "-frelaxed"]


def run(toplevel, test_module, sources, testcase=None):
    build_dir = BUILD / toplevel
    build_dir.mkdir(parents=True, exist_ok=True)
    for mif in (ROOT / "fpga" / "ip").glob("*.mif"):      # ROMs load .mif from the cwd
        shutil.copy(mif, build_dir)
    runner = get_runner(os.environ.get("SIM", "ghdl"))
    runner.build(sources=sources, hdl_toplevel=toplevel, build_args=GHDL_ARGS,
                 build_dir=build_dir, always=True)
    # run in build_dir: GHDL's compiled library and the .mif files are there
    runner.test(hdl_toplevel=toplevel, test_module=test_module, test_dir=build_dir,
                build_dir=build_dir, test_args=GHDL_ARGS, testcase=testcase,
                plusargs=["--ieee-asserts=disable-at-0"],
                extra_env={"PYTHONPATH": str(HERE) + os.pathsep + os.environ.get("PYTHONPATH", "")})


def test_fx_chain():
    run("fx_chain", "test_fx_chain", IP_MODELS + FX_RTL,
        testcase=os.environ.get("TESTCASE"))


def test_wav():
    """Real guitar audio through every preset (GME_WAV_SECONDS, default 1 s)."""
    run("fx_chain", "test_wav", IP_MODELS + FX_RTL)
