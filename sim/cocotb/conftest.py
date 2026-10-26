"""
conftest.py - start the slowest suites first, so that parallel runs
(pytest -n auto, see sim/run_all.sh) finish as early as possible.
"""
SLOW_FIRST = ["test_cabfir_full", "test_refv2", "test_wav", "test_system", "test_fx_chain_24",
              "test_fx_chain", "test_reverbfv", "test_cabfir", "test_codec", "test_xfade", "test_trem", "test_moddelay"]


def pytest_collection_modifyitems(items):
    rank = {name: i for i, name in enumerate(SLOW_FIRST)}
    items.sort(key=lambda it: rank.get(it.originalname or it.name, len(SLOW_FIRST)))
