import os
from pathlib import Path

from huey import SqliteHuey

# Initialize Huey with SQLite backend for zero-dependency task queue
db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'leadgen_tasks.db')
huey = SqliteHuey('leadgen', filename=db_path)

LOG_DIR = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

