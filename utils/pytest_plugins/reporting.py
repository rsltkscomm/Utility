import os
import time
from utils.reporting.custom_reporter import DetailedTestReporter, SummaryReportGenerator
from dotenv import load_dotenv

def pytest_sessionstart(session):
    load_dotenv()
    DetailedTestReporter.create_detail_report()

def pytest_sessionfinish(session, exitstatus):
    DetailedTestReporter.save_worker_state()

    worker_id = os.getenv("PYTEST_XDIST_WORKER")

    if worker_id is None or worker_id == "master":
        time.sleep(2)
        DetailedTestReporter.load_all_worker_states()
        SummaryReportGenerator.generate_final_report()