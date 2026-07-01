-- =========================================================
-- Spotify Tracks ETL — Schema
-- Staging (raw) -> Dimensions -> Fact table
-- Run once at project setup (auto-runs via docker-compose init mount)
-- =========================================================

CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS analytics;

-- ---------------------------------------------------------
-- STAGING: land raw CSV data as-is, minimal typing.
-- Truncated + reloaded on every pipeline run.
-- ---------------------------------------------------------
DROP TABLE IF EXISTS staging.raw_tracks;
CREATE TABLE staging.raw_tracks (
    row_id              SERIAL PRIMARY KEY,
    track_id            TEXT,
    artists             TEXT,
    album_name          TEXT,
    track_name          TEXT,
    popularity          TEXT,
    duration_ms         TEXT,
    explicit            TEXT,
    danceability        TEXT,
    energy              TEXT,
    key                 TEXT,
    loudness            TEXT,
    mode                TEXT,
    speechiness         TEXT,
    acousticness        TEXT,
    instrumentalness    TEXT,
    liveness            TEXT,
    valence             TEXT,
    tempo               TEXT,
    time_signature      TEXT,
    track_genre         TEXT,
    loaded_at           TIMESTAMP DEFAULT NOW(),
    source_file         TEXT
);

-- ---------------------------------------------------------
-- DIMENSION: Artists
-- Dataset stores multiple artists as a delimited string;
-- we normalize into an artist bridge table (see track_artists below).
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS analytics.dim_artists (
    artist_id       SERIAL PRIMARY KEY,
    artist_name     TEXT UNIQUE NOT NULL
);

-- ---------------------------------------------------------
-- DIMENSION: Genres
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS analytics.dim_genres (
    genre_id        SERIAL PRIMARY KEY,
    genre_name      TEXT UNIQUE NOT NULL
);

-- ---------------------------------------------------------
-- DIMENSION: Albums
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS analytics.dim_albums (
    album_id        SERIAL PRIMARY KEY,
    album_name      TEXT NOT NULL,
    UNIQUE (album_name)
);

-- ---------------------------------------------------------
-- FACT: Tracks (one row per unique track_id + genre combo,
-- since the source dataset repeats tracks across genres)
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS analytics.fact_tracks (
    track_pk             BIGSERIAL PRIMARY KEY,
    track_id             VARCHAR(64) NOT NULL,
    track_name           TEXT NOT NULL,
    album_id             INT REFERENCES analytics.dim_albums(album_id),
    genre_id             INT REFERENCES analytics.dim_genres(genre_id),
    popularity            SMALLINT CHECK (popularity BETWEEN 0 AND 100),
    duration_min          NUMERIC(6,2),
    explicit              BOOLEAN,
    danceability          NUMERIC(5,4) CHECK (danceability BETWEEN 0 AND 1),
    energy                NUMERIC(5,4) CHECK (energy BETWEEN 0 AND 1),
    musical_key           SMALLINT,
    loudness              NUMERIC(6,3),
    mode                  SMALLINT,
    speechiness            NUMERIC(5,4),
    acousticness           NUMERIC(5,4),
    instrumentalness       NUMERIC(6,5),
    liveness               NUMERIC(5,4),
    valence                NUMERIC(5,4),
    tempo                  NUMERIC(7,3),
    time_signature          SMALLINT,
    mood_quadrant           TEXT,           -- derived feature (see src/transform.py)
    loaded_at                TIMESTAMP DEFAULT NOW(),
    UNIQUE (track_id, genre_id)
);

-- Bridge table: track <-> artist (many-to-many)
CREATE TABLE IF NOT EXISTS analytics.track_artists (
    track_pk    BIGINT REFERENCES analytics.fact_tracks(track_pk) ON DELETE CASCADE,
    artist_id   INT REFERENCES analytics.dim_artists(artist_id),
    PRIMARY KEY (track_pk, artist_id)
);

-- ---------------------------------------------------------
-- Indexes for common analytical queries (see queries.sql)
-- ---------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_fact_tracks_genre ON analytics.fact_tracks(genre_id);
CREATE INDEX IF NOT EXISTS idx_fact_tracks_popularity ON analytics.fact_tracks(popularity DESC);
CREATE INDEX IF NOT EXISTS idx_fact_tracks_mood ON analytics.fact_tracks(mood_quadrant);
CREATE INDEX IF NOT EXISTS idx_track_artists_artist ON analytics.track_artists(artist_id);