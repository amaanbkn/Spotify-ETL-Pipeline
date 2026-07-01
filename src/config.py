"""
src/config.py
Centralized configuration: paths and connection strings.
Every other module imports from here instead of hardcoding paths/env vars.
"""

import os
from pathlib import Path

# ---------------------------------------------------------
# Project paths
# ---------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent  # src/ -> project root

DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"

RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)

RAW_CSV_PATH = RAW_DATA_DIR / "spotify_tracks.csv"
PROCESSED_TRACKS_PATH = PROCESSED_DATA_DIR / "clean_tracks.parquet"
PROCESSED_ARTISTS_PATH = PROCESSED_DATA_DIR / "clean_artists.parquet"

# ---------------------------------------------------------
# Database
# ---------------------------------------------------------
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/spotify_db"
)

# ---------------------------------------------------------
# Misc
# ---------------------------------------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")