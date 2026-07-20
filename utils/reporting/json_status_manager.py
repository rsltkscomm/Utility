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
    Normalise the Environment config value into a canonical env key.

    Longer tokens (run24, run23, run19) are checked BEFORE the shorter
    "run" so that e.g. "Run19" is never misidentified as plain "Run".

    Environment (case-insensitive)   →  env key
    ────────────────────────────────────────────
    contains "run24"                 →  "Run24"
    contains "run23"                 →  "Run23"
    contains "run19"                 →  "Run19"
    contains "run"  (not above)      →  "Run"
    contains "team"                  →  "Team"
    anything else                    →  raw value, stripped
    """
    raw   = ConfigReader.get_property("Environment", "unknown").strip()
    lower = raw.lower()

    if "run24" in lower:
        return "Run24"
    if "run23" in lower:
        return "Run23"
    if "run19" in lower:
        return "Run19"
    if "run" in lower:
        return "Run"
    if "team" in lower:
        return "Team"
    return raw


def _get_suite_and_env_keys(env_key: str) -> tuple[str, str]:
    """
    Derive (suite_key, effective_env_key) from SuiteName + the already-resolved
    env_key.  env_key is only overridden (forced) for predeploy and production.

    Rules (evaluated in order):
    ─────────────────────────────────────────────────────────────────────────────
    Rule 1  "daily" in SuiteName
            → suite_key = "daily",  env_key unchanged
            → file: daily_<env>.json

    Rule 2  "predeploy" in SuiteName
            → ALWAYS deployment_Run19.json  (pre-deploy is always the Run19 gate)
            → suite_key = "deployment",  env_key FORCED to "Run19"
            (checked BEFORE Rule 3 so "predeploy" is never caught by "post")

    Rule 3  "post" in SuiteName
            (covers "post", "postdeploy"; "predeploy" already handled by Rule 2)
            → suite_key = "deployment",  env_key UNCHANGED
            → file: deployment_<env>.json  for ALL environments
                post + Run    →  deployment_Run.json
                post + Run19  →  deployment_Run19.json
                post + Run23  →  deployment_Run23.json
                post + Run24  →  deployment_Run24.json
                post + Team   →  deployment_Team.json

    Rule 4  "deploy" in SuiteName
            (covers "deploy", "deployment"; "predeploy"/"postdeploy" already handled)
            → suite_key = "deployment",  env_key UNCHANGED
            → file: deployment_<env>.json  for ALL environments

    Rule 5  "production" or "prod" in SuiteName
            → ALWAYS production_Run.json
            → suite_key = "production",  env_key FORCED to "Run"

    Rule 6  anything else  (regression / module / communication / …)
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

    # Rule 3 – post / postdeploy → deployment_<env>, env unchanged for ALL envs
    # "predeploy" already caught above so only true post/postdeploy reach here.
    if "post" in suite_name:
        return "deployment", env_key

    # Rule 4 – deploy / deployment → deployment_<env>, env unchanged for ALL envs
    # "predeploy" / "postdeploy" already caught above so only pure deploy reaches here.
    if "deploy" in suite_name:
        return "deployment", env_key

    # Rule 5 – production / prod → ALWAYS production_Run, env forced
    if "production" in suite_name or "prod" in suite_name:
        return "production", "Run"

    # Rule 6 – everything else (regression / module / communication / …)
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
    Atomic JSON-backed store for execution history, segregated by project.

    Storage structure:
        execution_history/
            Resul/
                <suite_key>_<env_key>.json
            MarketingStar/
                <suite_key>_<env_key>.json

    Supported suite keys : daily, deployment, production, regression
    Supported env keys   : Run, Run19, Run23, Run24, Team

    History window rules (used by read_last_7_days_status):
      • daily suite       → last 7 CALENDAR DATES (today back to today-6).
                             A date with no run recorded shows as "SKIPPED",
                             since daily suites are expected to run every day.
      • every other suite  → last 7 ACTUAL EXECUTIONS (the 7 most recent
        (deployment/post,     run records for that test, oldest → newest),
         production,          regardless of how many calendar days separate
         regression, ...)     them. This suits suites like "post" that may
                               only run once a week — using calendar dates
                               for those would show mostly "SKIPPED" gaps.

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
        Return the 7-slot history map consumed by the HTML report generator.

        Each slot is now a small dict — {"date": "YYYY-MM-DD" or None,
        "status": "PASS"/"FAIL"/"SKIPPED"} — instead of a bare status
        string, so the HTML report can display the REAL recorded date on
        hover rather than an assumed calendar date. This matters for
        suites that don't run daily (post/smoke/regression), where actual
        recorded executions can be days or weeks apart.

        Behaviour depends on the suite type:
          • "daily"           → 7 slots = last 7 CALENDAR DATES (oldest first).
                                 Every slot carries its real calendar date.
                                 Any date with no recorded run is
                                 {"date": <that date>, "status": "SKIPPED"}.
          • anything else     → 7 slots = last 7 ACTUAL EXECUTIONS (oldest
            (deployment/post,    first) for that test, each carrying its
             production,         OWN real recorded date. If fewer than 7
             regression, ...)    runs exist yet, the remaining leading
                                 slots are padded with {"date": None,
                                 "status": "SKIPPED"} — there is no real
                                 execution for that slot yet, so there is
                                 no date to show.

        Returns
        -------
        dict  →  { "scenario_id_or_tc_id": [ {"date": ..., "status": ...}, ... ] }
                 always a 7-element list.

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

        result = {}

        if suite_key == "daily":
            # Daily suites are expected to run every day, so anchor the 7 slots
            # to the last 7 calendar dates and backfill missing days as SKIPPED.
            # Every slot keeps its real calendar date, even when SKIPPED.
            last_7_dates = [
                (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
                for i in range(6, -1, -1)
            ]
            for key, entry_list in records.items():
                date_status = {
                    e["date"]: e["status"].upper()
                    for e in entry_list
                    if "date" in e and "status" in e
                }
                result[key] = [
                    {"date": d, "status": date_status.get(d, "SKIPPED")}
                    for d in last_7_dates
                ]
        else:
            # Non-daily suites (post/deployment, production, regression, ...)
            # don't run every day - e.g. "post" may only run once a week - so
            # instead of the last 7 calendar dates, take the last 7 ACTUAL
            # EXECUTIONS recorded for each test, each keeping its own real
            # recorded date, oldest -> newest.
            for key, entry_list in records.items():
                sorted_entries = sorted(
                    (e for e in entry_list if "date" in e and "status" in e),
                    key=lambda e: e["date"]
                )
                last_entries = sorted_entries[-7:]
                slots = [
                    {"date": e["date"], "status": e["status"].upper()}
                    for e in last_entries
                ]
                if len(slots) < 7:
                    # No real execution exists yet for these leading slots,
                    # so there is no real date to attach - date stays None.
                    slots = [{"date": None, "status": "SKIPPED"}] * (7 - len(slots)) + slots
                result[key] = slots

        print(
            f"[INFO] Loaded JSON history for {len(result)} test cases "
            f"(project={project_key}, suite={suite_key}, env={eff_env_key})."
        )
        return result