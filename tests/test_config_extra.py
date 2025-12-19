import os

import pytest

from multirig.config import (
    BandPreset,
    _band_limits,
    detect_bands_from_ranges,
    parse_dump_state_ranges,
    load_config,
)


def test_band_preset_fills_limits_for_known_band():
    bp = BandPreset(label="20m", frequency_hz=14074000, lower_hz=None, upper_hz=None)
    assert bp.lower_hz is not None
    assert bp.upper_hz is not None
    assert bp.lower_hz < bp.upper_hz


def test_band_limits_unknown_returns_none():
    assert _band_limits("not-a-band") is None


def test_parse_dump_state_ranges_handles_short_and_bad_lines():
    assert parse_dump_state_ranges([]) == []
    assert parse_dump_state_ranges(["a", "b", "oops", "1 2"]) == [(1, 2)]

    # only indexes 2 and 3 are considered; invalid/negative ranges ignored
    lines = [
        "header0",
        "header1",
        "0 0 modes",
        "100 50 modes",
    ]
    assert parse_dump_state_ranges(lines) == []


def test_detect_bands_from_ranges_default_when_empty():
    presets = detect_bands_from_ranges([])
    assert presets
    assert any(p.label.lower() == "20m" for p in presets)


def test_detect_bands_from_ranges_detects_overlap():
    presets = detect_bands_from_ranges([(14000000, 14350000)])
    labels = {p.label.lower() for p in presets}
    assert "20m" in labels


def test_load_config_migrates_legacy_rig_a_rig_b(tmp_path, monkeypatch):
    cfg_path = tmp_path / "cfg.yaml"
    cfg_path.write_text(
        "\n".join(
            [
                "rig_a:",
                "  name: A",
                "rig_b:",
                "  name: B",
                "poll_interval_ms: 250",
            ]
        )
    )

    monkeypatch.setenv("MULTIRIG_TEST_MODE", "1")
    cfg = load_config(cfg_path)
    assert cfg.poll_interval_ms == 250
    assert len(cfg.rigs) == 2
    assert cfg.rigs[0].name == "A"
    assert cfg.rigs[1].name == "B"


def test_load_config_creates_default_if_missing(tmp_path, monkeypatch):
    cfg_path = tmp_path / "missing.yaml"
    monkeypatch.setenv("MULTIRIG_TEST_MODE", "1")
    cfg = load_config(cfg_path)
    assert cfg.rigs
