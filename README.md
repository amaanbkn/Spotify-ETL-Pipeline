# Spotify ETL Pipeline

A complete, production-grade end-to-end data pipeline that extracts raw Spotify track data from a CSV file, ingests it into a PostgreSQL staging environment, cleans and processes it using Pandas, and loads it into a normalized star schema (Dimensions + Fact tables) ready for analytical querying and machine learning tasks. The workflow is orchestrated using Apache Airflow.

---

## 📂 Project Structure

```
spotify-etl-pipeline/
├── data/
│   ├── raw/                # Immutable source CSV data
│   └── processed/          # Cleaned intermediate parquet files (for recovery/debugging)
├── notebooks/              # Jupyter Notebooks for exploratory data analysis (EDA)
├── src/                    # Data pipeline source code
│   ├── __init__.py         # Package initialization
│   ├── config.py           # Path mapping, credentials, configuration constants
│   ├── extract.py          # Staging raw ingestion: CSV -> staging.raw_tracks
│   ├── transform.py        # Data cleaning, deduplication, and feature engineering
│   ├── load.py             # Idempotent database loading (Dimensions -> Fact -> Bridge)
│   ├── utils.py            # Loggers and SQLAlchemy engine connections
│   └── persist.py          # Save/load helpers to parquet
├── sql/
│   ├── schema.sql          # Staging & star-schema analytics database definition
│   └── queries.sql         # Common analysis queries (Top 10 tracks, mood stats, ML export)
├── airflow/
│   └── dags/
│       └── spotify_dag.py  # Airflow DAG for pipeline orchestration
├── tests/
│   ├── test_transform.py   # Unit tests for data cleaning logic
│   └── test_load.py        # Unit tests for database load operations
├── .env.example            # Environment template configuration
├── .gitignore              # Git ignore rules
├── requirements.txt        # Python package dependencies
├── docker-compose.yml      # Docker container configs (Postgres, Airflow)
├── main.py                 # local test execution entrypoint
└── README.md               # Project documentation
```

---

## 📊 Data Model & Database Architecture

The pipeline processes data into two distinct database schemas in PostgreSQL:

### 1. Staging Schema (`staging`)
- **`raw_tracks`**: A direct 1-to-1 copy of the source CSV dataset. It uses lightweight text-based columns to avoid load failures due to invalid types. It is truncated and fully refreshed on each run.

### 2. Analytics Schema (`analytics`)
A star schema optimized for analytical queries:
- **`dim_artists`**: Contains unique artist names.
- **`dim_genres`**: Contains unique genre names.
- **`dim_albums`**: Contains unique album names.
- **`fact_tracks`**: Contains individual track metrics (popularity, danceability, energy, tempo, duration, key, etc.).
- **`track_artists`**: A bridge table resolving the many-to-many relationship between tracks and artists.

### 🧠 Engineered Features
During the transformation step, several analytical features are generated:
- `duration_min`: Re-scales track duration from milliseconds to minutes.
- `mood_quadrant`: Classifies tracks into one of four mood categories based on `valence` (positivity) and `energy` (activity):
  - `energetic_positive` (High valence, High energy)
  - `calm_positive` (High valence, Low energy)
  - `energetic_negative` (Low valence, High energy)
  - `calm_negative` (Low valence, Low energy)

---

## 🛠️ Setup & Installation

### 1. Clone & Set Environment Variables
Copy `.env.example` to `.env` and fill in your local variables (defaults are pre-configured for Docker):
```bash
cp .env.example .env
```

### 2. Install Dependencies
Set up a Python 3.10+ virtual environment and install the required dependencies:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Place Raw Data
Ensure your source Spotify dataset CSV is placed in `data/raw/` and named `spotify_tracks.csv`.

---

## 🚀 Running the Pipeline

### Option A: Local Run (Python)
Ensure PostgreSQL is running, the schemas are initialized via `sql/schema.sql`, and execute the pipeline manually:
```bash
python main.py
```

### Option B: Orchestrated Run (Airflow)
If running inside a Docker setup, mount the project root to `/opt/airflow/project`. Airflow will orchestrate the execution steps daily:
1. **`extract`**: Clears the staging table and copies the raw file into `staging.raw_tracks`.
2. **`transform`**: Pulls from staging, cleans types, handles outliers, drops duplicates, computes features, and outputs processed parquet files.
3. **`quality_check`**: A verification check that ensures rows were processed and that no more than 50% of the raw data was dropped during cleaning.
4. **`load`**: Upserts clean dimensions, fact records, and bridge associations idempotently.
