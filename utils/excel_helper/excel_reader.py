import pandas as pd


class ExcelReader:

    def __init__(self, file_path):
        self.file_path = file_path
        self.workbook = pd.ExcelFile(file_path)
        self.sheets = {}

    def get_sheet_names(self):
        return self.workbook.sheet_names

    def load_sheet(self, sheet_name):
        if sheet_name not in self.sheets:
            if sheet_name not in self.workbook.sheet_names:
                raise Exception(
                    f"Sheet '{sheet_name}' not found. Available sheets: {self.workbook.sheet_names}"
                )

            df = pd.read_excel(self.file_path, sheet_name=sheet_name, header=0)

            if df is None or df.empty:
                # Return an empty DataFrame instead of raising exception
                print(f"Warning: Sheet '{sheet_name}' is empty")
                df = pd.DataFrame()  # Empty DataFrame

            # SAFE header cleanup
            if not df.empty:
                df.columns = df.columns.map(lambda x: str(x).strip())

            self.sheets[sheet_name] = df

        return self.sheets[sheet_name]

    def get_row_count(self, sheet_name):
        df = self.load_sheet(sheet_name)
        return len(df)

    def get_cell_data(self, sheet_name, column_name, row):

        df = self.load_sheet(sheet_name)

        column_name = column_name.strip()

        if column_name not in df.columns:
            raise Exception(f"Column '{column_name}' not found in sheet '{sheet_name}'")

        try:
            value = df.iloc[row - 2][column_name]
            return "" if pd.isna(value) else str(value)
        except Exception:
            return ""

    def set_cell_data(self, sheet_name, row_num, col_num, value):
        """Write a value to a specific Excel sheet, row, and column."""
        try:
            if sheet_name not in self.workbook.sheet_names:
                raise Exception(
                    f"Sheet '{sheet_name}' not found. "
                    f"Available sheets: {self.workbook.sheet_names}"
                )

            df = pd.read_excel(
                self.file_path,
                sheet_name=sheet_name,
                header=0
            )

            # Convert DataFrame columns to object type
            # so string values can be written to empty/numeric columns.
            df = df.astype(object)

            # Excel row 1 = header
            # Excel row 2 = first data row
            df_row = row_num - 2

            # Excel column 1 = first column
            df_col = col_num - 1

            if df_row < 0:
                raise ValueError(f"Invalid row number: {row_num}")

            if df_col < 0 or df_col >= len(df.columns):
                raise ValueError(f"Invalid column number: {col_num}")

            # Add rows if required
            while len(df) <= df_row:
                df.loc[len(df)] = [None] * len(df.columns)

            # Get actual column name
            column_name = df.columns[df_col]

            # Write value
            df.at[df_row, column_name] = value

            # Save workbook
            with pd.ExcelWriter(
                    self.file_path,
                    engine="openpyxl",
                    mode="a",
                    if_sheet_exists="replace"
            ) as writer:

                df.to_excel(
                    writer,
                    sheet_name=sheet_name,
                    index=False
                )

            # Refresh cached data
            self.workbook = pd.ExcelFile(self.file_path)
            self.sheets.pop(sheet_name, None)

            print(
                f"ExcelReader - Successfully wrote value '{value}' "
                f"to sheet '{sheet_name}', "
                f"row '{row_num}', "
                f"column '{col_num}'"
            )

            return True

        except Exception as e:
            print(
                f"ExcelReader - Error writing value "
                f"to sheet '{sheet_name}', "
                f"row '{row_num}', "
                f"column '{col_num}': {str(e)}"
            )

            import traceback
            traceback.print_exc()

            return False

