import os
import re

from ai_engine.claude_client import ask_claude
from ai_engine.file_scanner import DEFAULT_IGNORED_DIRS, get_all_files


def get_project_structure(root_dir):
    lines = []
    root_dir = os.path.abspath(root_dir)

    for root, dirs, files in os.walk(root_dir):
        dirs[:] = [directory for directory in dirs if directory not in DEFAULT_IGNORED_DIRS]
        level = root.replace(root_dir, "").count(os.sep)
        indent = "  " * level
        name = os.path.basename(root) or root
        lines.append(f"{indent}{name}/")

        file_indent = "  " * (level + 1)
        for file_name in sorted(files):
            if file_name.endswith((".py", ".feature", ".json")):
                lines.append(f"{file_indent}{file_name}")

    return "\n".join(lines)


def extract_keywords(text):
    words = re.findall(r"\b\w+\b", text.lower())
    return [word for word in words if len(word) > 3]


def process_request(root_dir, input_text, mode="user"):
    file_map = get_all_files(root_dir)
    structure = get_project_structure(root_dir)
    keywords = extract_keywords(input_text)

    relevant_files = {}
    for path, content in file_map.items():
        searchable = f"{path}\n{content}".lower()
        if not keywords or any(keyword in searchable for keyword in keywords):
            relevant_files[path] = content

    relevant_files = dict(
        sorted(relevant_files.items(), key=lambda item: len(item[1]))[:5]
    )

    instruction = "Fix the error." if mode == "error" else "Apply the user request."

    prompt = f"""
You are a senior Python automation engineer.

Instruction: {instruction}

User Input:
{input_text}

Project Structure:
{structure}

Relevant Files:
"""

    for path, content in relevant_files.items():
        prompt += f"\nFILE: {path}\n{content[:2000]}\n"

    prompt += """
IMPORTANT:
Return response STRICTLY in this format:

FILE: relative/path/to/file.py
```diff
--- a/relative/path/to/file.py
+++ b/relative/path/to/file.py
@@ -1,1 +1,1 @@
- old line
+ new line
```
"""
    return ask_claude(prompt)
