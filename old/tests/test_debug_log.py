from multirig.debug_log import DebugStore


def test_debug_store_resize_and_bounds():
    store = DebugStore(1, rig_maxlen=2, server_maxlen=3)
    assert store.rig(0) is not None
    assert store.rig(-1) is None
    assert store.rig(99) is None

    store.ensure_rigs(3, rig_maxlen=2)
    assert store.rig(2) is not None

    store.ensure_rigs(1, rig_maxlen=2)
    assert store.rig(1) is None

    store.ensure_rigs(-5, rig_maxlen=2)
    assert store.rig(0) is None
