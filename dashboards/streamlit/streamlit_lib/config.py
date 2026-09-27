"""Configuration for the public Streamlit dashboard. Nothing here is a secret — the
app reads only from the committed public CSV extracts (dashboards/streamlit/data/public/),
never from PostgreSQL, so there is no database credential to protect at runtime.

GITHUB_REPO_URL / CASE_STUDY_URL are deliberately environment-driven, not hardcoded:
no GitHub remote is configured for this repository yet, so no real URL exists to link
to. Set these via Streamlit Cloud's "Secrets"/environment settings once the repo is
pushed; until then, the UI shows a clearly-labelled placeholder rather than a
fabricated link.
"""

from __future__ import annotations

import os
from pathlib import Path

# dashboards/streamlit/streamlit_lib/config.py -> dashboards/streamlit/
APP_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_DATA_DIR = APP_ROOT / "data" / "public"


def get_data_dir() -> Path:
    """Resolved fresh on every call (not a module-level constant) so tests can point
    this at a temporary fixture directory via STREAMLIT_PUBLIC_DATA_DIR without
    fighting Python's module-import caching."""
    override = os.environ.get("STREAMLIT_PUBLIC_DATA_DIR")
    return Path(override) if override else _DEFAULT_DATA_DIR

GITHUB_REPO_URL = os.environ.get("GITHUB_REPO_URL", "")
CASE_STUDY_URL = os.environ.get("CASE_STUDY_URL", "")

DATASET_NAME = "UCI Online Retail dataset"
DATASET_SOURCE_URL = "https://archive.ics.uci.edu/dataset/352/online+retail"
DATASET_LICENCE = "CC BY 4.0 (verified against the UCI dataset page)"

# Populated at runtime from dataset_metadata.csv (see data_loader.py); these fallbacks
# only matter if that file is ever missing, and are clearly logged as such.
FALLBACK_DATE_RANGE = ("2010-12-01", "2011-12-09")

CURRENCY_FORMAT = "£{:,.2f}"
PERCENT_FORMAT = "{:.2f}%"

# Consistent categorical colour mapping for transaction_status wherever it appears.
STATUS_COLOURS = {
    "valid_sale": "#2E7D32",       # accent green
    "cancellation": "#F9A825",     # amber/warning
    "potential_return": "#5C6BC0",  # neutral indigo - NOT red; not a confirmed loss
    "non_standard": "#9E9E9E",     # grey
}

PAGE_ICON = "🛍️"
APP_TITLE = "UK E-commerce Sales & Customer Intelligence"
