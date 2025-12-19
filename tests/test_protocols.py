import pytest

from multirig.protocols import HamlibParser


def test_hamlib_parser_decode_bytes_and_unicode_error():
    assert HamlibParser.decode(b"F 14074000\n") == "SET FREQ: 14074000"
    assert HamlibParser.decode(b"\xff\xfe") == "<BINARY: 2 bytes>"


def test_hamlib_parser_decode_empty_and_fallbacks():
    assert HamlibParser.decode("\n\t") == "<EMPTY>"
    assert HamlibParser.decode("f") == "GET FREQ"
    assert HamlibParser.decode("14074000") == "DATA: 14074000 Hz"
    assert HamlibParser.decode("bogus stuff") == "RAW: bogus stuff"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("M USB 2400", "SET MODE: USB 2400"),
        ("l KEYSPD", "GET LEVEL: KEYSPD"),
        ("\\dump_state", "DUMP STATE"),
        ("RPRT 0", "SUCCESS"),
        ("RPRT -3", "ERROR: 3"),
    ],
)
def test_hamlib_parser_decode_patterns(raw, expected):
    assert HamlibParser.decode(raw) == expected
