"""
tests/test_load.py
Unit tests for src/load.py. No real Postgres connection is used —
the SQLAlchemy engine and pd.read_sql are mocked so these run fast
and in CI without a database.
"""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.load import (
    link_track_artists,
    load,
    load_fact_tracks,
    upsert_dim_albums,
    upsert_dim_artists,
    upsert_dim_genres,
)


def _mock_engine():
    """A MagicMock engine whose .begin() supports the `with engine.begin() as conn:` pattern."""
    engine = MagicMock()
    conn = MagicMock()
    engine.begin.return_value.__enter__.return_value = conn
    engine.begin.return_value.__exit__.return_value = False
    return engine, conn


# ---------------------------------------------------------
# upsert_dim_genres / upsert_dim_albums / upsert_dim_artists
# ---------------------------------------------------------
def test_upsert_dim_genres_executes_once_per_unique_genre():
    engine, conn = _mock_engine()
    df = pd.DataFrame({"track_genre": ["pop", "rock", "pop"]})  # 2 unique genres

    upsert_dim_genres(df, engine)

    assert conn.execute.call_count == 2
    called_genre_names = {call.args[1]["genre_name"] for call in conn.execute.call_args_list}
    assert called_genre_names == {"pop", "rock"}


def test_upsert_dim_genres_sql_uses_on_conflict_do_nothing():
    engine, conn = _mock_engine()
    df = pd.DataFrame({"track_genre": ["pop"]})

    upsert_dim_genres(df, engine)

    executed_sql = str(conn.execute.call_args_list[0].args[0])
    assert "ON CONFLICT" in executed_sql
    assert "DO NOTHING" in executed_sql


def test_upsert_dim_albums_deduplicates_album_names():
    engine, conn = _mock_engine()
    df = pd.DataFrame({"album_name": ["Album X", "Album X", "Album Y"]})

    upsert_dim_albums(df, engine)

    assert conn.execute.call_count == 2


def test_upsert_dim_artists_passes_correct_param_names():
    engine, conn = _mock_engine()
    artist_df = pd.DataFrame({"artist_name": ["Artist A"]})

    upsert_dim_artists(artist_df, engine)

    call_args = conn.execute.call_args_list[0]
    assert call_args.args[1] == {"artist_name": "Artist A"}


# ---------------------------------------------------------
# load_fact_tracks
# ---------------------------------------------------------
@patch("src.load.pd.read_sql")
def test_load_fact_tracks_joins_dim_keys_before_insert(mock_read_sql):
    engine, conn = _mock_engine()

    # First read_sql call returns genre map, second returns album map
    mock_read_sql.side_effect = [
        pd.DataFrame({"genre_id": [1], "genre_name": ["pop"]}),
        pd.DataFrame({"album_id": [10], "album_name": ["Album X"]}),
    ]

    df = pd.DataFrame([{
        "track_id": "t1", "track_name": "Song 1", "album_name": "Album X",
        "track_genre": "pop", "popularity": 70, "duration_min": 3.5,
        "explicit": False, "danceability": 0.5, "energy": 0.5, "key": 1,
        "loudness": -5.0, "mode": 1, "speechiness": 0.1, "acousticness": 0.1,
        "instrumentalness": 0.0, "liveness": 0.1, "valence": 0.5,
        "tempo": 120.0, "time_signature": 4, "mood_quadrant": "calm_positive",
    }])

    load_fact_tracks(df, engine)

    assert conn.execute.call_count == 1
    params = conn.execute.call_args_list[0].args[1]
    assert params["track_id"] == "t1"
    assert params["genre_id"] == 1     # resolved from the genre map, not the raw genre string
    assert params["album_id"] == 10    # resolved from the album map
    assert params["musical_key"] == 1  # renamed from "key" to avoid the SQL reserved word


@patch("src.load.pd.read_sql")
def test_load_fact_tracks_sql_uses_on_conflict_update(mock_read_sql):
    engine, conn = _mock_engine()
    mock_read_sql.side_effect = [
        pd.DataFrame({"genre_id": [1], "genre_name": ["pop"]}),
        pd.DataFrame({"album_id": [10], "album_name": ["Album X"]}),
    ]
    df = pd.DataFrame([{
        "track_id": "t1", "track_name": "Song 1", "album_name": "Album X",
        "track_genre": "pop", "popularity": 70, "duration_min": 3.5,
        "explicit": False, "danceability": 0.5, "energy": 0.5, "key": 1,
        "loudness": -5.0, "mode": 1, "speechiness": 0.1, "acousticness": 0.1,
        "instrumentalness": 0.0, "liveness": 0.1, "valence": 0.5,
        "tempo": 120.0, "time_signature": 4, "mood_quadrant": "calm_positive",
    }])

    load_fact_tracks(df, engine)

    executed_sql = str(conn.execute.call_args_list[0].args[0])
    assert "ON CONFLICT (track_id, genre_id) DO UPDATE" in executed_sql


# ---------------------------------------------------------
# link_track_artists
# ---------------------------------------------------------
@patch("src.load.pd.read_sql")
def test_link_track_artists_builds_correct_bridge_rows(mock_read_sql):
    engine, conn = _mock_engine()

    mock_read_sql.side_effect = [
        pd.DataFrame({"genre_id": [1], "genre_name": ["pop"]}),
        pd.DataFrame({"track_pk": [100], "track_id": ["t1"], "genre_id": [1]}),
        pd.DataFrame({"artist_id": [5], "artist_name": ["Artist A"]}),
    ]

    df = pd.DataFrame({"track_id": ["t1"], "track_genre": ["pop"]})
    artist_df = pd.DataFrame({
        "track_id": ["t1"], "track_genre": ["pop"], "artist_name": ["Artist A"],
    })

    link_track_artists(df, artist_df, engine)

    assert conn.execute.call_count == 1
    params = conn.execute.call_args_list[0].args[1]
    assert params == {"track_pk": 100, "artist_id": 5}


# ---------------------------------------------------------
# load() — full orchestration
# ---------------------------------------------------------
def test_load_calls_all_stages_in_order():
    """
    load() should call dims -> fact -> bridge, in that order, since
    the fact table depends on dim IDs and the bridge depends on the
    fact table's generated track_pk.
    """
    engine, _ = _mock_engine()
    tracks_df = pd.DataFrame({"track_genre": ["pop"], "album_name": ["Album X"]})
    artists_df = pd.DataFrame({"artist_name": ["Artist A"]})

    call_order = []
    with patch("src.load.upsert_dim_genres", side_effect=lambda *a, **k: call_order.append("genres")) as m_g, \
         patch("src.load.upsert_dim_albums", side_effect=lambda *a, **k: call_order.append("albums")) as m_a, \
         patch("src.load.upsert_dim_artists", side_effect=lambda *a, **k: call_order.append("artists")) as m_ar, \
         patch("src.load.load_fact_tracks", side_effect=lambda *a, **k: call_order.append("fact")) as m_f, \
         patch("src.load.link_track_artists", side_effect=lambda *a, **k: call_order.append("bridge")) as m_b:

        load(tracks_df, artists_df, engine=engine)

    assert call_order == ["genres", "albums", "artists", "fact", "bridge"]
    for mock_fn in (m_g, m_a, m_ar, m_f, m_b):
        mock_fn.assert_called_once()