from typing import List

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--no-upgrade", action="store_true", default=False, help="do not run upgrade tests"
    )


# Adapted from
# https://docs.pytest.org/en/latest/example/simple.html#control-skipping-of-tests-according-to-command-line-option
def pytest_collection_modifyitems(config: pytest.Config, items: List[pytest.Item]) -> None:
    if config.getoption("--no-upgrade"):
        skip_upgrade = pytest.mark.skip(reason="--no-upgrade option was given")
        for item in items:
            if "upgrade" in item.keywords:
                item.add_marker(skip_upgrade)
