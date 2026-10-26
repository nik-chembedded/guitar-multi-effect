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
             MODELS / "cab_coef_ram.vhd", *sorted((MODELS / "ip").glob("*.vhd"))]
FX_RTL = [RTL / f for f in ("fx_pkg.vhd", "fx_xfade.vhd", "lfo_sine_pkg.vhd", "nco_lfo.vhd",
                            "level_gain.vhd", "overdrive.vhd", "distortion.vhd", "mod_delay.vhd",
                            "tremolo_v2.vhd", "echo.vhd", "fv_comb.vhd",
                            "fv_allpass.vhd", "reverb_fv.vhd", "cab_fir.vhd", "cab_stage.vhd",
                            "dynamics.vhd", "biquad.vhd", "eq3.vhd", "fx_bypass.vhd",
                            "dyn_stage.vhd", "eq_stage.vhd", "FX_chain.vhd")]
# chain-level simulations use 16-clock frames: a 16-tap cabinet (2048 taps need 519 clocks per sample)
CAB16 = {"CAB_TAPS": 16, "CAB_INIT": "cab_test16.mif"}
GHDL_ARGS = ["--std=08", "-frelaxed"]


def run(toplevel, test_module, sources, testcase=None, parameters=None, extra_env=None, tag=""):
    build_dir = BUILD / (toplevel + tag)
    build_dir.mkdir(parents=True, exist_ok=True)
    for mif in (ROOT / "fpga" / "ip").glob("*.mif"):      # ROMs load .mif from the cwd
        shutil.copy(mif, build_dir)
    shutil.copy(MODELS / "cab_test16.mif", build_dir)     # 16-tap cabinet of the chain tests
    if toplevel == "fx_chain":
        parameters = {**CAB16, **(parameters or {})}
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


def test_cab_xfade():
    """Cabinet stage with the click-free chain (XFADE): the bank switch fades, no step above the signal's."""
    for dw in (16, 24):
        run("fx_chain", "test_fx_chain", IP_MODELS + FX_RTL, testcase="test_cab",
            parameters={"DW": dw, "XFADE": True}, extra_env={"GME_DW": str(dw), "GME_XFADE": "1"},
            tag="_cabx%d" % dw)


def test_dyn_eq_xfade():
    """Dynamics and EQ stages with the click-free chain (XFADE): enabling / disabling fades, no step above
    the steady states', exact bypass after the fade-out."""
    for dw in (16, 24):
        run("fx_chain", "test_fx_chain", IP_MODELS + FX_RTL, testcase="test_dyn_eq_fade",
            parameters={"DW": dw, "XFADE": True}, extra_env={"GME_DW": str(dw), "GME_XFADE": "1"},
            tag="_dyneqx%d" % dw)


def test_timing_invariance():
    """The chain gives identical output samples with 16-clock frames (simulation) and 1024-clock frames
    (board): one configuration with all effects on (dynamics, overdrive, distortion, cabinet, EQ, mod delay,
    tremolo, echo, reverb), 400 frames, two simulations (GME_HALF = 8 and 512)."""
    import numpy as np
    outs = {}
    for half in (8, 512):
        f = BUILD / ("invariance_%d.npy" % half)
        run("fx_chain", "test_invariance", IP_MODELS + FX_RTL, parameters={"DW": 24, "XFADE": True},
            extra_env={"GME_DW": "24", "GME_HALF": str(half), "GME_INV_OUT": str(f)}, tag="_inv%d" % half)
        outs[half] = np.load(f)
    a, b = outs[8], outs[512]
    assert a.shape == b.shape
    bad = np.nonzero(a != b)[0]
    assert not len(bad), "output differs between 16-clock and 1024-clock frames in %d of %d frames, first at %d (%d vs %d)" % (
        len(bad), len(a), bad[0], a[bad[0]], b[bad[0]])
    print("timing invariance: %d frames identical at 16 and 1024 clocks per frame" % len(a))


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


def test_i2s():
    """I2S master core (v2 step B2) against a WM8731 slave model."""
    run("i2s_core", "test_i2s", [RTL / "i2s_core.vhd"])


CAB_SRCS = [MODELS / "sim_dpram.vhd", MODELS / "fx_dpram.vhd", MODELS / "cab_coef_ram.vhd", RTL / "fx_pkg.vhd", RTL / "cab_fir.vhd"]


def test_cabfir():
    """Cabinet FIR (v2 step D3) bit-exact to its model: small configurations at 16 and 24 bit
    (random data, saturation, bank switch, impulse, latency)."""
    for dw, taps, lanes in ((16, 16, 4), (24, 64, 4), (16, 64, 4)):
        run("cab_fir", "test_cabfir", CAB_SRCS,
            parameters={"DW": dw, "TAPS": taps, "LANES": lanes},
            extra_env={"GME_DW": str(dw), "GME_TAPS": str(taps), "GME_LANES": str(lanes)},
            tag="_%d_%d_%d" % (dw, taps, lanes))


def test_cabfir_full():
    """The full 2048-tap cabinet FIR with the default .mif at 1024 clocks per sample (~7 min)."""
    run("cab_fir", "test_cabfir", CAB_SRCS, testcase="test_full",
        parameters={"DW": 24, "TAPS": 2048, "LANES": 4},
        extra_env={"GME_DW": "24", "GME_TAPS": "2048", "GME_LANES": "4"}, tag="_full")


REVERB_TESTS = ["test_bitexact", "test_mix0_and_bypass", "test_decay", "test_size", "test_damp",
                "test_overload", "test_level", "test_hw_timing"]


@pytest.mark.parametrize("dw", [16, 24])
@pytest.mark.parametrize("testcase", REVERB_TESTS)
def test_reverbfv(dw, testcase):
    """Freeverb reverb (v2 step D4) bit-exact to its model + behaviour checks, 16 and 24 bit.
    The block has no reset: every testcase is its own simulation."""
    run("reverb_fv", "test_reverbfv", [MODELS / "sim_dpram.vhd", MODELS / "fx_dpram.vhd", RTL / "fx_pkg.vhd",
                                       RTL / "fv_comb.vhd", RTL / "fv_allpass.vhd", RTL / "reverb_fv.vhd"],
        testcase=testcase, parameters={"DW": dw}, extra_env={"GME_DW": str(dw)},
        tag="_rv%d_%s" % (dw, testcase))


# dynamics (gate + compressor, v2 step D5a): the block has no reset, so every row is its own
# simulation (docstring of test_dynamics.py: DW, clocks per sample, GME_QUICK, testcases)
DYNAMICS_SIMS = [
    (24, 16, 0, "test_bitexact,test_bypass,test_click", "_24"),
    (16, 16, 0, "test_bitexact,test_bypass,test_click", "_16"),
    (24, 1024, 1, "test_bitexact", "_1024"),
    (24, 16, 0, "test_timing,test_accuracy", "_tim"),
    (24, 16, 0, "test_curve", "_curve"),
    (24, 16, 0, "test_attack_release", "_ar"),
    (24, 16, 0, "test_gate", "_gate"),
]


@pytest.mark.parametrize("dw,frame,quick,testcase,tag", DYNAMICS_SIMS, ids=[r[4].lstrip("_") for r in DYNAMICS_SIMS])
def test_dynamics(dw, frame, quick, testcase, tag):
    """Noise gate + compressor (v2 step D5a) bit-exact to its model + behaviour checks (7 simulations)."""
    run("dynamics", "test_dynamics", [RTL / "fx_pkg.vhd", RTL / "dynamics.vhd"],
        testcase=testcase, parameters={"DW": dw},
        extra_env={"GME_DW": str(dw), "GME_FRAME": str(frame), "GME_QUICK": str(quick)}, tag=tag)


EQ3_TESTS = ["test_bitexact", "test_response", "test_flat", "test_lowlevel", "test_saturation"]


@pytest.mark.parametrize("dw", [16, 24])
@pytest.mark.parametrize("testcase", EQ3_TESTS)
def test_eq3(dw, testcase):
    """3-band EQ (v2 step D5b) bit-exact to its model + response checks, 16 and 24 bit,
    one simulation per testcase (the block has no reset)."""
    run("eq3", "test_eq3", [RTL / "fx_pkg.vhd", RTL / "biquad.vhd", RTL / "eq3.vhd"],
        testcase=testcase, parameters={"DW": dw}, extra_env={"GME_DW": str(dw)},
        tag="_eq%d_%s" % (dw, testcase))


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
    run("gme_core", "test_system", SYS_RTL, testcase=os.environ.get("TESTCASE"),
        parameters={"INIT_WAIT_CLKS": 2000})


def test_system_dyneq():
    """gme_core with a 16-tap cabinet (the cabinet is off): dynamics and EQ over the Avalon registers on real
    1024-clock frames (test_system.test_dynamics_eq)."""
    run("gme_core", "test_system", SYS_RTL, testcase="test_dynamics_eq",
        parameters={"INIT_WAIT_CLKS": 2000, **CAB16}, extra_env={"GME_SYS_DYNEQ": "1"}, tag="_dyneq")


def test_system_level():
    """gme_core with a 16-tap cabinet (the cabinet is off): OD_LEVEL over the Avalon registers on real
    1024-clock frames, exact gains and glide (test_system.test_level_via_hps, 4700 frames)."""
    run("gme_core", "test_system", SYS_RTL, testcase="test_level_via_hps",
        parameters={"INIT_WAIT_CLKS": 2000, **CAB16}, extra_env={"GME_SYS_LEVEL": "1"}, tag="_level")


def test_refv2():
    """24-bit chain bit-exact to the v2 references (GME_REF_MODE=record to re-record; with GME_REF_ONLY=a,b only those presets),
    plus overdrive / distortion bit-exact to golden.py with full 24-bit input."""
    run("fx_chain", "test_refv2", IP_MODELS + FX_RTL, parameters={"DW": 24},
        extra_env={"GME_DW": "24", "GME_REF_MODE": os.environ.get("GME_REF_MODE", "check"),
                   "GME_REF_ONLY": os.environ.get("GME_REF_ONLY", "")},
        tag="_refv2")


WAV_PRESETS = ["dry", "overdrive", "dist_medium", "tremolo", "tremolo_saw", "chorus", "flanger", "vibrato",
               "echo", "reverb"]


@pytest.mark.parametrize("preset", WAV_PRESETS)
def test_wav(preset):
    """Real guitar audio through one preset on the 24-bit chain (GME_WAV_SECONDS, default 1 s)."""
    run("fx_chain", "test_wav", IP_MODELS + FX_RTL, parameters={"DW": 24},
        extra_env={"GME_DW": "24", "GME_WAV_PRESET": preset}, tag="_wav24_" + preset)
