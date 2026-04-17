import os
import pytest

from utilities_py.excel_helper.excel_reader import ExcelReader


@pytest.fixture(scope="session")
def excel_reader():
    project_root = os.getcwd()
    excel_path = os.path.join(project_root, "utils/data", "TestData.xlsx")
    return ExcelReader(excel_path)