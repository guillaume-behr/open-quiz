"""The packages of app/ only import from the layers below them.

From the bottom up: core, models, enums and schemas; domain and live;
records; services; responses; routers; and application, which assembles
everything. docs/architecture.md describes each package.
"""

import re
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "app"
LAYERS = {
    "core": 0,
    "models": 0,
    "enums": 0,
    "schemas": 0,
    "domain": 1,
    "live": 1,
    "records": 2,
    "services": 3,
    "responses": 4,
    "routers": 5,
    "application": 6,
}
IMPORT = re.compile(r"^\s*from app\.(\w+)", re.MULTILINE)


def layer_of(path: Path) -> str:
    return path.relative_to(APP).with_suffix("").parts[0]


MODULES = sorted(path for path in APP.rglob("*.py") if path != APP / "__init__.py")


@pytest.mark.parametrize("path", MODULES, ids=lambda path: str(path.relative_to(APP)))
def test_modules_import_only_from_lower_layers(path: Path) -> None:
    layer = layer_of(path)
    assert layer in LAYERS, f"app/{layer} belongs to no layer: add it to LAYERS"
    upward = [
        imported
        for imported in IMPORT.findall(path.read_text(encoding="utf-8"))
        if LAYERS[imported] > LAYERS[layer]
    ]
    assert not upward, f"{path.relative_to(APP)} imports from a higher layer: {upward}"
