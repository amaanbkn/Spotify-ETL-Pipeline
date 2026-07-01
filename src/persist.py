"""
persist.py
Checkpoints cleaned DataFrames to data/processed/ as Parquet.
Called after transform, before load — so load can resume from disk
without re-running extract+transform if it fails.
"""

import logging

import pandas as pd

from config import PROCESSED_ARTISTS_PATH, PROCESSED_TRACKS_PATH

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)


def save_processed(tracks_df: pd.DataFrame, artists_df: pd.DataFrame) -> None:
    """Write cleaned data to data/processed/ (Parquet — compact, typed, fast to reload)."""
    tracks_df.to_parquet(PROCESSED_TRACKS_PATH, index=False)
    artists_df.to_parquet(PROCESSED_ARTISTS_PATH, index=False)
    logger.info(
        f"Saved {len(tracks_df):,} tracks -> {PROCESSED_TRACKS_PATH}, "
        f"{len(artists_df):,} artist rows -> {PROCESSED_ARTISTS_PATH}"
    )


def load_processed() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read back the checkpointed clean data (e.g. to resume a failed load, or for notebooks)."""
    if not PROCESSED_TRACKS_PATH.exists():
        raise FileNotFoundError(
            f"No processed data found at {PROCESSED_TRACKS_PATH}. Run transform first."
        )
    tracks_df = pd.read_parquet(PROCESSED_TRACKS_PATH)
    artists_df = pd.read_parquet(PROCESSED_ARTISTS_PATH)
    logger.info(f"Loaded {len(tracks_df):,} tracks, {len(artists_df):,} artist rows from disk")
    return tracks_df, artists_df