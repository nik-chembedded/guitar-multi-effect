"""
test_runner.py - builds the design with GHDL and runs the cocotb tests.

    cd sim/cocotb && pytest -v            # all tests
    pytest -v -k overdrive                # select tests (by test name)
    GME_WAVES=1 pytest -v -k test_i2s     # also write a GTKWave waveform (<build>/<top>/<top>.ghw)

Environment: GME_BUILD (build directory), GME_WAVES=1 (waveforms), TESTCASE (one cocotb
test of the FX_chain suite). See sim/run_all.sh for the usual invocations.
"""
import os
import shutil
from pathlib import Path

import pytest

from cocotb_tools.runner import get_runner

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
RTL = ROOT / "fpga" / "rtl"
MODELS = ROOT / "sim" / "models"
BUILD = Path(os.environ.get("GME_BUILD", HERE / "sim_build"))

IP_MODELS = [MODELS / "sim_rom.vhd", MODELS / "sim_dpram.vhd", MODELS / "fx_dpram.vhd",
             *sorted((MODELS / "ip").glob("*.vhd"))]
FX_RTL = [RTL / f for f in ("fx_pkg.vhd", "fx_xfade.vhd", "lfo_sine_pkg.vhd", "nco_lfo.vhd",
                            "overdrive.vhd", "distortion.vhd", "chorus.vhd",
                            "tremolo_v2.vhd", "echo.vhd", "comb_filter.vhd",
                            "allpass_filter.vhd", "reverbe.vhd", "FX_chain.vhd")]
GHDL_ARGS = ["--std=08", "-frelaxed"]
# v1 ROM-table tremolo (simulation only), for the v1 reference tests
LEGACY = MODELS / "legacy"
LEGACY_TREM = [*sorted((LEGACY / "ip").glob("*.vhd")), LEGACY / "tremolo_legacy.vhd"]


def run(toplevel, test_module, sources, testcase=None, parameters=None, extra_env=None, tag=""):
    build_dir = BUILD / (toplevel + tag)
    build_dir.mkdir(parents=True, exist_ok=True)
    for mif in [*(ROOT / "fpga" / "ip").glob("*.mif"), *LEGACY.glob("mif/*.mif")]:
        shutil.copy(mif, build_dir)                       # ROMs load .mif from the cwd
    runner = get_runner(os.environ.get("SIM", "ghdl"))
    runner.build(sources=sources, hdl_toplevel=toplevel, build_args=GHDL_ARGS,
                 build_dir=build_dir, always=True, parameters=parameters or {})
    # run in build_dir: GHDL's compiled library and the .mif files are there
    waves = os.environ.get("GME_WAVES", "0") == "1"
    runner.test(hdl_toplevel=toplevel, test_module=test_module, test_dir=build_dir,
                build_dir=build_dir, test_args=GHDL_ARGS, testcase=testcase,
                plusargs=["--ieee-asserts=disable-at-0"],
                parameters=parameters or {}, waves=waves,
                extra_env={"PYTHONPATH": str(HERE) + os.pathsep + os.environ.get("PYTHONPATH", ""),
                           **(extra_env or {})})
    if waves:
        for w in sorted(build_dir.glob("*.ghw")):
            print("waveform: %s  (%.1f MB) - open with gtkwave" % (w, w.stat().st_size / 1e6))


def test_fx_chain():
    run("fx_chain", "test_fx_chain", IP_MODELS + FX_RTL,
        testcase=os.environ.get("TESTCASE"))


def test_fx_chain_24():
    """The same 7 effect tests on the 24-bit chain (16-bit stimulus x 256)."""
    run("fx_chain", "test_fx_chain", IP_MODELS + FX_RTL, testcase=os.environ.get("TESTCASE"),
        parameters={"DW": 24}, extra_env={"GME_DW": "24"}, tag="_24")


def test_lfo():
    """Generated LFO nco_lfo (v2 step D1) against its Python model."""
    run("nco_lfo", "test_lfo", [RTL / "lfo_sine_pkg.vhd", RTL / "nco_lfo.vhd"])


def test_lfo_vs_v1():
    """The generated LFO has the shapes and rates of the 8 v1 tables (no simulation)."""
    import test_lfo_v1
    test_lfo_v1.check_all()


def test_moddelay():
    """Modulated delay (chorus / flanger / vibrato, v2 step D2) bit-exact to its model."""
    srcs = [MODELS / "sim_dpram.vhd", MODELS / "fx_dpram.vhd",
            *[RTL / f for f in ("fx_pkg.vhd", "lfo_sine_pkg.vhd", "nco_lfo.vhd", "mod_delay.vhd")]]
    run("mod_delay", "test_moddelay", srcs, tag="_16")
    run("mod_delay", "test_moddelay", srcs, parameters={"DW": 24}, extra_env={"GME_DW": "24"}, tag="_24")


def test_trem():
    """Tremolo on the generated LFO, bit-exact to the Python model (16 and 24 bit)."""
    run("fx_chain", "test_trem", IP_MODELS + FX_RTL, tag="_trem")
    run("fx_chain", "test_trem", IP_MODELS + FX_RTL, parameters={"DW": 24},
        extra_env={"GME_DW": "24"}, tag="_trem24")


def test_fxlib():
    """Fixed-point library fx_pkg (v2 step C)."""
    run("fxlib_wrap", "test_fxlib", [RTL / "fx_pkg.vhd", HERE / "hdl" / "fxlib_wrap.vhd"])


def test_smooth():
    """Parameter smoothing (param_smooth)."""
    run("param_smooth", "test_smooth", [RTL / "param_smooth.vhd"])


def test_xfade():
    """Click-free effect on/off on the 24-bit chain."""
    run("fx_chain", "test_xfade", IP_MODELS + FX_RTL, parameters={"DW": 24, "XFADE": True},
        extra_env={"GME_DW": "24"}, tag="_xfade")


def test_ref24():
    """24-bit chain: bit-exact 24-bit golden models + the 27 v1 presets within 16-bit rounding."""
    run("fx_chain", "test_ref24", IP_MODELS + FX_RTL + LEGACY_TREM,
        parameters={"DW": 24, "ECHO_AW": 16, "LEGACY_TREM": True},
        extra_env={"GME_DW": "24"}, tag="_ref24")


def test_i2s():
    """I2S master core (v2 step B2) against a WM8731 slave model."""
    run("i2s_core", "test_i2s", [RTL / "i2s_core.vhd"])


CTRL_RTL = [RTL / f for f in ("reg_file.vhd", "ctrl_avmm.vhd")]


def test_avmm():
    """Avalon-MM control slave (HPS lightweight bridge) + register file + CODEC register."""
    run("ctrl_avmm", "test_avmm", CTRL_RTL)


def test_codec():
    """I2C master + codec init sequencer (v2 step B4) against an I2C slave model."""
    run("codec_ctrl", "test_codec", [RTL / "i2c_master.vhd", RTL / "codec_ctrl.vhd"],
        parameters={"WAIT_CLKS": 2000})


SYS_RTL = (IP_MODELS + FX_RTL + CTRL_RTL +
           [RTL / f for f in ("i2s_core.vhd", "i2c_master.vhd", "codec_ctrl.vhd", "param_smooth.vhd",
                              "gme_core.vhd")])


def test_system():
    """gme_core end to end: codec init, control over the Avalon slave (HPS), I2S audio."""
    run("gme_core", "test_system", SYS_RTL,
        parameters={"INIT_WAIT_CLKS": 2000})


def test_reference():
    """Bit-exact against the recorded v1 outputs (GME_REF_MODE=record to re-record).
    DW = 16, the v1 echo line size (64 k words) and the v1 ROM-table tremolo."""
    run("fx_chain", "test_ref", IP_MODELS + FX_RTL + LEGACY_TREM,
        parameters={"ECHO_AW": 16, "LEGACY_TREM": True}, tag="_v1")


WAV_PRESETS = ["dry", "overdrive", "dist_medium", "tremolo", "tremolo_saw", "chorus", "echo", "reverb"]


@pytest.mark.parametrize("preset", WAV_PRESETS)
def test_wav(preset):
    """Real guitar audio through one preset on the 24-bit chain (GME_WAV_SECONDS, default 1 s)."""
    run("fx_chain", "test_wav", IP_MODELS + FX_RTL, parameters={"DW": 24},
        extra_env={"GME_DW": "24", "GME_WAV_PRESET": preset}, tag="_wav24_" + preset)
