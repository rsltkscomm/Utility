import os


DEFAULT_EXTENSIONS = (".py", ".feature", ".json")
DEFAULT_IGNORED_DIRS = {
    ".git",
    ".idea",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "assets",
    "reports",
    "screenshots",
    "videos",
}
DEFAULT_MAX_FILE_SIZE = 250_000


def get_all_files(
    root_dir,
    extensions=DEFAULT_EXTENSIONS,
    ignored_dirs=DEFAULT_IGNORED_DIRS,
    max_file_size=DEFAULT_MAX_FILE_SIZE,
):
    file_map = {}
    root_dir = os.path.abspath(root_dir)

    for root, dirs, files in os.walk(root_dir):
        dirs[:] = [directory for directory in dirs if directory not in ignored_dirs]
        parts = set(os.path.relpath(root, root_dir).split(os.sep))
        if parts & ignored_dirs:
            continue

        for file_name in files:
            if not file_name.endswith(extensions):
                continue

            path = os.path.join(root, file_name)
            try:
                if os.path.getsize(path) > max_file_size:
                    continue

                with open(path, "r", encoding="utf-8") as file:
                    relative_path = os.path.relpath(path, root_dir)
                    file_map[relative_path] = file.read()
            except (OSError, UnicodeDecodeError):
                continue

    return file_map
