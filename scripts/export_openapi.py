"""Write the API's OpenAPI schema to `docs/openapi.json`.

That file is the contract between the HTTP API and anything that talks to it:
the React front end generates its TypeScript types from it, and the Rust port
implements the same endpoints. `tests/test_openapi_snapshot.py` fails when
the API changes without this being rerun, so a change to the contract is
always a visible diff.

Usage (repo root, after `uv sync`):
    uv run python scripts/export_openapi.py
"""

import json
from pathlib import Path

from openfloat_formatter.main import app

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "docs" / "openapi.json"


def main() -> None:
    text = json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n"
    OUTPUT_PATH.write_text(text, encoding="utf-8", newline="\n")
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
