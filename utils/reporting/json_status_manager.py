"""
json_status_manager.py
Place this file at:  utils/reporting/json_status_manager.py

Storage layout  (under  FrameworkConstants.ONEDRIVE_BASE_PATH / "execution_history"):

    execution_history/
        daily_Team.json
        daily_Run19.json
        daily_Run.json
        deployment_Run19.json     ← any deploy/post/prod suite running on Run19
        production_Run.json       ← any deploy/post/prod suite running on Run (live)
        regression_Team.json
        regression_Run19.json
        regression_Run.json
        ...

Suite + Env combined logic
──────────────────────────
Suite key is NOT derived from SuiteName alone for deploy/prod suites.
The Environment value is the deciding factor:

  SuiteName contains "daily"
      → always  "daily"  regardless of env

  SuiteName contains "post", "deploy", OR "prod"
      + env is Run19  →  suite_key = "deployment"   (pre-production gate)
      + env is Run    →  suite_key = "production"   (live / production)
      + env is Team   →  suite_key = "deployment"   (default for other envs)

  Anything else (regression / module suites)
      → always  "regression"

Env key normalisation (case-insensitive, "run19" checked before "run"):
  "run19" in env  →  "Run19"
  "run"   in env  →  "Run"
  "team"  in env  →  "Team"
  other           →  raw value stripped

Final file-name examples:
  SuiteName=deployment  + Env=Run19  →  deployment_Run19.json
  SuiteName=predeploy   + Env=Run19  →  deployment_Run19.json
  SuiteName=deployment  + Env=Run    →  production_Run.json
  SuiteName=production  + Env=Run    →  production_Run.json
  SuiteName=production  + Env=Run19  →  deployment_Run19.json
  SuiteName=daily       + Env=Run19  →  daily_Run19.json
  SuiteName=daily       + Env=Run    →  daily_Run.json
  SuiteName=communication + Env=Run19 → regression_Run19.json
  SuiteName=communication + Env=Run   → regression_Run.json
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

from utils.constants.framework_constants import FrameworkConstants
from utils.ini_file_reader.config_reader import ConfigReader


# ── internal helpers ──────────────────────────────────────────────────────────

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


def _get_suite_key(env_key: str) -> str:
    """
    Derive the suite key using BOTH SuiteName and the already-resolved env_key.

    For deploy/post/prod suites the environment is the deciding factor:
      - Run19 env  →  "deployment"   (pre-production, not yet live)
      - Run   env  →  "production"   (live environment)
      - other env  →  "deployment"   (safe default)

    SuiteName (case-insensitive)          env_key   →  suite key
    ──────────────────────────────────────────────────────────────
    contains "daily"                      any       →  "daily"
    contains "post"/"deploy"/"prod"       Run19     →  "deployment"
    contains "post"/"deploy"/"prod"       Run       →  "production"
    contains "post"/"deploy"/"prod"       other     →  "deployment"
    anything else                         any       →  "regression"
    """
    suite_name = ConfigReader.get_property("SuiteName", "").strip().lower()

    if "daily" in suite_name:
        return "daily"

    if "post" in suite_name or "deploy" in suite_name or "prod" in suite_name:
        if env_key == "Run":
            return "production"
        return "deployment"       # Run19 or any other env

    return "regression"


def _history_dir() -> Path:
    """Return (and create if needed) the execution_history folder."""
    base = FrameworkConstants.ONEDRIVE_BASE_PATH / "execution_history"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _json_path(suite_key: str, env_key: str) -> Path:
    """Full path for a given suite + env combination."""
    return _history_dir() / f"{suite_key}_{env_key}.json"


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
    return {"suite": "", "environment": "", "records": {}}


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
    Atomic JSON-backed store for 7-day execution history.

    Entry points:
      save_current_run(test_executions)   →  write today's results
      read_last_7_days_status()           →  read back for the HTML report
    """

    @staticmethod
    def save_current_run(test_executions) -> None:
        """
        Persist today's run results into the correct JSON history file.

        Parameters
        ----------
        test_executions : list[TestExecution]
            From DetailedTestReporter.get_test_executions()
        """
        env_key   = _get_env_key()
        suite_key = _get_suite_key(env_key)
        path      = _json_path(suite_key, env_key)
        today     = datetime.now().strftime("%Y-%m-%d")

        store                = _load_store(path)
        store["suite"]       = suite_key
        store["environment"] = env_key
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
            f"→ {path.name}  (suite={suite_key}, env={env_key})"
        )

    @staticmethod
    def read_last_7_days_status(suite_key: str = None, env_key: str = None) -> dict:
        """
        Return the 7-day history map consumed by the HTML report generator.

        Returns
        -------
        dict  →  { "scenario_id_or_tc_id": ["SKIPPED", "PASS", "FAIL", ...] }
                 7-element list, oldest first; missing days filled with "SKIPPED".

        Parameters
        ----------
        suite_key, env_key : str, optional
            Override config-derived values (useful in unit tests).
        """
        env_key   = env_key   or _get_env_key()
        suite_key = suite_key or _get_suite_key(env_key)
        path      = _json_path(suite_key, env_key)

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
            f"(suite={suite_key}, env={env_key})."
        )
        return result