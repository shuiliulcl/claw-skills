import json
import os
import shutil
import subprocess

from .config_runtime import FEISHU_CLI_BIN, FEISHU_CLI_ENABLED, FEISHU_CLI_EXTRA_ARGS, FEISHU_CLI_TIMEOUT
from .paths import get_agent_workspace
from .scheduler import (
    create_scheduled_task,
    delete_scheduled_task,
    list_scheduled_tasks,
    set_task_enabled,
    update_task_window,
)


def is_feishu_cli_enabled() -> bool:
    return FEISHU_CLI_ENABLED


def resolve_feishu_cli_bin() -> str | None:
    if os.path.sep in FEISHU_CLI_BIN or (os.path.altsep and os.path.altsep in FEISHU_CLI_BIN):
        return FEISHU_CLI_BIN if os.path.exists(FEISHU_CLI_BIN) else None
    return shutil.which(FEISHU_CLI_BIN)


def ensure_feishu_cli_ready():
    if not is_feishu_cli_enabled():
        raise RuntimeError("飞书 CLI 未启用")
    if not resolve_feishu_cli_bin():
        raise RuntimeError(
            f"未找到 lark-cli 可执行文件：{FEISHU_CLI_BIN}。"
            "请先安装 Node.js，并执行 `npm install -g @larksuite/cli`。"
        )


def _normalize_cli_args(args) -> list[str]:
    if not isinstance(args, list) or not args:
        raise ValueError("args 必须是非空字符串数组")
    normalized = []
    for item in args:
        text = str(item).strip()
        if not text:
            raise ValueError("args 中不能包含空字符串")
        normalized.append(text)
    return normalized


def _without_unsupported_format_args(args: list[str]) -> list[str]:
    cleaned = []
    skip_next = False
    for idx, item in enumerate(args):
        if skip_next:
            skip_next = False
            continue
        if item == "--format":
            if idx + 1 < len(args) and str(args[idx + 1]).lower() == "json":
                skip_next = True
            continue
        cleaned.append(item)
    return cleaned


def run_feishu_cli(args: list[str], dry_run: bool = False) -> str:
    ensure_feishu_cli_ready()
    normalized_args = _normalize_cli_args(args)
    env = os.environ.copy()
    env["NO_COLOR"] = "1"

    def _run(extra_args: list[str]):
        command = [resolve_feishu_cli_bin() or FEISHU_CLI_BIN]
        command.extend(extra_args)
        command.extend(normalized_args)
        if dry_run and "--dry-run" not in command:
            command.append("--dry-run")
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=FEISHU_CLI_TIMEOUT,
            env=env,
        )
        return proc, command

    try:
        proc, command = _run(FEISHU_CLI_EXTRA_ARGS)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"lark-cli 执行超时（>{FEISHU_CLI_TIMEOUT}s）")
    combined_output = ((proc.stdout or "") + "\n" + (proc.stderr or "")).lower()
    if proc.returncode != 0 and "unknown flag: --format" in combined_output and "--format" in FEISHU_CLI_EXTRA_ARGS:
        proc, command = _run(_without_unsupported_format_args(FEISHU_CLI_EXTRA_ARGS))
    payload = {
        "command": command,
        "exit_code": proc.returncode,
        "stdout": (proc.stdout or "").strip(),
        "stderr": (proc.stderr or "").strip(),
    }
    if proc.returncode != 0:
        raise RuntimeError(json.dumps(payload, ensure_ascii=False))
    return json.dumps(payload, ensure_ascii=False)


def resolve_workspace_path(path: str) -> str:
    if not path or not str(path).strip():
        raise ValueError("路径不能为空")
    workspace = os.path.abspath(get_agent_workspace())
    raw_path = str(path).strip()
    resolved = os.path.abspath(raw_path if os.path.isabs(raw_path) else os.path.join(workspace, raw_path))
    if os.path.commonpath([workspace, resolved]) != workspace:
        raise ValueError(f"路径超出工作区范围: {path}")
    return resolved


def list_workspace_dir(path: str = ".", recursive: bool = False) -> str:
    target = resolve_workspace_path(path)
    if not os.path.exists(target):
        raise FileNotFoundError(f"路径不存在: {path}")
    if not os.path.isdir(target):
        raise NotADirectoryError(f"不是目录: {path}")
    items = []
    if recursive:
        for root, dirs, files in os.walk(target):
            dirs.sort()
            files.sort()
            rel_root = os.path.relpath(root, get_agent_workspace())
            for name in dirs:
                items.append(os.path.join(rel_root, name).replace("\\", "/") + "/")
            for name in files:
                items.append(os.path.join(rel_root, name).replace("\\", "/"))
    else:
        for entry in sorted(os.listdir(target)):
            full = os.path.join(target, entry)
            rel = os.path.relpath(full, get_agent_workspace()).replace("\\", "/")
            items.append(rel + ("/" if os.path.isdir(full) else ""))
    return json.dumps({"path": path, "items": items}, ensure_ascii=False)


def read_workspace_file(path: str) -> str:
    target = resolve_workspace_path(path)
    if not os.path.exists(target):
        raise FileNotFoundError(f"文件不存在: {path}")
    if os.path.isdir(target):
        raise IsADirectoryError(f"路径是目录: {path}")
    with open(target, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    return json.dumps({"path": path, "content": content}, ensure_ascii=False)


def write_workspace_file(path: str, content: str) -> str:
    target = resolve_workspace_path(path)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    return json.dumps({"path": path, "status": "written", "bytes": len(content.encode('utf-8'))}, ensure_ascii=False)


def append_workspace_file(path: str, content: str) -> str:
    target = resolve_workspace_path(path)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "a", encoding="utf-8", newline="\n") as f:
        f.write(content)
    return json.dumps({"path": path, "status": "appended", "bytes": len(content.encode('utf-8'))}, ensure_ascii=False)


def delete_workspace_path(path: str) -> str:
    target = resolve_workspace_path(path)
    if not os.path.exists(target):
        raise FileNotFoundError(f"路径不存在: {path}")
    if os.path.isdir(target):
        shutil.rmtree(target)
        kind = "directory"
    else:
        os.remove(target)
        kind = "file"
    return json.dumps({"path": path, "status": "deleted", "kind": kind}, ensure_ascii=False)


def make_workspace_dir(path: str) -> str:
    target = resolve_workspace_path(path)
    os.makedirs(target, exist_ok=True)
    return json.dumps({"path": path, "status": "created"}, ensure_ascii=False)


def write_memory_file(path: str, content: str) -> str:
    memory_path = path if path.startswith("memory/") or path.startswith("memory\\") else os.path.join("memory", path)
    return write_workspace_file(memory_path, content)


WORKSPACE_TOOLS = [
    {"type": "function", "function": {"name": "list_dir", "description": "列出工作区内目录内容，可选递归。", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "recursive": {"type": "boolean"}}, "required": [], "additionalProperties": False}}},
    {"type": "function", "function": {"name": "read_file", "description": "读取工作区内文本文件内容。", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"], "additionalProperties": False}}},
    {"type": "function", "function": {"name": "write_file", "description": "写入工作区内文件。", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"], "additionalProperties": False}}},
    {"type": "function", "function": {"name": "append_file", "description": "向工作区文件末尾追加内容。", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"], "additionalProperties": False}}},
    {"type": "function", "function": {"name": "delete_path", "description": "删除工作区内文件或目录。", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"], "additionalProperties": False}}},
    {"type": "function", "function": {"name": "make_dir", "description": "在工作区内创建目录。", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"], "additionalProperties": False}}},
    {"type": "function", "function": {"name": "write_memory", "description": "将记忆内容写入工作区 memory 目录。", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"], "additionalProperties": False}}},
]

SHELL_TOOLS = [
    {"type": "function", "function": {"name": "run_shell", "description": "执行 PowerShell 命令。", "parameters": {"type": "object", "properties": {"command": {"type": "string"}, "cwd": {"type": "string"}, "timeout_seconds": {"type": "integer"}}, "required": ["command"], "additionalProperties": False}}},
]

SCHEDULE_TOOLS = [
    {"type": "function", "function": {"name": "create_scheduled_task", "description": "创建 interval/daily/once 定时任务。必须使用稳定的 chat_id 或 open_id 作为投递目标，不要使用 message_id 或 thread_id。", "parameters": {"type": "object", "properties": {"schedule_type": {"type": "string"}, "interval_minutes": {"type": "integer"}, "time_of_day": {"type": "string"}, "run_at_text": {"type": "string"}, "prompt": {"type": "string"}, "chat_id": {"type": "string"}, "open_id": {"type": "string"}, "reply_id": {"type": "string"}, "workdays": {"type": "array", "items": {"type": "integer"}}, "work_time_start": {"type": "string"}, "work_time_end": {"type": "string"}}, "required": ["schedule_type", "prompt", "chat_id"], "additionalProperties": False}}},
    {"type": "function", "function": {"name": "list_scheduled_tasks", "description": "列出当前所有定时任务。", "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False}}},
    {"type": "function", "function": {"name": "delete_scheduled_task", "description": "删除指定定时任务。", "parameters": {"type": "object", "properties": {"task_id": {"type": "string"}}, "required": ["task_id"], "additionalProperties": False}}},
    {"type": "function", "function": {"name": "set_scheduled_task_enabled", "description": "暂停或恢复定时任务。", "parameters": {"type": "object", "properties": {"task_id": {"type": "string"}, "enabled": {"type": "boolean"}}, "required": ["task_id", "enabled"], "additionalProperties": False}}},
    {"type": "function", "function": {"name": "set_scheduled_task_window", "description": "设置任务工作窗口。", "parameters": {"type": "object", "properties": {"task_id": {"type": "string"}, "workdays": {"type": "array", "items": {"type": "integer"}}, "work_time_start": {"type": "string"}, "work_time_end": {"type": "string"}}, "required": ["task_id"], "additionalProperties": False}}},
]


def execute_workspace_tool(name: str, arguments: dict) -> str:
    if name == "list_dir":
        return list_workspace_dir(arguments.get("path", "."), bool(arguments.get("recursive", False)))
    if name == "read_file":
        return read_workspace_file(arguments["path"])
    if name == "write_file":
        return write_workspace_file(arguments["path"], arguments["content"])
    if name == "append_file":
        return append_workspace_file(arguments["path"], arguments["content"])
    if name == "delete_path":
        return delete_workspace_path(arguments["path"])
    if name == "make_dir":
        return make_workspace_dir(arguments["path"])
    if name == "write_memory":
        return write_memory_file(arguments["path"], arguments["content"])
    raise ValueError(f"未知工具: {name}")


def execute_shell_tool(arguments: dict) -> str:
    command = str(arguments["command"]).strip()
    if not command:
        raise ValueError("command 不能为空")
    cwd = arguments.get("cwd")
    workdir = os.path.abspath(cwd) if cwd and os.path.isabs(str(cwd).strip()) else (resolve_workspace_path(cwd) if cwd else get_agent_workspace())
    timeout_seconds = max(1, min(int(arguments.get("timeout_seconds", 120) or 120), 600))
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            cwd=workdir,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Shell 命令执行超时（>{timeout_seconds}s）")
    return json.dumps(
        {
            "command": command,
            "cwd": workdir,
            "exit_code": proc.returncode,
            "stdout": (proc.stdout or "").strip(),
            "stderr": (proc.stderr or "").strip(),
        },
        ensure_ascii=False,
    )


def execute_schedule_tool(name: str, arguments: dict) -> str:
    if name == "create_scheduled_task":
        task = create_scheduled_task(
            arguments.get("interval_minutes"),
            arguments["prompt"],
            arguments.get("reply_id") or arguments.get("chat_id") or arguments.get("open_id"),
            created_by="agent",
            schedule_type=arguments["schedule_type"],
            time_of_day=arguments.get("time_of_day"),
            run_at_text=arguments.get("run_at_text"),
            chat_id=arguments.get("chat_id"),
            open_id=arguments.get("open_id"),
            workdays=arguments.get("workdays"),
            work_time_start=arguments.get("work_time_start"),
            work_time_end=arguments.get("work_time_end"),
        )
        return json.dumps({"status": "created", "task": task}, ensure_ascii=False)
    if name == "list_scheduled_tasks":
        return json.dumps({"tasks": list_scheduled_tasks()}, ensure_ascii=False)
    if name == "delete_scheduled_task":
        return json.dumps({"status": "deleted", "task": delete_scheduled_task(arguments["task_id"])}, ensure_ascii=False)
    if name == "set_scheduled_task_enabled":
        return json.dumps({"status": "updated", "task": set_task_enabled(arguments["task_id"], bool(arguments["enabled"]))}, ensure_ascii=False)
    if name == "set_scheduled_task_window":
        return json.dumps(
            {
                "status": "updated",
                "task": update_task_window(arguments["task_id"], arguments.get("workdays"), arguments.get("work_time_start"), arguments.get("work_time_end")),
            },
            ensure_ascii=False,
        )
    raise ValueError(f"未知定时任务工具: {name}")


def get_all_tools() -> list:
    return WORKSPACE_TOOLS + SHELL_TOOLS + SCHEDULE_TOOLS


def execute_tool(name: str, arguments: dict) -> str:
    if name == "run_shell":
        return execute_shell_tool(arguments)
    if name in {"create_scheduled_task", "list_scheduled_tasks", "delete_scheduled_task", "set_scheduled_task_enabled", "set_scheduled_task_window"}:
        return execute_schedule_tool(name, arguments)
    return execute_workspace_tool(name, arguments)
