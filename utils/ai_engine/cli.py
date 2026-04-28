from utils.ai_engine.assistant import ask_ai_to_modify
from utils.ai_engine.executor import apply_ai_changes


PROJECT_ROOT = "."


def run():
    while True:
        user_input = input("\nAsk AI > ")

        if user_input.lower() in ["exit", "quit"]:
            break

        response = ask_ai_to_modify(PROJECT_ROOT, user_input)

        print("\nAI Response:\n", response)

        confirm = input("\nApply changes? (y/n): ")

        if confirm.lower() == "y":
            apply_ai_changes(response, root_dir=PROJECT_ROOT)


if __name__ == "__main__":
    run()
