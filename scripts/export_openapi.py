"""Export the OpenAPI spec from the FastAPI app to a static JSON file.

Usage:
    python -m scripts.export_openapi [output_path]

Defaults to docs/openapi.json if no path is given.
"""

import json
import sys
from pathlib import Path


def main() -> None:
    from src.dashboard_api import app

    spec = app.openapi()
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("docs/openapi.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    print(f"Exported OpenAPI spec to {output} ({output.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
