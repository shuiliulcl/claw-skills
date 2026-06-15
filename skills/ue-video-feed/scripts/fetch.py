#!/usr/bin/env python3
"""Sync latest videos from the Unreal Engine official YouTube channel to Feishu Base.

Pulls latest uploads via YouTube Data API v3, dedupes against existing
videoIds in the Base, inserts new ones with status=新发现, and pushes a
markdown DM to the user. Silent when no new videos.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

# Force UTF-8 stdio so 中文 logs render correctly under Windows cp936 console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Resolve lark-cli once. On Windows the npm shim is lark-cli.cmd which forwards
# args via `%*` through cmd.exe, mangling JSON / markdown with special chars.
# Detect the underlying node entry script and call node directly to bypass cmd.
def _resolve_lark_cmd():
    cli = shutil.which("lark-cli")
    if not cli:
        return ["lark-cli"]
    if sys.platform != "win32" or not cli.lower().endswith(".cmd"):
        return [cli]
    # Find the run.js used by the .cmd shim: node_modules/@larksuite/cli/scripts/run.js
    # next to the .cmd file.
    cli_dir = Path(cli).parent
    run_js = cli_dir / "node_modules" / "@larksuite" / "cli" / "scripts" / "run.js"
    if not run_js.exists():
        return [cli]
    node_exe = shutil.which("node") or "node"
    return [node_exe, str(run_js)]


_LARK_CMD = _resolve_lark_cmd()

CHANNEL_ID = "UCBobmJyzsJ6Ll7UbfhI4iwQ"
BASE_TOKEN = "SpvXbLleeaQQMusl2bQcd04pncc"
TABLE_ID = "tblhyTM6a1bDlybm"
USER_OPEN_ID = "ou_2b6334604d63123d4dc232d596e9d46d"
CONFIG_DIR = Path(os.path.expandvars(r"%USERPROFILE%\.config\ue-video-feed"))
CONFIG_PATH = CONFIG_DIR / "config.json"
UPLOADS_CACHE = CONFIG_DIR / "uploads_playlist.txt"
MAX_RESULTS = 50
API_BASE = "https://www.googleapis.com/youtube/v3"


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def load_config():
    if not CONFIG_PATH.exists():
        log(
            f"配置文件不存在: {CONFIG_PATH}\n"
            f"请创建该文件,内容:\n"
            f'  {{"youtube_api_key": "你的_API_KEY"}}'
        )
        sys.exit(2)
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if not cfg.get("youtube_api_key"):
        log(f"配置文件 {CONFIG_PATH} 缺少 youtube_api_key 字段")
        sys.exit(2)
    # anthropic key/url/model 可选,config 缺失时回退到环境变量
    if not cfg.get("anthropic_api_key"):
        env_key = (
            os.environ.get("ANTHROPIC_AUTH_TOKEN")
            or os.environ.get("ANTHROPIC_API_KEY")
            or ""
        )
        if env_key:
            cfg["anthropic_api_key"] = env_key
    if not cfg.get("anthropic_base_url"):
        cfg["anthropic_base_url"] = os.environ.get(
            "ANTHROPIC_BASE_URL", "https://api.anthropic.com"
        ).rstrip("/")
    if not cfg.get("anthropic_model"):
        # 官方 Anthropic 用带日期版的 ID,PaperHub 等中转用短名
        is_official = "api.anthropic.com" in cfg["anthropic_base_url"]
        cfg["anthropic_model"] = (
            "claude-haiku-4-5-20251001" if is_official else "claude-haiku-4-5"
        )
    return cfg


def yt_get(path, params, api_key):
    qs = urllib.parse.urlencode({**params, "key": api_key})
    url = f"{API_BASE}/{path}?{qs}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        if e.code == 403 and "quotaExceeded" in body:
            log("YouTube API 配额已用尽,明日 UTC 0 点重置")
        else:
            log(f"YouTube API HTTP {e.code}: {body[:500]}")
        sys.exit(3)
    except urllib.error.URLError as e:
        log(f"YouTube API 网络错误: {e}")
        sys.exit(3)


def get_uploads_playlist_id(api_key):
    if UPLOADS_CACHE.exists():
        cached = UPLOADS_CACHE.read_text(encoding="utf-8").strip()
        if cached:
            return cached
    data = yt_get("channels", {"part": "contentDetails", "id": CHANNEL_ID}, api_key)
    items = data.get("items", [])
    if not items:
        log(f"找不到频道 {CHANNEL_ID}")
        sys.exit(3)
    pid = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS_CACHE.write_text(pid, encoding="utf-8")
    return pid


def get_playlist_videos(playlist_id, api_key):
    data = yt_get(
        "playlistItems",
        {
            "part": "snippet,contentDetails",
            "playlistId": playlist_id,
            "maxResults": MAX_RESULTS,
        },
        api_key,
    )
    out = []
    for it in data.get("items", []):
        s = it["snippet"]
        c = it["contentDetails"]
        out.append(
            {
                "video_id": c["videoId"],
                "title": s["title"],
                "published_at": c.get("videoPublishedAt") or s.get("publishedAt"),
            }
        )
    return out


def get_video_durations(video_ids, api_key):
    out = {}
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i : i + 50]
        data = yt_get(
            "videos",
            {"part": "contentDetails", "id": ",".join(batch)},
            api_key,
        )
        for it in data.get("items", []):
            out[it["id"]] = it["contentDetails"]["duration"]
    return out


_DURATION_RE = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")


def parse_iso_duration_seconds(s):
    if not s:
        return 0
    m = _DURATION_RE.match(s)
    if not m:
        return 0
    h, mn, sec = (int(x or 0) for x in m.groups())
    return h * 3600 + mn * 60 + sec


def format_duration(total_sec):
    if total_sec <= 0:
        return ""
    h, rem = divmod(total_sec, 3600)
    mn, sec = divmod(rem, 60)
    if h:
        return f"{h}:{mn:02d}:{sec:02d}"
    return f"{mn}:{sec:02d}"


# 过滤阈值:时长不足 10 分钟跳过
MIN_DURATION_SEC = 10 * 60

# 标题"明显与游戏开发无关"模式: 营销/活动/预告/UEFN(Fortnite 创作者向)
NON_DEV_TITLE_PATTERNS = [
    re.compile(r"\btrailer\b", re.I),
    re.compile(r"\bout now\b", re.I),
    re.compile(r"\bavailable now\b", re.I),
    re.compile(r"\btune in\b", re.I),
    re.compile(r"\bjoin us live\b", re.I),
    re.compile(r"^this just in[:!]", re.I),
    re.compile(r"^this time next week", re.I),
    re.compile(r"\blive (next week|tomorrow|today)\b", re.I),
    re.compile(r"^(coming|launching) (next|in)\b", re.I),
    re.compile(r"\bUEFN\b"),                      # Fortnite 创作者编辑器,与 UE 主项目开发无关
    re.compile(r"\bCreating in Fortnite\b", re.I),
    re.compile(r"\bMetaHuman", re.I),             # 数字人/角色资产工具链,与游戏系统开发分离
]


def is_dev_relevant(title):
    if not title:
        return False
    for pat in NON_DEV_TITLE_PATTERNS:
        if pat.search(title):
            return False
    return True


def format_published(iso):
    if not iso:
        return ""
    iso = iso.replace("Z", "").split(".")[0]
    try:
        dt = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%S")
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return iso


def run_lark_cli(args):
    cmd = _LARK_CMD + args
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")


def get_existing_video_ids():
    existing = set()
    offset = 0
    limit = 200
    while True:
        proc = run_lark_cli(
            [
                "base",
                "+record-list",
                "--base-token",
                BASE_TOKEN,
                "--table-id",
                TABLE_ID,
                "--field-id",
                "视频ID",
                "--limit",
                str(limit),
                "--offset",
                str(offset),
                "--format",
                "json",
                "--as",
                "user",
            ]
        )
        if proc.returncode != 0:
            log(f"读取 Base 已有视频ID失败,跳过去重\n{proc.stderr or proc.stdout}")
            return existing
        try:
            envelope = json.loads(proc.stdout)
        except json.JSONDecodeError:
            log(f"无法解析 Base 返回前 200 字: {proc.stdout[:200]}")
            return existing
        data_obj = envelope.get("data") or {}
        # record-list returns columnar 2D array: data.data[row][col]
        # paired with data.fields[col] for header order.
        rows = data_obj.get("data") or []
        fields = data_obj.get("fields") or []
        try:
            idx = fields.index("视频ID")
        except ValueError:
            log("Base 返回中缺少 视频ID 列")
            return existing
        for row in rows:
            if not isinstance(row, list) or len(row) <= idx:
                continue
            v = row[idx]
            if isinstance(v, list):
                v = "".join(seg.get("text", "") for seg in v if isinstance(seg, dict))
            if v:
                existing.add(str(v).strip())
        has_more = bool(data_obj.get("has_more"))
        if not has_more or len(rows) < limit:
            break
        offset += limit
    return existing


def write_new_records(new_videos):
    if not new_videos:
        return 0
    fields = ["视频ID", "中文标题", "英文标题", "链接", "时长", "发布时间", "状态"]
    written = 0
    chunk_size = 20
    for i in range(0, len(new_videos), chunk_size):
        chunk = new_videos[i : i + chunk_size]
        rows = [
            [
                v["video_id"],
                v.get("zh_title", ""),
                v["title"],
                f"https://www.youtube.com/watch?v={v['video_id']}",
                v["duration"],
                v["published"],
                "新发现",
            ]
            for v in chunk
        ]
        payload = {"fields": fields, "rows": rows}
        proc = run_lark_cli(
            [
                "base",
                "+record-batch-create",
                "--base-token",
                BASE_TOKEN,
                "--table-id",
                TABLE_ID,
                "--json",
                json.dumps(payload, ensure_ascii=False),
                "--as",
                "user",
            ]
        )
        if proc.returncode != 0:
            log(
                f"批量写入第 {i // chunk_size + 1} 批失败 ({len(chunk)} 条)\n"
                f"{proc.stderr or proc.stdout}"
            )
            continue
        written += len(chunk)
    return written


TRANSLATE_SYSTEM_PROMPT = (
    "你是 UE 游戏开发频道的视频标题翻译助手。任务:把英文标题翻译成简洁中文。\n"
    "\n"
    "硬规则:\n"
    "- 保留原文不译: Unreal Engine、UE5、UEFN、Niagara、Lumen、Nanite、MegaLights、Chaos、Substrate、MetaHuman、Cascadeur 等技术名词与产品名\n"
    "- 保留原文不译: 游戏名(NBA THE RUN、Beastro、Mixtape 等)、工作室名(Sumo Digital、Neon Giant 等)、品牌名\n"
    "- 保留原文不译: | Inside Unreal、| Game Profile、| Indie Games Week、| UEFN Build Along、| Creating in Fortnite 等系列后缀\n"
    "- 翻译要简短自然,不加引号,不加解释,不画蛇添足\n"
    "\n"
    "输入: JSON 数组(每元素一个英文标题)\n"
    "输出: 同长度 JSON 数组(每元素对应位置的中文标题)。**只输出 JSON 数组,不要任何其他文字**"
)


def translate_titles(en_titles, anthropic_api_key, base_url=None, model=None):
    """批量翻译英文标题到中文 (Claude Haiku 4.5)。
    无 key / 失败 / 长度不匹配时返回与输入等长的空字符串列表,不阻塞主流程。

    base_url: 默认 https://api.anthropic.com,可指向 PaperHub 等中转
    model: 默认 claude-haiku-4-5-20251001(官方)或 claude-haiku-4-5(中转)
    鉴权:base_url 为官方 Anthropic 时用 x-api-key,中转走 Authorization: Bearer
    """
    if not en_titles:
        return []
    if not anthropic_api_key:
        log("config 无 anthropic_api_key,跳过翻译")
        return ["" for _ in en_titles]

    base_url = (base_url or "https://api.anthropic.com").rstrip("/")
    model = model or "claude-haiku-4-5-20251001"
    is_official = "api.anthropic.com" in base_url

    payload = {
        "model": model,
        "max_tokens": 4096,
        "system": [
            {
                "type": "text",
                "text": TRANSLATE_SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        "messages": [
            {"role": "user", "content": json.dumps(en_titles, ensure_ascii=False)}
        ],
    }
    headers = {
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    if is_official:
        headers["x-api-key"] = anthropic_api_key
    else:
        headers["Authorization"] = f"Bearer {anthropic_api_key}"

    req = urllib.request.Request(
        f"{base_url}/v1/messages",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.load(resp)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        log(f"翻译 API HTTP {e.code}: {body[:300]}")
        return ["" for _ in en_titles]
    except urllib.error.URLError as e:
        log(f"翻译 API 网络错误: {e}")
        return ["" for _ in en_titles]

    text = (result.get("content") or [{}])[0].get("text", "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()
    try:
        zh_list = json.loads(text)
    except json.JSONDecodeError:
        log(f"翻译返回非合法 JSON,原文前 200 字: {text[:200]}")
        return ["" for _ in en_titles]
    if not isinstance(zh_list, list) or len(zh_list) != len(en_titles):
        log(f"翻译返回结构不匹配 (期望 list 长度 {len(en_titles)})")
        return ["" for _ in en_titles]

    usage = result.get("usage") or {}
    cache_read = usage.get("cache_read_input_tokens", 0)
    cache_create = usage.get("cache_creation_input_tokens", 0)
    if cache_read or cache_create:
        log(f"  翻译 cache: read {cache_read} / create {cache_create} tokens")

    return [str(t) if t else "" for t in zh_list]


def push_dm(new_videos):
    if not new_videos:
        return False
    lines = [f"**UE 频道新增 {len(new_videos)} 条**", ""]
    for i, v in enumerate(new_videos, 1):
        date = v["published"][:10] if v["published"] else ""
        url = f"https://www.youtube.com/watch?v={v['video_id']}"
        # 优先显示中文标题,没翻则回退英文
        display_title = v.get("zh_title") or v["title"]
        lines.append(f"{i}. [{display_title}]({url}) · {v['duration']} · {date}")
    md = "\n".join(lines)
    proc = run_lark_cli(
        [
            "im",
            "+messages-send",
            "--user-id",
            USER_OPEN_ID,
            "--markdown",
            md,
            "--as",
            "bot",
        ]
    )
    if proc.returncode != 0:
        log(f"推送飞书私聊失败\n{proc.stderr or proc.stdout}")
        return False
    return True


def main():
    cfg = load_config()
    api_key = cfg["youtube_api_key"]

    uploads_id = get_uploads_playlist_id(api_key)
    log(f"上传播放列表: {uploads_id}")

    videos = get_playlist_videos(uploads_id, api_key)
    log(f"YouTube 返回 {len(videos)} 条最近视频")

    durations = get_video_durations([v["video_id"] for v in videos], api_key)
    for v in videos:
        sec = parse_iso_duration_seconds(durations.get(v["video_id"], ""))
        v["duration_sec"] = sec
        v["duration"] = format_duration(sec)
        v["published"] = format_published(v["published_at"])

    # 过滤: 时长 < 10 分钟,或标题明显非开发主题
    eligible = []
    short_n = off_n = 0
    for v in videos:
        if 0 < v["duration_sec"] < MIN_DURATION_SEC:
            short_n += 1
            log(f"  过滤(短<{MIN_DURATION_SEC // 60}min): {v['duration']} | {v['title'][:60]}")
            continue
        if not is_dev_relevant(v["title"]):
            off_n += 1
            log(f"  过滤(非开发): {v['title'][:80]}")
            continue
        eligible.append(v)
    log(f"过滤后保留 {len(eligible)}/{len(videos)} 条 (短 {short_n} + 非开发 {off_n})")

    if not eligible:
        log("过滤后无可写入,退出")
        return

    existing = get_existing_video_ids()
    log(f"Base 已有 {len(existing)} 条记录")

    new_videos = [v for v in eligible if v["video_id"] not in existing]
    log(f"本次新增 {len(new_videos)} 条")

    if not new_videos:
        log("无新增,静默退出")
        return

    new_videos.sort(key=lambda v: v["published_at"] or "", reverse=True)

    # 翻译中文标题(可选,失败不阻塞)
    zh_titles = translate_titles(
        [v["title"] for v in new_videos],
        cfg.get("anthropic_api_key", ""),
        base_url=cfg.get("anthropic_base_url"),
        model=cfg.get("anthropic_model"),
    )
    for v, zh in zip(new_videos, zh_titles):
        v["zh_title"] = zh
    ok_zh = sum(1 for t in zh_titles if t)
    if ok_zh:
        log(f"翻译完成 {ok_zh}/{len(new_videos)} 条中文标题")

    written = write_new_records(new_videos)
    if written > 0:
        sent = push_dm(new_videos)
        if sent:
            log(f"完成: 写入 Base {written} 条 + 已推送私聊")
        else:
            log(f"完成: 写入 Base {written} 条 (私聊推送失败,见上方错误)")
    else:
        log("未写入 Base, 跳过推送")


if __name__ == "__main__":
    main()
