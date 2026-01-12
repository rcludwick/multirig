from unittest.mock import Mock


def test_main_calls_run(monkeypatch):
    import multirig.__main__ as mainmod

    m = Mock()
    monkeypatch.setattr(mainmod, "run", m)

    mainmod.main()
    m.assert_called_once_with()
