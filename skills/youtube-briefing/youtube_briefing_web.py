from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.parse
import uuid
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


WORKDIR = Path(__file__).resolve().parent
CLI_SCRIPT = WORKDIR / "youtube_briefing.py"
PYTHON_EXE = Path(sys.executable)
DEFAULT_OUTPUT_DIR = Path(r"D:\YouTubeBriefings")
HOST = "127.0.0.1"
PORT = 8765

JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()

JOB_QUEUE: list[str] = []
QUEUE_LOCK = threading.Lock()
QUEUE_EVENT = threading.Event()


def now_ts() -> float:
    return time.time()


def queue_worker() -> None:
    while True:
        QUEUE_EVENT.wait()
        while True:
            job_id: str | None = None
            with QUEUE_LOCK:
                if JOB_QUEUE:
                    job_id = JOB_QUEUE.pop(0)
                else:
                    QUEUE_EVENT.clear()
                    break
            if job_id:
                run_job(job_id)


def create_job(
    url: str,
    output_dir: str = "",
    skip_video: bool = False,
    extract_keyframes: bool = True,
    scene_threshold: float = 0.04,
    min_interval: float = 10.0,
) -> dict:
    job_id = uuid.uuid4().hex[:8]
    job = {
        "id": job_id,
        "url": url,
        "output_dir": output_dir or str(DEFAULT_OUTPUT_DIR),
        "skip_video": skip_video,
        "extract_keyframes": extract_keyframes,
        "scene_threshold": scene_threshold,
        "min_interval": min_interval,
        "status": "queued",
        "created_at": now_ts(),
        "started_at": None,
        "finished_at": None,
        "logs": [],
        "result": {},
        "job_dir": None,
        "returncode": None,
        "has_warnings": False,
        "saw_done": False,
        "last_log_at": None,
    }
    with JOBS_LOCK:
        JOBS[job_id] = job
    with QUEUE_LOCK:
        JOB_QUEUE.append(job_id)
    QUEUE_EVENT.set()
    return job


def append_log(job: dict, line: str) -> None:
    with JOBS_LOCK:
        job["logs"].append(line.rstrip("\n"))
        job["logs"] = job["logs"][-3000:]
        job["last_log_at"] = now_ts()


def update_result_from_line(job: dict, line: str) -> None:
    mappings = {
        "Job directory: ": "job_dir",
        "Video: ": "video",
        "English subtitles: ": "english_subtitles",
        "Chinese subtitles: ": "chinese_subtitles",
        "Canonical English subtitles: ": "canonical_english_subtitles",
        "Canonical AI Chinese subtitles: ": "canonical_ai_chinese_subtitles",
        "Outline: ": "outline",
        "Keyframes: ": "keyframes",
    }
    for prefix, key in mappings.items():
        if line.startswith(prefix):
            value = line[len(prefix):].strip()
            with JOBS_LOCK:
                if key == "job_dir":
                    job["job_dir"] = value
                else:
                    job["result"][key] = value
            return

    warning_markers = [
        "AI polishing failed; falling back",
        "Fallback Google translation hit an SSL certificate issue",
        "Warning:",
        "ERROR: ",
        "RuntimeError:",
        "Traceback (most recent call last):",
    ]
    if line == "Done":
        with JOBS_LOCK:
            job["saw_done"] = True
        return
    if any(marker in line for marker in warning_markers):
        with JOBS_LOCK:
            job["has_warnings"] = True


def run_job(job_id: str) -> None:
    with JOBS_LOCK:
        job = JOBS[job_id]
        job["status"] = "running"
        job["started_at"] = now_ts()

    output_dir = job.get("output_dir") or str(DEFAULT_OUTPUT_DIR)
    command = [str(PYTHON_EXE), str(CLI_SCRIPT), job["url"], "--output-dir", output_dir]
    if job.get("skip_video"):
        command.append("--skip-video")
    if not job.get("extract_keyframes", True):
        command.append("--no-extract-keyframes")
    else:
        command.extend(["--scene-threshold", str(job.get("scene_threshold", 0.04))])
        command.extend(["--min-interval", str(job.get("min_interval", 10.0))])

    try:
        process = subprocess.Popen(
            command,
            cwd=str(WORKDIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            append_log(job, line)
            update_result_from_line(job, line.strip())
        returncode = process.wait()
    except Exception as exc:
        append_log(job, f"Web runner error: {exc}")
        returncode = 1

    with JOBS_LOCK:
        job["returncode"] = returncode
        job["finished_at"] = now_ts()
        if returncode == 0:
            job["status"] = "completed_with_warnings" if job.get("has_warnings") else "completed"
        else:
            job["status"] = "failed"
        enrich_job_files(job)


def enrich_job_files(job: dict) -> None:
    job_dir = job.get("job_dir")
    if not job_dir:
        return
    path = Path(job_dir)
    if not path.exists() or not path.is_dir():
        return

    files = []
    for child in sorted(path.iterdir()):
        if child.is_file():
            files.append({"name": child.name, "size": child.stat().st_size, "path": str(child)})

    featured = []
    video = next((item for item in files if item["name"].lower().endswith(".mp4")), None)
    zh_ai = next((item for item in files if item["name"] == "subtitles.zh.ai.srt"), None)
    outline = next((item for item in files if item["name"] == "outline.zh.md"), None)
    for item in (video, zh_ai, outline):
        if item is not None:
            featured.append(item)

    kf_dir = path / "keyframes"
    kf_thumbnails: list[dict] = []
    if kf_dir.exists():
        kf_jpgs = sorted(kf_dir.glob("*.jpg"), key=lambda p: p.name)
        kf_thumbnails = [{"name": f.name, "path": str(f), "size": f.stat().st_size} for f in kf_jpgs]
        ts_file = kf_dir / "timestamps.txt"
        if ts_file.exists():
            featured.append({"name": "keyframes/timestamps.txt", "size": ts_file.stat().st_size, "path": str(ts_file)})

    job["result"]["files"] = files
    job["result"]["featured_files"] = featured
    job["result"]["keyframe_thumbnails"] = kf_thumbnails
    job["result"]["keyframes_count"] = len(kf_thumbnails)


def get_job(job_id: str) -> dict | None:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job is None:
            return None
        return json.loads(json.dumps(job, ensure_ascii=False))


def list_jobs() -> list[dict]:
    with JOBS_LOCK:
        values = list(JOBS.values())
    with QUEUE_LOCK:
        queue_positions = {jid: i + 1 for i, jid in enumerate(JOB_QUEUE)}
    values.sort(key=lambda item: item["created_at"], reverse=True)
    return [
        {
            "id": item["id"],
            "url": item["url"],
            "status": item["status"],
            "created_at": item["created_at"],
            "job_dir": item["job_dir"],
            "started_at": item["started_at"],
            "finished_at": item["finished_at"],
            "queue_position": queue_positions.get(item["id"]),
        }
        for item in values
    ]


def is_allowed_file(path: Path) -> bool:
    try:
        resolved = path.resolve()
    except (FileNotFoundError, OSError):
        return False
    allowed_roots = [WORKDIR.resolve(), DEFAULT_OUTPUT_DIR.resolve()]
    with JOBS_LOCK:
        for job in JOBS.values():
            for field in ("output_dir", "job_dir"):
                val = job.get(field)
                if val:
                    try:
                        allowed_roots.append(Path(val).resolve())
                    except (ValueError, OSError):
                        pass
    return any(str(resolved).startswith(str(root)) for root in allowed_roots)


def open_directory(path_text: str) -> None:
    path = Path(path_text)
    if path.exists():
        os.startfile(str(path))  # type: ignore[attr-defined]


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            self.respond_html(INDEX_HTML)
            return
        if parsed.path == "/api/jobs":
            self.respond_json({"jobs": list_jobs()})
            return
        if parsed.path.startswith("/api/jobs/"):
            job_id = parsed.path.rsplit("/", 1)[-1]
            job = get_job(job_id)
            if job is None:
                self.respond_json({"error": "Job not found"}, status=HTTPStatus.NOT_FOUND)
                return
            self.respond_json(job)
            return
        if parsed.path == "/file":
            params = urllib.parse.parse_qs(parsed.query)
            target = params.get("path", [""])[0]
            self.serve_file(target)
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/jobs":
            payload = self.read_json()
            url = str(payload.get("url", "")).strip()
            if not url:
                self.respond_json({"error": "Missing url"}, status=HTTPStatus.BAD_REQUEST)
                return
            output_dir = str(payload.get("output_dir", "")).strip()
            skip_video = bool(payload.get("skip_video", False))
            extract_keyframes = bool(payload.get("extract_keyframes", True))
            scene_threshold = float(payload.get("scene_threshold", 0.04))
            min_interval = float(payload.get("min_interval", 10.0))
            job = create_job(
                url,
                output_dir=output_dir,
                skip_video=skip_video,
                extract_keyframes=extract_keyframes,
                scene_threshold=scene_threshold,
                min_interval=min_interval,
            )
            self.respond_json({"id": job["id"], "status": job["status"]}, status=HTTPStatus.CREATED)
            return
        if parsed.path.startswith("/api/jobs/") and parsed.path.endswith("/open-dir"):
            job_id = parsed.path.split("/")[-2]
            job = get_job(job_id)
            if job is None or not job.get("job_dir"):
                self.respond_json({"error": "Job directory not available"}, status=HTTPStatus.NOT_FOUND)
                return
            open_directory(job["job_dir"])
            self.respond_json({"ok": True})
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args) -> None:
        return

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    def respond_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def respond_html(self, html: str) -> None:
        data = html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def serve_file(self, target: str) -> None:
        if not target:
            self.send_error(HTTPStatus.BAD_REQUEST)
            return
        path = Path(target)
        if not path.exists() or not path.is_file() or not is_allowed_file(path):
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        suffix = path.suffix.lower()
        content_type = "application/octet-stream"
        if suffix in {".md", ".txt", ".json", ".srt", ".vtt"}:
            content_type = "text/plain; charset=utf-8"
        elif suffix == ".mp4":
            content_type = "video/mp4"
        elif suffix in {".jpg", ".jpeg"}:
            content_type = "image/jpeg"

        file_size = path.stat().st_size
        range_header = self.headers.get("Range")

        if range_header:
            match = re.match(r"bytes=(\d+)-(\d*)", range_header)
            if match:
                start = int(match.group(1))
                end = int(match.group(2)) if match.group(2) else file_size - 1
                end = min(end, file_size - 1)
                if start > end or start >= file_size:
                    self.send_error(416)
                    return
                length = end - start + 1
                self.send_response(206)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
                self.send_header("Content-Length", str(length))
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Disposition", f'inline; filename="{path.name}"')
                self.end_headers()
                with open(path, "rb") as f:
                    f.seek(start)
                    remaining = length
                    while remaining > 0:
                        chunk = f.read(min(65536, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
                return

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(file_size))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Disposition", f'inline; filename="{path.name}"')
        self.end_headers()
        with open(path, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                self.wfile.write(chunk)


INDEX_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>YouTube Briefing</title>
  <style>
    :root {
      --bg: #f4efe8;
      --panel: rgba(255, 249, 241, 0.94);
      --ink: #172126;
      --muted: #5e6b73;
      --line: #d6c7b4;
      --accent: #b24a2a;
      --accent2: #1b6b72;
      --ok: #dcefd9;
      --warn: #fde9b8;
      --fail: #f6c8c0;
      --info: #cce4f5;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Segoe UI", "PingFang SC", sans-serif;
      background:
        radial-gradient(circle at top left, #f7d9b8 0, transparent 28%),
        radial-gradient(circle at bottom right, #d8efe6 0, transparent 24%),
        var(--bg);
      color: var(--ink);
    }
    .wrap { max-width: 1240px; margin: 0 auto; padding: 28px; }
    .hero { display: grid; grid-template-columns: 1.4fr 1fr; gap: 20px; margin-bottom: 20px; }
    .grid { display: grid; grid-template-columns: 320px 1fr; gap: 20px; }
    .card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 20px;
      box-shadow: 0 8px 24px rgba(50, 32, 18, 0.08);
      backdrop-filter: blur(6px);
    }
    h1 { margin: 0 0 8px; font-size: 32px; }
    h3 { margin: 18px 0 10px; font-size: 15px; }
    p { color: var(--muted); line-height: 1.65; margin: 0 0 12px; font-size: 14px; }
    .toolbar { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 12px; }
    input[type="text"], input[type="number"] {
      padding: 9px 13px;
      border-radius: 10px;
      border: 1px solid var(--line);
      background: #fffdf9;
      font-size: 14px;
      color: var(--ink);
    }
    input[type="text"]:focus, input[type="number"]:focus {
      outline: none;
      border-color: var(--accent2);
    }
    .url-row { display: flex; gap: 8px; margin-bottom: 10px; }
    .url-row input[type="text"] { flex: 1; padding: 13px 15px; font-size: 15px; border-radius: 12px; }
    .outdir-row { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; }
    .outdir-row label { color: var(--muted); font-size: 13px; white-space: nowrap; }
    .outdir-row input[type="text"] { flex: 1; font-size: 13px; }
    .opts-row { display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 10px; align-items: center; }
    .kf-panel {
      margin-top: 8px;
      padding: 12px 14px;
      background: rgba(0,0,0,0.03);
      border-radius: 10px;
      border: 1px solid var(--line);
      display: flex;
      flex-wrap: wrap;
      gap: 14px;
      align-items: center;
    }
    .kf-panel label { color: var(--muted); font-size: 13px; display: flex; align-items: center; gap: 6px; }
    .kf-panel input[type="number"] { width: 72px; }
    .kf-panel .hint { font-size: 11px; color: #999; }
    .chk-label { display: flex; align-items: center; gap: 7px; cursor: pointer; color: var(--muted); font-size: 14px; }
    .chk-label input[type="checkbox"] { width: 16px; height: 16px; cursor: pointer; }
    button {
      border: 0;
      border-radius: 12px;
      padding: 11px 20px;
      background: var(--accent);
      color: white;
      font-weight: 600;
      cursor: pointer;
      white-space: nowrap;
      font-size: 14px;
    }
    button.secondary { background: var(--accent2); }
    button:disabled { opacity: 0.45; cursor: default; }
    .jobs { max-height: 72vh; overflow: auto; }
    .job {
      padding: 11px 13px;
      border-radius: 12px;
      border: 1px solid var(--line);
      background: #fffdf9;
      margin-bottom: 8px;
      cursor: pointer;
      transition: background 0.15s;
    }
    .job:hover { background: #fff7ee; }
    .job.active { border-color: var(--accent); background: #fff1e8; }
    .job-url { font-weight: 600; word-break: break-word; line-height: 1.4; font-size: 13px; }
    .job-meta { display: flex; gap: 8px; align-items: center; margin-top: 6px; flex-wrap: wrap; }
    .status {
      display: inline-block;
      padding: 3px 9px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 500;
      background: #efe3d6;
      color: var(--ink);
    }
    .status.completed { background: var(--ok); }
    .status.completed_with_warnings { background: var(--warn); }
    .status.failed { background: var(--fail); color: #7a1010; }
    .status.running { background: var(--info); }
    .mono {
      font-family: Consolas, "Courier New", monospace;
      font-size: 13px;
      white-space: pre-wrap;
      background: #161b22;
      color: #e6edf3;
      border-radius: 14px;
      padding: 16px;
      min-height: 300px;
      max-height: 440px;
      overflow: auto;
    }
    .files a {
      display: block;
      color: var(--accent2);
      text-decoration: none;
      margin-bottom: 8px;
      line-height: 1.4;
      font-size: 14px;
    }
    .files a strong { color: var(--ink); }
    .muted { color: var(--muted); font-size: 14px; }
    .info-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .info-box {
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 12px 14px;
      background: #fffdf9;
      font-size: 13px;
      line-height: 1.75;
      color: var(--muted);
    }
    .info-box strong { color: var(--ink); display: block; margin-bottom: 4px; }
    .kf-gallery {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
      gap: 6px;
      margin-bottom: 4px;
    }
    .kf-gallery a img {
      width: 100%;
      border-radius: 8px;
      border: 1px solid var(--line);
      display: block;
      background: #111;
    }
    @media (max-width: 980px) {
      .hero, .grid, .info-grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="hero">
      <div class="card">
        <h1>YouTube Briefing</h1>
        <p>输入 YouTube 链接，自动生成视频、AI 中文字幕、中文大纲和关键帧截图。多任务加入队列依次执行。</p>

        <div class="url-row">
          <input id="urlInput" type="text" placeholder="https://www.youtube.com/watch?v=..." />
          <button id="startBtn">加入队列</button>
        </div>

        <div class="outdir-row">
          <label for="outputDirInput">输出目录：</label>
          <input id="outputDirInput" type="text" value="D:\\YouTubeBriefings" placeholder="D:\\YouTubeBriefings" />
        </div>

        <div class="opts-row">
          <label class="chk-label">
            <input type="checkbox" id="skipVideoChk">
            跳过视频下载（仅字幕和大纲）
          </label>
        </div>

        <div class="kf-panel" id="kfPanel">
          <label class="chk-label" style="margin-right:2px">
            <input type="checkbox" id="extractKfChk" checked>
            提取关键帧
          </label>
          <label>
            场景阈值
            <input type="number" id="sceneThresholdInput" value="0.04" min="0.01" max="1.0" step="0.01">
            <span class="hint">越小帧越多</span>
          </label>
          <label>
            最小间隔
            <input type="number" id="minIntervalInput" value="10" min="1" max="300" step="1">
            <span class="hint">秒，默认 10</span>
          </label>
        </div>
      </div>

      <div class="card">
        <div class="info-grid">
          <div class="info-box">
            <strong>核心产物</strong>
            <div>· 视频（best MP4）</div>
            <div>· 英文原始字幕</div>
            <div>· AI 中文字幕</div>
            <div>· 中文大纲</div>
            <div>· 关键帧截图</div>
          </div>
          <div class="info-box">
            <strong>队列规则</strong>
            <div>· 多任务依次执行</div>
            <div>· 等待时显示 #N</div>
            <div>· 提交后自动跳转</div>
            <div>· 每 2 秒自动刷新</div>
          </div>
        </div>
      </div>
    </div>

    <div class="grid">
      <div class="card jobs">
        <div class="toolbar">
          <button class="secondary" id="refreshJobsBtn">刷新任务</button>
        </div>
        <div id="jobList"></div>
      </div>
      <div class="card">
        <div class="toolbar">
          <button class="secondary" id="openDirBtn" disabled>打开目录</button>
        </div>
        <div id="jobMeta" class="muted">还没有选择任务。</div>
        <h3>核心结果</h3>
        <div id="featuredFileList" class="files muted">完成后会优先显示视频、AI 中文字幕和中文大纲。</div>
        <h3>关键帧 <span id="kfCountLabel" class="muted"></span></h3>
        <div id="kfGallery" class="muted">完成后显示关键帧缩略图。</div>
        <h3>实时日志</h3>
        <div id="logBox" class="mono"></div>
        <h3>全部输出</h3>
        <div id="fileList" class="files muted">完成后会显示全部文件链接。</div>
      </div>
    </div>
  </div>

  <script>
    let selectedJobId = null;
    let pollTimer = null;

    async function fetchJson(url, options) {
      const res = await fetch(url, options);
      return await res.json();
    }

    function formatStatus(status, queuePosition) {
      if (status === 'completed_with_warnings') return '已完成（有降级）';
      if (status === 'completed') return '已完成';
      if (status === 'failed') return '失败';
      if (status === 'running') return '运行中';
      if (status === 'queued') return queuePosition ? `排队中 #${queuePosition}` : '排队中';
      return status;
    }

    function formatTime(ts) {
      if (!ts) return '未开始';
      return new Date(ts * 1000).toLocaleString();
    }

    function formatDuration(startedAt, finishedAt, status) {
      if (!startedAt) return '未开始';
      const end = finishedAt || (status === 'running' ? Date.now() / 1000 : startedAt);
      const seconds = Math.max(0, Math.round(end - startedAt));
      const mins = Math.floor(seconds / 60);
      const secs = seconds % 60;
      return `${mins}分 ${secs}秒`;
    }

    function formatSize(size) {
      if (size > 1024 * 1024 * 1024) return (size / (1024 * 1024 * 1024)).toFixed(2) + ' GB';
      if (size > 1024 * 1024) return (size / (1024 * 1024)).toFixed(2) + ' MB';
      if (size > 1024) return (size / 1024).toFixed(2) + ' KB';
      return size + ' B';
    }

    async function loadJobs() {
      const data = await fetchJson('/api/jobs');
      const list = document.getElementById('jobList');
      list.innerHTML = '';
      for (const job of data.jobs) {
        const el = document.createElement('div');
        el.className = 'job' + (job.id === selectedJobId ? ' active' : '');
        const statusText = formatStatus(job.status, job.queue_position);
        el.innerHTML = `
          <div class="job-url">${job.url}</div>
          <div class="job-meta">
            <span class="status ${job.status}">${statusText}</span>
            <span class="muted" style="font-size:11px">${job.id}</span>
          </div>
        `;
        el.onclick = () => selectJob(job.id);
        list.appendChild(el);
      }
    }

    async function selectJob(jobId) {
      selectedJobId = jobId;
      await loadJobs();
      await loadJobDetail();
      if (pollTimer) clearInterval(pollTimer);
      pollTimer = setInterval(async () => { await loadJobs(); await loadJobDetail(); }, 2000);
    }

    async function loadJobDetail() {
      if (!selectedJobId) return;
      const job = await fetchJson(`/api/jobs/${selectedJobId}`);
      const outputPath = job.job_dir || job.output_dir || '尚未生成';
      document.getElementById('jobMeta').innerHTML = `
        <div><strong>状态：</strong>${formatStatus(job.status, null)}</div>
        <div><strong>链接：</strong><span style="word-break:break-all">${job.url}</span></div>
        <div><strong>输出目录：</strong>${outputPath}</div>
        <div><strong>关键帧参数：</strong>阈值 ${job.scene_threshold || 0.04}，间隔 ${job.min_interval || 10} 秒</div>
        <div><strong>开始时间：</strong>${formatTime(job.started_at)}</div>
        <div><strong>结束时间：</strong>${formatTime(job.finished_at)}</div>
        <div><strong>耗时：</strong>${formatDuration(job.started_at, job.finished_at, job.status)}</div>
      `;

      const openBtn = document.getElementById('openDirBtn');
      openBtn.disabled = !job.job_dir;
      openBtn.onclick = async () => {
        await fetch(`/api/jobs/${selectedJobId}/open-dir`, { method: 'POST' });
      };

      const logBox = document.getElementById('logBox');
      const wasAtBottom = logBox.scrollTop + logBox.clientHeight >= logBox.scrollHeight - 20;
      logBox.textContent = (job.logs || []).join('\\n');
      if (wasAtBottom) logBox.scrollTop = logBox.scrollHeight;

      const featuredFileList = document.getElementById('featuredFileList');
      const fileList = document.getElementById('fileList');
      const featuredFiles = (job.result && job.result.featured_files) || [];
      const files = (job.result && job.result.files) || [];

      if (!featuredFiles.length) {
        featuredFileList.textContent =
          job.status === 'completed' || job.status === 'completed_with_warnings'
            ? '没有识别到核心结果文件。'
            : '完成后会优先显示视频、AI 中文字幕和中文大纲。';
      } else {
        featuredFileList.innerHTML = featuredFiles.map(file => {
          const href = '/file?path=' + encodeURIComponent(file.path);
          return `<a href="${href}" target="_blank"><strong>${file.name}</strong> <span class="muted">(${formatSize(file.size)})</span></a>`;
        }).join('');
      }

      const kfThumbs = (job.result && job.result.keyframe_thumbnails) || [];
      const kfCount = (job.result && job.result.keyframes_count) || 0;
      const kfGallery = document.getElementById('kfGallery');
      const kfCountLabel = document.getElementById('kfCountLabel');
      if (kfThumbs.length) {
        kfCountLabel.textContent = `(${kfCount} 帧)`;
        kfGallery.className = 'kf-gallery';
        kfGallery.innerHTML = kfThumbs.map(frame => {
          const href = '/file?path=' + encodeURIComponent(frame.path);
          return `<a href="${href}" target="_blank"><img src="${href}" loading="lazy" title="${frame.name}"></a>`;
        }).join('');
      } else {
        kfCountLabel.textContent = '';
        kfGallery.className = 'muted';
        kfGallery.textContent =
          job.status === 'completed' || job.status === 'completed_with_warnings'
            ? '没有关键帧（跳过或 ffmpeg 不可用）。'
            : '完成后显示关键帧缩略图。';
      }

      if (!files.length) {
        fileList.textContent =
          job.status === 'completed' || job.status === 'completed_with_warnings'
            ? '没有发现文件。'
            : '完成后会显示全部文件链接。';
      } else {
        fileList.innerHTML = files.map(file => {
          const href = '/file?path=' + encodeURIComponent(file.path);
          return `<a href="${href}" target="_blank">${file.name} <span class="muted">(${formatSize(file.size)})</span></a>`;
        }).join('');
      }

      if (job.status !== 'running' && job.status !== 'queued' && pollTimer) {
        clearInterval(pollTimer);
        pollTimer = null;
      }
    }

    // Keyframe option interactions
    function syncKfPanelState() {
      const skipVideo = document.getElementById('skipVideoChk').checked;
      const extractKf = document.getElementById('extractKfChk');
      const kfPanel = document.getElementById('kfPanel');
      const threshInput = document.getElementById('sceneThresholdInput');
      const intervalInput = document.getElementById('minIntervalInput');
      if (skipVideo) {
        extractKf.checked = false;
        extractKf.disabled = true;
        threshInput.disabled = true;
        intervalInput.disabled = true;
        kfPanel.style.opacity = '0.4';
      } else {
        extractKf.disabled = false;
        const kfEnabled = extractKf.checked;
        threshInput.disabled = !kfEnabled;
        intervalInput.disabled = !kfEnabled;
        kfPanel.style.opacity = kfEnabled ? '1' : '0.6';
      }
    }

    document.getElementById('skipVideoChk').onchange = syncKfPanelState;
    document.getElementById('extractKfChk').onchange = syncKfPanelState;

    document.getElementById('startBtn').onclick = async () => {
      const url = document.getElementById('urlInput').value.trim();
      if (!url) return;
      const outputDir = document.getElementById('outputDirInput').value.trim();
      const skipVideo = document.getElementById('skipVideoChk').checked;
      const extractKf = document.getElementById('extractKfChk').checked;
      const sceneThreshold = parseFloat(document.getElementById('sceneThresholdInput').value) || 0.04;
      const minInterval = parseFloat(document.getElementById('minIntervalInput').value) || 10.0;
      const result = await fetchJson('/api/jobs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url,
          output_dir: outputDir,
          skip_video: skipVideo,
          extract_keyframes: extractKf,
          scene_threshold: sceneThreshold,
          min_interval: minInterval,
        })
      });
      if (result.id) {
        document.getElementById('urlInput').value = '';
        await selectJob(result.id);
      }
    };

    document.getElementById('urlInput').addEventListener('keydown', e => {
      if (e.key === 'Enter') document.getElementById('startBtn').click();
    });

    document.getElementById('refreshJobsBtn').onclick = loadJobs;
    loadJobs();
  </script>
</body>
</html>
"""


threading.Thread(target=queue_worker, daemon=True).start()


def main() -> int:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"YouTube Briefing UI running at http://{HOST}:{PORT}")
    threading.Timer(0.8, lambda: webbrowser.open(f"http://{HOST}:{PORT}")).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
