"""
json_status_manager.py
Place this file at:  utils/reporting/json_status_manager.py

Storage layout  (under  FrameworkConstants.ONEDRIVE_BASE_PATH / "execution_history"):

    execution_history/
        Resul/
            daily_Team.json
            daily_Run19.json
            daily_Run.json
            deployment_Run19.json     ← predeploy (any env) / deploy+postdeploy+post on Run19
            production_Run.json       ← deploy+postdeploy+post on Run / production(any env)
            regression_Team.json
            regression_Run19.json
            regression_Run.json
            ...
        MarketingStar/
            (same structure)

Project key normalisation (case-insensitive, from "Project" config property):
  "resul" in project   →  "Resul"
  "star"  in project   →  "MarketingStar"
  anything else        →  raw value stripped  (safe fallback)

Suite + Env combined logic
──────────────────────────
Rule 1 – "daily" anywhere in SuiteName
    → always "daily", env used as-is
    → daily_Run19.json / daily_Run.json / daily_Team.json

Rule 2 – "predeploy" anywhere in SuiteName
    → ALWAYS deployment_Run19.json  (pre-deploy is always a Run19/pre-prod gate)
    → env key is forced to "Run19" regardless of what the config says

Rule 3 – "deploy" OR "postdeploy" OR "post" anywhere in SuiteName
    (but NOT "predeploy" — that is already caught by Rule 2)
    → env decides the file:
        env = Run19  →  deployment_Run19.json
        env = Run    →  production_Run.json
        env = Team   →  deployment_Run19.json  (pre-prod default)

Rule 4 – "production" OR "prod" anywhere in SuiteName
    → ALWAYS production_Run.json  (production suite only ever targets the live env)
    → env key is forced to "Run" regardless of what the config says

Rule 5 – anything else (regression / module / communication suites)
    → always "regression", env used as-is
    → regression_Run19.json / regression_Run.json / regression_Team.json

Env key normalisation (case-insensitive, "run19" checked BEFORE "run"):
  "run19" in env  →  "Run19"
  "run"   in env  →  "Run"
  "team"  in env  →  "Team"
  other           →  raw value stripped

Complete file-name truth table  (inside the project sub-folder):
  SuiteName          Env      →  file
  ──────────────────────────────────────────────────────────────────────
  predeploy          Run19    →  deployment_Run19.json  ← forced (Rule 2)
  predeploy          Run      →  deployment_Run19.json  ← forced (Rule 2)
  predeploy          Team     →  deployment_Run19.json  ← forced (Rule 2)
  deployment         Run19    →  deployment_Run19.json
  postdeploy         Run19    →  deployment_Run19.json
  post               Run19    →  deployment_Run19.json
  deployment         Run      →  production_Run.json
  postdeploy         Run      →  production_Run.json
  post               Run      →  production_Run.json
  production         Run      →  production_Run.json
  production         Run19    →  production_Run.json   ← forced to Run (Rule 4)
  prod               Run19    →  production_Run.json   ← forced to Run (Rule 4)
  daily              Run19    →  daily_Run19.json
  daily              Run      →  daily_Run.json
  communication      Run19    →  regression_Run19.json
  communication      Run      →  regression_Run.json
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

from utils.constants.framework_constants import FrameworkConstants
from utils.ini_file_reader.config_reader import ConfigReader


# ── internal helpers ──────────────────────────────────────────────────────────

def _get_project_key() -> str:
    """
    Normalise the Project config value into a folder name.

    Project (case-insensitive)   →  project key (folder name)
    ──────────────────────────────────────────────────────────
    contains "resul"             →  "Resul"
    contains "star"              →  "MarketingStar"
    anything else                →  raw value, stripped  (safe fallback)
    """
    raw   = ConfigReader.get_property("Project", "unknown").strip()
    lower = raw.lower()

    if "resul" in lower:
        return "Resul"
    if "star" in lower:
        return "MarketingStar"
    return raw


def _get_env_key() -> str:
    """
    Normalise the Environment config value.
    "run19" is checked BEFORE "run" so Run19 is never misidentified as Run.

    Environment (case-insensitive)   →  env key
    ────────────────────────────────────────────
    contains "run19"                 →  "Run19"
    contains "run" (not "run19")     →  "Run"
    contains "team"                  →  "Team"
    anything else                    →  raw value, stripped
    """
    raw   = ConfigReader.get_property("Environment", "unknown").strip()
    lower = raw.lower()

    if "run19" in lower:
        return "Run19"
    if "run" in lower:
        return "Run"
    if "team" in lower:
        return "Team"
    return raw


def _get_suite_and_env_keys(env_key: str) -> tuple[str, str]:
    """
    Derive (suite_key, effective_env_key) using SuiteName + the already-resolved
    env_key.  env_key may be overridden (forced) for predeploy and production suites.

    Rules (evaluated in order):
    ─────────────────────────────────────────────────────────────────────────────
    Rule 1  "daily" in SuiteName
            → suite_key = "daily",  env_key unchanged
            → file: daily_<env>.json

    Rule 2  "predeploy" in SuiteName
            → ALWAYS deployment_Run19.json  (pre-deploy is always a pre-prod/Run19 gate)
            → suite_key = "deployment",  env_key FORCED to "Run19"
            (checked BEFORE Rule 3 so "predeploy" is never caught by the "deploy" branch)

    Rule 3  "deploy" OR "post" in SuiteName  (catches postdeploy, deployment, post)
            → env decides:
                Run19  →  suite_key = "deployment",  env_key = "Run19"
                Run    →  suite_key = "production",   env_key = "Run"
                other  →  suite_key = "deployment",   env_key = "Run19"  (pre-prod default)

    Rule 4  "production" or "prod" in SuiteName
            → ALWAYS production_Run.json  (production suite always targets live/Run env)
            → suite_key = "production",  env_key FORCED to "Run"
            (must come AFTER Rule 3; "prod" is not a substring of "postdeploy" so safe)

    Rule 5  anything else  (regression / module / communication / …)
            → suite_key = "regression",  env_key unchanged
            → file: regression_<env>.json
    ─────────────────────────────────────────────────────────────────────────────
    Returns
    -------
    (suite_key, effective_env_key)
    """
    suite_name = ConfigReader.get_property("SuiteName", "").strip().lower()

    # Rule 1 – daily
    if "daily" in suite_name:
        return "daily", env_key

    # Rule 2 – predeploy → ALWAYS deployment_Run19, env forced
    if "predeploy" in suite_name:
        return "deployment", "Run19"

    # Rule 3 – deploy / postdeploy / post  (env decides)
    if "deploy" in suite_name or "post" in suite_name:
        if env_key == "Run":
            return "production", "Run"
        return "deployment", "Run19"   # Run19 or Team → pre-prod gate

    # Rule 4 – production / prod → ALWAYS production_Run, env forced
    if "production" in suite_name or "prod" in suite_name:
        return "production", "Run"

    # Rule 5 – everything else
    return "regression", env_key


def _history_dir(project_key: str) -> Path:
    """
    Return (and create if needed) the project-specific sub-folder inside
    execution_history.

    Layout:
        <ONEDRIVE_BASE_PATH>/execution_history/<project_key>/
    """
    base = FrameworkConstants.ONEDRIVE_BASE_PATH / "execution_history" / project_key
    base.mkdir(parents=True, exist_ok=True)
    return base


def _json_path(suite_key: str, env_key: str, project_key: str) -> Path:
    """Full path for a given project + suite + env combination."""
    return _history_dir(project_key) / f"{suite_key}_{env_key}.json"


def _load_store(path: Path) -> dict:
    """Load existing JSON store, or return a blank one if missing / unreadable."""
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict) and "records" in data:
                return data
        except Exception as exc:
            print(f"[WARNING] Could not read history JSON '{path}': {exc}. Starting fresh.")
    return {"project": "", "suite": "", "environment": "", "records": {}}


def _save_store(path: Path, store: dict) -> None:
    """
    Atomically write the JSON store:
      1. Write to <name>.tmp
      2. Rename .tmp → final path
    Guarantees the file is never left half-written / corrupted.
    """
    tmp = path.with_suffix(".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(store, fh, indent=2)
        tmp.replace(path)
    except Exception as exc:
        print(f"[ERROR] Could not write history JSON '{path}': {exc}")
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass


def _purge_old_entries(records: dict, keep_days: int = 30) -> None:
    """Remove entries older than keep_days from every record list (in-place)."""
    cutoff = (datetime.now() - timedelta(days=keep_days)).strftime("%Y-%m-%d")
    for key in list(records.keys()):
        records[key] = [e for e in records[key] if e.get("date", "") >= cutoff]
        if not records[key]:
            del records[key]


# ── public class ──────────────────────────────────────────────────────────────

class JSONStatusManager:
    """
    Atomic JSON-backed store for 7-day execution history, segregated by project.

    Storage structure:
        execution_history/
            Resul/
                <suite_key>_<env_key>.json
            MarketingStar/
                <suite_key>_<env_key>.json

    Entry points:
      save_current_run(test_executions)   →  write today's results
      read_last_7_days_status()           →  read back for the HTML report
    """

    @staticmethod
    def save_current_run(test_executions) -> None:
        """
        Persist today's run results into the correct project-specific JSON history file.

        Parameters
        ----------
        test_executions : list[TestExecution]
            From DetailedTestReporter.get_test_executions()
        """
        project_key            = _get_project_key()
        env_key                = _get_env_key()
        suite_key, eff_env_key = _get_suite_and_env_keys(env_key)
        path                   = _json_path(suite_key, eff_env_key, project_key)
        today                  = datetime.now().strftime("%Y-%m-%d")

        store                = _load_store(path)
        store["project"]     = project_key
        store["suite"]       = suite_key
        store["environment"] = eff_env_key
        records: dict        = store.setdefault("records", {})

        for execution in test_executions:
            # Primary key: scenario_id (function/scenario name).
            # Falls back to test_case_id for backward-compatibility.
            key = (getattr(execution, "scenario_id", "") or "").strip() \
                  or (getattr(execution, "test_case_id", "") or "").strip()
            if not key:
                continue

            status     = (getattr(execution, "status", "") or "SKIPPED").upper()
            entry_list = records.setdefault(key, [])

            # Update today's entry if it already exists, otherwise append
            existing = next((e for e in entry_list if e.get("date") == today), None)
            if existing:
                existing["status"] = status
            else:
                entry_list.append({"date": today, "status": status})

        _purge_old_entries(records, keep_days=30)
        _save_store(path, store)

        print(
            f"[INFO] Saved execution history for {len(test_executions)} test cases "
            f"→ {project_key}/{path.name}  "
            f"(project={project_key}, suite={suite_key}, env={eff_env_key})"
        )

    @staticmethod
    def read_last_7_days_status(
        suite_key: str = None,
        env_key: str = None,
        project_key: str = None,
    ) -> dict:
        """
        Return the 7-day history map consumed by the HTML report generator.

        Returns
        -------
        dict  →  { "scenario_id_or_tc_id": ["SKIPPED", "PASS", "FAIL", ...] }
                 7-element list, oldest first; missing days filled with "SKIPPED".

        Parameters
        ----------
        suite_key, env_key, project_key : str, optional
            Override config-derived values (useful in unit tests).
        """
        project_key = project_key or _get_project_key()
        raw_env     = env_key     or _get_env_key()

        if suite_key is None:
            suite_key, eff_env_key = _get_suite_and_env_keys(raw_env)
        else:
            eff_env_key = env_key or raw_env

        path    = _json_path(suite_key, eff_env_key, project_key)
        store   = _load_store(path)
        records = store.get("records", {})

        # Last 7 calendar dates, oldest → newest
        last_7_dates = [
            (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            for i in range(6, -1, -1)
        ]

        result = {}
        for key, entry_list in records.items():
            date_status = {
                e["date"]: e["status"].upper()
                for e in entry_list
                if "date" in e and "status" in e
            }
            result[key] = [date_status.get(d, "SKIPPED") for d in last_7_dates]

        print(
            f"[INFO] Loaded JSON history for {len(result)} test cases "
            f"(project={project_key}, suite={suite_key}, env={eff_env_key})."
        )
        return result