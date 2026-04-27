import os
import re
import shutil


def extract_patches(response_text):
    pattern = r"FILE:\s*(.*?)\r?\n```diff\r?\n(.*?)```"
    return re.findall(pattern, response_text, re.DOTALL)


def _normalise_diff_line(line):
    return line if line.endswith("\n") else line + "\n"


def _resolve_target(root_dir, file_path):
    root_dir = os.path.abspath(root_dir)
    target = os.path.abspath(os.path.join(root_dir, file_path))

    if os.path.commonpath([root_dir, target]) != root_dir:
        raise ValueError(f"Patch target is outside project root: {file_path}")

    return target


def _apply_unified_diff(original_lines, diff_text):
    hunk_header = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")
    diff_lines = diff_text.splitlines()
    patched_lines = []
    source_index = 0
    line_index = 0

    while line_index < len(diff_lines):
        line = diff_lines[line_index]

        if line.startswith("---") or line.startswith("+++"):
            line_index += 1
            continue

        match = hunk_header.match(line)
        if not match:
            line_index += 1
            continue

        old_start = int(match.group(1)) - 1
        if old_start < source_index:
            raise ValueError("Overlapping or out-of-order diff hunk.")

        patched_lines.extend(original_lines[source_index:old_start])
        source_index = old_start
        line_index += 1

        while line_index < len(diff_lines) and not diff_lines[line_index].startswith("@@"):
            line = diff_lines[line_index]

            if line.startswith("\\"):
                line_index += 1
                continue

            if not line:
                raise ValueError("Invalid unified diff line.")

            marker = line[0]
            content = _normalise_diff_line(line[1:])

            if marker == " ":
                if source_index >= len(original_lines) or original_lines[source_index] != content:
                    raise ValueError(f"Diff context does not match near line {source_index + 1}.")
                patched_lines.append(original_lines[source_index])
                source_index += 1
            elif marker == "-":
                if source_index >= len(original_lines) or original_lines[source_index] != content:
                    raise ValueError(f"Diff removal does not match near line {source_index + 1}.")
                source_index += 1
            elif marker == "+":
                patched_lines.append(content)
            else:
                raise ValueError(f"Unsupported unified diff marker: {marker}")

            line_index += 1

    patched_lines.extend(original_lines[source_index:])
    return patched_lines


def apply_ai_changes(response_text, root_dir="."):
    patches = extract_patches(response_text)
    changed_files = []

    for file_path, diff in patches:
        file_path = file_path.strip()
        target_path = _resolve_target(root_dir, file_path)

        if not os.path.exists(target_path):
            print(f"WARNING File not found: {file_path}")
            continue

        shutil.copy(target_path, target_path + ".bak")

        with open(target_path, "r", encoding="utf-8") as file:
            lines = file.readlines()

        new_lines = _apply_unified_diff(lines, diff)

        with open(target_path, "w", encoding="utf-8") as file:
            file.writelines(new_lines)

        changed_files.append(file_path)
        print(f"Patched: {file_path}")

    if not patches:
        print("No diff patches found in AI response.")

    return changed_files
