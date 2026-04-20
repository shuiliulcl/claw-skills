import json
import re

from lark_oapi.api.im.v1 import (
    CreateMessageReactionRequest,
    CreateMessageReactionRequestBody,
    CreateMessageRequest,
    CreateMessageRequestBody,
    DeleteMessageReactionRequest,
    Emoji,
    GetMessageRequest,
)

from .config_runtime import MSG_CHUNK_SIZE, NOTIFY_CHAT_ID, NOTIFY_OPEN_ID, client
from .utils import compact_dict, first_non_empty, format_timestamp_ms, json_dumps, serialize_sdk_value


def get_receive_id_type(reply_id: str) -> str:
    return "thread_id" if reply_id.startswith("ot_") else "chat_id"


def _send(receive_id_type: str, receive_id: str, msg_type: str, content: str) -> str | None:
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
    if not reaction_id:
        return
    request = DeleteMessageReactionRequest.builder().message_id(message_id).reaction_id(reaction_id).build()
    resp = client.im.v1.message_reaction.delete(request)
    if not resp.success():
        if str(resp.code) == "231003":
            return
        print(f"[WARN] 移除表情失败: {resp.code} {resp.msg}")


def plain_text_content(text: str) -> str:
    plain = str(text or "").replace("\r\n", "\n")
    plain = re.sub(r"```[^\n]*\n", "", plain)
    plain = plain.replace("```", "")
    plain = re.sub(r"(?<!\\)`([^`]+)`", r"\1", plain)
    plain = re.sub(r"\*\*([^*]+)\*\*", r"\1", plain)
    plain = re.sub(r"__([^_]+)__", r"\1", plain)
    plain = re.sub(r"^#{1,6}\s*", "", plain, flags=re.MULTILINE)
    plain = re.sub(r"^\>\s?", "", plain, flags=re.MULTILINE)
    plain = re.sub(r"\n{3,}", "\n\n", plain).strip()
    return json_dumps({"text": plain})


def send_card(reply_id: str, text: str):
    _send(get_receive_id_type(reply_id), reply_id, "text", plain_text_content(text))


def send_card_to_chat(chat_id: str, text: str):
    _send("chat_id", chat_id, "text", plain_text_content(text))


def send_card_to_open_id(open_id: str, text: str):
    _send("open_id", open_id, "text", plain_text_content(text))


def send_admin_notification(text: str):
    if NOTIFY_CHAT_ID:
        send_card_to_chat(NOTIFY_CHAT_ID, text)
    if NOTIFY_OPEN_ID:
        send_card_to_open_id(NOTIFY_OPEN_ID, text)


def split_message(text: str, chunk_size: int = MSG_CHUNK_SIZE) -> list[str]:
    if len(text) <= chunk_size:
        return [text]
    chunks = []
    remaining = text
    while len(remaining) > chunk_size:
        cut = remaining.rfind("\n", 0, chunk_size)
        if cut == -1:
            cut = chunk_size
        chunks.append(remaining[:cut])
        remaining = remaining[cut:].lstrip("\n")
    if remaining:
        chunks.append(remaining)
    return chunks


def send_reply(reply_id: str, text: str):
    chunks = split_message(text)
    total = len(chunks)
    for index, chunk in enumerate(chunks, start=1):
        content = chunk if total == 1 else f"**[{index}/{total}]**\n\n{chunk}"
        send_card(reply_id, content)


def mention_display_name(mention) -> str:
    name = (getattr(mention, "name", None) or "").strip()
    if name:
        return name

    mention_id = getattr(mention, "id", None)
    if hasattr(mention_id, "open_id"):
        for value in [mention_id.open_id, mention_id.user_id, mention_id.union_id]:
            if value:
                return value

    for attr in ["id", "open_id", "user_id", "union_id"]:
        value = getattr(mention, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "unknown"


def mention_identifier(mention) -> str:
    mention_id = getattr(mention, "id", None)
    if hasattr(mention_id, "open_id"):
        return first_non_empty(mention_id.user_id, mention_id.open_id, mention_id.union_id)
    return first_non_empty(
        getattr(mention, "id", None),
        getattr(mention, "user_id", None),
        getattr(mention, "open_id", None),
        getattr(mention, "union_id", None),
    )


def restore_mentions_in_text(text: str, mentions) -> str:
    restored = text or ""
    for index, mention in enumerate(list(mentions or []), start=1):
        display = mention_display_name(mention)
        key = str(getattr(mention, "key", "") or "").strip()
        replacement = f"@{display}"
        candidates = []
        if key:
            candidates.append(key)
            if not key.startswith("@"):
                candidates.append(f"@{key}")
        candidates.append(f"@User_{index}")

        seen = set()
        for candidate in candidates:
            if candidate and candidate not in seen and candidate in restored:
                restored = restored.replace(candidate, replacement)
                seen.add(candidate)
    return restored


def build_mentions_meta(mentions) -> list[dict]:
    items = []
    for index, mention in enumerate(list(mentions or []), start=1):
        mention_id = getattr(mention, "id", None)
        items.append(
            compact_dict(
                {
                    "index": index,
                    "display_name": mention_display_name(mention),
                    "key": first_non_empty(getattr(mention, "key", None)),
                    "name": first_non_empty(getattr(mention, "name", None)),
                    "user_id": first_non_empty(getattr(mention_id, "user_id", None), getattr(mention, "user_id", None)),
                    "open_id": first_non_empty(getattr(mention_id, "open_id", None), getattr(mention, "open_id", None)),
                    "union_id": first_non_empty(getattr(mention_id, "union_id", None), getattr(mention, "union_id", None)),
                    "tenant_key": first_non_empty(getattr(mention, "tenant_key", None)),
                    "fallback_id": mention_identifier(mention),
                    "raw": serialize_sdk_value(mention),
                }
            )
        )
    return items


def resolve_sender_identity(sender) -> dict:
    sender_id = getattr(sender, "sender_id", None)
    return compact_dict(
        {
            "sender_id": first_non_empty(getattr(sender_id, "user_id", None)),
            "sender_open_id": first_non_empty(getattr(sender_id, "open_id", None)),
            "sender_union_id": first_non_empty(getattr(sender_id, "union_id", None)),
            "sender_type": first_non_empty(getattr(sender, "sender_type", None)),
            "tenant_key": first_non_empty(getattr(sender, "tenant_key", None)),
            "sender_raw": serialize_sdk_value(sender),
        }
    )


def build_message_meta(msg, sender=None, mentions=None, content_data=None) -> dict:
    meta = compact_dict(
        {
            "message_id": first_non_empty(getattr(msg, "message_id", None)),
            "root_id": first_non_empty(getattr(msg, "root_id", None)),
            "parent_id": first_non_empty(getattr(msg, "parent_id", None)),
            "thread_id": first_non_empty(getattr(msg, "thread_id", None)),
            "chat_id": first_non_empty(getattr(msg, "chat_id", None)),
            "chat_type": first_non_empty(getattr(msg, "chat_type", None)),
            "message_type": first_non_empty(getattr(msg, "message_type", None), getattr(msg, "msg_type", None)),
            "create_time": format_timestamp_ms(getattr(msg, "create_time", None)),
            "update_time": format_timestamp_ms(getattr(msg, "update_time", None)),
            "user_agent": first_non_empty(getattr(msg, "user_agent", None)),
            "content_raw": content_data,
            "message_raw": serialize_sdk_value(msg),
        }
    )
    if sender is not None:
        meta.update(resolve_sender_identity(sender))
    mention_items = build_mentions_meta(mentions)
    if mention_items:
        meta["mentions"] = mention_items
    return meta


def render_message_meta(meta: dict) -> str:
    return "" if not meta else "[消息元信息]\n" + json.dumps(meta, ensure_ascii=False, indent=2)


def render_user_message(text: str, meta: dict | None = None) -> str:
    stripped = (text or "").strip()
    meta_block = render_message_meta(meta or {})
    if stripped and meta_block:
        return f"{stripped}\n{meta_block}"
    return stripped or meta_block


def parse_message_content(message_type: str, content: str, mentions=None) -> tuple[str, object]:
    data = json.loads(content)
    if message_type == "text":
        text = (data.get("text") or "").strip()
        return restore_mentions_in_text(text, mentions), data
    label = message_type or "unknown"
    return f"[{label} 消息]", data


def fetch_message_text(message_id: str) -> str | None:
    try:
        request = GetMessageRequest.builder().message_id(message_id).build()
        resp = client.im.v1.message.get(request)
        if resp.success() and resp.data.items:
            item = resp.data.items[0]
            text, content_data = parse_message_content(item.msg_type, item.body.content, getattr(item, "mentions", None))
            meta = build_message_meta(item, getattr(item, "sender", None), getattr(item, "mentions", None), content_data)
            return render_user_message(text, meta)
    except Exception:
        return None
    return None
