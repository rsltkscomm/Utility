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


def _register_network_capture(page):
    """Passively record every XHR/fetch call the browser makes during a UI scenario.

    Independent of the API-validation flow (steps/API/*, api/clients/BaseClient) -
    this only observes real browser network traffic behind the scenes.
    """

    def _on_request_finished(request):
        # request.timing is only fully populated once the request has
        # finished (responseEnd is -1 while the response body is still
        # streaming), so we must listen on "requestfinished", not
        # "response" - otherwise durationMillis is always captured as 0.
        try:
            if request.resource_type not in ("xhr", "fetch"):
                return

            response = request.response()
            if response is None:
                return

            test_case_ids = getattr(TestContext, "current_testcase_ids", None)
            if not test_case_ids:
                single = getattr(TestContext, "current_testcase_id", None)
                test_case_ids = [single] if single else [None]

            duration_ms = 0
            try:
                timing = request.timing
                if timing and timing.get("responseEnd", -1) >= 0:
                    duration_ms = int(timing["responseEnd"])
            except Exception:
                pass

            try:
                request_headers = request.all_headers()
            except Exception:
                request_headers = None

            try:
                response_headers = response.all_headers()
            except Exception:
                response_headers = None

            try:
                response_body = response.text()
            except Exception:
                response_body = None

            for test_case_id in test_case_ids:
                DetailedTestReporter.record_api_call(
                    test_case_id=test_case_id,
                    method=request.method,
                    url=request.url,
                    status_code=response.status,
                    duration_ms=duration_ms,
                    request_body=request.post_data,
                    response_body=response_body,
                    request_headers=request_headers,
                    response_headers=response_headers,
                    success=response.ok,
                )
        except Exception:
            # Network telemetry must never break the actual UI test.
            pass

    page.on("requestfinished", _on_request_finished)


@pytest.fixture(scope="function")
def browser_instance(playwright,request):
    if any(mark in request.node.keywords for mark in ["api", "login_api"]):
        yield None
        return
    os.makedirs("videos", exist_ok=True)

    browser_name = ConfigReader.get_property("Browser").lower()
    environment = ConfigReader.get_property("Environment").upper()

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
        ignore_https_errors=True
    )

    page = context.new_page()
    TestContext.video_path = None
    _register_network_capture(page)

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
                    test_case_ids = getattr(TestContext, "current_testcase_ids", None) or (
                        [test_case_id] if test_case_id else []
                    )
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
                                for tc_id in test_case_ids:
                                    DetailedTestReporter.attach_video(tc_id, url)
                                print(f"\n[VIDEO] Uploaded video and attached URL: {url}")
                        except Exception as upload_error:
                            print(f"[VIDEO] Upload failed: {upload_error}")
    except Exception as exc:
        print(f"[ERROR] Video handling error: {exc}")

    browser.close()
