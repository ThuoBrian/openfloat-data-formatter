"""The committed OpenAPI schema matches the API, so contract changes are visible.

`docs/openapi.json` is what the React front end's types are generated from and
what the Rust port implements. If this fails, the API changed: run
`uv run python scripts/export_openapi.py` and commit the diff.
"""

import json
from pathlib import Path

from openfloat_formatter.main import app

SNAPSHOT = Path(__file__).resolve().parent.parent / "docs" / "openapi.json"


def test_openapi_snapshot_is_current():
    committed = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert app.openapi() == committed, (
        "The API changed. Run `uv run python scripts/export_openapi.py` and commit "
        "docs/openapi.json."
    )
