import json

from openai import APIError, APITimeoutError, AuthenticationError

from . import state
from .config_runtime import COMPRESS_AT, KEEP_RECENT, MAX_TOOL_STEPS, OPENAI_API_KEY, OPENAI_MODEL, openai_client
from .paths import build_agent_system_prompt, load_heartbeat_text
from .tools import execute_tool, get_all_tools


def ask_chatgpt(prompt: str, system_prompt: str = "") -> str:
    if not OPENAI_API_KEY:
        return "（未配置 OPENAI_API_KEY）"
    try:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        tools = get_all_tools()

        for _ in range(MAX_TOOL_STEPS):
            response = openai_client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=messages,
                tools=tools,
                tool_choice="auto",
            )
            message = response.choices[0].message
            tool_calls = getattr(message, "tool_calls", None) or []

            if not tool_calls:
                output = (message.content or "").strip()
                return output or "（ChatGPT 没有返回内容）"

            messages.append(
                {
                    "role": "assistant",
                    "content": message.content or "",
                    "tool_calls": [
                        {
                            "id": tool_call.id,
                            "type": "function",
                            "function": {
                                "name": tool_call.function.name,
                                "arguments": tool_call.function.arguments,
                            },
                        }
                        for tool_call in tool_calls
                    ],
                }
            )

            for tool_call in tool_calls:
                try:
                    arguments = json.loads(tool_call.function.arguments or "{}")
                    tool_result = execute_tool(tool_call.function.name, arguments)
                except Exception as e:
                    tool_result = json.dumps(
                        {"error": str(e), "tool": tool_call.function.name},
                        ensure_ascii=False,
                    )

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": tool_result,
                    }
                )

        return "（工具调用轮数超限，请拆分任务后重试）"
    except APITimeoutError:
        return "（响应超时，请重试）"
    except AuthenticationError:
        return "（OpenAI 认证失败，请检查 OPENAI_API_KEY）"
    except APIError as e:
        return f"（OpenAI API 出错：{e}）"
    except Exception as e:
        return f"（调用出错：{e}）"


def _format_history_for_summary(turns: list[dict]) -> str:
    lines = []
    for turn in turns:
        label = "用户" if turn["role"] == "user" else "助手"
        lines.append(f"{label}：{turn['content']}")
    return "\n".join(lines)


def compress_history(chat_id: str):
    history = state.conversations.get(chat_id, [])
    keep = KEEP_RECENT * 2

    if history and history[0]["role"] == "summary":
        prev_summary = history[0]["content"]
        to_compress = history[1:-keep] if len(history) > keep + 1 else []
        recent = history[-keep:]
    else:
        prev_summary = None
        to_compress = history[:-keep]
        recent = history[-keep:]

    if not to_compress:
        return

    turns_text = _format_history_for_summary(to_compress)
    if prev_summary:
        prompt = (
            f"以下是已有的对话摘要：\n{prev_summary}\n\n"
            "请将下面的新对话整合进摘要，保留关键信息、决策和上下文，输出更新后的摘要：\n\n"
            f"{turns_text}"
        )
    else:
        prompt = "请将以下对话压缩成简洁摘要，保留关键信息、决策和上下文：\n\n" + turns_text

    print(f"[压缩历史] chat={chat_id}，压缩 {len(to_compress) // 2} 轮...")
    summary = ask_chatgpt(prompt, build_agent_system_prompt())
    state.conversations[chat_id] = [{"role": "summary", "content": summary}] + recent


def build_prompt(chat_id: str, user_text: str, quoted_text: str | None = None) -> str:
    history = state.conversations.get(chat_id, [])
    history_block = ""
    quoted_block = ""
    reply_suffix = ""

    if history:
        lines = ["以下是本次会话的历史记录：", ""]
        for turn in history:
            if turn["role"] == "summary":
                lines.append(f"[历史摘要]\n{turn['content']}\n")
            elif turn["role"] == "user":
                lines.append(f"用户：{turn['content']}")
            else:
                lines.append(f"助手：{turn['content']}")
        history_block = "\n".join(lines).strip() + "\n\n"

    if quoted_text:
        quoted_block = f"用户引用了以下内容：\n> {quoted_text}\n\n"

    if history or quoted_text:
        reply_suffix = "（请直接回复最新的用户问题）"

    return f"{history_block}{quoted_block}用户：{user_text}\n{reply_suffix}".strip()


def update_history(chat_id: str, user_text: str, assistant_reply: str):
    history = state.conversations.setdefault(chat_id, [])
    history.append({"role": "user", "content": user_text})
    history.append({"role": "assistant", "content": assistant_reply})
    non_summary = [turn for turn in history if turn["role"] != "summary"]
    if len(non_summary) > COMPRESS_AT * 2:
        compress_history(chat_id)


def run_agent_heartbeat_check() -> str:
    heartbeat_text = load_heartbeat_text()
    prompt = (
        "现在执行一次 HEARTBEAT 轮询。\n"
        "请严格根据当前工作区的 AGENTS.md 和 HEARTBEAT.md 执行自检。\n"
        "如果 HEARTBEAT.md 为空、仅注释，或检查结果正常且无需通知，请只输出 `HEARTBEAT_OK`。\n"
        "如果需要通知用户，请直接输出要发送给用户的正文，不要输出解释、前言、代码块或额外包装。"
    )
    if heartbeat_text:
        prompt += "\n\n下面是 HEARTBEAT.md 当前内容，供你参考：\n" + heartbeat_text
    return ask_chatgpt(prompt, build_agent_system_prompt()).strip()
