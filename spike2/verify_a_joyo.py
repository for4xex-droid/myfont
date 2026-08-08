"""A. 常用漢字リストの実在確認（PLAN §3.2）。"""

from __future__ import annotations

import json
from pathlib import Path

from kanji_lists import JOYO, KYOIKU

OUT = Path(__file__).resolve().parent / "output"
OUT.mkdir(parents=True, exist_ok=True)


def main() -> None:
    joyo = sorted(JOYO, key=lambda c: ord(c))
    kyoiku = sorted(KYOIKU, key=lambda c: ord(c))
    assert len(joyo) == len(set(joyo))
    assert len(kyoiku) == len(set(kyoiku))

    joyo_path = OUT / "glyphset_joyo2136.txt"
    kyoiku_path = OUT / "glyphset_kyoiku1026.txt"
    joyo_path.write_text("".join(joyo) + "\n", encoding="utf-8")
    kyoiku_path.write_text("".join(kyoiku) + "\n", encoding="utf-8")

    # uniXXXX 形式の一覧も併記
    uni_path = OUT / "glyphset_joyo2136_uninames.txt"
    uni_path.write_text(
        "\n".join(f"uni{ord(c):04X}" for c in joyo) + "\n", encoding="utf-8"
    )

    report = {
        "source": "PyPI kanji-lists (MIT)",
        "JOYO_count": len(joyo),
        "JOYO_expected": 2136,
        "JOYO_ok": len(joyo) == 2136,
        "KYOIKU_count": len(kyoiku),
        "KYOIKU_expected": 1026,
        "KYOIKU_ok": len(kyoiku) == 1026,
        "KYOIKU_subset_of_JOYO": set(kyoiku).issubset(set(joyo)),
        "outputs": [str(joyo_path), str(kyoiku_path), str(uni_path)],
        "sample_head": "".join(joyo[:20]),
        "sample_tail": "".join(joyo[-20:]),
        "verdict": "前提成立" if len(joyo) == 2136 and len(kyoiku) == 1026 else "不成立",
    }
    (OUT / "verify_a_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
