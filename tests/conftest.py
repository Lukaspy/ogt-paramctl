"""Pytest configuration shared by unit, integration, and hardware tests."""
from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register CLI options used by hardware tests."""
    parser.addoption(
        "--resource",
        action="store",
        default=None,
        help=(
            "VISA resource string for hardware tests "
            "(e.g. 'GPIB0::17::INSTR' or 'USB0::0x2A8D::0xFE03::MY12345678::INSTR'). "
            "Required for tests marked @pytest.mark.hardware."
        ),
    )


@pytest.fixture
def visa_resource(request: pytest.FixtureRequest) -> str:
    """Return the user-supplied VISA resource string, or skip the test.

    Hardware tests depend on this fixture. They are skipped when ``--resource``
    is not provided so that ``pytest`` (with no arguments) stays green on
    machines without an instrument attached.
    """
    resource = request.config.getoption("--resource")
    if resource is None:
        pytest.skip("--resource not provided; hardware test skipped")
    return str(resource)
