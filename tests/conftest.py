"""Keep a public checkout testable without silently passing missing-data checks."""

from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-data",
        action="store_true",
        default=False,
        help="Run data integration tests; missing private inputs are failures in this mode.",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--run-data"):
        return
    skip = pytest.mark.skip(reason="requires approved local data; opt in with --run-data")
    for item in items:
        if "data" in item.keywords:
            item.add_marker(skip)
