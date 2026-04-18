import configparser
from pathlib import Path
from utils.constants.framework_constants import FrameworkConstants
import threading


class ConfigReader:
    _config = configparser.ConfigParser(strict=False)
    _initialized = False

    _runtime_data = threading.local()

    @classmethod
    def _load_config(cls):
        if cls._initialized:
            return
        files = []
        dynamic_file = Path(FrameworkConstants.get_dynamic_file_path())
        if dynamic_file.exists():
            files.append(dynamic_file)
        properties_dir = FrameworkConstants.get_properties_path()
        if properties_dir.exists():
            for file in properties_dir.iterdir():
                if file.suffix == ".ini":
                    files.append(file)

        cls._config.read([str(f) for f in files])
        print(f"[CONFIG] Loaded files: {files}")
        cls._initialized = True

    @classmethod
    def _get_runtime_dict(cls):
        if not hasattr(cls._runtime_data, "data"):
            cls._runtime_data.data = {}
        return cls._runtime_data.data

    @classmethod
    def get_property(cls, key, default=None, section="DEFAULT"):
        cls._load_config()
        runtime_dict = cls._get_runtime_dict()
        if key in runtime_dict:
            return runtime_dict[key]
        try:
            value = cls._config.get(section, key, fallback=default)
            if value is None:
                print(f"[CONFIG] Missing key: {key} (using default: {default})")
            return value
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
        if hasattr(cls._runtime_data, "data"):
            cls._runtime_data.data.clear()
        print("[RUNTIME CONFIG] Cleared")