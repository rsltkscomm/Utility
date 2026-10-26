import os
import time
from datetime import datetime
from utils.ini_file_reader.config_reader import ConfigReader
from utils.reporting.custom_reporter import DetailedTestReporter, SummaryReportGenerator
from utils.excel_helper.excel_report_generator import ExcelReportGenerator
from utils.constants.framework_constants import FrameworkConstants


def pytest_sessionstart(session):
    ConfigReader._load_config()

    # Store start time
    # Store start time
    start_time = datetime.now()
    formatted_start_time = start_time.strftime("%d-%m-%y %I:%M:%S %p")
    Execution_start_time = start_time.strftime("%d-%b-%Y %H:%M:%S")
    os.environ["Execution_start_time"] = Execution_start_time

    print(f"Start Time: {formatted_start_time}")

    # Store globally (safe for xdist)
    os.environ["START_TIME"] = formatted_start_time
    os.environ["START_TIME_RAW"] = start_time.isoformat()

    DetailedTestReporter.create_detail_report()


def pytest_sessionfinish(session, exitstatus):
    try:

        test_executions = (
            DetailedTestReporter.get_test_executions()
        )
        flags = (
            f"{ConfigReader.get_property('DateWiseReport')},"
            f"{ConfigReader.get_property('ReleasewiseReport')},"
            f"{ConfigReader.get_property('AccountWiseReport')}"
        )
        ExcelReportGenerator.write_test_executions_to_excel(
            default_path=FrameworkConstants.ONEDRIVE_BASE_PATH,
            sheet_names="Daily,Release,Account",
            flags=flags,
            releases=ConfigReader.get_property('ReleaseVersion'),
            account_header=ConfigReader.get_property('UserName'),
            module_name=ConfigReader.get_property('SuiteName'),
            test_executions=test_executions
        )

        print("Excel report generated successfully.")

    except Exception as e:

        print(
            f"Error while generating Excel report: {str(e)}"
        )
    DetailedTestReporter.save_worker_state()

    worker_id = os.getenv("PYTEST_XDIST_WORKER")

    # Run only in master
    if worker_id is None or worker_id == "master":
        time.sleep(2)
        DetailedTestReporter.load_all_worker_states()

        # Get start time safely
        start_time_str = os.getenv("START_TIME_RAW")
        start_time = datetime.fromisoformat(start_time_str)

        # End time
        end_time = datetime.now()
        formatted_end_time = end_time.strftime("%d-%m-%y %I:%M:%S %p")

        # Total duration
        total_time = end_time - start_time
        total_seconds = int(total_time.total_seconds())

        formatted_total_time = f"{total_seconds // 3600:02}:{(total_seconds % 3600) // 60:02}:{total_seconds % 60:02}"

        print(f"\nStart Time : {os.getenv('START_TIME')}")
        print(f"End Time   : {formatted_end_time}")
        os.environ["End_TIME"] = formatted_end_time
        os.environ["Total_duration"] = formatted_total_time
        print(f"Duration   : {formatted_total_time}")

        try:
            from utils.test_management.jira_zephyr_client import update_zephyr_and_report_defects

            update_zephyr_and_report_defects()
        except Exception as exc:
            print(f"[JIRA/ZEPHYR] Integration skipped or failed: {exc}")

        # Optional: pass to your report generator
        SummaryReportGenerator.generate_final_report()
