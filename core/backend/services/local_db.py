import os
import json
import uuid
from typing import List, Dict, Any

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../local_db")
os.makedirs(DATA_DIR, exist_ok=True)

def load_json(filename: str, default: Any) -> Any:
    path = os.path.join(DATA_DIR, filename)
    if os.path.exists(path):
        with open(path, "r") as f:
            try:
                return json.load(f)
            except:
                pass
    return default

def save_json(filename: str, data: Any):
    path = os.path.join(DATA_DIR, filename)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

