#!/usr/bin/env python3
"""仮名レビューループ C: Gemini 観察（合否なし・任意レーン）。

キーは環境変数 `GEMINI_API_KEY`、またはリポジトリ直下の `.env`（gitignore 済み）。
無い場合は status=skipped（B の合否には影響しない）。CI では走らせない。

観察で「対象に見えない／取り違えあり」のときは exit=3（注意。B の合否ではない）。
空虚な観察（構造・取り違え無し）はスクリプト側で注意扱い。

例:
  cp .env.example .env   # 値を書き換えて chmod 600 .env
  python scripts/kana_vision_review.py --glyph tsu
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from load_dotenv import load_repo_dotenv, redact_secrets  # noqa: E402

PROMPT_PATH = ROOT / "scripts" / "prompts" / "kana_review_v2.txt"
DEFAULT_MODEL = "gemini-2.5-flash"
PLACEHOLDER_KEYS = frozenset(
    {"", "your_gemini_api_key_here", "changeme", "xxx", "TODO"}
)

# 字ごとの既知取り違え（プロンプトに必ず渡す）
CONFUSABLES: dict[str, list[str]] = {
    "し": ["つ", "へ", "じ"],
    "つ": ["し", "へ", "っ"],
    "い": ["り", "ん"],
    "と": ["ど", "て"],
}

EMPTY_NOTE_MARKERS = (
    "単一の曲線",
    "一画で構成",
    "なめらかな曲線",
    "単一の曲線で構成",
)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _resolve_api_key() -> tuple[str | None, str]:
    load_repo_dotenv(ROOT)
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        return None, "missing"
    if key in PLACEHOLDER_KEYS:
        return None, "placeholder"
    return key, "env_or_dotenv"


def _attention_reasons(observation: dict, char: str) -> list[str]:
    """合否語は使わず、エージェントが放置できない観察欠陥を列挙。"""
    reasons: list[str] = []
    if observation.get("parse_error"):
        reasons.append("observation_parse_error")
        return reasons
    reads = str(observation.get("reads_as_target", "")).lower()
    if reads in ("no", "unclear", ""):
        reasons.append(f"reads_as_target={reads or 'missing'}")
    conf = observation.get("confusable_with") or []
    if isinstance(conf, list) and conf:
        reasons.append(f"confusable_with={conf}")
    sil = str(observation.get("silhouette", ""))
    if char == "つ" and sil in ("fishhook_shi", "latin_c", "open_c_tsu", "valley_he"):
        reasons.append(f"silhouette={sil}_for_tsu")
    if char == "し" and sil in ("bowl_tsu", "open_c_tsu", "latin_c"):
        reasons.append(f"silhouette={sil}_for_shi")
    notes = observation.get("notes") or []
    if isinstance(notes, list):
        joined = " ".join(str(n) for n in notes)
        if any(m in joined for m in EMPTY_NOTE_MARKERS) and len(joined) < 40:
            reasons.append("empty_notes")
        if char and char not in joined and reads != "yes":
            # 対象字への言及が無く、かつ yes でもない
            if not conf:
                reasons.append("notes_omit_target_or_confusion")
    return reasons


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Kana vision observation (optional C)")
    ap.add_argument("--glyph", required=True)
    ap.add_argument(
        "--png",
        type=Path,
        default=None,
        help="input PNG (default: proofs/out/kana/<glyph>/single.png)",
    )
    ap.add_argument("--iter", type=int, default=1, help="iteration index for out path")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument(
        "--out-root",
        type=Path,
        default=ROOT / "proofs" / "review",
    )
    args = ap.parse_args(argv)

    png = args.png or (ROOT / "proofs" / "out" / "kana" / args.glyph / "single.png")
    out_dir = args.out_root / args.glyph
    out_dir.mkdir(parents=True, exist_ok=True)
    out_json = out_dir / f"{args.iter}.json"

    key, key_source = _resolve_api_key()
    if not key:
        reason = (
            "GEMINI_API_KEY is placeholder; set a real key in .env"
            if key_source == "placeholder"
            else "GEMINI_API_KEY not set (export or repo-root .env)"
        )
        payload = {
            "status": "skipped",
            "reason": reason,
            "glyph_id": args.glyph,
            "png": str(png) if png.is_file() else None,
            "note": "C is optional; B gate decides pass/fail. See .env.example",
        }
        out_json.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"status=skipped report={out_json}")
        return 0

    if not png.is_file():
        print(f"error: PNG not found: {png}", file=sys.stderr)
        return 2
    if not PROMPT_PATH.is_file():
        print(f"error: prompt missing: {PROMPT_PATH}", file=sys.stderr)
        return 2

    png_sha = _sha256_file(png)
    # プロンプト版をキャッシュキーに含め、v1 の空虚観察を再利用しない
    prompt_sha = _sha256_file(PROMPT_PATH)[:8]
    cache_path = out_dir / f"cache_{prompt_sha}_{png_sha[:16]}.json"
    if cache_path.is_file():
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        out_json.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        obs = payload.get("observation") or {}
        attn = _attention_reasons(obs, str(payload.get("char") or ""))
        print(f"status=cache_hit report={out_json}")
        _print_obs(obs, attn)
        return 3 if attn else 0

    import urllib.error
    import urllib.request

    char = args.glyph
    engine_src = ROOT / "engine" / "src"
    if str(engine_src) not in sys.path:
        sys.path.insert(0, str(engine_src))
    try:
        from engine.kana import KANA_GLYPH_META, kana_characters

        kana_characters()
        if args.glyph in KANA_GLYPH_META:
            char = str(KANA_GLYPH_META[args.glyph]["char"])
    except Exception:
        pass

    confusable = CONFUSABLES.get(char, CONFUSABLES.get(args.glyph, []))
    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    prompt += (
        f"\n\n対象文字: {char}\n"
        f"取り違え候補（この中から選んで confusable_with に入れる）: {confusable}\n"
        f"期待: 対象が「{char}」に読め、候補字により近く見えないこと。\n"
    )
    import base64

    b64 = base64.b64encode(png.read_bytes()).decode("ascii")
    body = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": "image/png",
                            "data": b64,
                        }
                    },
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "responseMimeType": "application/json",
        },
    }
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{args.model}:generateContent"
    )
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        print(
            f"error: Gemini HTTP {e.code}: {redact_secrets(err[:400], key)}",
            file=sys.stderr,
        )
        return 1
    except urllib.error.URLError as e:
        print(
            f"error: Gemini network: {redact_secrets(str(e), key)}",
            file=sys.stderr,
        )
        return 1

    text = ""
    try:
        text = raw["candidates"][0]["content"]["parts"][0]["text"]
        observation = json.loads(text)
    except (KeyError, IndexError, json.JSONDecodeError, TypeError):
        observation = {"raw_text": text, "parse_error": True}

    attn = _attention_reasons(observation, char)
    payload = {
        "status": "attention" if attn else "ok",
        "glyph_id": args.glyph,
        "char": char,
        "model": args.model,
        "png": str(png),
        "png_sha256": png_sha,
        "prompt": str(PROMPT_PATH.name),
        "confusable_candidates": confusable,
        "attention_reasons": attn,
        "observation": observation,
        "note": "observation only; status=attention means revise YAML before human accept",
    }
    blob = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    out_json.write_text(blob, encoding="utf-8")
    cache_path.write_text(blob, encoding="utf-8")
    print(f"status={payload['status']} report={out_json}")
    _print_obs(observation, attn)
    return 3 if attn else 0


def _print_obs(observation: dict, attn: list[str]) -> None:
    print(
        "observe: "
        f"silhouette={observation.get('silhouette')} "
        f"reads_as_target={observation.get('reads_as_target')} "
        f"confusable_with={observation.get('confusable_with')} "
        f"tip={observation.get('tip_direction')}"
    )
    for n in observation.get("notes") or []:
        print(f"  note: {n}")
    if attn:
        print(f"attention: {attn}  → YAML を直してから人間へ渡すこと", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
