"""M8-T139: when stage_routing.enabled is false, skip deep validation.

A user who disables stage routing should not be blocked by invalid tiers/stage_map
config that they're not using. The resolver should accept enabled=false with any
other field content (or missing fields), since the router won't use them anyway.

This replaces a measured failure mode: a user sets enabled=false to turn off
routing, but their old/typo'd tiers config still throws ConfigError at startup.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from minicc.config import ConfigError, load_config


def _write_config(tmp_path: Path, stage_routing: dict) -> Path:
    """Write a minimal config.json with the given stage_routing object."""
    cfg = tmp_path / ".minicc" / "config.json"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(json.dumps({
        "model": "gpt-4o-mini",
        "api_key": "sk-test123",
        "stage_routing": stage_routing,
    }))
    return tmp_path


class TestStageRoutingDisabledSkipsValidation:
    def test_enabled_false_with_invalid_tiers_still_loads(self, tmp_path):
        """When enabled=false, invalid tiers should not block config loading."""
        cfg_dir = _write_config(tmp_path, {
            "enabled": False,
            "tiers": {
                # Invalid: models should be list of strings, not a single string
                "fast": "not-a-list",
            },
        })
        # Should NOT raise ConfigError
        config = load_config(workspace=str(cfg_dir))
        assert config.stage_routing is not None
        assert config.stage_routing.get("enabled") is False

    def test_enabled_false_with_missing_tiers_loads(self, tmp_path):
        """When enabled=false, missing tiers should be fine."""
        cfg_dir = _write_config(tmp_path, {
            "enabled": False,
            # No tiers key at all
        })
        config = load_config(workspace=str(cfg_dir))
        assert config.stage_routing is not None
        assert config.stage_routing.get("enabled") is False

    def test_enabled_false_with_invalid_stage_map_loads(self, tmp_path):
        """When enabled=false, invalid stage_map should not block loading."""
        cfg_dir = _write_config(tmp_path, {
            "enabled": False,
            "stage_map": {
                # Invalid: unknown stage name
                "unknown_stage": "fast",
            },
        })
        config = load_config(workspace=str(cfg_dir))
        assert config.stage_routing is not None
        assert config.stage_routing.get("enabled") is False

    def test_enabled_true_with_invalid_tiers_still_raises(self, tmp_path):
        """When enabled=true, invalid tiers must still raise ConfigError."""
        cfg_dir = _write_config(tmp_path, {
            "enabled": True,
            "tiers": {
                "fast": "not-a-list",  # Invalid
            },
        })
        with pytest.raises(ConfigError):
            load_config(workspace=str(cfg_dir))

    def test_enabled_true_with_valid_config_loads(self, tmp_path):
        """When enabled=true with valid config, everything should work."""
        cfg_dir = _write_config(tmp_path, {
            "enabled": True,
            "tiers": {
                "fast": ["gpt-4o-mini"],
                "balanced": ["gpt-4o"],
            },
            "stage_map": {
                "inspect": "fast",
                "implement": "balanced",
            },
        })
        config = load_config(workspace=str(cfg_dir))
        assert config.stage_routing is not None
        assert config.stage_routing.get("enabled") is True
        assert "fast" in config.stage_routing.get("tiers", {})
