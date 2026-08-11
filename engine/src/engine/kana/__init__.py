"""仮名パラメトリック生成（P1-B）。"""

from engine.kana.gate import GateReport, run_gate, run_gate_on, run_gate_path
from engine.kana.load import (
    KANA_GLYPH_META,
    get_gate,
    get_joins,
    kana_characters,
    kana_labels,
    load_kana_skeleton,
    skeletons_dir,
)
from engine.kana.schema import GateSpec, JoinSpec

__all__ = [
    "GateReport",
    "GateSpec",
    "JoinSpec",
    "KANA_GLYPH_META",
    "get_gate",
    "get_joins",
    "kana_characters",
    "kana_labels",
    "load_kana_skeleton",
    "run_gate",
    "run_gate_on",
    "run_gate_path",
    "skeletons_dir",
]
