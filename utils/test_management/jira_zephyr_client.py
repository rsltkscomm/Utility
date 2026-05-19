import base64
import hashlib
import json
import mimetypes
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import unquote, urlparse

import requests

from utils.ini_file_reader.config_reader import ConfigReader
from utils.reporting.custom_reporter import DetailedTestReporter, ExecutionStatus, StepStatus


def _setting(key: str, default=None):
    value = ConfigReader.get_runtime_property(key, None)
    if value in (None, ""):
        value = os.getenv(key, None)
    if value in (None, ""):
        value = ConfigReader.get_property(key, default)
    return value


def _enabled(key: str, default: str = "No") -> bool:
    return str(_setting(key, default)).strip().lower() in {"1", "true", "yes", "y"}


def _status_to_zephyr(status: str) -> str:
    if status == ExecutionStatus.PASS:
        return "Pass"
    if status == ExecutionStatus.FAIL:
        return "Fail"
    return "Blocked"


@dataclass
class TestResult:
    test_case_key: str
    status: str
    execution: object


class JiraZephyrClient:
    def __init__(self):
        self.jira_base_url = str(_setting("JIRA_BASE_URL", "")).rstrip("/")
        self.jira_email = _setting("JIRA_EMAIL", "")
        self.jira_api_key = _setting("JIRA_API_KEY", "")
        self.zephyr_api_key = _setting("ZEPHYR_API_KEY", "")
        self.project_key = _setting("PROJECT_KEY", "")
        self.test_cycle_key = _setting("TEST_CYCLE_ID", _setting("TEST_CYCLE_KEY", ""))
        self.report_bug = _enabled("REPORT_BUG", _setting("reportdefect", "No"))
        self.update_zephyr = _enabled("UPDATE_ZEPHYR_EXECUTION", "No")
        self.bug_priority = _setting("BUG_PRIORITY", "High")
        self.bug_component = _setting("BUG_COMPONENT", "Automation Testing")
        self.bug_assignee = _setting("BUG_ASSIGNEE", "")
        self.test_case_id_field = _setting("TEST_CASE_ID_FIELD", "")
        self.report_version_field = _setting("REPORT_VERSION_FIELD", "customfield_10375")
        self.report_version = _setting("ReportVersion", "v1.0")
        self.check_duplicates = _enabled("CHECK_DUPLICATES", "true")
        self.report_script_failures = _enabled("REPORT_SCRIPT_FAILURE_BUGS", "No")
        self.timeout = int(_setting("CONNECTION_TIMEOUT_MS", _setting("READ_TIMEOUT_MS", "60")) or 60)

    def update_from_reporter(self):
        print(f"[JIRA/ZEPHYR] Flags: UPDATE_ZEPHYR_EXECUTION={self.update_zephyr}, REPORT_BUG={self.report_bug}")
        results = [
            TestResult(execution.test_case_id, execution.status, execution)
            for execution in DetailedTestReporter.get_test_executions()
            if execution.test_case_id
        ]
        self.update_test_results(results)

    def update_test_results(self, test_results: Iterable[TestResult]):
        for result in test_results:
            try:
                if self.update_zephyr:
                    self.update_single_test_result(result)
                if result.status == ExecutionStatus.FAIL and self.report_bug:
                    self.create_jira_bug_for_result(result)
            except Exception as exc:
                print(f"[JIRA/ZEPHYR] Error processing {result.test_case_key}: {exc}")

    def update_single_test_result(self, result: TestResult):
        self._require(self.zephyr_api_key, "ZEPHYR_API_KEY")
        self._require(self.project_key, "PROJECT_KEY")
        self._require(self.test_cycle_key, "TEST_CYCLE_ID")

        payload = {
            "projectKey": self.project_key,
            "testCycleKey": self.test_cycle_key,
            "testCaseKey": result.test_case_key,
            "statusName": _status_to_zephyr(result.status),
        }

        step_results = []
        for step in getattr(result.execution, "steps", []) or []:
            step_results.append({
                "statusName": "Pass" if step.status == StepStatus.PASS else "Fail"
            })
        if step_results:
            payload["testStepResults"] = step_results

        response = requests.post(
            "https://api.zephyrscale.smartbear.com/v2/testexecutions",
            json=payload,
            headers={
                "Authorization": f"Bearer {self.zephyr_api_key}",
                "Accept": "application/json",
            },
            timeout=self.timeout,
        )
        print(f"[ZEPHYR] {result.test_case_key} -> {payload['statusName']} | {response.status_code}")
        if response.status_code >= 400:
            print(f"[ZEPHYR] Response: {response.text}")
        response.raise_for_status()

    def create_jira_bug_for_result(self, result: TestResult) -> Optional[str]:
        self._require(self.jira_base_url, "JIRA_BASE_URL")
        self._require(self.jira_email, "JIRA_EMAIL")
        self._require(self.jira_api_key, "JIRA_API_KEY")
        self._require(self.project_key, "PROJECT_KEY")

        failure_reason = self._failure_reason(result.execution)
        if self._is_script_failure(failure_reason) and not self.report_script_failures:
            print(f"[JIRA] Skipping bug for script/framework failure in {result.test_case_key}: {failure_reason}")
            return None

        if self.check_duplicates:
            existing = self._find_duplicate_bug(result.test_case_key, failure_reason)
            if existing:
                print(f"[JIRA] Duplicate defect found for {result.test_case_key}: {existing}")
                self._record_bug(existing, result.test_case_key, failure_reason, created=False)
                return existing

        payload = {"fields": self._build_issue_fields(result, failure_reason)}
        response = requests.post(
            f"{self.jira_base_url}/rest/api/3/issue",
            json=payload,
            headers=self._jira_headers(),
            timeout=self.timeout,
        )

        if response.status_code != 201:
            print(f"[JIRA] Failed to create bug for {result.test_case_key}: {response.status_code}")
            print(f"[JIRA] Response: {response.text}")
            return None

        bug_key = response.json().get("key")
        print(f"[JIRA] Bug created for {result.test_case_key}: {bug_key}")
        self._record_bug(bug_key, result.test_case_key, failure_reason, created=True)
        self._attach_execution_files(bug_key, result.execution)
        self._link_bug_to_test_case(bug_key, result.test_case_key)
        return bug_key

    @staticmethod
    def _record_bug(bug_key: str, test_case_key: str, failure_reason: str, created: bool):
        if not bug_key:
            return

        raw_value = ConfigReader.get_runtime_property("ALLBUGS", "{}") or "{}"
        try:
            all_bugs = json.loads(raw_value) if isinstance(raw_value, str) else dict(raw_value)
        except Exception:
            all_bugs = {}

        all_bugs[bug_key] = {
            "testCaseKey": test_case_key,
            "failureReason": failure_reason,
            "created": created,
        }
        ConfigReader.setproperty("ALLBUGS", json.dumps(all_bugs, ensure_ascii=True))

    def _build_issue_fields(self, result: TestResult, failure_reason: str) -> dict:
        reason_id = self._failure_reason_id(failure_reason)
        fields = {
            "summary": f"AUTO BUG: {result.test_case_key} - {failure_reason[:180]}",
            "description": self._create_bug_description(result, failure_reason),
            "project": {"key": self.project_key},
            "issuetype": {"name": "Bug"},
            "labels": ["automation", f"auto_failure_{reason_id}"],
        }

        if self.bug_priority:
            fields["priority"] = {"name": self.bug_priority}
        if self.bug_component:
            fields["components"] = [{"name": self.bug_component}]
        if self.bug_assignee:
            fields["assignee"] = {"emailAddress": self.bug_assignee}
        if self.test_case_id_field:
            fields[self.test_case_id_field] = f"{self.jira_base_url}/browse/{result.test_case_key}"
        if self.report_version_field and self.report_version:
            fields[self.report_version_field] = {"value": self.report_version}

        return fields

    def _create_bug_description(self, result: TestResult, failure_reason: str) -> dict:
        execution = result.execution
        content = [
            self._heading("Test Information", 3),
            self._paragraph(f"Test Case Key: {result.test_case_key}"),
            self._paragraph(f"Test Case Name: {getattr(execution, 'short_description', '') or getattr(execution, 'scenario_id', '')}"),
            self._paragraph(f"Failure Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"),
            self._paragraph(f"UserName: {ConfigReader.get_property("UserName")}"),
            self._paragraph(f"Environment: {_setting('Environment', 'QA')}"),
            self._heading("Failure Details", 3),
            self._paragraph(f"Failure Reason: {failure_reason}"),
        ]

        steps = getattr(execution, "steps", []) or []
        if steps:
            content.append(self._heading("Steps to Replicate", 3))
            for index, step in enumerate(steps, start=1):
                content.append(self._paragraph(f"{index}. {step.action or 'Step'}"))

            content.append(self._paragraph("Expected Result: All test steps should pass"))
            content.append(self._paragraph(f"Actual Result: {failure_reason}"))
            content.append(self._heading("Detailed Test Step Results", 3))

            for index, step in enumerate(steps, start=1):
                status = "PASS" if step.status == StepStatus.PASS else "FAIL"
                content.append(self._paragraph(f"{index}. {status}: {step.action or 'Step'}"))
                if step.status != StepStatus.PASS:
                    content.append(self._paragraph(f"Error: {step.actual_result or 'No failure details captured'}"))

        content.append(self._heading("Attachments", 3))
        content.append(self._paragraph("Failed-step screenshot and execution video are attached as files when available."))

        content.extend([
            self._heading("Additional Information", 3),
            self._paragraph(f"Browser: {_setting('Browser', 'Chrome')}"),
            self._paragraph("This bug was automatically generated by the automation framework."),
        ])

        return {"version": 1, "type": "doc", "content": content}

    def _find_duplicate_bug(self, test_case_key: str, failure_reason: str) -> Optional[str]:
        reason_id = self._failure_reason_id(failure_reason)
        summary_text = f"AUTO BUG: {test_case_key}"
        reason_label = f"auto_failure_{reason_id}"
        jql = (
            f'project = "{self.project_key}" AND issuetype = Bug '
            f'AND summary ~ "{summary_text}" AND labels = "{reason_label}" '
            f'AND statusCategory != Done ORDER BY created DESC'
        )
        response = requests.get(
            f"{self.jira_base_url}/rest/api/3/search/jql",
            params={"jql": jql, "maxResults": 1, "fields": "key"},
            headers=self._jira_headers(),
            timeout=self.timeout,
        )
        if response.status_code >= 400:
            print(f"[JIRA] Duplicate check failed: {response.status_code} {response.text}")
            return None
        issues = response.json().get("issues", [])
        return issues[0]["key"] if issues else None

    @staticmethod
    def _failure_reason_id(failure_reason: str) -> str:
        normalized = " ".join(str(failure_reason or "").lower().split())
        return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:10]

    def _attach_execution_files(self, bug_key: str, execution):
        paths = []
        for step in getattr(execution, "steps", []) or []:
            if step.status != StepStatus.PASS:
                paths.extend([step.screenshot_path, step.log_file_path, step.har_file_path])

        video_url = getattr(execution, "video_url", None)
        if video_url:
            paths.append(video_url)

        attached = set()
        for path in paths:
            file_path = self._resolve_media_file(path)
            if not file_path or file_path in attached:
                continue
            self._attach_file(bug_key, file_path)
            attached.add(file_path)

    def _resolve_media_file(self, value) -> Optional[Path]:
        if not value:
            return None

        text = str(value)
        if text.startswith("data:"):
            return None

        direct_path = Path(text)
        if direct_path.exists() and direct_path.is_file():
            return direct_path

        filename = self._filename_from_url(text)
        if not filename:
            return None

        search_roots = [Path("screenshots"), Path("videos")]
        for root in search_roots:
            if not root.exists():
                continue
            for candidate in root.rglob("*"):
                if not candidate.is_file():
                    continue
                if candidate.name == filename or filename.endswith(candidate.name) or candidate.name in filename:
                    return candidate

        print(f"[JIRA] Local media file not found for attachment: {filename}")
        return None

    @staticmethod
    def _filename_from_url(value: str) -> Optional[str]:
        parsed = urlparse(value)
        if parsed.scheme in {"http", "https", "file"}:
            return Path(unquote(parsed.path)).name
        return Path(value).name if value else None

    def _attach_file(self, bug_key: str, file_path: Path):
        mime_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
        with file_path.open("rb") as handle:
            response = requests.post(
                f"{self.jira_base_url}/rest/api/3/issue/{bug_key}/attachments",
                headers={**self._jira_headers(content_type=None), "X-Atlassian-Token": "no-check"},
                files={"file": (file_path.name, handle, mime_type)},
                timeout=self.timeout,
            )
        if response.status_code >= 400:
            print(f"[JIRA] Failed to attach {file_path.name}: {response.status_code} {response.text}")
        else:
            print(f"[JIRA] Attached {file_path.name} to {bug_key}")

    def _link_bug_to_test_case(self, bug_key: str, test_case_key: str):
        if not bug_key or not test_case_key:
            return
        if not self._jira_issue_exists(test_case_key):
            print(f"[JIRA] Skipping Jira issue link: {test_case_key} is not a Jira issue key")
            return
        payload = {
            "type": {"name": "Relates"},
            "inwardIssue": {"key": bug_key},
            "outwardIssue": {"key": test_case_key},
        }
        response = requests.post(
            f"{self.jira_base_url}/rest/api/3/issueLink",
            json=payload,
            headers=self._jira_headers(),
            timeout=self.timeout,
        )
        if response.status_code not in {200, 201}:
            print(f"[JIRA] Failed to link {bug_key} to {test_case_key}: {response.status_code}")

    def _jira_issue_exists(self, issue_key: str) -> bool:
        response = requests.get(
            f"{self.jira_base_url}/rest/api/3/issue/{issue_key}",
            params={"fields": "key"},
            headers=self._jira_headers(),
            timeout=self.timeout,
        )
        if response.status_code == 200:
            return True
        if response.status_code == 404:
            return False
        print(f"[JIRA] Could not verify Jira issue {issue_key}: {response.status_code} {response.text}")
        return False

    def _jira_headers(self, content_type: Optional[str] = "application/json") -> dict:
        auth = base64.b64encode(f"{self.jira_email}:{self.jira_api_key}".encode("utf-8")).decode("ascii")
        headers = {
            "Authorization": f"Basic {auth}",
            "Accept": "application/json",
        }
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    @staticmethod
    def _failure_reason(execution) -> str:
        for step in getattr(execution, "steps", []) or []:
            if step.status != StepStatus.PASS and step.actual_result:
                return str(step.actual_result)
        return "Test execution failed"

    @staticmethod
    def _is_script_failure(failure_reason: str) -> bool:
        text = str(failure_reason or "").lower()
        script_failure_patterns = [
            "locator.",
            "locator.wait_for",
            "timeout ",
            "timeouterror",
            "playwright",
            "target closed",
            "browser has been closed",
            "context has been closed",
            "page has been closed",
            "strict mode violation",
            "element is not attached",
            "net::",
            "connection refused",
            "nameerror",
            "attributeerror",
            "typeerror",
            "keyerror",
            "indexerror",
            "syntaxerror",
            "importerror",
            "modulenotfounderror",
        ]
        return any(pattern in text for pattern in script_failure_patterns)

    @staticmethod
    def _heading(text: str, level: int) -> dict:
        return {
            "type": "heading",
            "attrs": {"level": level},
            "content": [{"type": "text", "text": str(text)}],
        }

    @staticmethod
    def _paragraph(text: str) -> dict:
        return {
            "type": "paragraph",
            "content": [{"type": "text", "text": str(text or "")}],
        }

    @staticmethod
    def _is_url_or_data(value: str) -> bool:
        text = str(value)
        return text.startswith(("http://", "https://", "data:"))

    @staticmethod
    def _require(value, key: str):
        if not value:
            raise RuntimeError(f"Missing required Jira/Zephyr setting: {key}")


def update_zephyr_and_report_defects():
    client = JiraZephyrClient()
    if not client.update_zephyr and not client.report_bug:
        return
    client.update_from_reporter()
