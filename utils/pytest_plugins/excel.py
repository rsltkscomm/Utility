import os
import pytest

from utils.excel_helper.excel_reader import ExcelReader
from utils.ini_file_reader.config_reader import ConfigReader


@pytest.fixture(scope="session")
def excel_reader():
    project_root = os.getcwd()
    username = ConfigReader.get_property("UserName").lower()
    environment = ConfigReader.get_property("Environment").lower()
    excel_name = "TestData.xlsx"
    if environment == "team":
        excel_name = f"TestData_{environment}_{username}.xlsx"
    elif environment in ("run", "run19", "run24", "run23"):
        excel_name = f"TestData_{username}.xlsx"
    excel_path = os.path.join(
        project_root,
        "loc_utils",
        "data",
        excel_name
    )
    return ExcelReader(excel_path)