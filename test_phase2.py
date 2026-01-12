"""Tests for Phase 2 adapters."""
import asyncio
from multirig.hamlib.caps import parse_dump_caps
from multirig.adapters.rigctld import RigctldAdapter
from multirig.adapters.managed import ManagedRigAdapter
from multirig.zenoh.session import init_session, close_session


async def test_caps_parsing():
    """Test capabilities parsing."""
    # Sample dump_caps output
    dump_caps_output = """
Model name:         IC-7300
Mfg name:           Icom
Backend version:    0.6
Backend copyright:  LGPL
Backend status:     Stable

Can set Frequency:              Y
Can get Frequency:              Y
Can set Mode:                   Y
Can get Mode:                   Y
Can set VFO:                    Y
Can get VFO:                    Y
Can set PTT:                    Y
Can get PTT:                    Y

Mode list: USB LSB CW CWR RTTY RTTYR AM FM
"""
    
    caps, modes = parse_dump_caps(dump_caps_output)
    
    # Check capabilities
    assert caps["freq_set"] == True
    assert caps["freq_get"] == True
    assert caps["mode_set"] == True
    assert caps["mode_get"] == True
    assert caps["vfo_set"] == True
    assert caps["vfo_get"] == True
    assert caps["ptt_set"] == True
    assert caps["ptt_get"] == True
    
    # Check modes
    assert "USB" in modes
    assert "LSB" in modes
    assert "CW" in modes
    assert "AM" in modes
    assert "FM" in modes
    
    print("✓ Capabilities parsing works")


async def test_adapter_instantiation():
    """Test that adapters can be instantiated."""
    # Initialize Zenoh session
    await init_session()
    
    # Test RigctldAdapter instantiation
    adapter1 = RigctldAdapter(
        rig_id="test_rig1",
        host="localhost",
        port=4532
    )
    assert adapter1.rig_id == "test_rig1"
    assert adapter1.host == "localhost"
    assert adapter1.port == 4532
    print("✓ RigctldAdapter instantiation works")
    
    # Test ManagedRigAdapter instantiation
    adapter2 = ManagedRigAdapter(
        rig_id="test_rig2",
        model_id=370,  # IC-7300
        device="/dev/ttyUSB0"
    )
    assert adapter2.rig_id == "test_rig2"
    assert adapter2.model_id == 370
    assert adapter2.device == "/dev/ttyUSB0"
    print("✓ ManagedRigAdapter instantiation works")
    
    # Test safety configuration
    adapter1.set_safety_config(
        allow_out_of_band=False,
        band_limits={
            "20m": {"min": 14000000, "max": 14350000},
            "40m": {"min": 7000000, "max": 7300000}
        }
    )
    assert adapter1._allow_out_of_band == False
    assert adapter1._band_limits is not None
    print("✓ Safety configuration works")
    
    await close_session()


async def test_command_safety():
    """Test that safety checks work."""
    await init_session()
    
    adapter = RigctldAdapter(
        rig_id="test_rig",
        host="localhost",
        port=4532
    )
    
    # Configure band limits
    adapter.set_safety_config(
        allow_out_of_band=False,
        band_limits={
            "20m": {"min": 14000000, "max": 14350000}
        }
    )
    
    # Test frequency within band
    from multirig.messages import RigCommand
    cmd_in_band = RigCommand.set_frequency(14074000)
    assert adapter._check_safety(cmd_in_band) == True
    
    # Test frequency outside band
    cmd_out_of_band = RigCommand.set_frequency(7074000)
    assert adapter._check_safety(cmd_out_of_band) == False
    
    # Test with allow_out_of_band=True
    adapter.set_safety_config(allow_out_of_band=True)
    assert adapter._check_safety(cmd_out_of_band) == True
    
    print("✓ Command safety checks work")
    
    await close_session()


async def main():
    await test_caps_parsing()
    await test_adapter_instantiation()
    await test_command_safety()
    print("\n✓ All Phase 2 tests passed!")


if __name__ == '__main__':
    asyncio.run(main())
