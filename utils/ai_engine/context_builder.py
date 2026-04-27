# ai_engine/context_builder.py

def find_relevant_files(file_map, keyword):
    relevant = {}
    for path, content in file_map.items():
        if keyword.lower() in content.lower():
            relevant[path] = content
    return relevant


def build_context(structure, relevant_files, error):
    context = f"""
You are an expert Python automation engineer.

Project Structure:
{structure}

Error:
{error}

Relevant Files:
"""
    for path, content in relevant_files.items():
        context += f"\nFILE: {path}\n{content[:1500]}\n"

    context += "\nFix the issue and return updated code."
    return context