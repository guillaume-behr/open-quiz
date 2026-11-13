"""The packages of app/ only import from the layers below them.

From the bottom up: enums; core and models; schemas; domain; records; live;
services; responses; routers; and application, which assembles everything.
docs/architecture.md describes each package.
"""

import ast
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "app"
# One entry per layer, lowest first. Packages listed together import each
# other: the tables of models need the declarative base of core, whose
# guards load the users those tables describe.
ORDER: list[tuple[str, ...]] = [
    ("enums",),
    ("core", "models"),
    ("schemas",),
    ("domain",),
    ("records",),
    ("live",),
    ("services",),
    ("responses",),
    ("routers",),
    ("application",),
]
LAYERS = {package: rank for rank, group in enumerate(ORDER) for package in group}
MODULES = sorted(path for path in APP.rglob("*.py") if path != APP / "__init__.py")


def layer_of(path: Path) -> str:
    return path.relative_to(APP).with_suffix("").parts[0]


def imported_packages(source: str) -> set[str]:
    """The packages of app/ a module imports, whatever the form of the import."""
    packages: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level:
            # Relative imports would escape this check: app/ uses none.
            packages.add("a relative import")
            continue
        elif isinstance(node, ast.ImportFrom) and node.module == "app":
            names = [f"app.{alias.name}" for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        else:
            continue
        packages.update(name.split(".")[1] for name in names if name.startswith("app."))
    return packages


@pytest.mark.parametrize("path", MODULES, ids=lambda path: str(path.relative_to(APP)))
def test_modules_import_only_from_lower_layers(path: Path) -> None:
    layer = layer_of(path)
    assert layer in LAYERS, f"app/{layer} belongs to no layer: add it to ORDER"
    imported = imported_packages(path.read_text(encoding="utf-8")) - {layer}
    unknown = sorted(imported - LAYERS.keys())
    assert not unknown, f"{path.relative_to(APP)} imports outside the layers: {unknown}"
    upward = sorted(name for name in imported if LAYERS[name] > LAYERS[layer])
    assert not upward, f"{path.relative_to(APP)} imports from a higher layer: {upward}"


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("import app.services.grading", {"services"}),
        ("from app import routers, models", {"routers", "models"}),
        ("from app.core.config import Settings", {"core"}),
        ("def late():\n    from app.live import hub", {"live"}),
        ("from . import sibling", {"a relative import"}),
        ("import json\nfrom pathlib import Path", set()),
    ],
)
def test_every_form_of_import_is_seen(source: str, expected: set[str]) -> None:
    assert imported_packages(source) == expected
