"""
airflow/dags/spotify_dag.py
Orchestrates: extract -> transform -> quality_check -> load.
Place the whole airflow/ folder such that dags/ is mounted to
Airflow's DAGS_FOLDER (see docker-compose.yml).
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.email import send_email

# Make the project's src/ package importable from inside the Airflow container.
# docker-compose.yml mounts the project root to /opt/airflow/project.
sys.path.insert(0, "/opt/airflow/project")

from src.extract import extract, load_to_staging          # noqa: E402
from src.transform import clean_tracks, split_artists, save_processed  # noqa: E402
from src.load import load                                  # noqa: E402
from src.utils import get_engine, get_logger                # noqa: E402

logger = get_logger(__name__)


def notify_failure(context):
    """Simple failure alert — swap in a Slack webhook / PagerDuty call as needed."""
    task = context["task_instance"]
    send_email(
        to=["you@example.com"],
        subject=f"[Airflow] Spotify ETL failed: {task.task_id}",
        html_content=(
            f"Task {task.task_id} failed on {context['execution_date']}. "
            f"Log: {task.log_url}"
        ),
    )


default_args = {
    "owner": "data-eng",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "on_failure_callback": notify_failure,
    "email_on_failure": False,  # handled via notify_failure instead
}


def _extract(**kwargs):
    engine = get_engine()
    raw_df = extract()
    load_to_staging(raw_df, source_file="spotify_tracks.csv", engine=engine)
    kwargs["ti"].xcom_push(key="raw_row_count", value=len(raw_df))


def _transform(**kwargs):
    engine = get_engine()
    raw_df = pd.read_sql("SELECT * FROM staging.raw_tracks", engine)

    clean_df = clean_tracks(raw_df)
    artist_df = split_artists(clean_df)

    # Checkpoint to data/processed/ so load can resume from disk if it fails
    save_processed(clean_df, artist_df)

    kwargs["ti"].xcom_push(key="clean_row_count", value=len(clean_df))


def _quality_check(**kwargs):
    """Fail the DAG early if the transform output looks suspicious."""
    ti = kwargs["ti"]
    raw_count = ti.xcom_pull(key="raw_row_count", task_ids="extract")
    clean_count = ti.xcom_pull(key="clean_row_count", task_ids="transform")

    if clean_count == 0:
        raise ValueError("Transform produced zero rows — aborting load.")
    if clean_count < raw_count * 0.5:
        raise ValueError(
            f"Transform dropped more than 50% of rows "
            f"({raw_count} -> {clean_count}). Check data quality before loading."
        )
    logger.info(f"Quality check passed: {raw_count} raw -> {clean_count} clean rows")


def _load(**kwargs):
    from src.transform import load_processed  # local import to avoid unused-at-parse-time noise

    engine = get_engine()
    clean_df, artist_df = load_processed()
    load(clean_df, artist_df, engine=engine)


with DAG(
    dag_id="spotify_tracks_etl",
    default_args=default_args,
    description="Ingest, clean, and load Spotify tracks into PostgreSQL",
    schedule_interval="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["spotify", "etl"],
) as dag:

    extract_task = PythonOperator(
        task_id="extract",
        python_callable=_extract,
    )

    transform_task = PythonOperator(
        task_id="transform",
        python_callable=_transform,
    )

    quality_check_task = PythonOperator(
        task_id="quality_check",
        python_callable=_quality_check,
    )

    load_task = PythonOperator(
        task_id="load",
        python_callable=_load,
    )

    extract_task >> transform_task >> quality_check_task >> load_task