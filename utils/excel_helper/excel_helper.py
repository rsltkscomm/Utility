# utils/excel_helper.py
def method_name_to_scenario(method_name):
    """Convert pytest method name to Excel scenario name format"""
    scenario = method_name

    # Remove parameters in brackets if present (e.g. [arg1-arg2])
    if '[' in scenario:
        scenario = scenario.split('[')[0]

    return scenario


def is_tcid_found(test_context):
    """Find TCID in Excel and update test context"""
    table = test_context.datatable
    method_name = test_context.method_name

    if table is None:
        print("Datatable not initialized")
        return False

    print(f"Searching for method: {method_name}")

    # Convert method name to scenario name format (preserving underscores)
    expected_scenario = method_name_to_scenario(method_name)
    print(f"Looking for scenario: '{expected_scenario}'")

    # Get all sheets
    sheet_names = table.get_sheet_names()

    for sheet in sheet_names:
        try:
            row_count = table.get_row_count(sheet)

            if row_count < 1:
                continue

            # row_count is len(df), so range should be to len(df) + 2
            # to include all rows (starting from Excel row 2)
            for i in range(2, row_count + 2):
                try:
                    cell_value = table.get_cell_data(sheet, "Method_Name", i)
                    cell_value_str = str(cell_value).strip() if cell_value else ""

                    # Compare with the expected scenario name
                    if cell_value_str == expected_scenario:
                        print(f"PASS: TCID match found for -> {method_name}")
                        print(f"      in sheet -> {sheet}, row -> {i}")

                        test_context.sheet_name = sheet
                        test_context.current_row = i
                        return True
                except Exception:
                    continue
        except Exception:
            continue

    print(f"FAIL: TCID not found for method: {method_name}")
    return False