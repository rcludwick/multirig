import asyncio
from types import SimpleNamespace

import pytest

from multirig.service import SyncService


class DummyRig:
    def __init__(self, *, name="r", enabled=True, follow_main=True, connected=True, freq=14074000, mode="USB", pb=2400):
        self.cfg = SimpleNamespace(name=name, enabled=enabled, follow_main=follow_main)
        self._status = SimpleNamespace(
            connected=connected,
            frequency_hz=freq,
            mode=mode,
            passband=pb,
        )
        self._last_error = None
        self.set_frequency_calls = []
        self.set_mode_calls = []
        self.set_frequency_result = True
        self.set_mode_result = True

    async def status(self):
        return self._status

    async def set_frequency(self, hz: int) -> bool:
        self.set_frequency_calls.append(int(hz))
        return bool(self.set_frequency_result)

    async def set_mode(self, mode: str, passband=None) -> bool:
        self.set_mode_calls.append((mode, passband))
        return bool(self.set_mode_result)


@pytest.mark.asyncio
async def test_sync_service_skips_when_disabled():
    src = DummyRig(name="src")
    dst = DummyRig(name="dst")
    svc = SyncService([src, dst], interval_ms=1, enabled=False, source_index=0)

    await svc.start()
    await asyncio.sleep(0.12)
    await svc.stop()

    assert dst.set_frequency_calls == []
    assert dst.set_mode_calls == []


@pytest.mark.asyncio
async def test_sync_service_updates_followers_and_debounces():
    src = DummyRig(name="src", freq=14074000, mode="USB", pb=2400)
    follower = DummyRig(name="f1", follow_main=True)
    manual = DummyRig(name="m1", follow_main=False)
    svc = SyncService([src, follower, manual], interval_ms=1, enabled=True, source_index=0)

    await svc.start()
    await asyncio.sleep(0.12)

    # One update should have happened.
    assert follower.set_frequency_calls
    assert follower.set_mode_calls
    assert manual.set_frequency_calls == []
    assert manual.set_mode_calls == []

    calls_before = (len(follower.set_frequency_calls), len(follower.set_mode_calls))

    # No change -> should debounce and not keep spamming.
    await asyncio.sleep(0.12)
    assert (len(follower.set_frequency_calls), len(follower.set_mode_calls)) == calls_before

    # Change source -> should trigger another update.
    src._status.frequency_hz = 7074000
    src._status.mode = "LSB"
    src._status.passband = 1800

    await asyncio.sleep(0.12)
    assert len(follower.set_frequency_calls) > calls_before[0]
    assert len(follower.set_mode_calls) > calls_before[1]

    await svc.stop()


@pytest.mark.asyncio
async def test_sync_service_selects_first_enabled_source_if_source_disabled():
    disabled_src = DummyRig(name="disabled", enabled=False)
    real_src = DummyRig(name="real")
    follower = DummyRig(name="f1")

    svc = SyncService([disabled_src, real_src, follower], interval_ms=1, enabled=True, source_index=0)

    await svc.start()
    await asyncio.sleep(0.12)
    await svc.stop()

    assert follower.set_frequency_calls


@pytest.mark.asyncio
async def test_sync_service_sets_last_error_on_failures():
    src = DummyRig(name="src")
    follower = DummyRig(name="f1")
    follower.set_frequency_result = False
    follower.set_mode_result = False

    svc = SyncService([src, follower], interval_ms=1, enabled=True, source_index=0)

    await svc.start()
    await asyncio.sleep(0.12)
    await svc.stop()

    assert follower._last_error is not None
