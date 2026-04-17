import pytest
from utilities_py.baseclass.PW_BaseClass import PlaywrightActions
from utilities_py.excel_helper.test_context import TestContext
from utilities_py.excel_helper.excel_helper import is_tcid_found

@pytest.fixture
def actions(browser_instance):
    return PlaywrightActions(browser_instance)

@pytest.fixture(autouse=True)
def setup_test(request, excel_reader):
    TestContext.datatable = excel_reader
    TestContext.method_name = request.node.name
    TestContext.sheet_name = None
    TestContext.current_row = None
    TestContext.video_path = None
    is_tcid_found(TestContext)

    yield

    TestContext.datatable = None
    TestContext.method_name = None
    TestContext.sheet_name = None
    TestContext.current_row = None
    TestContext.video_path = None