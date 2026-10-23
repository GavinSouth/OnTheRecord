"""Smoke test: proves the package imports and the toolchain runs."""

import ontherecord
from ontherecord.main import create_app


def test_package_imports() -> None:
    assert ontherecord.__version__ == "0.1.0"


def test_app_is_importable() -> None:
    assert callable(create_app)
