"""fontdb パッケージのルートパス解決。"""

from __future__ import annotations

from pathlib import Path

# src/fontdb/paths.py → parents[2] = fontdb/
PACKAGE_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PACKAGE_ROOT / "config"
SCHEMAS_DIR = PACKAGE_ROOT / "schemas"
DATA_DIR = PACKAGE_ROOT / "data"
FONTS_DIR = DATA_DIR / "fonts"
SYNTHETIC_DIR = DATA_DIR / "synthetic"
RENDERS_DIR = DATA_DIR / "renders"
DB_DIR = DATA_DIR / "db"
DB_PATH = DB_DIR / "fontdb.sqlite"
OUTPUT_DIR = PACKAGE_ROOT / "output"
SCATTERS_DIR = OUTPUT_DIR / "scatters"

CORPUS_YAML = CONFIG_DIR / "corpus.yaml"
SYNTHETIC_FACES_YAML = CONFIG_DIR / "synthetic_faces.yaml"
RENDER_PROFILES_YAML = CONFIG_DIR / "render_profiles.yaml"
PROBE_DEFS_YAML = CONFIG_DIR / "probe_defs.yaml"
SCHEMA_SQL = SCHEMAS_DIR / "schema.sql"

EXTRACTOR_VERSION = "0.1.0"
DEFAULT_PROFILE_ID = "ft_1024_nohint_gray_v1"
