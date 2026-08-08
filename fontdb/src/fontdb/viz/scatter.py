"""散布図出力（PLAN T6）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from fontdb.paths import DEFAULT_PROFILE_ID, SCATTERS_DIR

SHORT_LABEL = {
    "source_han_serif_jp": "SourceHanSerifJP",
    "ipaex_mincho": "IPAexMincho",
    "shippori_mincho": "ShipporiMincho",
    "zen_old_mincho": "ZenOldMincho",
    "biz_ud_mincho": "BIZ UDMincho",
}


def plot_contrast_uroko(probe_summary: list[dict[str, Any]], out: Path | None = None) -> Path:
    SCATTERS_DIR.mkdir(parents=True, exist_ok=True)
    out = out or (SCATTERS_DIR / "scatter_contrast_uroko.png")

    fig, ax = plt.subplots(figsize=(8.5, 6.5))
    xs, ys = [], []
    for r in probe_summary:
        c, u = r.get("contrast"), r.get("uroko_rel")
        if c is None or u is None:
            continue
        label = SHORT_LABEL.get(r["family_id"], r["family_id"])
        xs.append(c)
        ys.append(u)
        ax.scatter(c, u, s=80, zorder=3)
        ax.annotate(label, (c, u), textcoords="offset points", xytext=(6, 6), fontsize=9)

    ax.set_xlabel("contrast (vert / horiz) — juu_contrast")
    ax.set_ylabel("uroko relative size — san_uroko")
    ax.set_title(f"fontdb: contrast × uroko  (profile={DEFAULT_PROFILE_ID})")
    ax.grid(True, alpha=0.3)
    ax.axhline(0, color="#888", lw=0.5)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return out
