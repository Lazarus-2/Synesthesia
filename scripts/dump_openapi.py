"""Dump the FastAPI OpenAPI spec to disk (Plan 2 D3).

Run from the project root:

    python scripts/dump_openapi.py [--output PATH]

Default output: ``frontend/web/src/types/openapi.json``.

The frontend's ``npm run codegen`` script then runs ``openapi-typescript``
against that file to produce a TS types module. Decoupling the dump from
the codegen lets us regenerate types in CI without spinning up the API.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Make ``backend`` importable when invoked from the project root, regardless
# of how the user launched Python (``python scripts/foo.py`` vs ``-m``).
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Quiet noisy startup logs so the dump output isn't muddied.
logging.disable(logging.CRITICAL)

# Importing main is enough to trigger app construction. The DB ping inside
# the lifespan handler is skipped here because we never run the lifespan
# during a sync dump.
from backend.main import app  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=Path("frontend/web/src/types/openapi.json"),
    )
    args = parser.parse_args()

    spec = app.openapi()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.output} ({len(spec['paths'])} paths)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
