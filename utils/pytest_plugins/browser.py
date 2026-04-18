import os

import pytest

from utils.baseclass import TestContext
from utils.ini_file_reader.config_reader import ConfigReader
from utils.reporting.custom_reporter import DetailedTestReporter


@pytest.fixture(scope="function")
def browser_instance(playwright, request):
    global browser
    os.makedirs("videos", exist_ok=True)
    workspace_url = ConfigReader.get_property("workspace_url").strip()
    service_token = ConfigReader.get_property("service_token").strip()
    print(f"URL {workspace_url}")
    print(f"TOKEN LENGTH {len(service_token)}")
    connect_url = f"{workspace_url}?access-token={service_token}"
    cloud_execution = ConfigReader.get_property("cloud_execution").strip()
    if cloud_execution == "yes":
        try:
            browser = playwright.chromium.connect(
                workspace_url,
                headers={"Authorization": f"Bearer {service_token}"}
            )
        except Exception as e:
            print(e)
    else:
        browser_name = ConfigReader.get_property("Browser").lower()
        if browser_name in ["chrome", "chromium"]:
            browser = playwright.chromium.launch(headless=False)
        elif browser_name == "firefox":
            browser = playwright.firefox.launch(headless=False)
        elif browser_name == "webkit":
            browser = playwright.webkit.launch(headless=False)
        elif browser_name == "chromeheadless":
            browser = playwright.chromium.launch(headless=True)
        else:
            raise ValueError(f"Unsupported browser: {browser_name}")

    worker_id = os.getenv("PYTEST_XDIST_WORKER", "master")
    video_dir = f"videos/{worker_id}"
    os.makedirs(video_dir, exist_ok=True)
    context = browser.new_context(
        record_video_dir=video_dir,
        record_video_size={"width": 1280, "height": 720}
    )
    page = context.new_page()
    TestContext.video_path = None
    yield page
    video = page.video
    context.close()
    try:
        if video:
            video_path = video.path()
            print(f"\n[VIDEO] Video recorded at: {video_path}")
            if os.path.exists(video_path):
                import datetime
                timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
                method_name = TestContext.method_name or "test"
                new_video_name = f"{method_name}_{timestamp}.webm"
                new_video_path = os.path.join(video_dir, new_video_name)
                os.rename(video_path, new_video_path)
                file_size = os.path.getsize(new_video_path)
                print(f"[VIDEO] Renamed video: {new_video_path}")
                print(f"[VIDEO] Video file size: {file_size} bytes")
                if file_size > 0:
                    TestContext.video_path = new_video_path
                    try:
                        import base64
                        test_case_id = getattr(TestContext, "current_testcase_id", None)
                        with open(new_video_path, "rb") as video_file:
                            encoded_string = base64.b64encode(video_file.read()).decode()
                            video_href = f"data:video/webm;base64,{encoded_string}"
                            DetailedTestReporter.attach_video(test_case_id, video_href)
                            print(f"\n[VIDEO] Successfully mounted Base64 Standalone Video Payload!")
                    except Exception as e:
                        print(f"[VIDEO] ❌ Error archiving Base64 Payload: {e}")
                else:
                    print("[VIDEO] Video file is empty")
            else:
                print(f"[VIDEO] Video file does not exist: {video_path}")
    except Exception as e:
        print(f"[ERROR] Error handling video: {e}")
    browser.close()