from ai_engine.core import process_request


def fix_error(root_dir, error_message):
    return process_request(root_dir, error_message, mode="error")
