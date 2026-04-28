# ai_engine/assistant.py

from utils.ai_engine.core import process_request


def ask_ai_to_modify(root_dir, user_request):
    return process_request(root_dir, user_request, mode="user")
