import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from multirig.rig import RigClient, RigStatus, parse_dump_caps


def test_parse_dump_caps_extracts_caps_and_modes():
    text = "\n".join(
        [
            "dump_caps:",
            "Mode list: USB LSB, CW AM FM.",
            "Can get Frequency: Y",
            "Can set Frequency: N",
            "Can get Mode: E",
            "Can set Mode: N",
            "Can get VFO: N",
            "Can set VFO: Y",
            "Can get PTT: N",
            "Can set PTT: Y",
        ]
    )

    caps, modes = parse_dump_caps(text)
    assert caps == {
        "freq_get": True,
        "freq_set": False,
        "mode_get": True,
        "mode_set": False,
        "vfo_get": False,
        "vfo_set": True,
        "ptt_get": False,
        "ptt_set": True,
    }
    assert modes == ["USB", "LSB", "CW", "AM", "FM"]


@pytest.mark.asyncio
async def test_rigclient_refresh_caps_sets_cache_and_is_json_safe():
    cfg = MagicMock()
    cfg.name = "TestRig"
    cfg.enabled = True
    cfg.connection_type = "rigctld"
    cfg.follow_main = True
    cfg.model_id = 2
    cfg.band_presets = []
    cfg.allow_out_of_band = False
    cfg.host = "127.0.0.1"
    cfg.port = 4532

    backend = AsyncMock()
    backend.dump_caps.return_value = [
        "dump_caps:",
        "Mode list: USB CW",
        "Can get Frequency: Y",
        "Can set Frequency: Y",
        "Can get Mode: Y",
        "Can set Mode: Y",
        "Can get VFO: N",
        "Can set VFO: N",
        "Can get PTT: N",
        "Can set PTT: Y",
    ]
    backend.status.return_value = RigStatus(connected=True, frequency_hz=14074000, mode="USB", passband=2400)

    with patch("multirig.rig.RigClient._make_backend", return_value=backend):
        rig = RigClient(cfg)

    result = await rig.refresh_caps()

    assert result["caps"]["freq_get"] is True
    assert result["caps"]["ptt_set"] is True
    assert result["modes"] == ["USB", "CW"]
    assert isinstance(result["raw"], list)

    st = await rig.safe_status()
    assert st["caps"] == result["caps"]
    assert st["modes"] == result["modes"]
