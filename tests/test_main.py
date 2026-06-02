"""app.main の dispatch table を検証する。"""

from __future__ import annotations

import pytest

from app import main


def test_commands_cover_4() -> None:
    assert set(main.COMMANDS) == {"seed-csv", "load-bq", "register-fs", "batch-read-offline"}


def test_dispatch_calls_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[str] = []
    monkeypatch.setitem(main.COMMANDS, "seed-csv", lambda: called.append("seed-csv"))
    assert main.main(["prog", "seed-csv"]) == 0
    assert called == ["seed-csv"]


def test_no_args_returns_2(capsys: pytest.CaptureFixture[str]) -> None:
    assert main.main(["prog"]) == 2
    assert "usage" in capsys.readouterr().err


def test_unknown_command_returns_2(capsys: pytest.CaptureFixture[str]) -> None:
    assert main.main(["prog", "bogus"]) == 2
    assert "unknown command" in capsys.readouterr().err
