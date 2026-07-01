"""
tests/test_transform.py
Unit tests for src/transform.py — pure DataFrame-in, DataFrame-out
logic, so no database or file I/O is needed for most of these.
"""

import pandas as pd
import pytest

from src.transform import (
    _cast_types,
    _deduplicate,
    _drop_invalid_rows,
    _engineer_features,
    clean_tracks,
    split_artists,
)


def _make_row(**overrides):
    """A single valid raw row, with any fields overridden for the test at hand."""
    base = {
        "track_id": "t1", "artists": "Artist A", "album_name": "Album X",
        "track_name": "Song 1", "popularity": "50", "duration_ms": "200000",
        "explicit": "False", "danceability": "0.5", "energy": "0.5", "key": "1",
        "loudness": "-5.0", "mode": "1", "speechiness": "0.1", "acousticness": "0.1",
        "instrumentalness": "0.0", "liveness": "0.1", "valence": "0.5",
        "tempo": "120.0", "time_signature": "4", "track_genre": "pop",
    }
    base.update(overrides)
    return base


def _make_df(rows):
    return pd.DataFrame(rows)


# ---------------------------------------------------------
# _cast_types
# ---------------------------------------------------------
def test_cast_types_converts_strings_to_numeric():
    df = _make_df([_make_row(popularity="75", danceability="0.812")])
    result = _cast_types(df)
    assert result["popularity"].dtype.kind in "if"
    assert result["danceability"].iloc[0] == pytest.approx(0.812)


def test_cast_types_handles_explicit_boolean():
    df = _make_df([_make_row(explicit="True"), _make_row(track_id="t2", explicit="False")])
    result = _cast_types(df)
    # pandas may store these as numpy.bool_ rather than Python bool, so compare
    # by value (== True) rather than identity (is True).
    assert result["explicit"].iloc[0] == True  # noqa: E712
    assert result["explicit"].iloc[1] == False  # noqa: E712


def test_cast_types_coerces_bad_numeric_to_nan():
    df = _make_df([_make_row(popularity="not_a_number")])
    result = _cast_types(df)
    assert pd.isna(result["popularity"].iloc[0])


# ---------------------------------------------------------
# _drop_invalid_rows
# ---------------------------------------------------------
def test_drops_out_of_range_popularity():
    df = _cast_types(_make_df([_make_row(popularity="150"), _make_row(track_id="t2", popularity="50")]))
    result = _drop_invalid_rows(df)
    assert len(result) == 1
    assert result.iloc[0]["popularity"] == 50


def test_drops_negative_popularity():
    df = _cast_types(_make_df([_make_row(popularity="-5")]))
    result = _drop_invalid_rows(df)
    assert len(result) == 0


def test_drops_out_of_range_ratio_features():
    df = _cast_types(_make_df([
        _make_row(track_id="t1", danceability="1.5"),   # invalid, > 1
        _make_row(track_id="t2", danceability="0.5"),   # valid
    ]))
    result = _drop_invalid_rows(df)
    assert len(result) == 1
    assert result.iloc[0]["track_id"] == "t2"


def test_drops_rows_missing_required_fields():
    df = _cast_types(_make_df([_make_row(track_name=None)]))
    result = _drop_invalid_rows(df)
    assert len(result) == 0


def test_drops_unrealistic_duration():
    df = _cast_types(_make_df([
        _make_row(track_id="t1", duration_ms="1000"),        # 1 second, too short
        _make_row(track_id="t2", duration_ms="200000"),      # valid
        _make_row(track_id="t3", duration_ms="99999999"),    # way too long
    ]))
    result = _drop_invalid_rows(df)
    assert list(result["track_id"]) == ["t2"]


# ---------------------------------------------------------
# _deduplicate
# ---------------------------------------------------------
def test_deduplicate_removes_exact_track_genre_repeats():
    df = _cast_types(_make_df([
        _make_row(track_id="t1", track_genre="pop"),
        _make_row(track_id="t1", track_genre="pop"),   # exact duplicate
    ]))
    result = _deduplicate(df)
    assert len(result) == 1


def test_deduplicate_keeps_same_track_across_different_genres():
    df = _cast_types(_make_df([
        _make_row(track_id="t1", track_genre="pop"),
        _make_row(track_id="t1", track_genre="rock"),   # same track, different genre tag
    ]))
    result = _deduplicate(df)
    assert len(result) == 2


# ---------------------------------------------------------
# _engineer_features
# ---------------------------------------------------------
@pytest.mark.parametrize(
    "valence,energy,expected",
    [
        (0.8, 0.8, "energetic_positive"),
        (0.8, 0.2, "calm_positive"),
        (0.2, 0.8, "energetic_negative"),
        (0.2, 0.2, "calm_negative"),
    ],
)
def test_mood_quadrant_assignment(valence, energy, expected):
    df = _cast_types(_make_df([_make_row(valence=str(valence), energy=str(energy))]))
    result = _engineer_features(df)
    assert result["mood_quadrant"].iloc[0] == expected


def test_mood_quadrant_is_none_when_features_missing():
    df = _cast_types(_make_df([_make_row(valence="not_a_number")]))
    result = _engineer_features(df)
    assert result["mood_quadrant"].iloc[0] is None


def test_duration_min_derived_correctly():
    df = _cast_types(_make_df([_make_row(duration_ms="180000")]))  # 3 minutes exactly
    result = _engineer_features(df)
    assert result["duration_min"].iloc[0] == pytest.approx(3.0)


def test_genre_is_lowercased_and_stripped():
    df = _cast_types(_make_df([_make_row(track_genre="  Pop ")]))
    result = _engineer_features(df)
    assert result["track_genre"].iloc[0] == "pop"


# ---------------------------------------------------------
# clean_tracks (full pipeline)
# ---------------------------------------------------------
def test_clean_tracks_end_to_end():
    df = _make_df([
        _make_row(track_id="t1", track_genre="pop", popularity="70"),
        _make_row(track_id="t1", track_genre="pop", popularity="70"),  # duplicate, dropped
        _make_row(track_id="t2", track_genre="rock", popularity="200"),  # invalid, dropped
        _make_row(track_id="t3", track_genre="jazz", popularity="40"),
    ])
    result = clean_tracks(df)
    assert len(result) == 2
    assert set(result["track_id"]) == {"t1", "t3"}
    assert "mood_quadrant" in result.columns
    assert "duration_min" in result.columns


# ---------------------------------------------------------
# split_artists
# ---------------------------------------------------------
def test_split_artists_explodes_multiple_artists():
    df = _make_df([_make_row(track_id="t1", artists="Artist A; Artist B;Artist C")])
    df = _cast_types(df)
    result = split_artists(df)
    assert len(result) == 3
    assert set(result["artist_name"]) == {"Artist A", "Artist B", "Artist C"}


def test_split_artists_single_artist():
    df = _cast_types(_make_df([_make_row(track_id="t1", artists="Solo Artist")]))
    result = split_artists(df)
    assert len(result) == 1
    assert result["artist_name"].iloc[0] == "Solo Artist"


def test_split_artists_preserves_track_genre_key():
    df = _cast_types(_make_df([_make_row(track_id="t1", track_genre="pop", artists="A;B")]))
    result = split_artists(df)
    assert set(result.columns) == {"track_id", "track_genre", "artist_name"}
    assert (result["track_genre"] == "pop").all()