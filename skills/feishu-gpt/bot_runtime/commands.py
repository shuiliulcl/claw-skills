import threading

from . import state
from .agent import ask_chatgpt
from .config_runtime import OPENAI_MODEL
from .messaging import send_card, send_reply
from .paths import build_agent_system_prompt, get_agent_workspace, get_agents_file_path
from .scheduler import (
    create_scheduled_task,
    delete_scheduled_task,
    format_task_summary,
    get_scheduled_task,
    list_scheduled_tasks,
    run_scheduled_task,
    set_task_enabled,
    update_task_window,
)

COMMANDS = {
    "/help": "显示可用指令列表",
    "/clear": "清除当前会话的对话历史",
    "/history": "查看当前上下文保留轮数和工作区",
    "/task-add": "创建定时任务：/task-add <分钟> <任务内容>",
    "/task-add-daily": "创建每日任务：/task-add-daily <HH:MM> <任务内容>",
    "/task-add-once": "创建一次性任务：/task-add-once <YYYY-MM-DD HH:MM> <任务内容>",
    "/task-list": "查看当前定时任务",
    "/task-del": "删除定时任务：/task-del <task_id>",
    "/task-run": "立即执行定时任务：/task-run <task_id>",
    "/task-pause": "暂停定时任务：/task-pause <task_id>",
    "/task-resume": "恢复定时任务：/task-resume <task_id>",
    "/task-window": "设置工作时间：/task-window <task_id> <days> <HH:MM-HH:MM>",
}


def handle_command(chat_id: str, text: str, reply_id: str) -> bool:
    cmd = text.strip()

    if cmd == "/help":
        lines = ["**可用指令：**\n"]
        for command, desc in COMMANDS.items():
            lines.append(f"- `{command}` — {desc}")
        send_card(reply_id, "\n".join(lines))
        return True

    if cmd == "/clear":
        state.conversations.pop(chat_id, None)
        send_card(reply_id, "✅ 已清除当前会话的对话历史")
        return True

    if cmd == "/history":
        history = state.conversations.get(chat_id, [])
        non_summary = [turn for turn in history if turn["role"] != "summary"]
        has_summary = any(turn["role"] == "summary" for turn in history)
        turns = len(non_summary) // 2
        message = f"📊 当前保留 **{turns}** 轮完整对话"
        if has_summary:
            message += "（另有更早对话已压缩为摘要）"
        message += f"\n🤖 当前模型：`{OPENAI_MODEL}`"
        message += "\n🧩 Shell 工具：`enabled`"
        message += f"\n📁 工作区：`{get_agent_workspace()}`"
        message += f"\n📄 AGENTS 文件：`{get_agents_file_path()}`"
        send_card(reply_id, message)
        return True

    if cmd == "/task-list":
        tasks = list_scheduled_tasks()
        if not tasks:
            send_card(reply_id, "当前没有定时任务。")
            return True
        send_card(reply_id, "**定时任务列表**\n\n" + "\n".join(format_task_summary(task) for task in tasks))
        return True

    if cmd.startswith("/task-add "):
        parts = cmd[len("/task-add "):].strip().split(maxsplit=1)
        if len(parts) != 2:
            send_card(reply_id, "用法：`/task-add <分钟> <任务内容>`")
            return True
        try:
            task = create_scheduled_task(int(parts[0]), parts[1], chat_id, created_by="command", chat_id=chat_id)
            send_card(reply_id, f"已创建定时任务：\n{format_task_summary(task)}")
        except Exception as e:
            send_card(reply_id, f"创建定时任务失败：{e}")
        return True

    if cmd.startswith("/task-add-daily "):
        parts = cmd[len("/task-add-daily "):].strip().split(maxsplit=1)
        if len(parts) != 2:
            send_card(reply_id, "用法：`/task-add-daily <HH:MM> <任务内容>`")
            return True
        try:
            task = create_scheduled_task(None, parts[1], chat_id, created_by="command", schedule_type="daily", time_of_day=parts[0], chat_id=chat_id)
            send_card(reply_id, f"已创建每日任务：\n{format_task_summary(task)}")
        except Exception as e:
            send_card(reply_id, f"创建每日任务失败：{e}")
        return True

    if cmd.startswith("/task-add-once "):
        parts = cmd[len("/task-add-once "):].strip().split(maxsplit=2)
        if len(parts) != 3:
            send_card(reply_id, "用法：`/task-add-once <YYYY-MM-DD> <HH:MM> <任务内容>`")
            return True
        try:
            task = create_scheduled_task(
                None,
                parts[2],
                chat_id,
                created_by="command",
                schedule_type="once",
                run_at_text=f"{parts[0]} {parts[1]}",
                chat_id=chat_id,
            )
            send_card(reply_id, f"已创建一次性任务：\n{format_task_summary(task)}")
        except Exception as e:
            send_card(reply_id, f"创建一次性任务失败：{e}")
        return True

    if cmd.startswith("/task-del "):
        try:
            task = delete_scheduled_task(cmd[len("/task-del "):].strip())
            send_card(reply_id, f"已删除定时任务：`{task['task_id']}`")
        except Exception as e:
            send_card(reply_id, f"删除定时任务失败：{e}")
        return True

    if cmd.startswith("/task-run "):
        try:
            task = get_scheduled_task(cmd[len("/task-run "):].strip())
            threading.Thread(
                target=run_scheduled_task,
                args=(task["task_id"], ask_chatgpt, build_agent_system_prompt, send_reply, True),
                daemon=True,
            ).start()
            send_card(reply_id, f"已触发立即执行：`{task['task_id']}`")
        except Exception as e:
            send_card(reply_id, f"执行定时任务失败：{e}")
        return True

    if cmd.startswith("/task-pause "):
        try:
            task = set_task_enabled(cmd[len("/task-pause "):].strip(), False)
            send_card(reply_id, f"已暂停定时任务：\n{format_task_summary(task)}")
        except Exception as e:
            send_card(reply_id, f"暂停定时任务失败：{e}")
        return True

    if cmd.startswith("/task-resume "):
        try:
            task = set_task_enabled(cmd[len("/task-resume "):].strip(), True)
            send_card(reply_id, f"已恢复定时任务：\n{format_task_summary(task)}")
        except Exception as e:
            send_card(reply_id, f"恢复定时任务失败：{e}")
        return True

    if cmd.startswith("/task-window "):
        parts = cmd[len("/task-window "):].strip().split(maxsplit=2)
        if len(parts) != 3 or "-" not in parts[2]:
            send_card(reply_id, "用法：`/task-window <task_id> <days> <HH:MM-HH:MM>`，如 `/task-window task_xxx 1,2,3,4,5 09:00-18:00`")
            return True
        try:
            start_text, end_text = parts[2].split("-", 1)
            workdays = [] if parts[1].lower() == "all" else [int(item) for item in parts[1].split(",") if item.strip()]
            task = update_task_window(parts[0], workdays=workdays, work_time_start=start_text, work_time_end=end_text)
            send_card(reply_id, f"已更新工作时间窗口：\n{format_task_summary(task)}")
        except Exception as e:
            send_card(reply_id, f"设置工作时间窗口失败：{e}")
        return True

    return False
