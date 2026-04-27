import os


def _resolve_target(root_dir, file_path):
    root_dir = os.path.abspath(root_dir)
    target = os.path.abspath(os.path.join(root_dir, file_path))

    if os.path.commonpath([root_dir, target]) != root_dir:
        raise ValueError(f"Target is outside project root: {file_path}")

    return target


def apply_fix(file_path, new_code, root_dir="."):
    target_path = _resolve_target(root_dir, file_path)

    with open(target_path, "w", encoding="utf-8") as file:
        file.write(new_code)
