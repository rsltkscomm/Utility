# utils/test_context.py
import threading


class TestContext:
    """Thread-safe test context for parallel execution"""
    _local = threading.local()

    @property
    def datatable(self):
        return getattr(self._local, 'datatable', None)

    @datatable.setter
    def datatable(self, value):
        self._local.datatable = value

    @property
    def method_name(self):
        return getattr(self._local, 'method_name', None)

    @method_name.setter
    def method_name(self, value):
        self._local.method_name = value

    @property
    def sheet_name(self):
        return getattr(self._local, 'sheet_name', None)

    @sheet_name.setter
    def sheet_name(self, value):
        self._local.sheet_name = value

    @property
    def current_row(self):
        return getattr(self._local, 'current_row', None)

    @current_row.setter
    def current_row(self, value):
        self._local.current_row = value

    @property
    def current_testcase_id(self):
        return getattr(self._local, 'current_testcase_id', None)

    @current_testcase_id.setter
    def current_testcase_id(self, value):
        self._local.current_testcase_id = value

    @property
    def current_scenario_name(self):
        return getattr(self._local, 'current_scenario_name', None)

    @current_scenario_name.setter
    def current_scenario_name(self, value):
        self._local.current_scenario_name = value


# Create a singleton instance
TestContext = TestContext()
