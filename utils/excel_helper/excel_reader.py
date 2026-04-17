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