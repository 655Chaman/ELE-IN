import json
import sys
import os
from pathlib import Path

# Add project root to sys.path so we can import core.backend.main
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from core.backend.main import app

def generate_openapi():
    schema = app.openapi()
    output_path = project_root / "openapi.json"
    with open(output_path, "w") as f:
        json.dump(schema, f, indent=2)
    print(f"OpenAPI schema successfully written to {output_path}")

if __name__ == "__main__":
    generate_openapi()
