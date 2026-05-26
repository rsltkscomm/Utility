import os
import sys

import pytest
from dotenv import load_dotenv
from utils.ini_file_reader.config_reader import ConfigReader

env_path = os.path.join(os.path.dirname(__file__), 'environment.env')
if os.path.exists(env_path):
    load_dotenv(env_path)

from utils.constants.framework_constants import FrameworkConstants

project = os.getenv("PROJECT_NAME") or "Resul"
FrameworkConstants.PROJECT_NAME = project

import conftest_healing

conftest_healing.install_healing_overlay()

from utils.baseclass.HealingPlaywrightActions import HealingPlaywrightActions
from utils.reporting.custom_reporter import DetailedTestReporter

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def _log_heal_to_report(message: str):
    try:
        from utils.excel_helper.test_context import TestContext

        test_case_id = getattr(TestContext, "current_testcase_id", None)
        if test_case_id:
            DetailedTestReporter.log_step(
                action=message,
                expected_result="Locator healed",
                actual_result=message,
                status=True,
            )
    except Exception:
        pass


@pytest.fixture
def actions(browser_instance):
    """Overrides utils.pytest_plugins.core.actions with healing-enabled actions."""
    healing_actions = HealingPlaywrightActions(browser_instance)
    healing_actions.register_heal_callback(_log_heal_to_report)
    return healing_actions


pytest_plugins = [
    "utils.pytest_plugins.browser",
    "utils.pytest_plugins.core",
    "utils.pytest_plugins.excel",
    "utils.pytest_plugins.hooks",
    "utils.pytest_plugins.reporting",
    "fixtures.pages",
    "fixtures.report",
    "fixtures.file_loader",
    "fixtures.step_loader",
]


def pytest_addoption(parser):
    parser.addoption("--UserName", action="store", default=None)
    parser.addoption("--Environment", action="store", default=None)
    parser.addoption("--Browser", action="store", default=None)
    parser.addoption("--SuiteName", action="store", default=None)
    parser.addoption("--UPDATE_ZEPHYR_EXECUTION", action="store", default=None)
    parser.addoption("--REPORT_BUG", action="store", default=None)
    parser.addoption("--recipientEmails", action="store", default=None)
    parser.addoption("--subject", action="store", default=None)
    parser.addoption("--isReportSend", action="store", default=None)
    parser.addoption("--reportType", action="store", default=None)
    parser.addoption("--reportFileName", action="store", default=None)
    parser.addoption("--updatedailychecklistexcel", action="store", default=None)
    parser.addoption("--reportTitle", action="store", default=None)
    parser.addoption("--DateWiseReport", action="store", default=None)
    parser.addoption("--ReleasewiseReport", action="store", default=None)
    parser.addoption("--AccountWiseReport", action="store", default=None)


def pytest_configure(config):
    try:
        import requests
        from utils.services.healing_config import healing_enabled

        if healing_enabled():
            base = os.getenv("MEDIA_SERVER_URL", "").rstrip("/")
            if base:
                spec = requests.get(f"{base}/openapi.json", timeout=5).json()
                if not any("locator" in p for p in spec.get("paths", {})):
                    print(
                        "\n[HEALING] WARNING: /locators API not on media server. "
                        "Deploy updated main.py on VM and restart uvicorn. "
                        "Run: python scripts/verify_healing.py\n"
                    )
    except Exception:
        pass

    custom_options = [
        "UserName", "Environment", "Browser", "SuiteName",
        "UPDATE_ZEPHYR_EXECUTION", "REPORT_BUG", "recipientEmails",
        "subject", "isReportSend", "reportType", "reportFileName",
        "updatedailychecklistexcel", "reportTitle", "DateWiseReport",
        "ReleasewiseReport", "AccountWiseReport"
    ]
    for key in custom_options:
        value = getattr(config.option, key, None)
        if value is not None:
            ConfigReader.set_runtime_property(key, value)

            # If the property is Environment, also ensure it's available in os.environ
            if key.lower() == "environment":
                os.environ["Environment"] = str(value)
