"""
src/extract.py
Reads the Spotify tracks CSV from data/raw/ and lands it into
staging.raw_tracks with zero transformation.
"""

import shutil
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from src.config import RAW_CSV_PATH, RAW_DATA_DIR
from src.utils import get_engine, get_logger

logger = get_logger(__name__)

RAW_COLUMNS = [
    "track_id", "artists", "album_name", "track_name", "popularity",
    "duration_ms", "explicit", "danceability", "energy", "key",
    "loudness", "mode", "speechiness", "acousticness", "instrumentalness",
    "liveness", "valence", "tempo", "time_signature", "track_genre",
]


def ingest_source_file(source_path: str) -> Path:
    """
    Copy an externally-downloaded CSV (e.g. from ~/Downloads after a
    Kaggle export) into data/raw/, so raw/ always holds the canonical copy.
    """
    source = Path(source_path)
    if not source.exists():
        raise FileNotFoundError(f"Source file not found: {source}")

    dest = RAW_DATA_DIR / source.name
    shutil.copy2(source, dest)
    logger.info(f"Copied {source} -> {dest}")
    return dest


def extract(csv_path: Path = RAW_CSV_PATH) -> pd.DataFrame:
    """Read the raw CSV from data/raw/. This file is treated as immutable."""
    if not csv_path.exists():
        raise FileNotFoundError(
            f"Could not find {csv_path}. Place the Kaggle CSV in data/raw/ "
            f"(or call ingest_source_file() to copy it there first)."
        )

    logger.info(f"Reading {csv_path}")
    df = pd.read_csv(csv_path)

    # Kaggle CSV export includes a stray "Unnamed: 0" index column
    df = df.loc[:, ~df.columns.str.contains("^Unnamed")]

    missing = set(RAW_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"CSV is missing expected columns: {missing}")

    logger.info(f"Extracted {len(df):,} rows")
    return df


def load_to_staging(df: pd.DataFrame, source_file: str, engine=None) -> int:
    """Truncate + reload staging.raw_tracks. Staging is always a full refresh."""
    engine = engine or get_engine()
    df = df.copy()
    df["source_file"] = source_file

    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE staging.raw_tracks RESTART IDENTITY"))

    df.to_sql(
        "raw_tracks", engine, schema="staging",
        if_exists="append", index=False, method="multi", chunksize=5000,
    )
    logger.info(f"Loaded {len(df):,} rows into staging.raw_tracks")
    return len(df)


if __name__ == "__main__":
    raw_df = extract()
    load_to_staging(raw_df, source_file=RAW_CSV_PATH.name)