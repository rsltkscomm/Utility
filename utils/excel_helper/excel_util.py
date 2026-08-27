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

    # @staticmethod
    # def write_value(column, value):
    #     """Write value to Excel based on current test context."""
    #     try:
    #         table = TestContext.datatable
    #         sheet_name = TestContext.sheet_name
    #         current_row = TestContext.current_row
    #
    #         if not sheet_name:
    #             print(f"Warning: sheet_name is None for column '{column}'")
    #             return False
    #
    #         if current_row is None:
    #             print(f"Warning: current_row is None for column '{column}'")
    #             return False
    #
    #         if not table:
    #             print(f"Warning: datatable is None for column '{column}'")
    #             return False
    #
    #         table.set_cell_data(sheet_name,column,current_row,value)
    #
    #         print( f"ExcelUtil - Written value '{value}' "f"to sheet '{sheet_name}', row '{current_row}', column '{column}'")
    #         return True
    #
    #     except Exception as e:
    #         print(f"Error writing Excel value for column '{column}': {str(e)}")
    #         import traceback
    #         traceback.print_exc()
    #         return False

    @staticmethod
    def write_value(sheet_name, row_num, col_num, value):
        """Write value to the current Excel file for a specific sheet, row and column."""
        try:
            table = TestContext.datatable

            if not table:
                print("Warning: datatable is None")
                return False

            table.set_cell_data(
                sheet_name,
                row_num,
                col_num,
                value
            )

            print(
                f"ExcelUtil - Successfully wrote '{value}' "
                f"to sheet '{sheet_name}', "
                f"row '{row_num}', column '{col_num}'"
            )

            return True

        except Exception as e:
            print(
                f"Error writing value to sheet '{sheet_name}', "
                f"row '{row_num}', column '{col_num}': {str(e)}"
            )
            return False

