import datetime
import os
import uuid

import pytest
from dotenv import load_dotenv

load_dotenv()

from utils.excel_helper.test_context import TestContext
from utils.ini_file_reader.config_reader import ConfigReader
from utils.reporting.custom_reporter import DetailedTestReporter

from utils.services.media_uploader import MediaUploader


MEDIA_UPLOADER = MediaUploader()


@pytest.fixture(scope="function")
def browser_instance(playwright,request):
    if any(mark in request.node.keywords for mark in ["api", "login_api"]):
        yield None
        return
    os.makedirs("videos", exist_ok=True)

    browser_name = ConfigReader.get_property("Browser").lower()

    service_url = os.getenv("PLAYWRIGHT_SERVICE_URL", "").strip()
    service_access_token = os.getenv("PLAYWRIGHT_SERVICE_ACCESS_TOKEN", "").strip()
    service_os = os.getenv("PLAYWRIGHT_SERVICE_OS", "windows").strip()

    if service_url:
        run_id = os.getenv("PLAYWRIGHT_SERVICE_RUN_ID", str(uuid.uuid4()))
        ws_endpoint = (
            f"{service_url}&os={service_os}&runId={run_id}&api-version=2023-10-01-preview"
            if "?" in service_url
            else f"{service_url}?os={service_os}&runId={run_id}&api-version=2023-10-01-preview"
        )
        headers = {"Authorization": f"Bearer {service_access_token}"} if service_access_token else None
        browser = playwright.chromium.connect(
            ws_endpoint=ws_endpoint,
            headers=headers,
            timeout=60000,
        )
    else:
        if browser_name in ["chrome", "chromium"]:
            browser = playwright.chromium.launch(headless=False)
        elif browser_name == "firefox":
            browser = playwright.firefox.launch(headless=False)
        elif browser_name == "webkit":
            browser = playwright.webkit.launch(headless=False)
        elif browser_name == "chromeheadless":
            browser = playwright.chromium.launch(headless=True)
        else:
            raise ValueError("Unsupported browser")

    worker_id = os.getenv("PYTEST_XDIST_WORKER", "master")
    video_dir = os.path.join("videos", worker_id)
    os.makedirs(video_dir, exist_ok=True)

    context = browser.new_context(
        record_video_dir=video_dir,
        record_video_size={"width": 1280, "height": 720},
    )

    page = context.new_page()
    TestContext.video_path = None

    yield page

    video = page.video
    context.close()

    try:
        if video:
            video_path = video.path()
            if os.path.exists(video_path):
                timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
                method_name = TestContext.method_name or "test"

                new_path = os.path.join(video_dir, f"{method_name}_{timestamp}.webm")
                os.rename(video_path, new_path)

                if os.path.getsize(new_path) > 0:
                    TestContext.video_path = new_path
                    print(f"\n[VIDEO] Video saved for remote upload: {new_path}")
                    test_case_id = getattr(TestContext, "current_testcase_id", None)
                    if test_case_id:
                        try:
                            url = MEDIA_UPLOADER.upload(
                                file_path=new_path,
                                test_name=test_case_id,
                                file_type="video",
                                run_id=os.getenv("RUN_ID", ""),
                                worker_id=worker_id,
                            )
                            if url:
                                DetailedTestReporter.attach_video(test_case_id, url)
                                print(f"\n[VIDEO] Uploaded video and attached URL: {url}")
                        except Exception as upload_error:
                            print(f"[VIDEO] Upload failed: {upload_error}")
    except Exception as exc:
        print(f"[ERROR] Video handling error: {exc}")

    browser.close()
