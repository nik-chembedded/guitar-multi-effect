"""
conftest.py - start the slowest suites first, so that parallel runs
(pytest -n auto, see sim/run_all.sh) finish as early as possible.
"""
SLOW_FIRST = ["test_system_level", "test_refv2", "test_system_dyneq", "test_cabfir_full", "test_refv2_golden24", "test_system",
              "test_timing_invariance", "test_fx_chain", "test_wav", "test_trem",
              "test_dynamics", "test_eq3", "test_reverbfv", "test_dyn_eq_xfade", "test_cab_xfade",
              "test_route_invariance", "test_cabfir", "test_codec", "test_xfade", "test_moddelay"]


def pytest_collection_modifyitems(items):
    rank = {name: i for i, name in enumerate(SLOW_FIRST)}
    items.sort(key=lambda it: rank.get(it.originalname or it.name, len(SLOW_FIRST)))
