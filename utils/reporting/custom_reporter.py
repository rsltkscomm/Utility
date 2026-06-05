import json
import os
import base64
from datetime import datetime, timedelta
from openpyxl import load_workbook

from utils.constants.framework_constants import FrameworkConstants
from utils.ini_file_reader.config_reader import ConfigReader
from utils.reporting.email_sender import EmailSender
from utils.excel_helper.Weekly_final_status import WeeklyStatusManager


class ExecutionStatus:
    PASS = "PASS"
    FAIL = "FAIL"
    SKIPPED = "SKIPPED"


class StepStatus:
    PASS = "PASS"
    FAIL = "FAIL"
    SKIPPED = "SKIPPED"


class TestStep:
    def __init__(self):
        self.step_no = 0
        self.action = ""
        self.expected_result = ""
        self.actual_result = ""
        self.status = StepStatus.SKIPPED
        self.screenshot_path = None
        self.log_file_path = None
        self.har_file_path = None


class TestExecution:
    def __init__(self):
        self.module = ""
        self.scenario_id = ""
        self.test_case_id = ""
        self.short_description = ""
        self.start_time = None
        self.end_time = None
        self.status = ExecutionStatus.PASS
        self.steps = []
        self.video_url = None


class DetailedTestReporter:
    test_executions = []

    # Store the mapping: { "scenario_name": "testcaseID" }
    session_map = {}

    @classmethod
    def create_detail_report(cls):
        cls.test_executions = []

    @classmethod
    def set_session_map(cls, mapping):
        cls.session_map = mapping

    @classmethod
    def save_worker_state(cls):
        worker_id = os.environ.get("PYTEST_XDIST_WORKER", "master")
        import pickle
        with open(f".report_state_{worker_id}.pkl", "wb") as f:
            pickle.dump(cls.test_executions, f)

    @classmethod
    def load_all_worker_states(cls):
        import glob
        import pickle
        cls.test_executions = []
        for file in glob.glob(".report_state_*.pkl"):
            try:
                with open(file, "rb") as f:
                    executions = pickle.load(f)
                    cls.test_executions.extend(executions)
                import os
                os.remove(file)
            except Exception as e:
                print(f"⚠️ Failed to load worker state {file}: {e}")

        cls._dedupe_test_executions()

    @classmethod
    def _latest_execution(cls, test_case_id):
        return next((e for e in reversed(cls.test_executions) if e.test_case_id == test_case_id), None)

    @staticmethod
    def _build_test_execution(module, scenario_id, test_case_id, short_description):
        execution = TestExecution()
        execution.module = module
        execution.scenario_id = scenario_id
        execution.test_case_id = test_case_id
        execution.short_description = short_description
        execution.start_time = datetime.now()
        execution.status = ExecutionStatus.PASS
        execution.steps = []
        return execution

    @classmethod
    def _dedupe_test_executions(cls):
        latest_by_test_case = {}
        for execution in cls.test_executions:
            if execution.test_case_id:
                latest_by_test_case[execution.test_case_id] = execution

        deduped = []
        emitted = set()
        for execution in cls.test_executions:
            key = execution.test_case_id
            if not key:
                deduped.append(execution)
            elif latest_by_test_case[key] is execution and key not in emitted:
                deduped.append(execution)
                emitted.add(key)

        cls.test_executions = deduped

    @classmethod
    def attach_video(cls, test_case_id, video_url):
        execution = cls._latest_execution(test_case_id)
        if not execution and cls.test_executions:
            execution = cls.test_executions[-1]

        if execution:
            execution.video_url = video_url

    @classmethod
    def get_test_executions(cls):
        return cls.test_executions

    @classmethod
    def add_test_execution(cls, module, scenario_id, test_case_id, short_description, replace_existing=False):
        existing_index = next(
            (index for index in range(len(cls.test_executions) - 1, -1, -1)
             if cls.test_executions[index].test_case_id == test_case_id),
            None,
        )

        if existing_index is not None and replace_existing:
            execution = cls._build_test_execution(module, scenario_id, test_case_id, short_description)
            cls.test_executions[existing_index] = execution
            return execution

        # Prevent duplicates
        if any(e.test_case_id == test_case_id for e in cls.test_executions):
            print(f"⚠️ Duplicate Test Case ID skipped: {test_case_id}")
            if existing_index is not None:
                return cls.test_executions[existing_index]
            return None

        execution = cls._build_test_execution(module, scenario_id, test_case_id, short_description)

        cls.test_executions.append(execution)
        return execution

    @classmethod
    def log_step(cls, action, expected_result, actual_result, status: bool, page=None):
        from utils.excel_helper.test_context import TestContext
        test_case_id = getattr(TestContext, "current_testcase_id", None)
        if not test_case_id:
            print("⚠️ Cannot log step without an active test_case_id in TestContext.")
            return

        step_status = StepStatus.PASS if status else StepStatus.FAIL

        execution = cls._latest_execution(test_case_id)

        if not execution:
            print(f"⚠️ Cannot find active test execution for {test_case_id}.")
            return

        step = TestStep()
        step.step_no = len(execution.steps) + 1
        step.action = action
        step.expected_result = expected_result
        step.actual_result = actual_result
        step.status = step_status

        if page:
            try:
                screenshot_bytes = page.screenshot()
                step.screenshot_path = "data:image/png;base64," + base64.b64encode(screenshot_bytes).decode()
            except Exception:
                pass

        execution.steps.append(step)

        if step_status == StepStatus.FAIL:
            execution.status = ExecutionStatus.FAIL

        execution.end_time = datetime.now()

    @classmethod
    def add_step(cls, test_case_id, action, expected_result, actual_result, status, page=None):
        execution = cls._latest_execution(test_case_id)

        if not execution:
            execution = TestExecution()
            execution.test_case_id = test_case_id
            execution.start_time = datetime.now()
            execution.status = ExecutionStatus.PASS
            execution.steps = []
            cls.test_executions.append(execution)

        step = TestStep()
        step.step_no = len(execution.steps) + 1
        step.action = action
        step.expected_result = expected_result
        step.actual_result = actual_result
        step.status = status

        if page:
            try:
                import base64
                screenshot_bytes = page.screenshot(type="jpeg", quality=40)
                step.screenshot_path = "data:image/jpeg;base64," + base64.b64encode(screenshot_bytes).decode()
            except Exception:
                pass

        execution.steps.append(step)

        if status == StepStatus.FAIL:
            execution.status = ExecutionStatus.FAIL

        execution.end_time = datetime.now()


class SummaryReportGenerator:

    @staticmethod
    def aggregate_stats():
        agg = {
            "totalPass": 0,
            "totalFail": 0,
            "totalSkip": 0,
            "totalDurationMillis": 0,
            "perModule": {}
        }

        for exec_obj in DetailedTestReporter.get_test_executions():
            module = exec_obj.module if exec_obj.module else "Other"
            if module not in agg["perModule"]:
                agg["perModule"][module] = {"passed": 0, "failed": 0, "skipped": 0, "durationMillis": 0}

            mod = agg["perModule"][module]
            if exec_obj.status == ExecutionStatus.PASS:
                agg["totalPass"] += 1
                mod["passed"] += 1
            elif exec_obj.status == ExecutionStatus.FAIL:
                agg["totalFail"] += 1
                mod["failed"] += 1
            else:
                agg["totalSkip"] += 1
                mod["skipped"] += 1

            if exec_obj.start_time and exec_obj.end_time and exec_obj.end_time > exec_obj.start_time:
                dur = int((exec_obj.end_time - exec_obj.start_time).total_seconds() * 1000)
                agg["totalDurationMillis"] += dur
                mod["durationMillis"] += dur

        return agg

    @staticmethod
    def generate_report_json(suite_start_time):

        agg = SummaryReportGenerator.aggregate_stats()

        root = {}

        history_map = WeeklyStatusManager.read_last_7_days_status(WeeklyStatusManager.FILE_PATH)

        pass_count = agg["totalPass"]
        fail_count = agg["totalFail"]
        skip_count = agg["totalSkip"]

        total = pass_count + fail_count + skip_count

        duration_millis = agg["totalDurationMillis"]

        summary = {
            "passed": pass_count,
            "failed": fail_count,
            "skipped": skip_count,
            "total": total,
            "durationMillis": str(duration_millis),
            "startTime": suite_start_time
        }

        root["summary"] = summary

        modules = []

        for mod_name, ms in agg["perModule"].items():
            mod_total = (
                    ms["passed"]
                    + ms["failed"]
                    + ms["skipped"]
            )

            modules.append({
                "module": mod_name.upper(),
                "total": mod_total,
                "passed": ms["passed"],
                "failed": ms["failed"],
                "skipped": ms["skipped"],
                "durationMillis": ms["durationMillis"]
            })

        modules.sort(
            key=lambda x: str(x["module"])
        )

        root["modules"] = modules

        root["meta"] = {
            "environment": ConfigReader.get_property("Environment", "NA"),
            "browser": ConfigReader.get_property("Browser", "NA"),
            "release": ConfigReader.get_property("ReleaseVersion", "NA"),
            "executionDate": datetime.now().strftime("%y-%m-%d %H:%M:%S"),
            "generatedBy": ConfigReader.get_property("USERNAME", "automation")
        }

        details = []

        for exec_obj in DetailedTestReporter.get_test_executions():

            start_time_str = (
                exec_obj.start_time.strftime("%y-%m-%d %H:%M:%S")
                if exec_obj.start_time else ""
            )

            end_time_str = (
                exec_obj.end_time.strftime("%y-%m-%d %H:%M:%S")
                if exec_obj.end_time else ""
            )

            dur_ms = 0

            if exec_obj.start_time and exec_obj.end_time:
                dur_ms = int(
                    (exec_obj.end_time - exec_obj.start_time).total_seconds() * 1000
                )

            steps = []

            for step in exec_obj.steps:
                steps.append({
                    "stepNo": step.step_no,
                    "action": (step.action if step.action else ""),
                    "expected": (step.expected_result if step.expected_result else ""),
                    "actual": (step.actual_result if step.actual_result else ""),
                    "status": (step.status if step.status else "SKIPPED"),
                    "screenshot": step.screenshot_path,
                    "logFilePath": step.log_file_path
                })

            details.append({
                "module": (exec_obj.module if exec_obj.module else ""),
                "scenarioId": (exec_obj.scenario_id if exec_obj.scenario_id else ""),
                "testCaseId": (exec_obj.test_case_id if exec_obj.test_case_id else ""),
                "description": (
                    exec_obj.short_description.replace("_", " ").strip()
                    if exec_obj.short_description else ""
                ),
                "status": (exec_obj.status if exec_obj.status else "SKIPPED"),
                # Look up history by scenario_id first (Excel col B stores scenario/function names),
                # then fall back to test_case_id for backward compatibility
                "history": (
                    history_map.get(exec_obj.scenario_id)
                    or history_map.get(exec_obj.test_case_id)
                    or []
                ),
                "startTime": start_time_str,
                "endTime": end_time_str,
                "durationMillis": dur_ms,
                "videoUrl": getattr(exec_obj, "video_url", "") or "",
                "steps": steps
            })

        root["details"] = details

        return json.dumps(root, indent=4)

    @staticmethod
    def _escape_html(text):
        if not text:
            return ""
        return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace(
            "'", "&#39;")

    @staticmethod
    def get_status_class(status):
        if status == "PASS":
            return "status-pass"
        elif status == "FAIL":
            return "status-fail"
        elif status == "SKIPPED":
            return "status-skipped"
        return ""

    @staticmethod
    def generate_detailed_html_from_json(json_str):
        """
        Generates only the inner HTML for the detailed report section.
        NOTE: The history modal + its JS are intentionally NOT included here.
        They live at the top level in build_custom_html so that position:fixed
        works correctly and backtick escaping cannot break the JS.
        """
        data = json.loads(json_str)
        meta = data.get("meta", {})
        details = data.get("details", [])

        companyLogoUrl = ConfigReader.get_property(
            "CompanyLogo",
            "https://www.resulticks.com/images/logos/resulticks-logo-blue.svg"
        )
        productLogoUrl = ConfigReader.get_property(
            "ProductLogo",
            "https://run19.resul.io/assets/resulticks-logo-white-391eec89.svg"
        )

        environment = meta.get("environment", "")
        browser = meta.get("browser", "")
        release = meta.get("release", "")
        executionDate = meta.get("executionDate", "")

        html = []
        html.append('<div class="header">')
        html.append(f'<img alt="Company Logo" src="{companyLogoUrl}"/>')
        html.append('<h2>Detail Test Report</h2>')
        html.append(f'<img alt="Product Logo" src="{productLogoUrl}"/>')
        html.append('</div>')

        html.append('<div class="environment-ribbon">')
        html.append(f'<span><strong>Environment:</strong> {SummaryReportGenerator._escape_html(environment)}</span>')
        html.append(f'<span><strong>Browser:</strong> {SummaryReportGenerator._escape_html(browser)}</span>')
        html.append(f'<span><strong>Release:</strong> {SummaryReportGenerator._escape_html(release)}</span>')
        html.append(f'<span><strong>Execution Date:</strong> {SummaryReportGenerator._escape_html(executionDate)}</span>')
        html.append('</div>')

        html.append('<div style="text-align:right; padding:10px;">')
        html.append('<a class="back-btn" onclick="showSummaryReport()"><span class="back-btn-icon">&#8592;</span> Back to Summary</a>')
        html.append('</div>')

        html.append('<div class="table-container">')
        html.append('<h3>Test Case Results</h3>')

        html.append('<div class="toolbar"><div style="display:flex; gap:15px; flex-wrap:wrap; margin:20px 0;">')
        html.append('<div><label><b>Search:</b></label><input id="searchInput" placeholder="Search test cases..." type="text"/></div>')
        html.append('<div><label><b>Filter by Status:</b></label><select id="statusFilter"><option value="">All</option><option value="PASS">Passed</option><option value="FAIL">Failed</option><option value="SKIPPED">Skipped</option></select></div>')
        html.append('</div></div>')

        html.append('''<table id="testcaseTable">
<colgroup>
  <col style="width:40px">
  <col style="width:11%">
  <col style="width:10%">
  <col>
  <col style="width:9%">
  <col style="width:8%">
  <col style="width:10%">
  <col style="width:26%">
</colgroup>
<thead><tr>
  <th class="th-expand"></th>
  <th>Module</th>
  <th>Test Case ID</th>
  <th>Description</th>
  <th style="text-align:center;">Status</th>
  <th style="text-align:center;">Duration</th>
  <th style="text-align:center;">Video</th>
  <th class="th-last7">Last 7 Execution</th>
</tr></thead><tbody>''')

        # Precompute the labels for the last 7 days (oldest -> newest, same order as history list)
        today = datetime.now()
        last_7_meta = []
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            last_7_meta.append({
                "tooltip": d.strftime("%a, %d %b %Y"),
            })

        counter = 1
        for test in details:
            module = test.get("module", "")
            testCaseId = test.get("testCaseId", "")
            desc = test.get("description", "")
            status = test.get("status", "")
            durationMs = test.get("durationMillis", 0)
            duration = f"{durationMs // 1000}s" if durationMs > 0 else "—"
            videoUrl = test.get("videoUrl") or ""
            runDate = test.get("endTime", "") or test.get("startTime", "") or ""
            # Format run date as YYYY-MM-DD only (no time), no wrap
            if runDate and len(runDate) >= 10:
                runDate = runDate[:10]

            # Attractive description: split by _ into words, title-case
            desc_display = " ".join(w.capitalize() for w in desc.replace("-", "_").split("_")) if desc else ""

            # Status badge
            if status == "PASS":
                statusBadge = '<span class="badge badge-pass">&#10003; Passed</span>'
            elif status == "FAIL":
                statusBadge = '<span class="badge badge-fail">&#10007; Failed</span>'
            else:
                statusBadge = '<span class="badge badge-skip">&#9888; Skipped</span>'

            statusClass = SummaryReportGenerator.get_status_class(status)
            videoLink = f'<a href="#" class="play-video-btn" data-video="{videoUrl}" onclick="playVideoHandler(event, this)"><span class="video-btn"><span class="video-btn-icon">&#9654;</span> View</span></a>' if videoUrl else "<span style='color:#bbb'>—</span>"

            # Build inline circles for the Last 7 column
            history = list(test.get("history", []))
            # Pad at the beginning (older days) if there are fewer than 7 entries
            while len(history) < 7:
                history.insert(0, "SKIPPED")
            # Keep only the most recent 7
            history = history[-7:]

            circles_parts = ['<div class="last7-row" onclick="event.stopPropagation()">']
            for idx, hist_status in enumerate(history):
                hs = (hist_status or "SKIPPED").upper()
                if hs == "PASS":
                    mini_cls = "mini-pass"
                    mini_sym = "&#10003;"
                    status_label = "Pass"
                elif hs == "FAIL":
                    mini_cls = "mini-fail"
                    mini_sym = "&#10007;"
                    status_label = "Fail"
                else:
                    mini_cls = "mini-skip"
                    mini_sym = "&minus;"
                    status_label = "Skipped"
                tooltip = f"{last_7_meta[idx]['tooltip']} - {status_label}"
                circles_parts.append(
                    f'<span class="mini-circle {mini_cls}" '
                    f'data-tooltip="{SummaryReportGenerator._escape_html(tooltip)}">'
                    f'{mini_sym}'
                    f'</span>'
                )
            circles_parts.append('</div>')
            circles_html = "".join(circles_parts)

            escaped_desc_display = SummaryReportGenerator._escape_html(desc_display)
            escaped_module = SummaryReportGenerator._escape_html(module)
            escaped_testCaseId = SummaryReportGenerator._escape_html(testCaseId)

            html.append(f'<tr data-test-id="tc{counter}" data-status="{status}" data-expanded="false" data-module="{escaped_module}" data-testcaseid="{escaped_testCaseId}" data-rundate="{SummaryReportGenerator._escape_html(runDate)}" data-duration="{duration}" data-env="" onclick="toggleDetails(this)" style="cursor:pointer;">')
            html.append('<td class="expand-icon"><span class="chevron">&#9654;</span></td>')
            html.append(f'<td class="td-module">{escaped_module}</td>')
            html.append(f'<td class="td-tcid">{escaped_testCaseId}</td>')
            html.append(f'<td class="td-desc"><span class="desc-chip">{escaped_desc_display}</span></td>')

            # Status column: badge, no link
            html.append(f'<td style="text-align:center;">{statusBadge}</td>')

            html.append(f'<td class="td-dur" style="text-align:center;">{duration}</td>')
            html.append(f'<td style="text-align:center;">{videoLink}</td>')

            # Last 7 column: inline circles with hover tooltips (no popup)
            html.append(f'<td class="td-last7">{circles_html}</td>')
            html.append('</tr>')

            html.append(f'<tr class="details-row" id="tc{counter}-details" style="display:none">')
            html.append('<td colspan="8"><table class="step-table"><tr><th>Action</th><th>Expected Result</th><th>Actual Result</th><th>Status</th><th>Screenshot</th></tr>')

            steps = test.get("steps", [])
            for step in steps:
                stepStatus = step.get("status", "")
                icon = "✅" if stepStatus == "PASS" else ("❌" if stepStatus == "FAIL" else "⚠️")
                screenshot_tag = f'<img class="screenshot" src="{step.get("screenshot")}"/>' if step.get("screenshot") else "-"

                html.append('<tr>')
                html.append(f'<td>{SummaryReportGenerator._escape_html(step.get("action", ""))}</td>')
                html.append(f'<td>{SummaryReportGenerator._escape_html(step.get("expected", ""))}</td>')
                html.append(f'<td>{SummaryReportGenerator._escape_html(step.get("actual", ""))}</td>')
                html.append(f'<td>{icon}</td>')
                html.append(f'<td>{screenshot_tag}</td>')
                html.append('</tr>')

            html.append('</table></td></tr>')
            counter += 1

        html.append('</tbody></table></div>')

        # Search/filter script only — NO modal, NO showHistoryPopup here
        html.append("""
<script>
function toggleDetails(row) {
    // row could be the <tr> itself (passed from onclick on the expand td)
    if (!row || !row.getAttribute) return;
    var detailsRow = document.getElementById(row.getAttribute('data-test-id') + '-details');
    if (!detailsRow) return;
    var expandIcon = row.querySelector('.expand-icon .chevron');
    if (detailsRow.style.display === 'none') {
        detailsRow.style.display = 'table-row';
        row.setAttribute('data-expanded', 'true');
        if (expandIcon) { expandIcon.innerHTML = '&#9660;'; expandIcon.style.color = '#0e4494'; }
    } else {
        detailsRow.style.display = 'none';
        row.setAttribute('data-expanded', 'false');
        if (expandIcon) { expandIcon.innerHTML = '&#9654;'; expandIcon.style.color = '#666'; }
    }
}

function playVideoHandler(event, element) {
    event.stopPropagation();
    event.preventDefault();
    var modal = document.getElementById('lightboxModal');
    var modalImg = document.getElementById('lightboxImage');
    var modalVideo = document.getElementById('lightboxVideo');
    if (modal && modalImg && modalVideo) {
        modalImg.style.display = 'none';
        modalImg.src = '';
        modalVideo.src = element.getAttribute('data-video');
        modalVideo.style.display = 'block';
        modal.style.display = 'block';
        modalVideo.play();
    }
}

function applySearchAndFilter() {
    var searchText = document.getElementById('searchInput').value.toLowerCase().trim();
    var filterValue = document.getElementById('statusFilter').value;
    var mainRows = document.querySelectorAll('#testcaseTable > tbody > tr:not(.details-row)');
    mainRows.forEach(function(row) {
        var rowText = row.textContent.toLowerCase();
        var rowStatus = row.getAttribute('data-status') || '';
        var matchesSearch = !searchText || rowText.includes(searchText);
        var matchesFilter = !filterValue || rowStatus === filterValue;
        var shouldShow = matchesSearch && matchesFilter;
        var testId = row.getAttribute('data-test-id');
        var detailsRow = document.getElementById(testId + '-details');
        if (shouldShow) {
            row.style.display = '';
            if (detailsRow) {
                var expanded = row.getAttribute('data-expanded') === 'true';
                detailsRow.style.display = expanded ? 'table-row' : 'none';
            }
        } else {
            row.style.display = 'none';
            if (detailsRow) detailsRow.style.display = 'none';
            var ch = row.querySelector('.expand-icon .chevron');
            if (ch) { ch.innerHTML = '&#9654;'; ch.style.color = '#666'; }
            row.setAttribute('data-expanded', 'false');
        }
    });
}

document.addEventListener('DOMContentLoaded', function() {
    var searchInput = document.getElementById('searchInput');
    var statusFilter = document.getElementById('statusFilter');
    if (searchInput) searchInput.addEventListener('input', applySearchAndFilter);
    if (statusFilter) statusFilter.addEventListener('change', applySearchAndFilter);
});
</script>
        """)

        return "".join(html)

    @staticmethod
    def format_millis_as_hms(millis_str):
        try:
            ms = int(millis_str)
            if ms <= 0: return "-"
            total_sec = ms // 1000
            h = total_sec // 3600
            m = (total_sec % 3600) // 60
            s = total_sec % 60
            return f"{h:02d}:{m:02d}:{s:02d}"
        except:
            return "-"

    @staticmethod
    def build_custom_html(json_str):
        data = json.loads(json_str)
        summary = data.get("summary", {})

        pass_c = summary.get("passed", 0)
        fail_c = summary.get("failed", 0)
        skip_c = summary.get("skipped", 0)
        total = summary.get("total", 0)
        duration = str(summary.get("durationMillis", 0))
        Total_duration = os.getenv("Total_duration")

        # Generate detailed section HTML (no modal/history JS inside)
        detailedReportContent = SummaryReportGenerator.generate_detailed_html_from_json(json_str)
        executionDate = data.get("meta", {}).get("executionDate", "")

        companyLogoUrl = os.environ.get(
            "CompanyLogo",
            "https://www.resulticks.com/images/logos/resulticks-logo-blue.svg"
        )
        productLogoUrl = os.environ.get(
            "PRODUCTLOGO",
            "https://run19.resul.io/assets/resulticks-logo-white-391eec89.svg"
        )

        overallDurationFormatted = SummaryReportGenerator.format_millis_as_hms(duration)
        reportTitle = os.environ.get("reportTitle", "Automation Test Summary Report")

        slaPercentage = ((pass_c / total) * 100) if total > 0 else 0
        slaFormatted = f"{int(slaPercentage)}%"
        passRate = f"{slaPercentage:.2f}%"

        moduleDataJson = json.dumps(data.get("modules", []))

        # Safe escaping for the module data only (no backtick issues here)
        escapedModuleData = (
            moduleDataJson
            .replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace('\n', '\\n')
            .replace('\r', '\\r')
            .replace('\t', '\\t')
        )

        # IMPORTANT: We no longer escape backticks in detailedReportContent because
        # the history popup JS (which used template literals) has been moved out of
        # that content and placed directly in this template below.
        # We only need to escape the grave accent if it still appears in step text etc.
        # Using a simple replace here is safe because no template literals remain inside.
        escapedDetailedReportContent = detailedReportContent.replace('`', '&#96;')

        html_template = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>Automation Test Summary Report</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js"></script>
<style>
/* ===== Last 7 inline circles (replaces the old History popup) ===== */
.last7-row {{
    display: flex;
    gap: 6px;
    align-items: center;
    justify-content: center;
    white-space: nowrap;
    width: 100%;
}}
.mini-circle {{
    width: 28px;
    height: 28px;
    border-radius: 50%;
    color: #fff;
    display: inline-flex;
    flex-shrink: 0;
    align-items: center;
    justify-content: center;
    font-weight: 800;
    font-size: 13px;
    line-height: 1;
    box-shadow: 0 2px 5px rgba(0,0,0,0.18);
    cursor: default;
    transition: transform 0.15s ease;
}}
.mini-circle:hover {{
    transform: scale(1.2);
    z-index: 20;
}}
.mini-pass {{ background: linear-gradient(135deg, #22c55e, #16a34a); }}
.mini-fail {{ background: linear-gradient(135deg, #ef4444, #dc2626); }}
.mini-skip {{ background: linear-gradient(135deg, #fbbf24, #f59e0b); }}

.th-last7 {{ text-align: center !important; }}
.td-last7 {{
    white-space: nowrap;
    text-align: center;
    overflow: visible !important;
    padding: 8px 4px !important;
    display: table-cell;
    vertical-align: middle;
}}
.last7-row {{
    display: flex;
    flex-wrap: nowrap;
    gap: 4px;
    align-items: center;
    justify-content: center;
    width: 100%;
}}

/* Floating tooltip lives in <body> so it can't be clipped by .table-container overflow */
#miniTooltip {{
    position: fixed;
    background: #1e293b;
    color: #fff;
    padding: 7px 11px;
    border-radius: 6px;
    font-family: 'Segoe UI', sans-serif;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.2px;
    white-space: nowrap;
    pointer-events: none;
    opacity: 0;
    transform: translateY(2px);
    transition: opacity 0.12s ease, transform 0.12s ease;
    z-index: 99999;
    box-shadow: 0 4px 12px rgba(0,0,0,0.25);
}}
#miniTooltip.show {{
    opacity: 1;
    transform: translateY(0);
}}
#miniTooltip::after {{
    content: '';
    position: absolute;
    top: 100%;
    left: 50%;
    transform: translateX(-50%);
    border: 5px solid transparent;
    border-top-color: #1e293b;
}}

/* ===== General Layout ===== */
body {{ font-family: 'Segoe UI', sans-serif; background:#f0f4fa; margin:0; color:#333; }}
.header {{ display:flex; justify-content:space-between; align-items:center; background:linear-gradient(33deg,#8db5f1,#021e49); color:white; padding:10px 20px; }}
.header img {{ height:40px; }}
.summary-band {{ background:#0e4494; color:white; display:flex; justify-content:center; gap:30px; padding:8px; font-weight:600; flex-wrap:wrap; }}
.summary-band div {{ display:flex; align-items:center; gap:5px; }}
.main {{ display:flex; gap:20px; padding:20px; flex-wrap:wrap; }}
.chart-container {{ flex:1; display:flex; justify-content:center; align-items:center; min-width:250px; }}
.table-container {{ flex:1; background:white; padding:15px; border-radius:8px; box-shadow:0 2px 6px rgba(0,0,0,0.1); overflow-x:hidden; box-sizing:border-box; min-width:300px; width:100%; }}
.table-container table {{ width:100%; border-collapse:collapse; }}
.table-container th, .table-container td {{ padding:8px; border-bottom:1px solid #eee; text-align:left; }}
.table-container th {{ background:#002b6b; color:white; }}
.footer {{ text-align:center; font-size:0.8em; padding:10px; background:#f1f1f1; margin-top:20px; }}
.detailed-section {{ display: none; }}

/* ===== Detail Table ===== */
#testcaseTable {{
    width: 100%;
    table-layout: fixed;
    border-collapse: separate;
    border-spacing: 0;
    font-size: 1em;
    border-radius: 12px;
    overflow: hidden;
    box-shadow: 0 2px 16px rgba(14,68,148,0.10);
}}
#testcaseTable thead tr {{
    background: linear-gradient(90deg, #0e4494 0%, #1a6fd4 100%);
}}
#testcaseTable thead th {{
    color: #fff;
    font-weight: 700;
    padding: 14px 10px;
    text-align: left;
    font-size: 0.88em;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    border: none;
    white-space: nowrap;
}}
#testcaseTable thead th.th-expand {{ width: 40px; text-align: center; }}
#testcaseTable tbody tr:not(.details-row) {{
    background: #fff;
    transition: background 0.18s;
    cursor: pointer;
}}
#testcaseTable tbody tr:not(.details-row):nth-child(even) {{
    background: #f7f9fd;
}}
#testcaseTable tbody tr:not(.details-row):hover {{
    background: #eaf2ff !important;
}}
#testcaseTable tbody td {{
    padding: 12px 10px;
    border-bottom: 1px solid #e8eef5;
    vertical-align: middle;
}}
.td-module {{ font-weight: 600; color: #1e293b; font-size: 0.98em; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.td-tcid {{ font-family: 'Courier New', monospace; font-size: 0.94em; color: #2563eb; font-weight: 700; letter-spacing: 0.3px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.td-desc {{ vertical-align: middle; }}
/* table-layout:fixed keeps each column at its assigned width.
   The description cell wraps text inside its column so the row height is
   driven only by the content of that run, not by neighbouring cells growing. */
#testcaseTable tbody tr:not(.details-row) td {{
    box-sizing: border-box;
    vertical-align: middle;
}}
/* Only clip module and tcid columns — never the Last 7 column */
#testcaseTable tbody td.td-module,
#testcaseTable tbody td.td-tcid {{
    overflow: hidden;
}}
.desc-chip {{
    display: -webkit-box;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 2;
    background: linear-gradient(90deg, #eff6ff, #e0ecff);
    color: #1e40af;
    border: 1px solid #bfdbfe;
    border-radius: 6px;
    padding: 7px 12px;
    font-size: 0.91em;
    font-weight: 600;
    letter-spacing: 0.1px;
    white-space: normal;
    word-break: break-word;
    overflow: hidden;
    line-height: 1.5;
    vertical-align: middle;
    box-sizing: border-box;
    width: 100%;
    max-height: calc(2 * 1.5em + 14px);
}}
.td-date {{ font-size: 0.92em; color: #475569; font-weight: 500; white-space: nowrap; }}
.td-dur {{ font-size: 0.91em; color: #64748b; white-space: nowrap; text-align: center; }}

/* ===== Status Badges ===== */
.badge {{
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 5px 14px;
    border-radius: 20px;
    font-size: 0.88em;
    font-weight: 700;
    letter-spacing: 0.2px;
    white-space: nowrap;
}}
.badge-pass {{ background: #dcfce7; color: #15803d; border: 1px solid #86efac; }}
.badge-fail {{ background: #fee2e2; color: #b91c1c; border: 1px solid #fca5a5; }}
.badge-skip {{ background: #fef9c3; color: #92400e; border: 1px solid #fde68a; }}

/* ===== Expand Chevron ===== */
.expand-icon {{ text-align: center; width: 36px; }}
.chevron {{
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 24px; height: 24px;
    border-radius: 50%;
    background: #f1f5f9;
    color: #666;
    font-size: 10px;
    transition: all 0.2s ease;
    border: 1px solid #e2e8f0;
}}
#testcaseTable tbody tr:hover .chevron {{
    background: #dbeafe;
    color: #1d4ed8;
    border-color: #93c5fd;
}}

/* ===== Video Button ===== */
.video-btn {{
    display: inline-flex; align-items: center; gap: 6px;
    background: linear-gradient(90deg, #0e4494, #2563eb);
    color: #fff;
    padding: 6px 14px;
    border-radius: 6px;
    font-size: 0.9em;
    font-weight: 600;
    text-decoration: none;
    transition: opacity 0.15s, transform 0.15s;
    box-shadow: 0 2px 6px rgba(14,68,148,0.25);
}}
.video-btn:hover {{ opacity: 0.92; transform: translateY(-1px); }}
.video-btn-icon {{
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 16px; height: 16px;
    background: rgba(255,255,255,0.22);
    border-radius: 50%;
    font-size: 9px;
    padding-left: 2px;
    line-height: 1;
}}

/* ===== Step Table ===== */
.step-table {{ width:95%; margin:10px auto; border-collapse:collapse; font-size:0.85em; table-layout:fixed; border-radius:8px; overflow:hidden; }}
.step-table th, .step-table td {{ border:1px solid #e2e8f0; padding:9px 10px; text-align:left; word-wrap:break-word; overflow-wrap:break-word; }}
.step-table th {{ background: linear-gradient(90deg,#1e293b,#334155); color:#fff; font-size:0.82em; text-transform:uppercase; letter-spacing:0.5px; }}
.step-table td:nth-child(1), .step-table th:nth-child(1) {{ width:30%; }}
.step-table td:nth-child(2), .step-table th:nth-child(2) {{ width:25%; }}
.step-table td:nth-child(3), .step-table th:nth-child(3) {{ width:25%; }}
.step-table td:nth-child(4), .step-table th:nth-child(4) {{ width:10%; text-align:center; }}
.step-table td:nth-child(5), .step-table th:nth-child(5) {{ width:10%; text-align:center; }}
.screenshot {{ max-width:80px; max-height:80px; object-fit:cover; cursor:pointer; border:1px solid #ccc; border-radius:4px; }}
.environment-ribbon {{ background:#f4f6f8; padding:10px; font-size:0.9em; border-bottom:1px solid #ddd; display:flex; justify-content:space-around; flex-wrap:wrap; gap:8px; }}
.toolbar input, .toolbar select, .toolbar button {{ padding:6px 10px; border-radius:5px; border:1px solid #ccc; }}
.toolbar button {{ background:#007bff; color:white; border:none; cursor:pointer; }}

/* ===== Lightbox Modal ===== */
.modal {{
    display: none; position: fixed; z-index: 9999;
    padding-top: 60px; left: 0; top: 0;
    width: 100%; height: 100%; overflow: auto;
    background-color: rgba(0,0,0,0.9);
}}
.modal-content {{ display:block; margin:auto; max-width:80%; max-height:80%; }}
video.modal-content {{ width:80%; background:black; }}
#closeModal {{
    position:absolute; top:20px; right:35px;
    color:#fff; font-size:30px; font-weight:bold; cursor:pointer;
}}
.chart-container canvas {{ max-width:300px !important; max-height:300px !important; }}
.detailed-report-link {{ text-align:right; padding:10px; display:block; }}
.detailed-report-link a {{ color:#0052cc; text-decoration:none; font-weight:600; cursor:pointer; padding-right:47px; }}
.detailed-report-link a:hover {{ text-decoration:underline; }}
.back-btn {{
    background: linear-gradient(90deg, #0e4494 0%, #1a6fd4 100%);
    color: #fff;
    padding: 10px 22px;
    border-radius: 999px;
    text-decoration: none;
    box-shadow: 0 4px 14px rgba(14,68,148,0.30);
    display: inline-flex;
    align-items: center;
    gap: 8px;
    margin: 14px 0;
    cursor: pointer;
    font-weight: 600;
    font-size: 0.95em;
    letter-spacing: 0.2px;
    transition: transform 0.15s ease, box-shadow 0.15s ease, opacity 0.15s ease;
    border: none;
}}
.back-btn:hover {{
    opacity: 0.95;
    transform: translateY(-1px);
    box-shadow: 0 6px 18px rgba(14,68,148,0.36);
}}
.back-btn-icon {{
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-size: 1.05em;
    line-height: 1;
}}
.status-pass {{ color:#28a745; font-weight:bold; }}
.status-fail {{ color:#dc3545; font-weight:bold; }}
.status-skipped {{ color:#ffc107; font-weight:bold; }}
.sla-pass {{ color:#28a745; font-weight:bold; }}
.sla-fail {{ color:#dc3545; font-weight:bold; }}
</style>
</head>
<body>

<!-- ===== Summary Section ===== -->
<div id="summary-section">
    <div class="header">
        <img alt="Company Logo" src="{companyLogoUrl}"/>
        <h2>{reportTitle}</h2>
        <img alt="Product Logo" src="{productLogoUrl}"/>
    </div>
    <div class="summary-band">
        <div>📊 Total: {total}</div>
        <div>✅ Passed: {pass_c}</div>
        <div>❌ Failed: {fail_c}</div>
        <div>⚠️ Skipped: {skip_c}</div>
        <div>⏱️ Duration: {Total_duration}</div>
        <div>🎯 SLA: 90%</div>
        <div>🎯 Pass Rate: {passRate}</div>
    </div>
    <div class="detailed-report-link">
        <a onclick="showDetailedReport()">📑 Detailed Report</a>
    </div>
    <div class="main">
        <div class="chart-container">
            <canvas id="chart1"></canvas>
        </div>
        <div class="table-container">
            <h3>Module-wise Results</h3>
            <table>
                <tr><th>Module</th><th>Total</th><th>Passed</th><th>Failed</th><th>Skipped</th><th>Duration</th><th>SLA %</th><th>Pass %</th></tr>
                <tbody id="moduleTableBody"></tbody>
            </table>
        </div>
    </div>
    <div class="footer">
        Report generated on <span id="current-datetime">{executionDate}</span> |
        Contact: <a href="mailto:qaautomation@resulticks.com">qaautomation@resulticks.com</a>
    </div>
</div>

<!-- ===== Detailed Section ===== -->
<div id="detailed-section" class="detailed-section" style="padding:20px; box-sizing:border-box; width:100%;">
    {escapedDetailedReportContent}
</div>

<!-- ===== Lightbox Modal ===== -->
<div class="modal" id="lightboxModal">
    <span id="closeModal">&#x2716;</span>
    <img class="modal-content" id="lightboxImage" style="display:none;"/>
    <video class="modal-content" id="lightboxVideo" controls style="display:none;"></video>
</div>

<!-- Floating tooltip for the Last 7 circles (body-level so it isn't clipped by table overflow) -->
<div id="miniTooltip"></div>

<script>
/* ===== Navigation ===== */
function showDetailedReport() {{
    document.getElementById("summary-section").style.display = "none";
    document.getElementById("detailed-section").style.display = "block";
    window.scrollTo(0, 0);
}}
function showSummaryReport() {{
    document.getElementById("detailed-section").style.display = "none";
    document.getElementById("summary-section").style.display = "block";
    window.scrollTo(0, 0);
}}

/* ===== Doughnut Chart ===== */
document.addEventListener('DOMContentLoaded', function() {{
    var ctx = document.getElementById('chart1');
    if (ctx) {{
        new Chart(ctx, {{
            type: 'doughnut',
            data: {{
                labels: ['Passed', 'Failed', 'Skipped'],
                datasets: [{{
                    data: [{pass_c}, {fail_c}, {skip_c}],
                    backgroundColor: ['#28a745', '#dc3545', '#ffc107']
                }}]
            }},
            options: {{ plugins: {{ legend: {{ position: 'bottom' }} }} }}
        }});
    }}
    showSummaryReport();
    populateModuleTable();
}});

/* ===== Module Table ===== */
var moduleDataRaw = "{escapedModuleData}";
var moduleData = [];
try {{ moduleData = JSON.parse(moduleDataRaw); }} catch (e) {{ console.error('Failed to parse module data:', e); }}

function formatDuration(ms) {{
    if (!ms || ms <= 0) return '-';
    var totalSeconds = Math.floor(ms / 1000);
    var hours = Math.floor(totalSeconds / 3600);
    var minutes = Math.floor((totalSeconds % 3600) / 60);
    var seconds = totalSeconds % 60;
    var pad = function(n) {{ return n.toString().padStart(2, '0'); }};
    return pad(hours) + ':' + pad(minutes) + ':' + pad(seconds);
}}

function populateModuleTable() {{
    var tableBody = document.getElementById('moduleTableBody');
    if (!tableBody) return;

    if (!moduleData || moduleData.length === 0) {{
        tableBody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:#666;">No module data available</td></tr>';
        return;
    }}

    tableBody.innerHTML = moduleData.map(function(m) {{
        var successRate = m.total > 0 ? ((m.passed / m.total) * 100).toFixed(0) : '0';
        var slaRate = 90;
        return '<tr onclick="showDetailedReport()" style="cursor:pointer;">'
            + '<td>' + (m.module || 'Unknown Module') + '</td>'
            + '<td>' + (m.total || 0) + '</td>'
            + '<td>' + (m.passed || 0) + '</td>'
            + '<td>' + (m.failed || 0) + '</td>'
            + '<td>' + (m.skipped || 0) + '</td>'
            + '<td>' + formatDuration(m.durationMillis || 0) + '</td>'
            + '<td class="' + (slaRate >= 90 ? 'sla-pass' : 'sla-fail') + '">' + slaRate + '%</td>'
            + '<td class="' + (successRate >= slaRate ? 'sla-pass' : 'sla-fail') + '">' + successRate + '%</td>'
            + '</tr>';
    }}).join('');
}}

/* ===== Floating tooltip for Last 7 circles =====
   Lives at body level so it is never clipped by .table-container's overflow.
   Uses document-level event delegation so it works for dynamically rendered rows. */
(function() {{
    var tip = document.getElementById('miniTooltip');
    if (!tip) return;

    function positionTip(target) {{
        var rect = target.getBoundingClientRect();
        var tipRect = tip.getBoundingClientRect();
        var left = rect.left + (rect.width / 2) - (tipRect.width / 2);
        var top = rect.top - tipRect.height - 10;
        var margin = 6;
        if (left < margin) left = margin;
        if (left + tipRect.width > window.innerWidth - margin) {{
            left = window.innerWidth - tipRect.width - margin;
        }}
        if (top < margin) {{
            // not enough room above — show below
            top = rect.bottom + 10;
        }}
        tip.style.left = left + 'px';
        tip.style.top = top + 'px';
    }}

    document.addEventListener('mouseover', function(e) {{
        var el = e.target;
        if (!el || !el.classList || !el.classList.contains('mini-circle')) return;
        var text = el.getAttribute('data-tooltip');
        if (!text) return;
        tip.textContent = text;
        tip.style.left = '-9999px';
        tip.style.top = '-9999px';
        tip.classList.add('show');
        // Position after the browser has laid out the tooltip with its new text.
        requestAnimationFrame(function() {{ positionTip(el); }});
    }});

    document.addEventListener('mouseout', function(e) {{
        var el = e.target;
        if (!el || !el.classList || !el.classList.contains('mini-circle')) return;
        tip.classList.remove('show');
    }});

    window.addEventListener('scroll', function() {{
        tip.classList.remove('show');
    }}, true);
}})();

/* ===== Lightbox (screenshot + video) ===== */
document.addEventListener('click', function(e) {{
    if (e.target.classList.contains('screenshot')) {{
        var modal = document.getElementById('lightboxModal');
        var modalImg = document.getElementById('lightboxImage');
        var modalVideo = document.getElementById('lightboxVideo');
        if (modal && modalImg && modalVideo) {{
            modalVideo.style.display = 'none';
            modalVideo.pause();
            modalVideo.src = '';
            modalImg.src = e.target.src;
            modalImg.style.display = 'block';
            modal.style.display = 'block';
        }}
    }}
    if (e.target.id === 'closeModal' || e.target.classList.contains('modal')) {{
        var modal = document.getElementById('lightboxModal');
        var modalVideo = document.getElementById('lightboxVideo');
        if (modalVideo) {{ modalVideo.pause(); modalVideo.src = ''; }}
        if (modal) {{ modal.style.display = 'none'; }}
    }}
}});
</script>
</body>
</html>
"""
        return html_template

    @staticmethod
    def generate_final_report():
        try:
            os.makedirs("reports", exist_ok=True)
            suite_start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            json_str = SummaryReportGenerator.generate_report_json(suite_start_time)
            json_path = os.path.join("reports", "report.json")
            with open(json_path, 'w', encoding='utf-8') as f:
                f.write(json_str)
            html_str = SummaryReportGenerator.build_custom_html(json_str)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            html_path = os.path.join("reports", f"report_{timestamp}.html")
            Env = ConfigReader.get_property("Environment")
            daily_checklist_html_path = FrameworkConstants.get_daily_checklist_result_path() / f"daily_checklist_{Env}_{timestamp}.html"
            deploy_checklist_html_path = FrameworkConstants.get_deploy_checklist_result_path() / f"deploy_checklist_{Env}_{timestamp}.html"
            regression_checklist_html_path = FrameworkConstants.get_regression_checklist_result_path() / f"{ConfigReader.get_property('SuiteName')}_{Env}_{timestamp}.html"

            if "resul" in ConfigReader.get_property("Project").lower():
                report_name = "RESUL"
            elif "star" in ConfigReader.get_property("Project").lower():
                report_name = "Marketing Star"

            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_str)

            subject_line_timestamp = datetime.now().strftime("%d %B %Y")
            suite_name = ConfigReader.get_property("SuiteName").lower()

            if "daily" in ConfigReader.get_property("SuiteName").lower():
                os.makedirs(FrameworkConstants.get_daily_checklist_result_path(), exist_ok=True)
                with open(daily_checklist_html_path, 'w', encoding='utf-8') as f:
                    f.write(html_str)
                print(f"\n[INFO] Generated Daily Checklist HTML at: {daily_checklist_html_path}")
                ConfigReader.set_runtime_property("execution_report_path", daily_checklist_html_path)
                subject_line = f"{report_name} - Daily Checklist Execution Completed in the {Env.upper()} Env on {subject_line_timestamp}."
            elif "post" in ConfigReader.get_property("SuiteName").lower():
                os.makedirs(FrameworkConstants.get_deploy_checklist_result_path(), exist_ok=True)
                with open(deploy_checklist_html_path, 'w', encoding='utf-8') as f:
                    f.write(html_str)
                print(f"\n[INFO] Generated Deployment Checklist HTML at: {deploy_checklist_html_path}")
                subject_line = f"{report_name} - Deployment Checklist Execution completed in the {Env.upper()} Env on {subject_line_timestamp}."
                ConfigReader.set_runtime_property("execution_report_path", deploy_checklist_html_path)
            else:
                os.makedirs(FrameworkConstants.get_regression_checklist_result_path(), exist_ok=True)
                with open(regression_checklist_html_path, 'w', encoding='utf-8') as f:
                    f.write(html_str)
                print(f"\n[INFO] Generated Regression Checklist HTML at: {regression_checklist_html_path}")
                subject_line = f"{report_name} - {ConfigReader.get_property("SuiteName")} Regression Execution Completed in the {Env.upper()} Env on {subject_line_timestamp}."
                ConfigReader.set_runtime_property("execution_report_path", regression_checklist_html_path)

            if "yes" in ConfigReader.get_property("isReportSend").lower():
                ConfigReader.set_runtime_property("subject", subject_line)
                if "daily" in suite_name:
                    EmailSender.send_email(daily_checklist_html_path, "Automation HTML Report")
                elif "post" in suite_name:
                    EmailSender.send_email(deploy_checklist_html_path, "Automation HTML Report")
                else:
                    EmailSender.send_email(regression_checklist_html_path, "Automation HTML Report")

            import webbrowser
            try:
                webbrowser.open(f"file://{os.path.abspath(html_path)}")
            except:
                pass
        except Exception as e:
            import traceback
            print(f"[ERROR] Generate Report Failed: {e}")
            traceback.print_exc()
