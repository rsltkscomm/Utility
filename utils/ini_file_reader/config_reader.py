import configparser
import os
from pathlib import Path
from utils.constants.framework_constants import FrameworkConstants
import threading


class ConfigReader:
    _config = configparser.ConfigParser(strict=False)
    _initialized = False

    _runtime_dict = {}

    @classmethod
    def _sync_to_environ(cls, file_path):
        """Sync key-value pairs from an INI file into os.environ preserving original casing."""
        try:
            path = Path(file_path)
            if not path.exists():
                return
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or line.startswith(";") or line.startswith("["):
                        continue
                    if "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip()
                        if k and k not in os.environ:
                            os.environ[k] = v
        except Exception as e:
            print(f"[CONFIG] Error syncing {file_path} to environment: {e}")

    @classmethod
    def _load_config(cls):
        if cls._initialized:
            return
        files = []

        # Load newenv.ini explicitly first if available
        newenv_file = FrameworkConstants.get_newenv_path()
        if newenv_file.exists():
            files.append(newenv_file)
            cls._sync_to_environ(newenv_file)

        dynamic_file = Path(FrameworkConstants.get_dynamic_file_path())
        if dynamic_file.exists() and dynamic_file not in files:
            files.append(dynamic_file)

        properties_dir = FrameworkConstants.get_properties_path()
        if properties_dir.exists():
            for file in properties_dir.iterdir():
                if file.suffix == ".ini" and file not in files:
                    files.append(file)
                    if file.name.lower() == "newenv.ini":
                        cls._sync_to_environ(file)

        cls._config.read([str(f) for f in files], encoding="utf-8")
        print(f"[CONFIG] Loaded files: {files}")
        cls._initialized = True

    @classmethod
    def _get_runtime_dict(cls):
        return cls._runtime_dict

    @classmethod
    def get_property(cls, key, default=None, section="DEFAULT"):
        cls._load_config()
        runtime_dict = cls._get_runtime_dict()
        if key in runtime_dict:
            return runtime_dict[key]
        try:
            # Check specified section
            if cls._config.has_section(section) and cls._config.has_option(section, key):
                return cls._config.get(section, key)
            # Check DEFAULT section
            if cls._config.has_option("DEFAULT", key):
                return cls._config.get("DEFAULT", key)
            # Check all other sections
            for sec in cls._config.sections():
                if cls._config.has_option(sec, key):
                    return cls._config.get(sec, key)
            # Fallback to os.environ
            if key in os.environ:
                return os.environ[key]
            if key.upper() in os.environ:
                return os.environ[key.upper()]
            return default
        except Exception as e:
            print(f"[CONFIG ERROR] {key}: {e}")
            return default

    @classmethod
    def set_runtime_property(cls, key, value):
        """Store value only for current test run (not persisted)"""
        runtime_dict = cls._get_runtime_dict()
        runtime_dict[key] = value
        print(f"[RUNTIME CONFIG] {key} = {value}")

    @classmethod
    def get_runtime_property(cls, key, default=None):
        runtime_dict = cls._get_runtime_dict()
        return runtime_dict.get(key, default)

    @classmethod
    def clear_runtime(cls):
        cls._runtime_dict.clear()
        print("[RUNTIME CONFIG] Cleared")

    @classmethod
    def iterate_mails(cls, section="account setup - webmails"):
        cls._load_config()

        if not cls._config.has_section(section):
            raise Exception(f"[CONFIG] Section '{section}' not found")

        for key, _ in cls._config.items(section):
            yield key