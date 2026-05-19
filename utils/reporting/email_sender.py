
import os
import time
import base64
import json
import shutil
import zipfile
import subprocess
import re
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from html import escape

import requests

from utils.constants.framework_constants import FrameworkConstants
from utils.ini_file_reader.config_reader import ConfigReader


class EmailSender:

    # -------------------------------
    # GLOBAL VARIABLES
    # -------------------------------
    ReportName = ConfigReader.get_property("reportFileName")

    CurrentDate = None
    CurrentTime = None

    Environment = None
    Project = None
    Build = None
    Date = None
    Time = None

    Total = None
    Passed = None
    Failed = None
    Skipped = None
    PassRate = None

    StartTime = None
    EndTime = None
    TriggerType = None
    Branch = None
    ShortSHA = None

    LogsLink = None
    Failure1 = None
    Failure2 = None
    Failure3 = None

    Browser = None
    Infrastructure = None
    OS = None

    DueDate = None
    Env = None

    zipPath = None
    FilePath = None

    topFails = []
    JIRA_LOOKUP_CACHE = {}
    jiraChecker = None

    GIT_EXE = r"C:\Program Files\Git\cmd\git.exe"


    # -------------------------------
    # SEND EMAIL
    # -------------------------------
    # @classmethod
    # def send_email(cls, file_paths, file_names):
    #     try:
    #         print("📤 Sending email...")
    #
    #         host = os.getenv("host")
    #         port = int(os.getenv("port", "587"))
    #         sender = os.getenv("senderEmail")
    #         password = os.getenv("senderPassword")
    #         recipients = os.getenv("recipientEmails")
    #
    #         subject = cls.get_email_subject()
    #
    #         msg = MIMEMultipart("mixed")
    #         msg["From"] = sender
    #         msg["To"] = recipients
    #         msg["Subject"] = subject
    #
    #         cls.handle_attachments(file_paths, file_names, msg)
    #
    #         html = cls.get_mail_html()
    #         msg.attach(MIMEText(html, "html"))
    #
    #
    #         with smtplib.SMTP(host, port) as server:
    #             server.starttls()
    #             server.login(sender, password)
    #             server.send_message(msg)
    #
    #         print("✅ Email sent")
    #
    #     except Exception as e:
    #         print("❌ Email failed:", e)

    # -------------------------------
    # ATTACH FILES
    # -------------------------------
    @classmethod
    def handle_attachments(cls, file_paths, file_names, msg):
        paths = file_paths.split(",")
        names = file_names.split(",")

        for i, path in enumerate(paths):
            if not os.path.exists(path):
                continue

            part = MIMEBase("application", "octet-stream")
            with open(path, "rb") as f:
                part.set_payload(f.read())

            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f'attachment; filename="{names[i]}"')
            msg.attach(part)

    # -------------------------------
    # ZIP FILE
    # -------------------------------
    @classmethod
    def zip_html(cls, source_file, folder):
        try:
            ts = datetime.now().strftime("%d%b%Y_%H%M%S")
            name = f"{cls.ReportName}_{ts}.zip"

            dest = os.path.join(folder, name)

            with zipfile.ZipFile(dest, "w") as zipf:
                zipf.write(source_file, os.path.basename(source_file))

            return dest
        except Exception as e:
            print("ZIP error:", e)
            return None

    # -------------------------------
    # JIRA LOOKUP
    # -------------------------------
    @classmethod
    def resolve_bug_key(cls, key, failure):
        try:
            if key:
                val = os.getenv(key)
                if val:
                    return val

            if not failure:
                return "N/A"

            if failure in cls.JIRA_LOOKUP_CACHE:
                return cls.JIRA_LOOKUP_CACHE[failure]

            result = cls.search_jira(failure)
            if result:
                cls.JIRA_LOOKUP_CACHE[failure] = result
                return result

        except Exception:
            pass

        return "N/A"

    @classmethod
    def search_jira(cls, text):
        try:
            base = os.getenv("JIRA_BASE_URL")
            email = os.getenv("JIRA_EMAIL")
            key = os.getenv("JIRA_API_KEY")

            if not base or not email or not key:
                return None

            url = f"{base}/rest/api/3/search"
            params = {"jql": f'text ~ "{text}"', "maxResults": 1}

            r = requests.get(url, params=params, auth=(email, key))

            if r.status_code == 200:
                issues = r.json().get("issues", [])
                if issues:
                    return issues[0]["key"]

        except Exception:
            pass

        return None

    # -------------------------------
    # GITHUB UPLOAD
    # -------------------------------
    @classmethod
    def upload_to_github(cls, file_path):
        try:
            token = os.getenv("GITHUB_TOKEN")
            repo = "rsltkscomm/Automation-Report"

            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            name = f"report_{ts}.html"

            with open(file_path, "rb") as f:
                content = base64.b64encode(f.read()).decode()

            url = f"https://api.github.com/repos/{repo}/contents/{name}"

            body = {
                "message": f"Add report {ts}",
                "content": content,
                "branch": "main"
            }

            headers = {"Authorization": f"token {token}"}

            r = requests.put(url, json=body, headers=headers)

            if r.status_code < 300:
                return f"https://rsltkscomm.github.io/Automation-Report/{name}"

        except Exception as e:
            print("GitHub upload failed:", e)

        return None

    # -------------------------------
    # INFRA + OS
    # -------------------------------
    @classmethod
    def set_env_details(cls):
        cls.OS = "Windows" if os.name == "nt" else "Linux"

        cls.Infrastructure = os.getenv("CLOUD_PROVIDER") or "Local"

    # -------------------------------
    # DUE DATE
    # -------------------------------
    @classmethod
    def set_due_date(cls):
        due = datetime.now() + timedelta(hours=6)
        cls.DueDate = due.strftime("%d-%b-%Y %I:%M %p")

    # -------------------------------
    # GIT INFO
    # -------------------------------
    @classmethod
    def set_git_info(cls):
        try:
            cls.Branch = subprocess.check_output(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"]
            ).decode().strip()

            cls.ShortSHA = subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"]
            ).decode().strip()
        except:
            cls.Branch = "Unknown"
            cls.ShortSHA = "Unknown"

    # -------------------------------
    # HTML REPORT
    # -------------------------------
    @classmethod
    def get_mail_html(cls):
        return f"""
        <html>
        <body>
        <h2>Automation Report</h2>
        <p>Project: {cls.Project}</p>
        <p>Environment: {cls.Environment}</p>
        <p>Pass: {cls.Passed}</p>
        <p>Fail: {cls.Failed}</p>
        <p>Pass Rate: {cls.PassRate}%</p>
        <p>Branch: {cls.Branch}</p>
        </body>
        </html>
        """

    # -------------------------------
    # SEARCH JIRA VIA API
    # -------------------------------
    @classmethod
    def search_jira_for_failure(cls, failure_text):
        try:
            jira_base = os.getenv("JIRA_BASE_URL")
            email = os.getenv("JIRA_EMAIL")
            api_key = os.getenv("JIRA_API_KEY")
            proj = os.getenv("PROJECT_KEY")

            if not jira_base or not email or not api_key:
                return None

            cleaned = failure_text.replace("\\", "\\\\").replace('"', '\\"')[:400]

            if proj and proj.strip():
                jql = f'project = {proj} AND issuetype = Bug AND status not in (Closed, Resolved, Done) AND (summary ~ "{cleaned}" OR description ~ "{cleaned}") ORDER BY created DESC'
            else:
                jql = f'issuetype = Bug AND status not in (Closed, Resolved, Done) AND (summary ~ "{cleaned}" OR description ~ "{cleaned}") ORDER BY created DESC'

            url = f"{jira_base}/rest/api/3/search"

            response = requests.get(
                url,
                params={"jql": jql, "maxResults": 1, "fields": "key"},
                auth=(email, api_key),
                timeout=10
            )

            if 200 <= response.status_code < 300:
                issues = response.json().get("issues", [])
                if issues:
                    return issues[0].get("key")

        except Exception as t:
            print(f"[JIRA-REST] error: {t}")

        return None

    # -------------------------------
    # READ HTTP RESPONSE
    # -------------------------------
    @staticmethod
    def read_http_response(response):
        try:
            return response.text
        except Exception:
            return ""

    # -------------------------------
    # SEND EMAIL
    # -------------------------------
    @classmethod
    def send_email(cls, file_paths, file_names):
        try:

            print("Paths:", file_paths)
            print("Names:", file_names)

            host = ConfigReader.get_property("host")
            port = ConfigReader.get_property("port")
            sender_email = ConfigReader.get_property("senderEmail")
            sender_password = ConfigReader.get_property("senderPassword")
            recipients = ConfigReader.get_property("recipientEmails")

            subject = cls.get_email_subject()

            cls.get_parameter()

            msg = MIMEMultipart("mixed")
            msg["From"] = sender_email
            msg["To"] = recipients
            msg["Subject"] = subject

            cls.handle_report_attachments(file_paths, file_names, msg)

            html_content = cls.get_mail_html()
            cls.add_html_part(msg, html_content)

            import smtplib
            with smtplib.SMTP(host, int(port)) as server:
                server.starttls()
                server.login(sender_email, sender_password)
                server.send_message(msg)

            print("Email sent successfully to:", recipients)

        except Exception as e:
            print("General email failure:", str(e))

    # -------------------------------
    # SMTP PROPERTIES
    # -------------------------------
    @staticmethod
    def get_smtp_properties(host, port):
        return {
            "mail.smtp.host": host,
            "mail.smtp.port": port,
            "mail.smtp.auth": "true",
            "mail.smtp.starttls.enable": "true"
        }

    # -------------------------------
    # CREATE SESSION (NOT USED IN PYTHON)
    # -------------------------------
    @staticmethod
    def create_mail_session(props, email, password):
        return {
            "props": props,
            "email": email,
            "password": password
        }

    # -------------------------------
    # PREPARE MESSAGE
    # -------------------------------
    @staticmethod
    def prepare_message(from_addr, to_list, subject):
        msg = MIMEMultipart()
        msg["From"] = from_addr
        msg["To"] = to_list
        msg["Subject"] = subject
        return msg

    # -------------------------------
    # PARSE RECIPIENTS
    # -------------------------------
    @staticmethod
    def parse_recipients(email_list):
        return [email.strip() for email in email_list.split(",") if email.strip()]

    # -------------------------------
    # HANDLE ATTACHMENTS + FILE COPY + GITHUB
    # -------------------------------
    @classmethod
    def handle_report_attachments(cls, file_paths, file_names, msg):

        paths = str(file_paths).split(",")
        names = file_names.split(",")

        source_file = paths[0]
        target_folder = ""
        ReportName = ConfigReader.get_property("SuiteName")

        if "daily" in ReportName.lower():
            target_folder = source_file
            LogsLink = "https://azureresulticks-my.sharepoint.com/:f:/g/personal/a_maheshanand_resulticks_com/Eq7fuRascUlEk9jufCwOBeYByg5PbIo-dOjEf3mfTbKBJg?e=4e7gMT";

        elif "Deploy" in ReportName.lower():
            target_folder = os.getenv("ONEDRIVE_BASE_PATH") + "\\DeploymentCheckListResults\\"
            LogsLink = "https://azureresulticks-my.sharepoint.com/:f:/g/personal/a_maheshanand_resulticks_com/Eq7fuRascUlEk9jufCwOBeYByg5PbIo-dOjEf3mfTbKBJg?e=4e7gMT";

        elif "Regression" in ReportName.lower():
            target_folder = os.getenv("ONEDRIVE_BASE_PATH") + "\\RegressionExecution\\"
            LogsLink = "https://azureresulticks-my.sharepoint.com/:f:/g/personal/a_maheshanand_resulticks_com/Eqc9Vj5D0sNMr_rEREbfQgIB1CDqSqq6M-5noPgNHXaTOA?e=dwAkeT";

        # import os
        # import shutil
        #
        # source_file = paths[0]
        # target_file = os.path.join(target_folder, os.path.basename(source_file))
        #
        # if not os.path.exists(target_file):
        #     shutil.copy(source_file, target_file)
        # else:
        #     print(f"File already exists, skipping: {target_file}")
        #
        # timestamp = str(int(time.time() * 1000))
        # new_file_path = os.path.join(target_folder, f"{timestamp}_{os.path.basename(source_file)}")
        #
        # shutil.copy(source_file, new_file_path)
        #
        # cls.FilePath = new_file_path
        # cls.zipPath = new_file_path
        #
        # github_url = cls.publish_to_github_root(new_file_path)  # ✅ FIXED
        # if github_url:
        #     cls.FilePath = github_url
        #     print("✅ GitHub Pages URL:", cls.FilePath)
        #
        # use_custom_name = os.getenv("AttachMailFile", "no").lower() == "yes"
        #
        # if use_custom_name:
        #     for i in range(len(paths)):
        #         cls.attach_file(msg, paths[i], names[i])  # ✅ FIXED
        #
        # print("📄 File stored in OneDrive path:", new_file_path)

    # -------------------------------
    # ATTACH FILE
    # -------------------------------
    @staticmethod
    def attach_file(msg, file_path, file_name):
        try:
            if not os.path.exists(file_path):
                print(f"Attachment not found: {file_path}")
                return

            part = MIMEBase("application", "octet-stream")

            with open(file_path, "rb") as f:
                part.set_payload(f.read())

            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f'attachment; filename="{file_name}"')

            msg.attach(part)

        except Exception as e:
            print(f"Failed to attach {file_path}: {str(e)}")

    # -------------------------------
    # ZIP HTML WITH TIMESTAMP
    # -------------------------------
    @classmethod
    def zip_html_with_timestamp(cls, source_file, one_drive_folder):
        try:
            time_stamp = datetime.now().strftime("%d%b%Y_%H%M%S")

            if "Daily" in cls.ReportName:
                zip_file_name = f"DailyCheckList_{time_stamp}.zip"
            elif "Deploy" in cls.ReportName:
                zip_file_name = f"DeploymentCheckList_{time_stamp}.zip"
            elif "Regression" in cls.ReportName:
                zip_file_name = f"{cls.ReportName}_{time_stamp}.zip"
            else:
                zip_file_name = f"{time_stamp}.zip"

            dest_zip_file = os.path.join(one_drive_folder, zip_file_name)

            with zipfile.ZipFile(dest_zip_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
                zipf.write(source_file, os.path.basename(source_file))

            return dest_zip_file

        except Exception as e:
            print(f"Error creating ZIP: {str(e)}")
            return None

    # -------------------------------
    # ADD HTML PART
    # -------------------------------
    @staticmethod
    def add_html_part(msg, html_content):
        part = MIMEText(html_content, "html")
        msg.attach(part)

    # -------------------------------
    # SET DATE TIME
    # -------------------------------
    @classmethod
    def set_date_time(cls):
        # suite_time="09-Apr-2026 12:33:47"
        suite_time = os.getenv("START_TIME")
        #   suite_time =  SummaryReportGenerator.suiteStartTime.split(" ")
        parts = suite_time.split(" ")

        if len(suite_time) >= 2:
            cls.CurrentDate = parts[0]
            cls.CurrentTime = parts[1]


    # -------------------------------
    # GET PARAMETER (MAIN SETUP)
    # -------------------------------
    @classmethod
    def get_parameter(cls):

        cls.ReportName = ConfigReader.get_property("SuiteName")

        cls.set_date_time()  # ✅ FIXED

        Environment = ConfigReader.get_property("Environment")
        Project = ConfigReader.get_property("Project")
        Build = ConfigReader.get_property("ReleaseVersion")

        cls.Date = cls.CurrentDate
        cls.Time = cls.CurrentTime
        from utils.reporting.custom_reporter import SummaryReportGenerator

        agg = SummaryReportGenerator.aggregate_stats()
        cls.Total = str(agg["totalSkip"] + agg["totalPass"] + agg["totalFail"])
        cls.Passed = str(agg["totalPass"])
        cls.Failed = str(agg["totalFail"])
        cls.Skipped = str(agg["totalSkip"])

        cls.total_tests = int(cls.Total)
        cls.passed_tests = int(cls.Passed)

        cls.PassRate = str((cls.passed_tests * 100) // cls.total_tests) if cls.total_tests > 0 else "0"

        # cls.StartTime = SummaryReportGenerator.currentDate
        # cls.EndTime = SummaryReportGenerator.endDateTime



        cls.Browser = ConfigReader.get_property("Browser")
        cls.Env = Environment

        cls.set_trigger_and_git_info()  # ✅ FIXED
        cls.set_infra_and_os()  # ✅ FIXED
        cls.set_due_date()  # ✅ FIXED

        # cls.calculate_top_failures(DetailedTestReporter.test_executions)  # ✅ FIXED

    # -------------------------------
    # SET INFRA + OS
    # -------------------------------
    @classmethod
    def set_infra_and_os(cls):

        os_name = os.name.lower()

        if "nt" in os_name:
            cls.OS = "Windows"
        elif "posix" in os_name:
            cls.OS = "Linux"
        else:
            cls.OS = "Unknown"

        cls.Infrastructure = "Local"

        cloud = os.getenv("CLOUD_PROVIDER")
        if cloud:
            cls.Infrastructure = cloud

    # -------------------------------
    # SET DUE DATE
    # -------------------------------
    @classmethod
    def set_due_date(cls):

        cal = datetime.now() + timedelta(hours=6)
        cal = cal.replace(minute=0, second=0, microsecond=0)

        cls.DueDate = cal.strftime("%d-%b-%Y %I:%M %p")

    # -------------------------------
    # SET TRIGGER + GIT INFO
    # -------------------------------
    @classmethod
    def set_trigger_and_git_info(cls):

        build_cause = os.getenv("BUILD_CAUSE")

        if build_cause and "TIMERTRIGGER" in build_cause:
            cls.TriggerType = "Scheduled"
        else:
            cls.TriggerType = "On-Demand"

        cls.Branch = os.getenv("GIT_BRANCH")
        cls.ShortSHA = os.getenv("GIT_COMMIT")

        if not cls.Branch or not cls.ShortSHA:
            try:
                cls.Branch = subprocess.check_output(
                    ["git", "rev-parse", "--abbrev-ref", "HEAD"]
                ).decode().strip()

                cls.ShortSHA = subprocess.check_output(
                    ["git", "rev-parse", "--short", "HEAD"]
                ).decode().strip()

            except Exception:
                cls.Branch = "Unknown"
                cls.ShortSHA = "Unknown"

    # -------------------------------
    # CALCULATE TOP FAILURES
    # -------------------------------
    @classmethod
    def calculate_top_failures(cls, executions):

        failure_counts = {}
        module_fail_tests = {}

        if executions:
            for t in executions:
                if not t or t.get_status() != "FAIL":
                    continue

                module = t.get_module() if t.get_module() else "Unknown"
                failure_reason = "Unknown"

                try:
                    steps = t.get_steps()

                    if steps:
                        for step in steps:
                            if step.get_status() == "FAIL":
                                ar = step.get_actual_result()
                                if ar:
                                    failure_reason = ar
                                    break
                except Exception:
                    pass

                failure_counts[module] = failure_counts.get(module, 0) + 1
                module_fail_tests.setdefault(module, []).append(failure_reason)

        modules_sorted = sorted(
            failure_counts.keys(),
            key=lambda m: (-failure_counts[m], m.lower())
        )

        top_fails_local = []

        for module in modules_sorted:
            if len(top_fails_local) >= 3:
                break

            reasons = module_fail_tests.get(module, [])
            unique_reasons = list(dict.fromkeys(reasons))

            for reason in unique_reasons:
                top_fails_local.append(f"Module: {module} | FailureReason: {reason}")
                if len(top_fails_local) >= 3:
                    break

        cls.Failure1 = top_fails_local[0] if len(top_fails_local) > 0 else "N/A"
        cls.Failure2 = top_fails_local[1] if len(top_fails_local) > 1 else "N/A"
        cls.Failure3 = top_fails_local[2] if len(top_fails_local) > 2 else "N/A"

    # -------------------------------
    # GET EMAIL SUBJECT
    # -------------------------------
    @classmethod
    def get_email_subject(cls):
        return ConfigReader.get_property("subject")

    # -------------------------------
    # PUBLISH TO GITHUB (CORE LOGIC)
    # -------------------------------
    @classmethod
    def publish_to_github_root(cls, report_file_path):
        try:
            token = ConfigReader.get_property("GITHUB_TOKEN")

            if not token:
                print("❌ GITHUB_TOKEN not set")
                return None

            repo = "rsltkscomm/Automation-Report"
            pages_base_url = "https://rsltkscomm.github.io/Automation-Report/"
            repo_dir = "C:/automation/github-pages/repo"

            repo_exists = os.path.exists(repo_dir) and os.path.exists(os.path.join(repo_dir, ".git"))

            if not repo_exists:
                print("First run: Cloning repository...")

                if os.path.exists(repo_dir):
                    cls.delete_directory(repo_dir)  # ✅ FIXED

                clone_url = f"https://{token}@github.com/{repo}.git"
                cls.run_git("C:/automation/github-pages", "clone", clone_url, "repo")  # ✅ FIXED

                default_branch = cls.detect_default_branch(repo_dir)  # ✅ FIXED

                if default_branch != "main":
                    cls.run_git(repo_dir, "branch", "-m", default_branch, "main")
                    cls.run_git(repo_dir, "push", "origin", "main")
                    cls.run_git(repo_dir, "push", "origin", "--delete", default_branch)
                    cls.run_git(repo_dir, "branch", "--set-upstream-to=origin/main", "main")

            else:
                print("Updating existing repository...")

                cls.cleanup_git_locks(repo_dir)

                try:
                    cls.run_git(repo_dir, "checkout", "main")
                except:
                    try:
                        cls.run_git(repo_dir, "fetch", "origin")
                        cls.run_git(repo_dir, "checkout", "-b", "main", "origin/main")
                    except Exception as ex:
                        print("Could not switch to main:", ex)

                try:
                    cls.run_git(repo_dir, "fetch", "origin")
                    cls.run_git(repo_dir, "reset", "--hard", "origin/main")
                except Exception as e:
                    print("Pull failed:", e)

            # Git config
            cls.run_git(repo_dir, "config", "user.name", "automation-bot")
            cls.run_git(repo_dir, "config", "user.email", "automation@company.com")

            # Copy report
            time_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_name = f"report_{time_stamp}.html"

            shutil.copy(report_file_path, os.path.join(repo_dir, report_name))

            cls.update_index_html(repo_dir, report_name, time_stamp)

            cls.run_git(repo_dir, "add", report_name)
            cls.run_git(repo_dir, "add", "index.html")

            status = subprocess.check_output(
                ["git", "status", "--porcelain"],
                cwd=repo_dir
            ).decode()

            if status.strip():
                cls.run_git(repo_dir, "commit", "-m", f"Add report {time_stamp}")
                print("Pushing to GitHub...")
                cls.run_git(repo_dir, "push", "origin", "main")
            else:
                print("No changes to commit")

            cls.verify_github_pages_branch(repo, token)

            return pages_base_url + report_name

        except Exception as e:
            print("GitHub publish failed:", e)
            return None

    # -------------------------------
    # DETECT DEFAULT BRANCH
    # -------------------------------
    @staticmethod
    def detect_default_branch(repo_dir):
        try:
            output = subprocess.check_output(
                ["git", "branch", "--show-current"],
                cwd=repo_dir
            ).decode().strip()

            if output:
                return output
        except:
            pass

        try:
            output = subprocess.check_output(
                ["git", "ls-remote", "--symref", "origin", "HEAD"],
                cwd=repo_dir
            ).decode()

            match = re.search(r"ref: refs/heads/(\S+)\s+HEAD", output)
            if match:
                return match.group(1)

        except:
            pass

        return "master"

    # -------------------------------
    # VERIFY GITHUB PAGES
    # -------------------------------
    @staticmethod
    def verify_github_pages_branch(repo, token):
        try:
            import requests

            api_url = f"https://api.github.com/repos/{repo}/pages"

            headers = {
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github.v3+json"
            }

            response = requests.get(api_url, headers=headers)

            if response.status_code == 200:
                print("GitHub Pages is configured on:", response.text)
            else:
                print("Could not verify GitHub Pages configuration")

        except Exception as e:
            print("Error verifying GitHub Pages:", str(e))

    # -------------------------------
    # UPDATE INDEX.HTML
    # -------------------------------
    @staticmethod
    def update_index_html(repo_dir, new_report, timestamp):
        index_file = os.path.join(repo_dir, "index.html")

        if os.path.exists(index_file):
            with open(index_file, "r", encoding="utf-8") as f:
                lines = f.readlines()

            for i in range(len(lines)):
                if "(Latest)" in lines[i]:
                    lines[i] = lines[i].replace(" (Latest)", "")
                    break
        else:
            lines = [
                "<!DOCTYPE html>\n",
                "<html>\n",
                "<head><title>Automation Reports</title>\n",
                "<style>\n",
                "body { font-family: Arial; margin: 20px; }\n",
                "h1 { color: #333; }\n",
                "ul { list-style-type: none; padding: 0; }\n",
                "li { margin: 10px 0; }\n",
                "a { color: #0066cc; text-decoration: none; }\n",
                "a:hover { text-decoration: underline; }\n",
                ".latest { font-weight: bold; color: #28a745; }\n",
                "</style>\n",
                "</head>\n",
                "<body>\n",
                "<h1>Automation Test Reports</h1>\n",
                "<ul>\n",
                "</ul>\n",
                "</body>\n",
                "</html>\n"
            ]

        for i in range(len(lines)):
            if "<ul>" in lines[i]:
                new_link = f"  <li><a href='{new_report}' class='latest'>🚀 Report {timestamp} (Latest)</a></li>\n"
                lines.insert(i + 1, new_link)
                break

        with open(index_file, "w", encoding="utf-8") as f:
            f.writelines(lines)

    # -------------------------------
    # CLEANUP GIT LOCKS
    # -------------------------------
    @staticmethod
    def cleanup_git_locks(repo_dir):
        try:
            git_dir = os.path.join(repo_dir, ".git")

            if not os.path.exists(git_dir):
                return

            for root, dirs, files in os.walk(git_dir):
                for file in files:
                    if file.endswith(".lock"):
                        try:
                            os.remove(os.path.join(root, file))
                        except Exception:
                            pass

        except Exception:
            pass

    # -------------------------------
    # UPLOAD VIA GITHUB API
    # -------------------------------
    @classmethod
    def upload_via_github_api(cls, report_file_path):
        try:
            token = os.getenv("GITHUB_TOKEN")
            repo = "rsltkscomm/Automation-Report"

            time_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_name = f"report_{time_stamp}.html"

            with open(report_file_path, "rb") as f:
                content = f.read()

            encoded_content = base64.b64encode(content).decode()

            api_url = f"https://api.github.com/repos/{repo}/contents/{report_name}"

            body = {
                "message": f"Add report {time_stamp}",
                "content": encoded_content,
                "branch": "main"
            }

            headers = {
                "Authorization": f"token {token}",
                "Content-Type": "application/json"
            }

            response = requests.put(api_url, json=body, headers=headers)

            if 200 <= response.status_code < 300:
                print("File uploaded via API")
                return f"https://rsltkscomm.github.io/Automation-Report/{report_name}"
            else:
                print(f"API upload failed: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            print("Upload failed:", str(e))
            return None

    # -------------------------------
    # CLEANUP OLD RUNS
    # -------------------------------
    @classmethod
    def cleanup_old_runs(cls):
        try:
            base_dir = "C:/automation/github-pages"

            if not os.path.exists(base_dir):
                return

            runs = [d for d in os.listdir(base_dir) if d.startswith("run_")]

            if len(runs) > 5:
                runs.sort(reverse=True)

                for run in runs[5:]:
                    cls.delete_directory(os.path.join(base_dir, run))  # ✅ FIXED
                    print(f"Cleaned up old run: {run}")

        except Exception as e:
            print("Cleanup failed:", str(e))

    # -------------------------------
    # DELETE DIRECTORY
    # -------------------------------
    @staticmethod
    def delete_directory(directory):
        try:
            if os.path.exists(directory):
                shutil.rmtree(directory, ignore_errors=True)
        except Exception:
            pass

    # -------------------------------
    # RUN GIT COMMAND
    # -------------------------------
    @staticmethod
    def run_git(dir_path, *cmd):
        try:
            full_cmd = ["git"] + list(cmd)

            print("[GIT]", " ".join(cmd))

            process = subprocess.Popen(
                full_cmd,
                cwd=dir_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True
            )

            output = ""

            for line in process.stdout:
                print("[GIT]", line.strip())
                output += line

            process.wait()

            if process.returncode != 0:
                raise Exception(f"Git command failed: {' '.join(cmd)}\nOutput: {output}")

        except Exception as e:
            raise Exception(str(e))

    # -------------------------------
    # GET MAIL HTML (FULL TEMPLATE)
    # -------------------------------
    @classmethod
    def get_mail_html(cls):

        execution_report_link = ""

        FilePath = "https://azureresulticks-my.sharepoint.com/my?id=%2Fpersonal%2Fqaautomation%5Fresulticks%5Fcom%2FDocuments%2FAutomation%2FResulticks%2FDailyCheckListResults&FolderCTID=0x012000BB23E8B091559D478C5E9FF3B7573B95";

        if FilePath and FilePath.startswith("https://azureresulticks-my.sharepoint.com/"):
            execution_report_link = f"<li>Execution report: <a href='{FilePath}' style='color: #007bff;'>[Report Link]</a></li>"

        valid_fails = []

        for failure in [cls.Failure1, cls.Failure2, cls.Failure3]:
            if failure and failure.strip() and failure.strip().lower() != "n/a":

                key = None

                if "Test:" in failure:
                    key = failure.split("Test:")[1].strip()
                elif "FailureReason:" in failure:
                    key = failure.split("FailureReason:")[1].strip()

                bug_id = "N/A"

                if key:
                    prop = os.getenv(key)
                    if prop:
                        bug_id = prop

                if bug_id == "N/A":
                    bug_id = cls.resolve_bug_key(key, failure)  # ✅ FIXED

                valid_fails.append(f"{failure} - Bug ID : <b>{bug_id or 'N/A'}</b>")

        failures_section = ""

        if valid_fails:
            failures_section = (
                    "<h4 style='color:#34495e;margin-top:25px;'>Failures (Top Items)</h4>"
                    "<ol style='margin-left:25px;'>"
                    + "".join([f"<li>{f}</li>" for f in valid_fails])
                    + "</ol>"
            )

        all_bugs_section = cls.get_all_bugs_html()

        if cls.ReportName and "daily" in cls.ReportName.lower():
            if "resul" in ConfigReader.get_property("Project").lower():
                report_name = "Resul - Daily Checklist"
            elif "star" in ConfigReader.get_property("Project").lower():
                report_name = "Marketing Star - Daily Checklist"
        elif cls.ReportName and "post" in cls.ReportName.lower():
            if "resul" in ConfigReader.get_property("Project").lower():
                report_name = "Resul - Deployment Checklist"
            elif "star" in ConfigReader.get_property("Project").lower():
                report_name = "Marketing Star - Deployment Checklist"
        else:
            if "resul" in ConfigReader.get_property("Project").lower():
                report_name = "Resul - Regression"
            elif "star" in ConfigReader.get_property("Project").lower():
                report_name = "Marketing Star - Regression"

        Environment = ConfigReader.get_property("Environment")
        Project = ConfigReader.get_property("Project")
        Build = ConfigReader.get_property("ReleaseVersion")
        start_time = os.getenv("START_TIME")
        End_TIME = os.getenv("End_TIME")

        time_format = "%d-%m-%y %I:%M:%S %p"

        # Convert string to datetime
        start_dt = datetime.strptime(start_time, time_format)
        end_dt = datetime.strptime(End_TIME, time_format)

        # Format time display
        formatted_start = start_dt.strftime("%d %b %y %I:%M %p")
        formatted_end = end_dt.strftime("%d %b %y %I:%M %p")

        # Calculate duration
        duration = end_dt - start_dt
        total_seconds = int(duration.total_seconds())

        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        formatted_duration = f"{hours:02d} Hrs : {minutes:02d} Mins : {seconds:02d} Sec"

        print(formatted_start)
        print(formatted_end)
        print(formatted_duration)

        print("Execution Duration:", duration)
        Resultickslog =FrameworkConstants.get_upload_files("resulticks-logo.svg")
        resullog =FrameworkConstants.get_upload_files("resul-logo.svg")

        LogsLink = "https://azureresulticks-my.sharepoint.com/:f:/g/personal/a_maheshanand_resulticks_com/IgCjcIOYWE09QYSBK5g1y84JAYqshazDsE60XQ6xvLUpbY4?e=RbhJDc";

        return f"""
                   <!DOCTYPE html>
        <html>
        <head>
        <meta charset="UTF-8">
        <title>Automation Execution Report</title>
        </head>

        <body style="margin:0;padding:10px;background-color:#f4f6f9;
        font-family:Segoe UI,Arial,sans-serif;">

        <table width="100%" cellpadding="0" cellspacing="0" border="0"
               style="background-color:##00006e;padding:10px 0;">

            <tr>
                <td align="center">

                    <!-- Main Container -->
                    <table width="980" cellpadding="0" cellspacing="0" border="0"
                           style="background:#ffffff;
                           border-radius:14px;
                           box-shadow:0 4px 14px rgba(0,0,0,0.08);
                           overflow:hidden;">

                        <!-- Header -->
                        <tr>
                <td style="
                    background:#00006e;
                    padding:32px 45px;
                    color:#ffffff;
                    text-align:center;
                ">

                    <h1 style="
                        margin:0;
                        font-size:30px;
                        font-weight:700;
                        letter-spacing:0.3px;
                    ">
                        {report_name} Automation Report
                    </h1>

                    <p style="
                        margin:12px 0 0 0;
                        font-size:22px;
                        font-weight:500;
                        color:#d1d5db;
                    ">
                        Execution Summary &amp; Validation Status
                    </p>

                </td>
            </tr>

                                <!-- Intro -->
                                <tr>
                                    <td style="padding:35px 45px 15px 45px;
                                    color:#374151;
                                    font-size:16px;
                                    line-height:1.9;">

                                        <p style="margin-top:0;">Hi Team,</p>

                                        <p>
                                            The <b>{report_name}</b> automation execution has been completed successfully
                                            on <b>{Environment}</b> for <b>{Project}</b>
                                            (Build <b>{Build}</b>) at
                                            <b>{cls.Date} {cls.Time} IST</b>.
                                        </p>

                                    </td>
                                </tr>

                                <!-- Summary Cards -->
                                <tr>
                                    <td style="padding:15px 45px 30px 45px;">

                                        <table width="100%" cellpadding="12"
                                               cellspacing="0" border="0">

                                            <tr>

                                                <!-- Total -->
                                                <td align="center"
                                                    style="background:#f9fafb;
                                                    border:1px solid #e5e7eb;
                                                    border-radius:10px;
                                                    padding:20px;">

                                                    <div style="font-size:15px;
                                                    color:#6b7280;
                                                    margin-bottom:8px;">

                                                        Total

                                                    </div>

                                                    <div style="font-size:36px;
                                                    font-weight:700;
                                                    color:#111827;">

                                                        {cls.Total}

                                                    </div>

                                                </td>

                                                <td width="15"></td>

                                                <!-- Passed -->
                                                <td align="center"
                                                    style="background:#ecfdf5;
                                                    border:1px solid #d1fae5;
                                                    border-radius:10px;
                                                    padding:20px;">

                                                    <div style="font-size:15px;
                                                    color:#047857;
                                                    margin-bottom:8px;">

                                                        Passed

                                                    </div>

                                                    <div style="font-size:36px;
                                                    font-weight:700;
                                                    color:#059669;">

                                                        {cls.Passed}

                                                    </div>

                                                </td>

                                                <td width="15"></td>

                                                <!-- Failed -->
                                                <td align="center"
                                                    style="background:#fef2f2;
                                                    border:1px solid #fecaca;
                                                    border-radius:10px;
                                                    padding:20px;">

                                                    <div style="font-size:15px;
                                                    color:#b91c1c;
                                                    margin-bottom:8px;">

                                                        Failed

                                                    </div>

                                                    <div style="font-size:36px;
                                                    font-weight:700;
                                                    color:#dc2626;">

                                                        {cls.Failed}

                                                    </div>

                                                </td>

                                                <td width="15"></td>

                                                <!-- Pass Rate -->
                                                <td align="center"
                                                    style="background:#eff6ff;
                                                    border:1px solid #bfdbfe;
                                                    border-radius:10px;
                                                    padding:20px;">

                                                    <div style="font-size:15px;
                                                    color:#1d4ed8;
                                                    margin-bottom:8px;">

                                                        Pass Rate

                                                    </div>

                                                    <div style="font-size:36px;
                                                    font-weight:700;
                                                    color:#2563eb;">

                                                        {cls.PassRate}%

                                                    </div>

                                                </td>

                                            </tr>

                                        </table>

                                    </td>
                                </tr>

                                <!-- Execution Details -->
                                <tr>
                                    <td style="padding:0 45px 25px 45px;">

                                        <h3 style="margin-bottom:18px;
                                        color:#111827;
                                        border-bottom:2px solid #e5e7eb;
                                        padding-bottom:10px;
                                        font-size:22px;">

                                            Execution Details

                                        </h3>

                                        <table width="100%"
                                               cellpadding="12"
                                               cellspacing="0"
                                               style="border-collapse:collapse;
                                               font-size:16px;">

                                            <tr style="background:#f9fafb;">
                                                <td width="35%"
                                                    style="font-weight:600;
                                                    color:#374151;">

                                                    Execution Duration

                                                </td>

                                                <td style="color:#111827;">

                                                    {formatted_start} - {formatted_end}
                                                    ({formatted_duration})

                                                </td>
                                            </tr>

                                            <tr>
                                                <td style="font-weight:600;color:#374151;">
                                                    Trigger Type
                                                </td>

                                                <td>{cls.TriggerType}</td>
                                            </tr>

                                            <tr style="background:#f9fafb;">
                                                <td style="font-weight:600;color:#374151;">
                                                    Branch
                                                </td>

                                                <td>{cls.Branch}</td>
                                            </tr>



                                            <tr style="background:#f9fafb;">
                                                <td style="font-weight:600;color:#374151;">
                                                    Environment
                                                </td>

                                                <td>{Environment}</td>
                                            </tr>

                                            <tr>
                                                <td style="font-weight:600;color:#374151;">
                                                    Browser / OS
                                                </td>

                                                <td>{cls.Browser} / {cls.OS}</td>
                                            </tr>

                                        </table>

                                    </td>
                                </tr>

                                <!-- Reports -->
                                <tr>
                                    <td style="padding:0 45px 25px 45px;">

                                        <h3 style="margin-bottom:18px;
                                        color:#111827;
                                        border-bottom:2px solid #e5e7eb;
                                        padding-bottom:10px;
                                        font-size:22px;">

                                            Reports & Artifacts

                                        </h3>

                                        <table cellpadding="0" cellspacing="0">

                                            <tr>
                                                <td style="padding-bottom:15px;">

                                                    <a href="{FilePath}"
                                                       style="background:#2563eb;
                                                       color:#ffffff;
                                                       text-decoration:none;
                                                       padding:14px 24px;
                                                       border-radius:8px;
                                                       font-size:16px;
                                                       font-weight:600;
                                                       display:inline-block;">

                                                        View Execution Report

                                                    </a>

                                                </td>
                                            </tr>

                                            <tr>
                                                <td>

                                                    <a href="{LogsLink}"
                                                       style="background:#111827;
                                                       color:#ffffff;
                                                       text-decoration:none;
                                                       padding:14px 24px;
                                                       border-radius:8px;
                                                       font-size:16px;
                                                       font-weight:600;
                                                       display:inline-block;">

                                                        View Logs & Evidence

                                                    </a>

                                                </td>
                                            </tr>

                                        </table>

                                    </td>
                                </tr>

                                <!-- Failures -->
                                {f'''
                                <tr>
                                    <td style="padding:0 45px 25px 45px;">

                                        <h3 style="margin-bottom:18px;
                                        color:#dc2626;
                                        border-bottom:2px solid #fecaca;
                                        padding-bottom:10px;
                                        font-size:22px;">

                                            Failure Summary

                                        </h3>

                                        <ol style="padding-left:22px;
                                        color:#374151;
                                        font-size:16px;
                                        line-height:2;">

                                            {"".join([f"<li>{f}</li>" for f in valid_fails])}

                                        </ol>

                                    </td>
                                </tr>
                                ''' if valid_fails else ""}

                                {all_bugs_section}

                                <!-- Action Items -->
                                <tr>
                                    <td style="padding:0 45px 35px 45px;">

                                        <h3 style="margin-bottom:18px;
                                        color:#111827;
                                        border-bottom:2px solid #e5e7eb;
                                        padding-bottom:10px;
                                        font-size:22px;">

                                            Action Items

                                        </h3>

                                        <ul style="padding-left:22px;
                                        color:#374151;
                                        font-size:16px;
                                        line-height:2;">

                                            <li>
                                                Resolve identified failures by
                                                <b>{cls.DueDate}</b>
                                                and re-execute it in <b>{cls.Env}</b>
                                            </li>

                                        </ul>

                                    </td>
                                </tr>

                                <!-- Footer Section -->
                <tr>
                    <td style="background: #f4f6f9; padding: 25px 30px; text-align: center; border-top: 1px solid #e2e8f0;">
                        <p style="margin: 0 0 8px 0; font-size: 14px; color: #4a5568;"> Thanks & Regards,</p>
                        <p style="margin: 0 0 12px 0; font-size: 16px; font-weight: 700; color: #1a202c;">QA Automation Team</p>
                        <p style="margin: 0; font-size: 12px; color: #a0aec0;">Generated on {cls.Date} at {cls.Time} IST • Automated Report System</p>
                        <div style="margin-top: 15px; padding-top: 15px; border-top: 1px solid #e2e8f0;">
                            <p style="margin: 0; font-size: 11px; color: #a0aec0;">
                                <strong>qaautomation@resultskmsail.com</strong>
                            </p>
                        </div>
                    </td>
                </tr>

                <!-- Email Footer Note -->
                <tr>
                    <td style="padding: 15px 30px; background: #edf2f7; text-align: center;">
                        <p style="margin: 0; font-size: 11px; color: #718096;">
                            This is an automated email from the QA Automation Framework. Please do not reply to this message.
                        </p>
                    </td>
                </tr>

            </table>

        </td>
    </tr>
</table>

</body>
</html>
                """

    @classmethod
    def get_all_bugs_html(cls):
        raw_value = ConfigReader.get_runtime_property("ALLBUGS", "{}") or "{}"
        try:
            all_bugs = json.loads(raw_value) if isinstance(raw_value, str) else dict(raw_value)
        except Exception as exc:
            print(f"[EMAIL] Failed to parse ALLBUGS: {exc}")
            all_bugs = {}

        if not all_bugs:
            return ""

        jira_base_url = (ConfigReader.get_property("JIRA_BASE_URL", "") or os.getenv("JIRA_BASE_URL", "")).rstrip("/")
        rows = []
        for bug_key, details in all_bugs.items():
            if not isinstance(details, dict):
                details = {"failureReason": str(details)}

            test_case_key = escape(str(details.get("testCaseKey", "")))
            failure_reason = escape(str(details.get("failureReason", "")))
            status_text = "Created" if details.get("created") else "Existing"
            status_color = "#047857" if details.get("created") else "#92400e"
            bug_label = escape(str(bug_key))
            if jira_base_url and bug_key:
                bug_cell = (
                    f'<a href="{jira_base_url}/browse/{bug_label}" '
                    f'style="color:#2563eb;text-decoration:none;font-weight:600;">{bug_label}</a>'
                )
            else:
                bug_cell = f"<b>{bug_label}</b>"

            rows.append(f"""
                <tr>
                    <td style="padding:10px;border:1px solid #e5e7eb;">{bug_cell}</td>
                    <td style="padding:10px;border:1px solid #e5e7eb;">{test_case_key}</td>
                    <td style="padding:10px;border:1px solid #e5e7eb;">{failure_reason}</td>
                    <td style="padding:10px;border:1px solid #e5e7eb;color:{status_color};font-weight:600;">{status_text}</td>
                </tr>
            """)

        return f"""
            <tr>
                <td style="padding:0 45px 25px 45px;">
                    <h3 style="margin-bottom:18px;
                    color:#111827;
                    border-bottom:2px solid #e5e7eb;
                    padding-bottom:10px;
                    font-size:22px;">
                        Jira Bugs
                    </h3>

                    <table width="100%" cellpadding="0" cellspacing="0"
                           style="border-collapse:collapse;font-size:15px;color:#374151;">
                        <tr style="background:#f9fafb;">
                            <th align="left" style="padding:10px;border:1px solid #e5e7eb;">Bug ID</th>
                            <th align="left" style="padding:10px;border:1px solid #e5e7eb;">Test Case</th>
                            <th align="left" style="padding:10px;border:1px solid #e5e7eb;">Failure Reason</th>
                            <th align="left" style="padding:10px;border:1px solid #e5e7eb;">Status</th>
                        </tr>
                        {"".join(rows)}
                    </table>
                </td>
            </tr>
        """
