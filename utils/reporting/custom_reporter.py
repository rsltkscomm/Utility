import json
import os
import base64
from datetime import datetime

from utils.constants.framework_constants import FrameworkConstants
from utils.ini_file_reader import ConfigReader
from utils.reporting.email_sender import EmailSender


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

    @classmethod
    def attach_video(cls, test_case_id, video_url):
        execution = next((e for e in cls.test_executions if e.test_case_id == test_case_id), None)
        if not execution and cls.test_executions:
            # Fallback to the latest execution recorded by this worker just in case context was wiped.
            execution = cls.test_executions[-1]
        
        if execution:
            execution.video_url = video_url

    @classmethod
    def get_test_executions(cls):
        return cls.test_executions

    @classmethod
    def add_test_execution(cls, module, scenario_id, test_case_id, short_description):
        # Prevent duplicates
        if any(e.test_case_id == test_case_id for e in cls.test_executions):
            print(f"⚠️ Duplicate Test Case ID skipped: {test_case_id}")
            return None

        execution = TestExecution()
        execution.module = module
        execution.scenario_id = scenario_id
        execution.test_case_id = test_case_id
        execution.short_description = short_description
        execution.start_time = datetime.now()
        execution.status = ExecutionStatus.PASS
        execution.steps = []

        cls.test_executions.append(execution)
        return execution

    @classmethod
    def log_step(cls, action, expected_result, actual_result, status: bool, page=None):
        from utilities_py.excel_helper.test_context import TestContext
        test_case_id = getattr(TestContext, "current_testcase_id", None)
        if not test_case_id:
            print("⚠️ Cannot log step without an active test_case_id in TestContext.")
            return

        step_status = StepStatus.PASS if status else StepStatus.FAIL
        
        execution = next((e for e in cls.test_executions if e.test_case_id == test_case_id), None)
        
        if not execution:
            print(f"⚠️ Cannot find active test execution for {test_case_id}.")
            return

        # check duplicate
        if any(s.action == action and s.expected_result == expected_result for s in execution.steps):
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
        execution = next((e for e in cls.test_executions if e.test_case_id == test_case_id), None)
        
        if not execution:
            execution = TestExecution()
            execution.test_case_id = test_case_id
            execution.start_time = datetime.now()
            execution.status = ExecutionStatus.PASS
            execution.steps = []
            cls.test_executions.append(execution)

        # check duplicate
        if any(s.action == action and s.expected_result == expected_result for s in execution.steps):
            return

        step = TestStep()
        step.step_no = len(execution.steps) + 1
        step.action = action
        step.expected_result = expected_result
        step.actual_result = actual_result
        step.status = status

        if page:
            try:
                import base64
                # We enforce aggressively compressed JPEG format natively out of Playwright.
                # A 30% quality JPEG drops screenshot payload sizes from ~2MB down to ~30KB !
                # This guarantees the single-file HTML wrapper stays extremely lightweight while 
                # supporting zero broken links for emailed stakeholders!
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
        pass_count = agg["totalPass"]
        fail_count = agg["totalFail"]
        skip_count = agg["totalSkip"]
        total = pass_count + fail_count + skip_count
        duration_millis = agg["totalDurationMillis"]
        
        root = {}
        
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
            mod_total = ms["passed"] + ms["failed"] + ms["skipped"]
            modules.append({
                "module": mod_name.upper(),
                "total": mod_total,
                "passed": ms["passed"],
                "failed": ms["failed"],
                "skipped": ms["skipped"],
                "durationMillis": ms["durationMillis"]
            })
            
        modules.sort(key=lambda x: str(x["module"]))
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
            start_time_str = exec_obj.start_time.strftime("%y-%m-%d %H:%M:%S") if exec_obj.start_time else ""
            end_time_str = exec_obj.end_time.strftime("%y-%m-%d %H:%M:%S") if exec_obj.end_time else ""
            dur_ms = 0
            if exec_obj.start_time and exec_obj.end_time:
                dur_ms = int((exec_obj.end_time - exec_obj.start_time).total_seconds() * 1000)
                
            steps = []
            for step in exec_obj.steps:
                steps.append({
                    "stepNo": step.step_no,
                    "action": step.action if step.action else "",
                    "expected": step.expected_result if step.expected_result else "",
                    "actual": step.actual_result if step.actual_result else "",
                    "status": step.status if step.status else "SKIPPED",
                    "screenshot": step.screenshot_path,
                    "logFilePath": step.log_file_path
                })
                
            details.append({
                "module": exec_obj.module if exec_obj.module else "",
                "scenarioId": exec_obj.scenario_id if exec_obj.scenario_id else "",
                "testCaseId": exec_obj.test_case_id if exec_obj.test_case_id else "",
                "description": exec_obj.short_description if exec_obj.short_description else "",
                "status": exec_obj.status if exec_obj.status else "SKIPPED",
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
        return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&#39;")

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
        data = json.loads(json_str)
        meta = data.get("meta", {})
        details = data.get("details", [])
        
        companyLogoUrl = ConfigReader.get_property("CompanyLogo", "https://www.resulticks.com/images/logos/resulticks-logo-blue.svg")
        productLogoUrl = ConfigReader.get_property("ProductLogo", "https://run19.resul.io/assets/resulticks-logo-white-391eec89.svg")
        
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
        html.append('<a class="back-btn" onclick="showSummaryReport()">⬅ Back to Summary Report</a>')
        html.append('</div>')
        
        html.append('<div class="table-container">')
        html.append('<h3>Test Case Results</h3>')
        
        html.append('<div class="toolbar"><div style="display:flex; gap:15px; flex-wrap:wrap; margin:20px 0;">')
        html.append('<div><label><b>Search:</b></label><input id="searchInput" placeholder="Search test cases..." type="text"/></div>')
        html.append('<div><label><b>Filter by Status:</b></label><select id="statusFilter"><option value="">All</option><option value="PASS">Passed</option><option value="FAIL">Failed</option><option value="SKIPPED">Skipped</option></select></div>')
        html.append('</div></div>')
        
        html.append('<table id="testcaseTable"><thead><tr><th></th><th>Module</th><th>Test Case ID</th><th>Description</th><th>Status</th><th>Duration</th><th>Video</th></tr></thead><tbody>')
        
        counter = 1
        for test in details:
            module = test.get("module", "")
            testCaseId = test.get("testCaseId", "")
            desc = test.get("description", "")
            status = test.get("status", "")
            durationMs = test.get("durationMillis", 0)
            duration = f"{durationMs // 1000}s" if durationMs > 0 else "-"
            videoUrl = test.get("videoUrl") or ""
            
            statusIcon = "✅ Passed" if status == "PASS" else ("❌ Failed" if status == "FAIL" else "⚠️ Skipped")
            statusClass = SummaryReportGenerator.get_status_class(status)
            videoLink = f'<a href="#" class="play-video-btn" data-video="{videoUrl}" onclick="playVideoHandler(event, this)">🎥 View</a>' if videoUrl else "-"
            
            html.append(f'<tr data-test-id="tc{counter}" data-expanded="false" onclick="toggleDetails(this)">')
            html.append('<td class="expand-icon">+</td>')
            html.append(f'<td>{SummaryReportGenerator._escape_html(module)}</td>')
            html.append(f'<td>{SummaryReportGenerator._escape_html(testCaseId)}</td>')
            html.append(f'<td>{SummaryReportGenerator._escape_html(desc)}</td>')
            html.append(f'<td class="{statusClass}">{statusIcon}</td>')
            html.append(f'<td>{duration}</td>')
            html.append(f'<td>{videoLink}</td>')
            html.append('</tr>')
            
            html.append(f'<tr class="details-row" id="tc{counter}-details" style="display:none">')
            html.append('<td colspan="7"><table class="step-table"><tr><th>Action</th><th>Expected Result</th><th>Actual Result</th><th>Status</th><th>Screenshot</th></tr>')
            
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
        
        html.append("""
<script>
function toggleDetails(row) {
    const detailsRow = document.getElementById(row.getAttribute('data-test-id') + '-details');
    const expandIcon = row.querySelector('.expand-icon');
    
    if (detailsRow.style.display === 'none') {
        detailsRow.style.display = 'table-row';
        row.setAttribute('data-expanded', 'true');
        expandIcon.innerHTML = '-';
    } else {
        detailsRow.style.display = 'none';
        row.setAttribute('data-expanded', 'false');
        expandIcon.innerHTML = '+';
    }
}

function playVideoHandler(event, element) {
    event.stopPropagation();
    event.preventDefault();
    const modal = document.getElementById('lightboxModal');
    const modalImg = document.getElementById('lightboxImage');
    const modalVideo = document.getElementById('lightboxVideo');
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
  var mainRows = document.querySelectorAll('#testcaseTable tbody tr:not(.details-row)');
  mainRows.forEach(function(row) {
    var rowText = row.textContent.toLowerCase();
    var statusText = row.cells[4] ? row.cells[4].textContent.toLowerCase() : '';
    var rowStatus = statusText.includes('pass') ? 'PASS' : statusText.includes('fail') ? 'FAIL' : statusText.includes('skip') ? 'SKIPPED' : '';
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
      if (row.querySelector('.expand-icon')) {
        row.querySelector('.expand-icon').textContent = '+';
        row.setAttribute('data-expanded', 'false');
      }
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
        
        detailedReportContent = SummaryReportGenerator.generate_detailed_html_from_json(json_str)
        executionDate = data.get("meta", {}).get("executionDate", "")
        
        companyLogoUrl = os.environ.get("CompanyLogo", "https://www.resulticks.com/images/logos/resulticks-logo-blue.svg")
        productLogoUrl = os.environ.get("ProductLogo", "https://run19.resul.io/assets/resulticks-logo-white-391eec89.svg")
        
        overallDurationFormatted = SummaryReportGenerator.format_millis_as_hms(duration)
        reportTitle = os.environ.get("reportTitle", "Automation Test Summary Report")
        
        slaPercentage = ((pass_c / total) * 100) if total > 0 else 0
        slaFormatted = f"{int(slaPercentage)}%"
        passRate = f"{slaPercentage:.2f}%"
        
        moduleDataJson = json.dumps(data.get("modules", []))
        
        escapedModuleData = moduleDataJson.replace("\\", "\\\\").replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
        escapedDetailedReportContent = detailedReportContent.replace('`', '\\`')
        
        html_template = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>Automation Test Summary Report</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js"></script>
<style>
body {{ font-family: 'Segoe UI', sans-serif; background:#f8f9fb; margin:0; color:#333; }}
.header {{ display:flex; justify-content:space-between; align-items:center; background:linear-gradient(33deg,#8db5f1,#021e49); color:white; padding:10px 20px; }}
.header img {{ height:40px; }}
.summary-band {{ background:#0e4494; color:white; display:flex; justify-content:center; gap:30px; padding:8px; font-weight:600; }}
.summary-band div {{ display:flex; align-items:center; gap:5px; }}
.main {{ display:flex; gap:20px; padding:20px; }}
.chart-container {{ flex:1; display:flex; justify-content:center; align-items:center; }}
.table-container {{ flex:1; background:white; padding:15px; border-radius:8px; box-shadow:0 2px 6px rgba(0,0,0,0.1); overflow-x: auto; box-sizing: border-box; }}
.table-container table {{ width:100%; border-collapse:collapse; }}
.table-container th, .table-container td {{ padding:8px; border-bottom:1px solid #eee; text-align:left; }}
.table-container th {{ background:#002b6b; color:white; }}
.footer {{ text-align:center; font-size:0.8em; padding:10px; background:#f1f1f1; margin-top:20px; }}

.detailed-section {{ display: none; }}
#smartui-section, #performance-section {{ display: none; }}

.step-table {{ width:95%; margin:10px auto; border-collapse:collapse; font-size:0.85em; table-layout: fixed; }}
.step-table th, .step-table td {{ border:1px solid #ccc; padding:8px; text-align:left; word-wrap: break-word; overflow-wrap: break-word; }}
.step-table th {{ background:#f1f1f1; color:black; }}
.step-table td:nth-child(1), .step-table th:nth-child(1) {{ width: 30%; }}
.step-table td:nth-child(2), .step-table th:nth-child(2) {{ width: 25%; }}
.step-table td:nth-child(3), .step-table th:nth-child(3) {{ width: 25%; }}
.step-table td:nth-child(4), .step-table th:nth-child(4) {{ width: 10%; text-align:center; }}
.step-table td:nth-child(5), .step-table th:nth-child(5) {{ width: 10%; text-align:center; }}
.screenshot {{ max-width:80px; max-height:80px; object-fit: cover; cursor:pointer; border: 1px solid #ccc; border-radius: 4px; }}
.environment-ribbon {{ background:#f4f6f8; padding:10px; font-size:0.9em; border-bottom:1px solid #ddd; display:flex; justify-content:space-around; }}
.toolbar input, .toolbar select, .toolbar button {{ padding:6px 10px; border-radius:5px; border:1px solid #ccc; }}
.toolbar button {{ background:#007bff; color:white; border:none; cursor:pointer; }}

.modal {{
  display: none;
  position: fixed;
  z-index: 9999;
  padding-top: 60px;
  left: 0;
  top: 0;
  width: 100%;
  height: 100%;
  overflow: auto;
  background-color: rgba(0,0,0,0.9);
}}
.modal-content {{
  display: block;
  margin: auto;
  max-width: 80%;
  max-height: 80%;
}}
video.modal-content {{
  width: 80%;
  background: black;
}}
#closeModal {{
  position: absolute;
  top: 20px;
  right: 35px;
  color: #fff;
  font-size: 30px;
  font-weight: bold;
  cursor: pointer;
}}

table tr[onclick]:hover {{
  background-color: #f0f8ff !important;
  transition: background-color 0.3s ease;
}}
.chart-container canvas {{ max-width: 300px !important; max-height: 300px !important; }}

.detailed-report-link {{ text-align:right; padding:10px; display: block; }}
.detailed-report-link a {{ color: #0052cc; text-decoration: none; font-weight: 600; cursor: pointer; padding-right: 47px; }}
.detailed-report-link a:hover {{ text-decoration: underline; }}

.back-btn {{ background: white; color: blue; padding: 8px 15px; border-radius: 5px; text-decoration: none; box-shadow: 0 2px 10px rgba(0,0,0,0.2); display:inline-block; margin:20px 0; cursor: pointer; }}
.status-pass {{ color: #28a745; font-weight: bold; }}
.status-fail {{ color: #dc3545; font-weight: bold; }}
.status-skipped {{ color: #ffc107; font-weight: bold; }}
.sla-pass {{ color: #28a745; font-weight: bold; }}
.sla-fail {{ color: #dc3545; font-weight: bold; }}
</style>
</head>
<body>
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
    <div>⏱️ Duration: {overallDurationFormatted}</div>
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
    <div class="footer">Report generated on <span id="current-datetime">{executionDate}</span> | Contact: <a href="mailto:qaautomation@resulticks.com">qaautomation@resulticks.com</a></div>
</div>

<div id="detailed-section" class="detailed-section" style="padding:20px; box-sizing:border-box;">
    {escapedDetailedReportContent}
</div>

<div class="modal" id="lightboxModal">
    <span id="closeModal">✖</span>
    <img class="modal-content" id="lightboxImage" style="display:none;"/>
    <video class="modal-content" id="lightboxVideo" controls style="display:none;"></video>
</div>

<script>
function showDetailedReport() {{
    document.getElementById("summary-section").style.display = "none";
    document.getElementById("detailed-section").style.display = "block";
    window.scrollTo(0,0);
}}
function showSummaryReport() {{
    document.getElementById("detailed-section").style.display = "none";
    document.getElementById("summary-section").style.display = "block";
    window.scrollTo(0,0);
}}

document.addEventListener('DOMContentLoaded', function() {{
    const ctx = document.getElementById('chart1');
    if (ctx) {{
        new Chart(ctx, {{
          type: 'doughnut',
          data: {{ labels:['Passed','Failed','Skipped'], datasets:[{{ data:[{pass_c},{fail_c},{skip_c}], backgroundColor:['#28a745','#dc3545','#ffc107']}}] }},
          options: {{ plugins:{{ legend:{{ position:'bottom'}} }} }}
        }});
    }}
}});

const moduleDataRaw = "{escapedModuleData}";
let moduleData = [];
try {{ moduleData = JSON.parse(moduleDataRaw); }} catch (e) {{ console.error('Failed to parse module data:', e); }}

function formatDuration(ms) {{
    if (!ms || ms <= 0) return '-';
    const totalSeconds = Math.floor(ms / 1000);
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    const pad = (n) => n.toString().padStart(2, '0');
    return `${{pad(hours)}}:${{pad(minutes)}}:${{pad(seconds)}}`;
}}

function populateModuleTable() {{
    const tableBody = document.getElementById('moduleTableBody');
    if (!tableBody) return;
    
    if (!moduleData || moduleData.length === 0) {{
        tableBody.innerHTML = '<tr><td colspan="8" style="text-align: center; color: #666;">No module data available</td></tr>';
        return;
    }}
    
    tableBody.innerHTML = moduleData.map(m => {{
        const successRate = m.total > 0 ? ((m.passed/m.total)*100).toFixed(0) : '0';
        const slaRate = 90;
        return `<tr onclick="showDetailedReport(); setTimeout(() => {{ const el = document.getElementById('module-' + m.module.toLowerCase()); if (el) el.scrollIntoView({{behavior:'smooth'}}); }}, 100);" style="cursor:pointer;">
            <td>${{m.module || 'Unknown Module'}}</td>
            <td>${{m.total || 0}}</td>
            <td>${{m.passed || 0}}</td>
            <td>${{m.failed || 0}}</td>
            <td>${{m.skipped || 0}}</td>
            <td>${{formatDuration(m.durationMillis || 0)}}</td>
            <td class="${{slaRate >= 90 ? 'sla-pass' : 'sla-fail'}}">${{slaRate}}%</td>
            <td class="${{successRate >= slaRate ? 'sla-pass' : 'sla-fail'}}">${{successRate}}%</td>
        </tr>`;
    }}).join('');
}}

document.addEventListener("DOMContentLoaded", function() {{
    showSummaryReport();
    populateModuleTable();
}});

document.addEventListener('click', function(e) {{
    if (e.target.classList.contains('screenshot')) {{
        const modal = document.getElementById('lightboxModal');
        const modalImg = document.getElementById('lightboxImage');
        const modalVideo = document.getElementById('lightboxVideo');
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
        const modal = document.getElementById('lightboxModal');
        const modalVideo = document.getElementById('lightboxVideo');
        if (modalVideo) {{
            modalVideo.pause();
            modalVideo.src = '';
        }}
        if (modal) {{
            modal.style.display = 'none';
        }}
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
            daily_checklist_html_path = FrameworkConstants.get_daily_checklist_result_path() / f"daily_checklist_{timestamp}.html"
            # Save the same HTML to both locations
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_str)
            # Check if this is a daily suite run
            if "daily" in ConfigReader.get_property("SuiteName").lower():
                # Create directory for daily checklist if it doesn't exist
                os.makedirs(FrameworkConstants.get_daily_checklist_result_path(), exist_ok=True)
                # Save the same HTML to daily checklist location
                with open(daily_checklist_html_path, 'w', encoding='utf-8') as f:
                    f.write(html_str)
                print(f"\n[INFO] Generated Daily Checklist HTML at: {daily_checklist_html_path}")
            print(f"\n[INFO] Generated Final JSON Report at: {json_path}")
            print(f"[INFO] Generated Final HTML Report at: {html_path}")

            EmailSender.send_email(daily_checklist_html_path,"Automation HTML Report")

            import webbrowser
            try:
                webbrowser.open(f"file://{os.path.abspath(html_path)}")
            except:
                pass
        except Exception as e:
            import traceback
            print(f"[ERROR] Generate Report Failed: {e}")
            traceback.print_exc()

