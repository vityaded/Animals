from __future__ import annotations

from typing import Optional

import pytest


def _description_for_item(item: pytest.Item) -> str:
    docstring = None
    if hasattr(item, "function"):
        docstring = getattr(item.function, "__doc__", None)
    if docstring:
        return " ".join(docstring.strip().split())
    return f"No description provided for {item.name}."


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo) -> None:
    outcome = yield
    report = outcome.get_result()
    if report.when == "call":
        report.description = _description_for_item(item)


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    if report.when != "call":
        return
    description: Optional[str] = getattr(report, "description", None)
    outcome = report.outcome.upper()
    test_name = report.nodeid
    detail = description or "No description available."
    print(f"\nTEST REPORT: {test_name}\nDESCRIPTION: {detail}\nRESULT: {outcome}\n")
