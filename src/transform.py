"""
src/transform.py
Cleans raw Spotify track data, derives analytical features, and
checkpoints the result to data/processed/ as Parquet.
"""

import pandas as pd

from src.config import PROCESSED_ARTISTS_PATH, PROCESSED_TRACKS_PATH
from src.utils import get_logger

logger = get_logger(__name__)

NUMERIC_COLS = [
    "popularity", "duration_ms", "danceability", "energy", "key",
    "loudness", "mode", "speechiness", "acousticness", "instrumentalness",
    "liveness", "valence", "tempo", "time_signature",
]

RATIO_COLS = [  # must be within [0, 1]
    "danceability", "energy", "speechiness", "acousticness",
    "instrumentalness", "liveness", "valence",
]


def _cast_types(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in NUMERIC_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["explicit"] = df["explicit"].map(
        {"True": True, "False": False, True: True, False: False}
    )
    return df


def _drop_invalid_rows(df: pd.DataFrame) -> pd.DataFrame:
    before = len(df)

    df = df.dropna(subset=["track_id", "track_name", "artists", "track_genre"])
    df = df[df["popularity"].between(0, 100, inclusive="both")]

    for col in RATIO_COLS:
        df = df[df[col].between(0, 1, inclusive="both") | df[col].isna()]

    df = df[df["duration_ms"].between(5_000, 7_200_000)]

    dropped = before - len(df)
    if dropped:
        logger.info(f"Dropped {dropped:,} invalid rows ({dropped/before:.1%})")
    return df


def _deduplicate(df: pd.DataFrame) -> pd.DataFrame:
    """
    Source data repeats each track_id once per genre it's tagged with.
    We keep (track_id, track_genre) as the natural key.
    """
    before = len(df)
    df = df.drop_duplicates(subset=["track_id", "track_genre"], keep="first")
    dropped = before - len(df)
    if dropped:
        logger.info(f"Removed {dropped:,} duplicate (track_id, genre) rows")
    return df


def _engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["duration_min"] = (df["duration_ms"] / 60_000).round(2)

    def mood_quadrant(row):
        if pd.isna(row["valence"]) or pd.isna(row["energy"]):
            return None
        if row["valence"] >= 0.5 and row["energy"] >= 0.5:
            return "energetic_positive"
        if row["valence"] >= 0.5 and row["energy"] < 0.5:
            return "calm_positive"
        if row["valence"] < 0.5 and row["energy"] >= 0.5:
            return "energetic_negative"
        return "calm_negative"

    df["mood_quadrant"] = df.apply(mood_quadrant, axis=1)

    df["track_name"] = df["track_name"].str.strip()
    df["album_name"] = df["album_name"].str.strip()
    df["artists"] = df["artists"].str.strip()
    df["track_genre"] = df["track_genre"].str.strip().str.lower()

    return df


def clean_tracks(df: pd.DataFrame) -> pd.DataFrame:
    """Main entry point: raw staging DataFrame -> clean, feature-rich DataFrame."""
    logger.info(f"Starting transform on {len(df):,} raw rows")
    df = _cast_types(df)
    df = _drop_invalid_rows(df)
    df = _deduplicate(df)
    df = _engineer_features(df)
    logger.info(f"Transform complete: {len(df):,} clean rows")
    return df


def split_artists(df: pd.DataFrame) -> pd.DataFrame:
    """Explode the semicolon-delimited artists string into one row per artist."""
    out = df[["track_id", "track_genre", "artists"]].copy()
    out["artists"] = out["artists"].str.split(";")
    out = out.explode("artists")
    out["artists"] = out["artists"].str.strip()
    out = out[out["artists"] != ""]
    return out.rename(columns={"artists": "artist_name"})


def save_processed(tracks_df: pd.DataFrame, artists_df: pd.DataFrame) -> None:
    """Checkpoint cleaned data to data/processed/ as Parquet."""
    tracks_df.to_parquet(PROCESSED_TRACKS_PATH, index=False)
    artists_df.to_parquet(PROCESSED_ARTISTS_PATH, index=False)
    logger.info(
        f"Saved {len(tracks_df):,} tracks -> {PROCESSED_TRACKS_PATH}, "
        f"{len(artists_df):,} artist rows -> {PROCESSED_ARTISTS_PATH}"
    )


def load_processed() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read back checkpointed clean data (resume a failed load, or for notebooks)."""
    if not PROCESSED_TRACKS_PATH.exists():
        raise FileNotFoundError(
            f"No processed data found at {PROCESSED_TRACKS_PATH}. Run transform first."
        )
    tracks_df = pd.read_parquet(PROCESSED_TRACKS_PATH)
    artists_df = pd.read_parquet(PROCESSED_ARTISTS_PATH)
    logger.info(f"Loaded {len(tracks_df):,} tracks, {len(artists_df):,} artist rows from disk")
    return tracks_df, artists_df