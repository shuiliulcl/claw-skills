import subprocess
import json
import logging
import os
import threading
from collections import deque, defaultdict
import lark_oapi as lark
from lark_oapi.api.im.v1 import *
from config import APP_ID, APP_SECRET, WORK_DIR, NOTIFY_CHAT_ID, CLAUDE_TIMEOUT, CLAUDE_SKIP_PERMISSIONS

# 屏蔽 SDK 里 "processor not found" 的无关日志
class _SuppressUnhandledEvents(logging.Filter):
    def filter(self, record):
        return "processor not found" not in record.getMessage()

_f = _SuppressUnhandledEvents()
for _name in ["lark_oapi", "Lark", "", "root"]:
    logging.getLogger(_name).addFilter(_f)

client = lark.Client.builder().app_id(APP_ID).app_secret(APP_SECRET).build()

# ── 去重：线程安全，上限 1000 条 ──────────────────────────────────────────────
_id_lock = threading.Lock()
_processed_ids: set = set()
_processed_order: deque = deque()
MAX_IDS = 1000


def is_duplicate(msg_id: str) -> bool:
    with _id_lock:
        if msg_id in _processed_ids:
            return True
        if len(_processed_ids) >= MAX_IDS:
            oldest = _processed_order.popleft()
            _processed_ids.discard(oldest)
        _processed_ids.add(msg_id)
        _processed_order.append(msg_id)
        return False


# ── 对话历史 + 工作目录（按 chat_id 隔离）────────────────────────────────────
conversations: dict = {}
chat_work_dirs: dict = {}          # chat_id -> 自定义工作目录
_chat_locks: dict = defaultdict(threading.Lock)

MAX_HISTORY = 10
COMPRESS_AT  = 8
KEEP_RECENT  = 4
MSG_CHUNK_SIZE = 4000


# ── Claude 调用 ───────────────────────────────────────────────────────────────

def get_work_dir(chat_id: str) -> str:
    return chat_work_dirs.get(chat_id) or WORK_DIR or os.path.expanduser("~")


def ask_claude(prompt: str, chat_id: str) -> str:
    work_dir = get_work_dir(chat_id)
    try:
        # 通过 stdin 传 prompt，避免 Windows cmd.exe 把换行符当命令分隔符
        cmd = ["claude.cmd", "-p"]
        if CLAUDE_SKIP_PERMISSIONS:
            cmd.append("--dangerously-skip-permissions")
        result = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            timeout=CLAUDE_TIMEOUT,
            cwd=work_dir,
            text=True,
            encoding="utf-8",
        )
        if result.returncode != 0 and result.stderr:
            print(f"[WARN] claude 退出码 {result.returncode}: {result.stderr[:300]}")
        output = result.stdout.strip()
        return output or "（Claude 没有返回内容）"
    except subprocess.TimeoutExpired:
        return "（响应超时，请重试）"
    except FileNotFoundError:
        return "（未找到 claude 命令，请确认 Claude Code 已安装并加入 PATH）"
    except Exception as e:
        return f"（调用出错：{e}）"


# ── 对话历史管理 ──────────────────────────────────────────────────────────────

def _format_history_for_summary(turns: list) -> str:
    lines = []
    for t in turns:
        label = "用户" if t["role"] == "user" else "助手"
        lines.append(f"{label}：{t['content']}")
    return "\n".join(lines)


def compress_history(chat_id: str):
    history = conversations.get(chat_id, [])
    keep = KEEP_RECENT * 2

    if history and history[0]["role"] == "summary":
        prev_summary  = history[0]["content"]
        to_compress   = history[1:-keep] if len(history) > keep + 1 else []
        recent        = history[-keep:]
    else:
        prev_summary  = None
        to_compress   = history[:-keep]
        recent        = history[-keep:]

    if not to_compress:
        return

    if prev_summary:
        prompt = (
            f"以下是已有的对话摘要：\n{prev_summary}\n\n"
            f"请将下面的新对话整合进摘要，保留关键信息、决策和上下文，输出更新后的摘要：\n\n"
            f"{_format_history_for_summary(to_compress)}"
        )
    else:
        prompt = (
            "请将以下对话压缩成简洁摘要，保留关键信息、决策和上下文：\n\n"
            f"{_format_history_for_summary(to_compress)}"
        )

    print(f"[压缩历史] chat={chat_id}，压缩 {len(to_compress)//2} 轮...")
    summary = ask_claude(prompt, chat_id)
    conversations[chat_id] = [{"role": "summary", "content": summary}] + recent


def build_prompt(chat_id: str, user_text: str, quoted_text: str = None) -> str:
    history = conversations.get(chat_id, [])
    lines = []

    if history:
        lines += ["以下是本次会话的历史记录：", ""]
        for t in history:
            if t["role"] == "summary":
                lines.append(f"[历史摘要]\n{t['content']}\n")
            elif t["role"] == "user":
                lines.append(f"用户：{t['content']}")
            else:
                lines.append(f"助手：{t['content']}")
        lines.append("")

    if quoted_text:
        lines.append(f"用户引用了以下内容：\n> {quoted_text}\n")

    lines.append(f"用户：{user_text}")
    if history or quoted_text:
        lines.append("（请直接回复最新的用户问题）")

    return "\n".join(lines)


def update_history(chat_id: str, user_text: str, assistant_reply: str):
    history = conversations.setdefault(chat_id, [])
    history.append({"role": "user",      "content": user_text})
    history.append({"role": "assistant", "content": assistant_reply})
    non_summary = [t for t in history if t["role"] != "summary"]
    if len(non_summary) > COMPRESS_AT * 2:
        compress_history(chat_id)


# ── 消息收发 ──────────────────────────────────────────────────────────────────

def _get_receive_id_type(reply_id: str) -> str:
    """根据 ID 前缀自动判断 receive_id_type：
    ot_ → thread_id，其余（oc_ 等）→ chat_id"""
    return "thread_id" if reply_id.startswith("ot_") else "chat_id"


def _send(receive_id_type: str, receive_id: str, msg_type: str, content: str) -> str | None:
    """底层发送，返回 message_id 或 None"""
    request = (
        CreateMessageRequest.builder()
        .receive_id_type(receive_id_type)
        .request_body(
            CreateMessageRequestBody.builder()
            .receive_id(receive_id)
            .msg_type(msg_type)
            .content(content)
            .build()
        )
        .build()
    )
    resp = client.im.v1.message.create(request)
    if resp.success():
        return resp.data.message_id
    print(f"[ERROR] 发送失败({msg_type}): {resp.code} {resp.msg}")
    return None


def add_thinking_reaction(message_id: str) -> str | None:
    """给用户消息添加🤔表情，返回 reaction_id"""
    request = (
        CreateMessageReactionRequest.builder()
        .message_id(message_id)
        .request_body(
            CreateMessageReactionRequestBody.builder()
            .reaction_type(Emoji.builder().emoji_type("THINKING").build())
            .build()
        )
        .build()
    )
    resp = client.im.v1.message_reaction.create(request)
    if resp.success():
        return resp.data.reaction_id
    print(f"[WARN] 添加表情失败: {resp.code} {resp.msg}")
    return None


def remove_reaction(message_id: str, reaction_id: str):
    """移除表情回复"""
    if not reaction_id:
        return
    request = (
        DeleteMessageReactionRequest.builder()
        .message_id(message_id)
        .reaction_id(reaction_id)
        .build()
    )
    resp = client.im.v1.message_reaction.delete(request)
    if not resp.success():
        print(f"[WARN] 移除表情失败: {resp.code} {resp.msg}")


def _card_content(text: str) -> str:
    return json.dumps(
        {
            "schema": "2.0",
            "body": {
                "elements": [
                    {"tag": "markdown", "content": text}
                ]
            },
        },
        ensure_ascii=False,
    )


def send_card(reply_id: str, text: str):
    """向 reply_id（thread 或 chat）发送 Markdown 卡片"""
    _send(_get_receive_id_type(reply_id), reply_id, "interactive", _card_content(text))


def send_card_to_chat(chat_id: str, text: str):
    """直接向会话发送 Markdown 卡片（不在串中，用于通知等）"""
    _send("chat_id", chat_id, "interactive", _card_content(text))


def split_message(text: str, chunk_size: int = MSG_CHUNK_SIZE) -> list:
    if len(text) <= chunk_size:
        return [text]
    chunks = []
    while len(text) > chunk_size:
        cut = text.rfind("\n", 0, chunk_size)
        if cut == -1:
            cut = chunk_size
        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n")
    if text:
        chunks.append(text)
    return chunks


def send_reply(thread_id: str, text: str):
    """分段向消息串发送回复"""
    chunks = split_message(text)
    total  = len(chunks)
    for i, chunk in enumerate(chunks):
        content = chunk if total == 1 else f"**[{i+1}/{total}]**\n\n{chunk}"
        send_card(thread_id, content)


def fetch_message_text(message_id: str) -> str | None:
    """获取指定消息的文本内容（用于解析引用）"""
    try:
        request = GetMessageRequest.builder().message_id(message_id).build()
        resp = client.im.v1.message.get(request)
        if resp.success() and resp.data.items:
            item = resp.data.items[0]
            if item.msg_type == "text":
                return json.loads(item.body.content).get("text", "").strip()
    except Exception:
        pass
    return None


# ── 管理指令 ──────────────────────────────────────────────────────────────────

COMMANDS = {
    "/help":      "显示可用指令列表",
    "/clear":     "清除当前会话的对话历史",
    "/history":   "查看当前上下文保留轮数",
    "/cd <路径>": "切换当前会话的 Claude 工作目录",
}


def handle_command(chat_id: str, text: str, thread_id: str) -> bool:
    """处理斜杠命令，返回 True 表示已处理"""
    cmd = text.strip()

    if cmd == "/help":
        lines = ["**可用指令：**\n"]
        for c, desc in COMMANDS.items():
            lines.append(f"- `{c}` — {desc}")
        send_card(thread_id, "\n".join(lines))
        return True

    if cmd == "/clear":
        conversations.pop(chat_id, None)
        send_card(thread_id, "✅ 已清除当前会话的对话历史")
        return True

    if cmd == "/history":
        history     = conversations.get(chat_id, [])
        non_summary = [t for t in history if t["role"] != "summary"]
        has_summary = any(t["role"] == "summary" for t in history)
        turns       = len(non_summary) // 2
        msg         = f"📊 当前保留 **{turns}** 轮完整对话"
        if has_summary:
            msg += "（另有更早对话已压缩为摘要）"
        cur_dir = get_work_dir(chat_id)
        msg += f"\n📁 工作目录：`{cur_dir}`"
        send_card(thread_id, msg)
        return True

    if cmd.startswith("/cd "):
        path = cmd[4:].strip()
        if os.path.isdir(path):
            chat_work_dirs[chat_id] = path
            send_card(thread_id, f"✅ 工作目录已切换为：`{path}`")
        else:
            send_card(thread_id, f"❌ 路径不存在：`{path}`")
        return True

    return False


# ── 核心处理 ──────────────────────────────────────────────────────────────────

def process_and_reply(chat_id: str, text: str, sender_id: str,
                      thread_id: str, message_id: str, quoted_text: str = None):
    with _chat_locks[chat_id]:
        reaction_id = add_thinking_reaction(message_id)
        try:
            prompt = build_prompt(chat_id, text, quoted_text)
            reply  = ask_claude(prompt, chat_id)
            print(f"[Claude 回复] {sender_id}: {reply[:80]}{'...' if len(reply) > 80 else ''}")
            update_history(chat_id, text, reply)
        except Exception as e:
            reply = f"（处理出错：{e}）"
        finally:
            remove_reaction(message_id, reaction_id)

    send_reply(thread_id, reply)


def on_message(data: P2ImMessageReceiveV1) -> None:
    msg = data.event.message

    if is_duplicate(msg.message_id):
        return
    if msg.message_type != "text":
        return

    try:
        text = json.loads(msg.content).get("text", "").strip()
    except Exception:
        return
    if not text:
        return

    chat_id   = msg.chat_id
    sender_id = data.event.sender.sender_id.user_id or "unknown"
    # 若消息在真实 thread 中（ot_ 前缀）则回复到 thread，否则回复到 chat
    thread_id = msg.thread_id if (msg.thread_id and msg.thread_id.startswith("ot_")) else chat_id
    print(f"[收到消息] {sender_id}: {text}")

    # 管理指令直接处理，不进队列
    if text.startswith("/"):
        if handle_command(chat_id, text, thread_id):
            return

    # 引用消息内容
    quoted_text = None
    if msg.parent_id:
        quoted_text = fetch_message_text(msg.parent_id)

    threading.Thread(
        target=process_and_reply,
        args=(chat_id, text, sender_id, thread_id, msg.message_id, quoted_text),
        daemon=True,
    ).start()


# ── 启动 ──────────────────────────────────────────────────────────────────────

PID_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot.pid")


def _write_pid():
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))


def _remove_pid():
    try:
        os.remove(PID_FILE)
    except OSError:
        pass


def main():
    import atexit
    _write_pid()
    atexit.register(_remove_pid)

    print("=" * 50)
    print("  飞书 × Claude Code 机器人启动中...")
    print(f"  APP_ID: {APP_ID}")
    print("=" * 50)

    handler = (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(on_message)
        .build()
    )

    ws_client = lark.ws.Client(
        APP_ID,
        APP_SECRET,
        event_handler=handler,
        log_level=lark.LogLevel.INFO,
    )

    print("正在连接飞书服务器（无需公网 IP）...")

    if NOTIFY_CHAT_ID:
        # 在后台延迟发送，等 WebSocket 连接就绪
        def _notify():
            import time; time.sleep(3)
            send_card_to_chat(NOTIFY_CHAT_ID, "✅ **机器人已上线**\n发送 `/help` 查看可用指令")
        threading.Thread(target=_notify, daemon=True).start()

    ws_client.start()


if __name__ == "__main__":
    main()
