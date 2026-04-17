import threading
from collections import defaultdict, deque

from .config_runtime import MAX_IDS

DEFAULT_AGENT_SYSTEM_PROMPT = """你是一个接入飞书群聊/私聊和本地终端的 ChatGPT Agent。
请使用简洁、直接、自然的中文回答；如果用户明确要求英文，再切换英文。
所有相对路径都相对于当前 Agent 工作区。"""

agent_system_prompt = DEFAULT_AGENT_SYSTEM_PROMPT
agent_system_mtime = None
agent_system_path = None

ws_client = None
bot_runtime_thread = None

heartbeat_lock = threading.Lock()
ws_consecutive_failures = 0
heartbeat_consecutive_failures = 0
last_heartbeat_ok_at = 0.0

tasks_lock = threading.Lock()
scheduled_tasks: dict = {}

id_lock = threading.Lock()
processed_ids: set = set()
processed_order: deque = deque()

conversations: dict = {}
chat_locks: dict = defaultdict(threading.Lock)
pending_message_lock = threading.Lock()
pending_messages: dict[str, threading.Event] = {}


def is_duplicate(msg_id: str) -> bool:
    with id_lock:
        if msg_id in processed_ids:
            return True
        if len(processed_ids) >= MAX_IDS:
            oldest = processed_order.popleft()
            processed_ids.discard(oldest)
        processed_ids.add(msg_id)
        processed_order.append(msg_id)
        return False


def register_pending_message(message_id: str) -> threading.Event:
    cancel_event = threading.Event()
    with pending_message_lock:
        pending_messages[message_id] = cancel_event
    return cancel_event


def cancel_pending_message(message_id: str) -> bool:
    with pending_message_lock:
        cancel_event = pending_messages.get(message_id)
    if cancel_event is None:
        return False
    cancel_event.set()
    return True


def finish_pending_message(message_id: str):
    with pending_message_lock:
        pending_messages.pop(message_id, None)
