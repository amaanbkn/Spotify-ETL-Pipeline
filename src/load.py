"""
src/load.py
Loads clean data into the star schema (dims + fact) with upsert
semantics so reruns are idempotent (safe to schedule daily).
"""

import pandas as pd
from sqlalchemy import text

from src.utils import get_engine, get_logger

logger = get_logger(__name__)


def upsert_dim_genres(df: pd.DataFrame, engine=None) -> None:
    engine = engine or get_engine()
    genres = df[["track_genre"]].drop_duplicates().rename(columns={"track_genre": "genre_name"})
    with engine.begin() as conn:
        for genre in genres["genre_name"]:
            conn.execute(
                text("""
                    INSERT INTO analytics.dim_genres (genre_name)
                    VALUES (:genre_name)
                    ON CONFLICT (genre_name) DO NOTHING
                """),
                {"genre_name": genre},
            )
    logger.info(f"Upserted {len(genres)} genres")


def upsert_dim_albums(df: pd.DataFrame, engine=None) -> None:
    engine = engine or get_engine()
    albums = df[["album_name"]].drop_duplicates()
    with engine.begin() as conn:
        for album in albums["album_name"]:
            conn.execute(
                text("""
                    INSERT INTO analytics.dim_albums (album_name)
                    VALUES (:album_name)
                    ON CONFLICT (album_name) DO NOTHING
                """),
                {"album_name": album},
            )
    logger.info(f"Upserted {len(albums)} albums")


def upsert_dim_artists(artist_df: pd.DataFrame, engine=None) -> None:
    engine = engine or get_engine()
    artists = artist_df[["artist_name"]].drop_duplicates()
    with engine.begin() as conn:
        for artist in artists["artist_name"]:
            conn.execute(
                text("""
                    INSERT INTO analytics.dim_artists (artist_name)
                    VALUES (:artist_name)
                    ON CONFLICT (artist_name) DO NOTHING
                """),
                {"artist_name": artist},
            )
    logger.info(f"Upserted {len(artists)} artists")


def load_fact_tracks(df: pd.DataFrame, engine=None) -> None:
    """Join dim keys back onto the fact rows, then upsert."""
    engine = engine or get_engine()
    genre_map = pd.read_sql("SELECT genre_id, genre_name FROM analytics.dim_genres", engine)
    album_map = pd.read_sql("SELECT album_id, album_name FROM analytics.dim_albums", engine)

    fact = df.merge(genre_map, left_on="track_genre", right_on="genre_name", how="left")
    fact = fact.merge(album_map, left_on="album_name", right_on="album_name", how="left")
    fact = fact.rename(columns={"key": "musical_key"})

    fact_cols = [
        "track_id", "track_name", "album_id", "genre_id", "popularity",
        "duration_min", "explicit", "danceability", "energy", "musical_key",
        "loudness", "mode", "speechiness", "acousticness", "instrumentalness",
        "liveness", "valence", "tempo", "time_signature", "mood_quadrant",
    ]

    with engine.begin() as conn:
        for _, row in fact.iterrows():
            conn.execute(
                text("""
                    INSERT INTO analytics.fact_tracks (
                        track_id, track_name, album_id, genre_id, popularity,
                        duration_min, explicit, danceability, energy, musical_key,
                        loudness, mode, speechiness, acousticness, instrumentalness,
                        liveness, valence, tempo, time_signature, mood_quadrant
                    ) VALUES (
                        :track_id, :track_name, :album_id, :genre_id, :popularity,
                        :duration_min, :explicit, :danceability, :energy, :musical_key,
                        :loudness, :mode, :speechiness, :acousticness, :instrumentalness,
                        :liveness, :valence, :tempo, :time_signature, :mood_quadrant
                    )
                    ON CONFLICT (track_id, genre_id) DO UPDATE SET
                        popularity = EXCLUDED.popularity,
                        loaded_at = NOW()
                """),
                row[fact_cols].to_dict(),
            )
    logger.info(f"Upserted {len(fact):,} rows into fact_tracks")


def link_track_artists(df: pd.DataFrame, artist_df: pd.DataFrame, engine=None) -> None:
    """Populate the track_artists bridge table."""
    engine = engine or get_engine()
    genre_map = pd.read_sql("SELECT genre_id, genre_name FROM analytics.dim_genres", engine)
    track_map = pd.read_sql(
        "SELECT track_pk, track_id, genre_id FROM analytics.fact_tracks", engine
    )
    artist_map = pd.read_sql("SELECT artist_id, artist_name FROM analytics.dim_artists", engine)

    bridge = artist_df.merge(genre_map, left_on="track_genre", right_on="genre_name")
    bridge = bridge.merge(track_map, on=["track_id", "genre_id"])
    bridge = bridge.merge(artist_map, on="artist_name")
    bridge = bridge[["track_pk", "artist_id"]].drop_duplicates()

    with engine.begin() as conn:
        for _, row in bridge.iterrows():
            conn.execute(
                text("""
                    INSERT INTO analytics.track_artists (track_pk, artist_id)
                    VALUES (:track_pk, :artist_id)
                    ON CONFLICT DO NOTHING
                """),
                row.to_dict(),
            )
    logger.info(f"Linked {len(bridge):,} track-artist relationships")


def load(tracks_df: pd.DataFrame, artists_df: pd.DataFrame, engine=None) -> None:
    """Run the full load sequence: dims first, then fact, then the bridge table."""
    engine = engine or get_engine()
    upsert_dim_genres(tracks_df, engine)
    upsert_dim_albums(tracks_df, engine)
    upsert_dim_artists(artists_df, engine)
    load_fact_tracks(tracks_df, engine)
    link_track_artists(tracks_df, artists_df, engine)