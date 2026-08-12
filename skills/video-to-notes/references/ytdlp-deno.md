# yt-dlp + deno (JS runtime) 排错

YouTube 现在对 dash 流(720p 及以上)强制 EJS challenge solving, 必须有 JS runtime 配合 yt-dlp。**如果跳过这一步, 720p 下载会无声卡死**(yt-dlp 进程活着, 只占 4-5MB working set, 但永远不写文件)。

## 症状速查

| 症状 | 原因 |
|---|---|
| `[download] Destination: xxx.mp4` 出现后无进度 | 没 JS runtime 解 EJS, 卡在 challenge |
| `WARNING: [youtube] [pot] PO Token Providers: none` | 同上, 信号 |
| `WARNING: [jsc] Remote component challenge solver script (node) was skipped` | 没装 challenge solver, 加 `--remote-components ejs:github` |
| 下载是 `format 18 (360p)` 单文件, 不需要 deno | legacy 格式不走 dash, 但分辨率不够看 slide |

## 正确的 JS runtime: deno

yt-dlp 默认 enabled 的 JS runtime 是 **deno**。Node.js **目前不行**(2026.06 nightly 测试) — Node 跑会出 "Remote component challenge solver script (node) was skipped"。

### 自动检查 + 安装

`scripts/ensure_deno.py` 做这件事:
1. 看 PATH 里有没有 `deno`
2. 看 `./bin/deno.exe` 在不在
3. 都没的话从 GitHub 拉 release zip 解到 `./bin/deno.exe`(不需要管理员权限)

手动版:
```powershell
$tools = './bin'
New-Item -ItemType Directory $tools -Force | Out-Null
$url = 'https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip'
Invoke-WebRequest -Uri $url -OutFile "$tools/deno.zip" -UseBasicParsing
Expand-Archive "$tools/deno.zip" -DestinationPath $tools -Force
Remove-Item "$tools/deno.zip"
& "$tools/deno.exe" --version
```

### 跑 yt-dlp 时指定

```bash
yt-dlp --js-runtimes "deno:./bin/deno.exe" -f 298 ...
```

如果 deno 在 PATH, 简化为 `--js-runtimes deno`。

## 升级 yt-dlp

老版本(2026.03 之前)没 EJS 支持, **升级到 nightly**:

```bash
# 用 yt-dlp 当初安装时用的那个 python(可能不是 PATH 里的默认 pip)
& "C:\Users\banqiang\AppData\Local\Programs\Python\Python313\python.exe" -m pip install --upgrade --pre yt-dlp
```

## 不要踩的坑

### 1. `--download-sections` 切片下载

会强制走 ffmpeg HLS streaming, **慢得离谱**(实测 18min 切片跑 5 分钟没动)。改成"完整下载 + 本地 ffmpeg 切片":

```bash
# 整段下
yt-dlp -f 298 -o full.mp4 "<url>"

# 本地秒切
ffmpeg -ss 00:04:30 -to 00:22:30 -i full.mp4 -c copy slice.mp4
```

### 2. format 18 (360p) 当备份方案

format 18 是 legacy 单文件 mp4, **不走 dash, 不需要 deno**, 230MB 整段 1.5h。看起来是个"备胎方案"。

但是 **360p slide 文字不可读** — benchmark 表数值、代码截图全模糊。这次实测后否决了。仅在你完全没法搞定 deno 时降级用, 且接受 OCR-style 信息从字幕回填。

### 3. 不要单独下音频

写作流程基于字幕, **不需要音频**, 别下 m4a。format 298 是 video-only。

### 4. JS runtime 警告 vs 错误

```
WARNING: [youtube] [jsc] Remote component challenge solver script (node) was skipped.
You can enable the download with --remote-components ejs:github (recommended).
```

加 `--remote-components ejs:github` 才会从 GitHub 拉 challenge solver script。但实测 **deno 默认就拉**, 不需要这个 flag(node 才需要)。

## Google CDN 坏边缘 host 处理

**症状**: yt-dlp 下载卡在某个特定 googlevideo host 反复 30s timeout, 例如:

```
[download] Got error: Connection to rr1---sn-ojnpo5-c3.googlevideo.com timed out (connect timeout=30.0)
```

原因: YouTube URL 签名把请求分配到一个从当前网络不可达的 edge server. `--force-ipv4` / `--extractor-args player_client=...` / `--external-downloader aria2c` **都不解决**, 因为 yt-dlp 内部无论走哪层, URL 里 embed 的 host 仍然是那个坏的.

**关键观察**: YouTube 每次调 `-g`(get URL) 会重新分配 edge, 有时候好有时候坏, 就是随机的.

### 正确的重试模式

预解析 URL, 检查 host, 坏就 retry, 好就立刻 curl -L 拉(避免二次分配):

```python
BAD_HOSTS = {"rr1---sn-ojnpo5-c3.googlevideo.com"}  # 累积踩过的坏 host

for attempt in range(1, 8):
    r = subprocess.run(["yt-dlp", "-f", "137/299/298", "-g", YT_URL],
                       capture_output=True, text=True)
    url = r.stdout.strip().splitlines()[-1]
    host = re.match(r"https?://([^/]+)/", url).group(1)
    if host in BAD_HOSTS:
        time.sleep(3); continue
    # 好 host — 立刻 curl -L 拉(必须 -L 跟随 302)
    subprocess.run(["curl", "-sSL", "--connect-timeout", "20",
                    "--max-time", "1200", "-o", str(OUT), url])
    if OUT.exists() and OUT.stat().st_size > 50*1024*1024:
        break
```

关键点:
- `curl -L` 必须, 不加会跟 302 redirect 失败, 文件 0 字节但 rc=0(假成功)
- `subprocess.run` 各种 yt-dlp 的 `--socket-timeout` / `--retries` 对同一坏 host 只是重复失败, 无意义 — 换 URL 才有效
- 累积一个 BAD_HOSTS 集合, 遇到就跳过重来. `sn-ojnpo5-c3` 是 2026-08 观察到的持续坏 host, 你可能会遇到别的

历史数据点(Witcher 4 Streaming 视频): 第 1-6 次尝试全撞 sn-ojnpo5-c3, 第 7 次拿到 sn-npoldne7 立刻成功, 98MB 视频下完.

