import sys

from bot_runtime.runtime import run_bot_and_local_chat, run_local_chat


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--local-chat":
        run_local_chat()
    else:
        run_bot_and_local_chat()
