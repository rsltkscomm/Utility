import os
import time
from datetime import datetime
from utils.reporting.custom_reporter import DetailedTestReporter, SummaryReportGenerator
from dotenv import load_dotenv


def pytest_sessionstart(session):
    load_dotenv()

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

        # Optional: pass to your report generator
        SummaryReportGenerator.generate_final_report()