import os
import pytest
import yaml
from multirig.config import load_config, save_config, AppConfig

def test_config_test_mode(tmp_path):
    config_file = tmp_path / "test_config.yaml"
    
    # 1. Create initial config
    initial_data = {"poll_interval_ms": 1000}
    config_file.write_text(yaml.dump(initial_data))
    
    # 2. Load with test mode ENABLED
    os.environ["MULTIRIG_TEST_MODE"] = "1"
    try:
        cfg = load_config(config_file)
        assert cfg.test_mode is True
        
        # 3. Modify and Save
        cfg.poll_interval_ms = 500
        save_config(cfg, config_file)
        
        # 4. Check file on disk - SHOULD BE UNCHANGED
        content = yaml.safe_load(config_file.read_text())
        assert content["poll_interval_ms"] == 1000, "File should not change in test mode"
        
        # 5. Check object state
        assert cfg.poll_interval_ms == 500, "Object should hold new value"
        
    finally:
        del os.environ["MULTIRIG_TEST_MODE"]

def test_config_normal_mode(tmp_path):
    config_file = tmp_path / "normal_config.yaml"
    initial_data = {"poll_interval_ms": 1000}
    config_file.write_text(yaml.dump(initial_data))
    
    # Ensure env var is unset
    if "MULTIRIG_TEST_MODE" in os.environ:
        del os.environ["MULTIRIG_TEST_MODE"]
        
    cfg = load_config(config_file)
    assert cfg.test_mode is False
    
    cfg.poll_interval_ms = 500
    save_config(cfg, config_file)
    
    content = yaml.safe_load(config_file.read_text())
    assert content["poll_interval_ms"] == 500, "File SHOULD change in normal mode"
