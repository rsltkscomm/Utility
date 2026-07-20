from utils.reporting.json_status_manager import JSONStatusManager


class WeeklyStatusManager:
    """
    Backward-compatible shim.

    custom_reporter.py still calls WeeklyStatusManager.read_last_7_days_status(...)
    and WeeklyStatusManager.save_current_run(...) — this class keeps that API
    intact while delegating all real work to the JSON-backed JSONStatusManager,
    so nothing in custom_reporter.py needs to change.

    FILE_PATH / EXISTS are kept only so old call sites that reference
    WeeklyStatusManager.FILE_PATH (e.g. as an argument placeholder) don't
    break. They are no longer used for anything — JSONStatusManager resolves
    its own project/suite/environment file path internally via ConfigReader.
    """

    FILE_PATH = None
    EXISTS = False

    @staticmethod
    def read_last_7_days_status(_ignored_file_path=None) -> dict:
        """
        Return the 7-slot history map consumed by the HTML report generator.
        The _ignored_file_path parameter is accepted (and ignored) purely so
        existing call sites like:
            WeeklyStatusManager.read_last_7_days_status(WeeklyStatusManager.FILE_PATH)
        keep working without modification.
        """
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