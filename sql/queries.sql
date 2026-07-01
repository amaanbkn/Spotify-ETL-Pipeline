-- =========================================================
-- Spotify Tracks — Analysis Queries
-- Run these manually (psql, a notebook, or a BI tool) after
-- the pipeline has loaded data. Not called by src/ code.
-- =========================================================

-- Top 10 most popular tracks per genre
SELECT genre_name, track_name, popularity
FROM (
    SELECT g.genre_name, f.track_name, f.popularity,
           ROW_NUMBER() OVER (PARTITION BY g.genre_id ORDER BY f.popularity DESC) AS rnk
    FROM analytics.fact_tracks f
    JOIN analytics.dim_genres g ON f.genre_id = g.genre_id
) ranked
WHERE rnk <= 10
ORDER BY genre_name, popularity DESC;


-- Average energy/valence/danceability by popularity decile
-- (quick way to eyeball whether "happier" or "more energetic" tracks trend more popular)
SELECT
    WIDTH_BUCKET(popularity, 0, 100, 10) AS popularity_decile,
    ROUND(AVG(energy)::numeric, 3) AS avg_energy,
    ROUND(AVG(valence)::numeric, 3) AS avg_valence,
    ROUND(AVG(danceability)::numeric, 3) AS avg_danceability,
    COUNT(*) AS track_count
FROM analytics.fact_tracks
GROUP BY popularity_decile
ORDER BY popularity_decile;


-- Mood quadrant distribution by genre
SELECT g.genre_name, f.mood_quadrant, COUNT(*) AS track_count
FROM analytics.fact_tracks f
JOIN analytics.dim_genres g ON f.genre_id = g.genre_id
GROUP BY g.genre_name, f.mood_quadrant
ORDER BY g.genre_name, track_count DESC;


-- Most prolific artists (by track count) with avg popularity
-- HAVING >= 5 filters out one-off artists so the ranking is meaningful
SELECT a.artist_name, COUNT(*) AS track_count, ROUND(AVG(f.popularity)::numeric, 1) AS avg_popularity
FROM analytics.track_artists ta
JOIN analytics.dim_artists a ON ta.artist_id = a.artist_id
JOIN analytics.fact_tracks f ON ta.track_pk = f.track_pk
GROUP BY a.artist_name
HAVING COUNT(*) >= 5
ORDER BY avg_popularity DESC
LIMIT 20;


-- Genre-level summary stats — useful as a quick data quality sanity check too
SELECT
    g.genre_name,
    COUNT(*) AS track_count,
    ROUND(AVG(f.popularity)::numeric, 1) AS avg_popularity,
    ROUND(AVG(f.duration_min)::numeric, 2) AS avg_duration_min,
    ROUND(AVG(f.tempo)::numeric, 1) AS avg_tempo
FROM analytics.fact_tracks f
JOIN analytics.dim_genres g ON f.genre_id = g.genre_id
GROUP BY g.genre_name
ORDER BY track_count DESC;


-- ML-ready feature export view
-- Downstream models / notebooks can just: SELECT * FROM analytics.ml_feature_matrix
CREATE OR REPLACE VIEW analytics.ml_feature_matrix AS
SELECT
    track_id,
    popularity,
    danceability, energy, loudness, speechiness, acousticness,
    instrumentalness, liveness, valence, tempo,
    duration_min,
    time_signature,
    mode,
    genre_id,          -- categorical, encode downstream (e.g. one-hot)
    mood_quadrant       -- categorical, encode downstream
FROM analytics.fact_tracks;