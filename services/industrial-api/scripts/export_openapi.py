"""导出 Industrial API 的 OpenAPI 3.1 契约到 packages/contracts。

用法（在 services/industrial-api 下）：
    .venv/Scripts/python.exe scripts/export_openapi.py
"""

import json
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SERVICE_ROOT.parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

from app.main import create_app  # noqa: E402

OUTPUT = REPO_ROOT / "packages" / "contracts" / "industrial-api.openapi.json"


def main() -> int:
    app = create_app()
    schema = app.openapi()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"openapi written: {OUTPUT}")
    print(f"openapi version: {schema.get('openapi')}")
    print(f"paths: {len(schema.get('paths', {}))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())