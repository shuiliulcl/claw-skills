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


def now_ts() -> float:
    return time.time()


def create_job(url: str, skip_video: bool = False) -> dict:
    job_id = uuid.uuid4().hex[:8]
    job = {
        "id": job_id,
        "url": url,
        "skip_video": skip_video,
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
    threading.Thread(target=run_job, args=(job_id,), daemon=True).start()
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

    command = [str(PYTHON_EXE), str(CLI_SCRIPT), job["url"]]
    if job.get("skip_video"):
        command.append("--skip-video")
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
            files.append(
                {
                    "name": child.name,
                    "size": child.stat().st_size,
                    "path": str(child),
                }
            )

    featured = []
    video = next((item for item in files if item["name"].lower().endswith(".mp4")), None)
    zh_ai = next((item for item in files if item["name"] == "subtitles.zh.ai.srt"), None)
    outline = next((item for item in files if item["name"] == "outline.zh.md"), None)
    for item in (video, zh_ai, outline):
        if item is not None:
            featured.append(item)

    job["result"]["files"] = files
    job["result"]["featured_files"] = featured


def get_job(job_id: str) -> dict | None:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job is None:
            return None
        return json.loads(json.dumps(job, ensure_ascii=False))


def list_jobs() -> list[dict]:
    with JOBS_LOCK:
        values = list(JOBS.values())
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
        }
        for item in values
    ]


def is_allowed_file(path: Path) -> bool:
    try:
        resolved = path.resolve()
    except FileNotFoundError:
        return False
    allowed_roots = [DEFAULT_OUTPUT_DIR.resolve(), WORKDIR.resolve()]
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
            skip_video = bool(payload.get("skip_video", False))
            job = create_job(url, skip_video=skip_video)
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
      padding: 18px;
      box-shadow: 0 8px 24px rgba(50, 32, 18, 0.08);
      backdrop-filter: blur(6px);
    }
    h1 { margin: 0 0 10px; font-size: 34px; }
    h3 { margin: 18px 0 10px; font-size: 16px; }
    p { color: var(--muted); line-height: 1.65; margin: 0 0 12px; }
    .row, .toolbar { display: flex; gap: 10px; flex-wrap: wrap; }
    .toolbar { margin-bottom: 12px; }
    input[type="text"] {
      width: 100%;
      padding: 14px 16px;
      border-radius: 12px;
      border: 1px solid var(--line);
      background: #fffdf9;
      font-size: 15px;
    }
    button {
      border: 0;
      border-radius: 12px;
      padding: 12px 16px;
      background: var(--accent);
      color: white;
      font-weight: 600;
      cursor: pointer;
    }
    button.secondary { background: var(--accent2); }
    .jobs { max-height: 72vh; overflow: auto; }
    .job {
      padding: 12px;
      border-radius: 12px;
      border: 1px solid var(--line);
      background: #fffdf9;
      margin-bottom: 10px;
      cursor: pointer;
    }
    .job.active { border-color: var(--accent); background: #fff1e8; }
    .job-url { font-weight: 600; word-break: break-word; line-height: 1.4; }
    .status {
      display: inline-block;
      padding: 4px 8px;
      border-radius: 999px;
      font-size: 12px;
      background: #efe3d6;
      color: var(--ink);
      margin-top: 8px;
    }
    .status.completed { background: var(--ok); }
    .status.completed_with_warnings { background: var(--warn); }
    .status.failed { background: var(--fail); }
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
    }
    .files a strong { color: var(--ink); }
    .muted { color: var(--muted); }
    .kv { margin: 8px 0; line-height: 1.55; }
    .summary { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
    .mini {
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 12px;
      background: #fffdf9;
    }
    @media (max-width: 980px) {
      .hero, .grid, .summary { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="hero">
      <div class="card">
        <h1>YouTube Briefing</h1>
        <p>输入一个 YouTube 链接，自动生成高画质视频、英文原字幕、AI 中文字幕和中文大纲。页面会实时显示日志，完成后可以直接打开目录或点开核心结果文件。</p>
        <div class="row">
          <input id="urlInput" type="text" placeholder="https://www.youtube.com/watch?v=..." />
          <button id="startBtn">开始处理</button>
        </div>
        <div style="margin-top:10px">
          <label style="display:flex;align-items:center;gap:8px;cursor:pointer;color:var(--muted)">
            <input type="checkbox" id="skipVideoChk" style="width:16px;height:16px;cursor:pointer">
            仅字幕和大纲，跳过视频下载
          </label>
        </div>
      </div>
      <div class="card">
        <div class="summary">
          <div class="mini">
            <div><strong>输出目录</strong></div>
            <div class="muted">D:\\YouTubeBriefings</div>
          </div>
          <div class="mini">
            <div><strong>核心产物</strong></div>
            <div class="muted">视频、AI 中文字幕、中文大纲</div>
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

    function formatStatus(status) {
      if (status === 'completed_with_warnings') return '已完成（有降级）';
      if (status === 'completed') return '已完成';
      if (status === 'failed') return '失败';
      if (status === 'running') return '运行中';
      if (status === 'queued') return '排队中';
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
        el.innerHTML = `
          <div class="job-url">${job.url}</div>
          <div class="status ${job.status}">${formatStatus(job.status)}</div>
          <div class="muted">${job.id}</div>
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
      pollTimer = setInterval(loadJobDetail, 2000);
    }

    async function loadJobDetail() {
      if (!selectedJobId) return;
      const job = await fetchJson(`/api/jobs/${selectedJobId}`);
      document.getElementById('jobMeta').innerHTML = `
        <div><strong>任务状态：</strong>${formatStatus(job.status)}</div>
        <div><strong>视频链接：</strong>${job.url}</div>
        <div><strong>输出目录：</strong>${job.job_dir || '尚未生成'}</div>
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

    document.getElementById('startBtn').onclick = async () => {
      const url = document.getElementById('urlInput').value.trim();
      if (!url) return;
      const skipVideo = document.getElementById('skipVideoChk').checked;
      const result = await fetchJson('/api/jobs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url, skip_video: skipVideo })
      });
      if (result.id) {
        document.getElementById('urlInput').value = '';
        await selectJob(result.id);
      }
    };

    document.getElementById('refreshJobsBtn').onclick = loadJobs;
    loadJobs();
  </script>
</body>
</html>
"""


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
