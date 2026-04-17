import atexit
import os
import threading

import lark_oapi as lark
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1, P2ImMessageRecalledV1

from . import state
from .agent import ThinkingInterrupted, ask_chatgpt, build_prompt, run_agent_heartbeat_check, update_history
from .commands import handle_command
from .config_runtime import APP_ID, APP_SECRET, OPENAI_MODEL
from .messaging import (
    add_thinking_reaction,
    build_message_meta,
    fetch_message_text,
    parse_message_content,
    remove_reaction,
    render_user_message,
    resolve_sender_identity,
    send_admin_notification,
    send_reply,
)
from .paths import build_agent_system_prompt, ensure_runtime_dirs, get_agent_workspace, get_agents_file_path, get_pid_file_path, get_tasks_file_path
from .scheduler import start_heartbeat_loop, start_task_scheduler
from .utils import first_non_empty


def process_and_reply(chat_id: str, text: str, sender_id: str, reply_id: str, message_id: str, quoted_text: str | None = None):
    cancel_event = state.register_pending_message(message_id)
    with state.chat_locks[chat_id]:
        reaction_id = add_thinking_reaction(message_id)
        try:
            if cancel_event.is_set():
                print(f"[消息已撤回] {sender_id}: {message_id}")
                return
            prompt = build_prompt(chat_id, text, quoted_text)
            reply = ask_chatgpt(prompt, build_agent_system_prompt(), cancel_event=cancel_event)
            if cancel_event.is_set():
                print(f"[思考已中断] {sender_id}: {message_id}")
                return
            print(f"[ChatGPT 回复] {sender_id}: {reply[:80]}{'...' if len(reply) > 80 else ''}")
            update_history(chat_id, text, reply)
        except ThinkingInterrupted:
            print(f"[思考已中断] {sender_id}: {message_id}")
            return
        except Exception as e:
            reply = f"（处理出错：{e}）"
        finally:
            remove_reaction(message_id, reaction_id)
            state.finish_pending_message(message_id)
    send_reply(reply_id, reply)


def on_message(data: P2ImMessageReceiveV1) -> None:
    msg = data.event.message
    if state.is_duplicate(msg.message_id):
        return

    try:
        raw_text, content_data = parse_message_content(msg.message_type, msg.content, getattr(msg, "mentions", None))
    except Exception:
        return
    if not raw_text:
        return

    chat_id = msg.chat_id
    sender_meta = resolve_sender_identity(data.event.sender)
    sender_id = (
        first_non_empty(
            sender_meta.get("sender_id"),
            sender_meta.get("sender_open_id"),
            sender_meta.get("sender_union_id"),
        )
        or "unknown"
    )
    message_meta = build_message_meta(msg, data.event.sender, getattr(msg, "mentions", None), content_data)
    text = render_user_message(raw_text, message_meta)
    reply_id = msg.thread_id if (msg.thread_id and msg.thread_id.startswith("ot_")) else chat_id
    print(f"[收到消息] {sender_id}: {raw_text}")

    if raw_text.startswith("/") and handle_command(chat_id, raw_text, reply_id):
        return

    quoted_text = fetch_message_text(msg.parent_id) if msg.parent_id else None
    threading.Thread(
        target=process_and_reply,
        args=(chat_id, text, sender_id, reply_id, msg.message_id, quoted_text),
        daemon=True,
    ).start()


def on_message_recalled(data: P2ImMessageRecalledV1) -> None:
    event = data.event
    message_id = getattr(event, "message_id", None)
    if not message_id:
        return
    recall_type = getattr(event, "recall_type", None) or "unknown"
    chat_id = getattr(event, "chat_id", None) or "unknown"
    cancelled = state.cancel_pending_message(message_id)
    status = "已中断思考" if cancelled else "未命中运行中思考"
    print(f"[消息撤回] chat={chat_id} message={message_id} recall_type={recall_type} {status}")


def write_pid():
    ensure_runtime_dirs()
    pid_path = get_pid_file_path()
    with open(pid_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(str(os.getpid()))


def remove_pid():
    try:
        os.remove(get_pid_file_path())
    except OSError:
        pass


def main():
    write_pid()
    atexit.register(remove_pid)

    print("=" * 50)
    print("  飞书 × ChatGPT 机器人启动中...")
    print(f"  APP_ID: {APP_ID}")
    print(f"  MODEL: {OPENAI_MODEL}")
    print("  SHELL TOOL: enabled")
    print(f"  WORKSPACE: {get_agent_workspace()}")
    print(f"  AGENTS: {get_agents_file_path()}")
    print(f"  TASKS: {get_tasks_file_path()}")
    print("=" * 50)

    handler = (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(on_message)
        .register_p2_im_message_recalled_v1(on_message_recalled)
        .build()
    )
    ws_client = lark.ws.Client(
        APP_ID,
        APP_SECRET,
        event_handler=handler,
        log_level=lark.LogLevel.INFO,
    )
    state.ws_client = ws_client

    print("正在连接飞书服务器（无需公网 IP）...")

    threading.Thread(target=_delayed_online_notify, daemon=True).start()

    start_heartbeat_loop(send_admin_notification, run_agent_heartbeat_check)
    start_task_scheduler(ask_chatgpt, build_agent_system_prompt, send_reply)
    ws_client.start()


def _delayed_online_notify():
    import time

    time.sleep(3)
    send_admin_notification("✅ **机器人已上线**\n")


def run_bot_and_local_chat():
    bot_thread = threading.Thread(target=main, daemon=True)
    state.bot_runtime_thread = bot_thread
    bot_thread.start()
    run_local_chat()


def run_local_chat():
    local_chat_id = "__local_chat__"
    print("=" * 50)
    print("  本地对话模式")
    print(f"  MODEL: {OPENAI_MODEL}")
    print("  SHELL TOOL: enabled")
    print(f"  WORKSPACE: {get_agent_workspace()}")
    print(f"  AGENTS: {get_agents_file_path()}")
    print(f"  TASKS: {get_tasks_file_path()}")
    print("  输入 /exit 退出，输入 /clear 清空上下文")
    print("=" * 50)

    while True:
        try:
            user_text = input("你> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n已退出本地对话。")
            return

        if not user_text:
            continue
        if user_text == "/exit":
            print("已退出本地对话。")
            return
        if user_text == "/clear":
            state.conversations.pop(local_chat_id, None)
            print("上下文已清空。")
            continue

        prompt = build_prompt(local_chat_id, user_text)
        reply = ask_chatgpt(prompt, build_agent_system_prompt())
        update_history(local_chat_id, user_text, reply)
        print(f"Agent> {reply}\n")
