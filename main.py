"""
main.py
CLI entrypoint for running the Spotify ETL pipeline locally, outside Airflow.


"""

import argparse
import sys
import time

import pandas as pd

from src.extract import extract, load_to_staging
from src.load import load
from src.transform import clean_tracks, load_processed, save_processed, split_artists
from src.utils import get_engine, get_logger

logger = get_logger(__name__)


def run_extract(engine) -> None:
    logger.info("=== EXTRACT ===")
    raw_df = extract()
    load_to_staging(raw_df, source_file="spotify_tracks.csv", engine=engine)


def run_transform(engine) -> tuple[pd.DataFrame, pd.DataFrame]:
    logger.info("=== TRANSFORM ===")
    raw_df = pd.read_sql("SELECT * FROM staging.raw_tracks", engine)
    clean_df = clean_tracks(raw_df)
    artist_df = split_artists(clean_df)
    save_processed(clean_df, artist_df)
    return clean_df, artist_df


def run_load(engine, clean_df: pd.DataFrame, artist_df: pd.DataFrame) -> None:
    logger.info("=== LOAD ===")
    load(clean_df, artist_df, engine=engine)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Spotify tracks ETL pipeline.")
    parser.add_argument(
        "--skip-extract",
        action="store_true",
        help="Skip re-reading the CSV; reuse whatever is already in staging.raw_tracks.",
    )
    parser.add_argument(
        "--from-processed",
        action="store_true",
        help="Skip extract AND transform entirely; load directly from the last "
             "checkpoint saved in data/processed/. Useful for resuming a failed load.",
    )
    args = parser.parse_args()

    start = time.time()
    engine = get_engine()

    try:
        if args.from_processed:
            logger.info("Resuming from data/processed/ checkpoint (skipping extract + transform)")
            clean_df, artist_df = load_processed()
        else:
            if not args.skip_extract:
                run_extract(engine)
            else:
                logger.info("Skipping extract (--skip-extract passed)")
            clean_df, artist_df = run_transform(engine)

        run_load(engine, clean_df, artist_df)

    except Exception:
        logger.exception("Pipeline failed")
        return 1

    elapsed = time.time() - start
    logger.info(f"Pipeline finished successfully in {elapsed:.1f}s "
                f"({len(clean_df):,} tracks, {len(artist_df):,} artist rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())