"""選好ログ。美の点数ではなく keep/discard/shift の方針記録。"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load():
    path = ROOT / "scripts" / "log_preference.py"
    spec = importlib.util.spec_from_file_location("log_preference", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_record_is_not_a_score():
    mod = _load()
    rec = mod.make_record(
        glyph="つ",
        axis="futokoro",
        left=0.06,
        right=0.10,
        choice="keep_right",
        note="ふところを少し開く",
    )
    assert rec["schema"] == "mymincho.preference.v1"
    assert rec["choice"] == "keep_right"
    assert rec["not_fitness"] is True
    assert "score" not in rec
    assert "fitness" not in rec


def test_shift_requires_target():
    mod = _load()
    try:
        mod.make_record(
            glyph="あ",
            axis="gravity",
            left=0.9,
            right=1.0,
            choice="shift",
        )
    except ValueError as e:
        assert "shift_to" in str(e)
    else:
        raise AssertionError("expected refuse")


def test_rejects_score_kw():
    mod = _load()
    try:
        mod.make_record(
            glyph="あ",
            axis="tension",
            left=1.0,
            right=1.1,
            choice="discard",
            score=0.8,
        )
    except TypeError:
        pass
    except ValueError as e:
        assert "score" in str(e).lower() or "fitness" in str(e).lower()
    else:
        raise AssertionError("expected refuse")


def test_unknown_choice_refused():
    mod = _load()
    try:
        mod.make_record(
            glyph="あ",
            axis="balance",
            left=1.0,
            right=1.1,
            choice="pretty",
        )
    except ValueError as e:
        assert "choice" in str(e)
    else:
        raise AssertionError("expected refuse")


def test_append_and_load_is_not_fitness(tmp_path: Path):
    mod = _load()
    path = tmp_path / "log.jsonl"
    a = mod.make_record(
        glyph="つ",
        axis="futokoro",
        left=0.06,
        right=0.10,
        choice="keep_right",
    )
    b = mod.make_record(
        glyph="つ",
        axis="futokoro",
        left=0.10,
        right=0.14,
        choice="discard",
        note="開きすぎ",
    )
    mod.append_jsonl(path, a)
    mod.append_jsonl(path, b)
    rows = mod.load_log(path)
    assert len(rows) == 2
    assert rows[0]["choice"] == "keep_right"
    assert rows[1]["choice"] == "discard"
    policy = mod.policy_summary(rows)
    assert policy["n"] == 2
    assert "mean_score" not in policy
    assert policy["counts"]["keep_right"] == 1
    assert policy["counts"]["discard"] == 1


def test_cli_appends(tmp_path: Path):
    mod = _load()
    dest = tmp_path / "log.jsonl"
    rc = mod.main(
        [
            "--glyph",
            "つ",
            "--axis",
            "futokoro",
            "--left",
            "0.06",
            "--right",
            "0.10",
            "--choice",
            "keep_left",
            "--out",
            str(dest),
        ]
    )
    assert rc == 0
    rec = json.loads(dest.read_text(encoding="utf-8").splitlines()[0])
    assert rec["choice"] == "keep_left"
    assert rec["not_fitness"] is True
