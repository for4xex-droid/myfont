"""scripts/load_dotenv.py の安全パース。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from load_dotenv import parse_dotenv_text, load_repo_dotenv, redact_secrets  # noqa: E402


def test_parse_allows_only_known_keys():
    text = """
# comment
export GEMINI_API_KEY="abc123"
PATH=/evil
OTHER=1
GEMINI_API_KEY='ignored_second_in_file_overwrites_in_dict'
"""
    # 同一キーは後勝ち（ファイル内）
    got = parse_dotenv_text(text)
    assert got == {"GEMINI_API_KEY": "ignored_second_in_file_overwrites_in_dict"}


def test_load_does_not_override_existing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GEMINI_API_KEY", "from_shell")
    (tmp_path / ".env").write_text("GEMINI_API_KEY=from_file\n", encoding="utf-8")
    loaded = load_repo_dotenv(tmp_path)
    assert os.environ["GEMINI_API_KEY"] == "from_shell"
    assert loaded == []  # 上書きしないので新規セットなし


def test_load_sets_when_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    (tmp_path / ".env").write_text("GEMINI_API_KEY=from_file\n", encoding="utf-8")
    loaded = load_repo_dotenv(tmp_path)
    assert loaded == ["GEMINI_API_KEY"]
    assert os.environ["GEMINI_API_KEY"] == "from_file"
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)


def test_redact():
    assert redact_secrets("key=secret123 ok", "secret123") == "key=*** ok"
