"""
paths.py -- one place for every file location in the project.

Participant-level data never lives in the repository. By default it is read
from ./data (git-ignored); point SYEP_DATA_DIR somewhere else to keep it
outside the repo entirely:

    export SYEP_DATA_DIR=/secure/location/SYEP/data

Aggregate outputs that are safe to publish go to ./results and ./figures.
Anything row-level (fitted values, residuals, analysis frames) goes under
DATA so it can never be committed by accident.
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# --- private, participant-level (git-ignored) ---------------------------
DATA = Path(os.environ.get("SYEP_DATA_DIR", ROOT / "data")).expanduser()
RAW = DATA / "raw"              # agency extracts, untouched
PROCESSED = DATA / "processed"  # merged / pruned application frames
TO_USE = DATA / "to_use"        # analysis-ready frames
PRIVATE_MODELS = TO_USE / "models"  # row-level model outputs (residuals)

# --- public, aggregate only ---------------------------------------------
RESULTS = ROOT / "results"
MODEL_RESULTS = RESULTS / "models"
DESC_RESULTS = RESULTS / "descriptives"

FIGURES = ROOT / "figures"
MODEL_FIGURES = FIGURES / "models"
DESC_FIGURES = FIGURES / "descriptives"
EXPLORATION_FIGURES = FIGURES / "exploration"
