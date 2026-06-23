from utils.reporting.json_status_manager import JSONStatusManager


class WeeklyStatusManager:

    FILE_PATH = None
    EXISTS = False

    @staticmethod
    def read_last_7_days_status(_ignored_file_path=None) -> dict:

        return JSONStatusManager.read_last_7_days_status()

    @staticmethod
    def save_current_run(test_executions) -> None:
        """
        Persist today's test results into the JSON history file for the current
        suite + environment combination.

        Call this once inside SummaryReportGenerator.generate_final_report(),
        BEFORE generate_report_json() is called, like this:

            WeeklyStatusManager.save_current_run(
                DetailedTestReporter.get_test_executions()
            )

        This ensures the 7-day circles in the HTML report already include today.
        """
        JSONStatusManager.save_current_run(test_executions)