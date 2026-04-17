# utils/excel_util.py
from .test_context import TestContext


class ExcelUtil:

    @staticmethod
    def get_value(column):
        """Get value from Excel based on current test context"""
        try:
            # Access thread-local attributes
            table = TestContext.datatable
            sheet_name = TestContext.sheet_name
            current_row = TestContext.current_row

            # Debug print
            print(f"ExcelUtil - sheet: {sheet_name}, row: {current_row}, column: {column}")

            if not sheet_name:
                print(f"Warning: sheet_name is None for column '{column}'")
                return ""

            if not current_row:
                print(f"Warning: current_row is None for column '{column}'")
                return ""

            if not table:
                print(f"Warning: datatable is None for column '{column}'")
                return ""

            # Get value from Excel
            value = table.get_cell_data(sheet_name, column, current_row)
            print(f"ExcelUtil - Retrieved value: '{value}'")

            return value

        except Exception as e:
            print(f"Error getting Excel value for column '{column}': {str(e)}")
            import traceback
            traceback.print_exc()
            return ""