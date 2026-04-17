import os
from collections import defaultdict

from utilities_py.constants.framework_constants import FrameworkConstants


class CustomFeatureGenerator:
    def __init__(self, sheet_name: str):
        self.project_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        self.excel_path = FrameworkConstants.get_script_details_file()
        self.sheet_name = sheet_name
        self.custom_feature_dir = os.path.join(
            self.project_root, "features", "customfeature"
        )

    def parse_steps(self, steps_text: str) -> list[str]:
        if not steps_text or str(steps_text).strip() == "":
            return []
        return [line.strip() for line in str(steps_text).splitlines() if line.strip()]

    def parse_examples(self, examples_text: str):
        if not examples_text or str(examples_text).strip() == "":
            return [], []

        rows = []
        headers = []

        example_sets = [item.strip() for item in str(examples_text).split(";") if item.strip()]

        for example in example_sets:
            pairs = [pair.strip() for pair in example.split(",") if pair.strip()]
            row_data = {}

            for pair in pairs:
                if "=" in pair:
                    key, value = pair.split("=", 1)
                    key = key.strip()
                    value = value.strip()
                    row_data[key] = value

                    if key not in headers:
                        headers.append(key)

            if row_data:
                rows.append(row_data)

        return headers, rows

    def get_original_feature_path(self, feature_file_path: str) -> str:
        feature_file_path = feature_file_path.replace("\\", "/").strip()

        if feature_file_path.startswith("features/"):
            return os.path.join(self.project_root, feature_file_path)

        return os.path.join(self.project_root, "features", feature_file_path)

    def get_custom_feature_path(self, feature_file_path: str) -> str:
        os.makedirs(self.custom_feature_dir, exist_ok=True)
        file_name = os.path.basename(feature_file_path)
        return os.path.join(self.custom_feature_dir, file_name)

    def read_feature_header(self, feature_file_path: str) -> str:
        """
        Read the existing feature file and return the same Feature: line.
        If not found, fall back to file name based feature title.
        """
        original_feature_path = self.get_original_feature_path(feature_file_path)

        if os.path.exists(original_feature_path):
            with open(original_feature_path, "r", encoding="utf-8") as file:
                for line in file:
                    stripped_line = line.strip()
                    if stripped_line.startswith("Feature:"):
                        return stripped_line

        file_name = os.path.basename(feature_file_path)
        feature_name = os.path.splitext(file_name)[0]
        feature_name = feature_name.replace("_", " ").replace("-", " ").title()
        return f"Feature: {feature_name}"

    def create_or_replace_feature_files(self, rows) -> list[str]:
        grouped_rows = defaultdict(list)

        for row in rows:
            feature_file = str(row.get("feature_file", "")).strip()
            scenario_name = str(row.get("scenario_name", "")).strip()
            steps = self.parse_steps(row.get("steps", ""))

            if not feature_file:
                print(f"Skipping custom row in sheet '{self.sheet_name}' because feature_file is empty.")
                continue

            if not scenario_name:
                print(f"Skipping custom row in sheet '{self.sheet_name}' because scenario_name is empty.")
                continue

            if not steps:
                print(f"Skipping custom row '{scenario_name}' because steps are empty.")
                continue

            grouped_rows[feature_file].append(row)

        created_feature_files = []

        for feature_file, feature_rows in grouped_rows.items():
            custom_feature_path = self.get_custom_feature_path(feature_file)
            feature_header = self.read_feature_header(feature_file)

            lines = [feature_header, ""]

            for row in feature_rows:
                tag = str(row.get("tag", "")).strip()
                scenario_type = str(row.get("scenario_type", "scenario")).strip().lower()
                scenario_name = str(row.get("scenario_name", "")).strip()
                steps = self.parse_steps(row.get("steps", ""))
                examples_text = row.get("examples", "")

                if tag:
                    if not tag.startswith("@"):
                        tag = f"@{tag}"
                    lines.append(f"  {tag}")

                if scenario_type == "outline":
                    lines.append(f"  Scenario Outline: {scenario_name}")
                else:
                    lines.append(f"  Scenario: {scenario_name}")

                for step in steps:
                    lines.append(f"    {step}")

                if scenario_type == "outline":
                    headers, example_rows = self.parse_examples(examples_text)

                    if headers and example_rows:
                        lines.append("")
                        lines.append("    Examples:")
                        lines.append("      | " + " | ".join(headers) + " |")

                        for row_data in example_rows:
                            values = [str(row_data.get(header, "")) for header in headers]
                            lines.append("      | " + " | ".join(values) + " |")

                lines.append("")

            with open(custom_feature_path, "w", encoding="utf-8") as file:
                file.write("\n".join(lines))

            print(f"Custom feature file created/replaced: {custom_feature_path}")
            created_feature_files.append(custom_feature_path)

        return created_feature_files