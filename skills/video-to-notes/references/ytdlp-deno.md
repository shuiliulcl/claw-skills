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

## PO Token 缺失 + CDN 逐 URL 限流 (2026-09 起新增)

**症状** (与"坏边缘 host"不同):
- **host 每次都同一个** (比如 `sn-aj3pm5-55`) — 换攻击不了它,resilient 脚本救不了
- **`Range: bytes=0-1048576` (1MB) 能过 → 但立刻再来个 8MB Range 就 403**
- 完整 GET (无 Range) 直接 0 字节
- yt-dlp 报 "Downloading android vr player API JSON" 后 403,不管你 `player_client=` 传了啥

**根因链**:
1. YouTube 2024 底起对 >360p 强制 PO Token (真实浏览器 attest 签发)
2. yt-dlp 拿不到 PO Token → 服务器仍给可解析 format 列表 (骗 UI),但下载被 CDN 拒
3. 特殊 client (`mediaconnect` / `android_creator` / `android_music` / `tv_embedded` / `android_producer`) 走的 request path 不需要 PO Token,能拿到高清签名 URL
4. 但**这些 URL 分配到特殊 edge cluster**, 该集群对**未签发的 client**做 per-URL 快速限流:允许探测性 1-2 个小 Range 请求 (让浏览器 seek preview 能工作),不允许持续 bulk 下载

**判断三步走**:

```bash
# 1) 常规 client 只给 360p?
yt-dlp -F "<url>" | grep -E "1080|1440"  # 如果没 720p+,PO Token 已卡 → 试 mediaconnect
yt-dlp --extractor-args "youtube:player_client=mediaconnect" -F "<url>" | grep -E "1080"
# 通常 mediaconnect 会列出 1080p60 (299) / 1440p (400)

# 2) 尝试完整下 mediaconnect 高清 — 通常会 403
yt-dlp --js-runtimes "deno:./bin/deno.exe" \
    --extractor-args "youtube:player_client=mediaconnect" \
    -f 299 --output test.%(ext)s "<url>"

# 3) 如果 403,验证是不是 Range 限流 (而不是坏 host):
URL=$(yt-dlp --js-runtimes "./bin/deno.exe" --extractor-args "youtube:player_client=mediaconnect" -f 299 -g "<url>" | tail -1)
curl -H "Range: bytes=0-1048576" -sSL -o test1.mp4 "$URL"        # 1MB
curl -H "Range: bytes=1048577-9437184" -sSL -o test2.mp4 "$URL"  # 8MB
ls -la test*.mp4
# test1.mp4 是完整 1MB + test2.mp4 是 0 字节 → 就是 CDN 逐 URL 限流,不是坏 host
```

**唯一根治方案**: **浏览器 cookies.txt**
1. Chrome/Edge 商店装扩展 "Get cookies.txt LOCALLY" (不是"Get cookies.txt",后者旧且不维护)
2. 在浏览器登录 YouTube 后打开目标视频页
3. 扩展导出 `cookies.txt`
4. `yt-dlp --cookies cookies.txt -f 299 -o full_1080p_videoonly.mp4 "<url>"`

**为什么 `--cookies-from-browser` 不行**: Windows DPAPI 加密 cookies 数据库,yt-dlp 需要以当前登录 Windows 用户身份运行且 chrome 已退出。Claude Code 通常跑不了这条链路,报 "Failed to decrypt with DPAPI"。

**降级方案**: 接受 360p (`--extractor-args "youtube:player_client=android" -f "bv*"`)
- Slide 大字号纯文字演讲 (Unreal Fest / GDC 主舞台) 360p 完全可读
- UE 编辑器截图 / Blueprint 节点图 / benchmark 表数值 → 糊,靠文字段自足
- Writer prompt 应传入"视频只有 360p"约束,让 caption 保守化

**历史数据点** (Inside Unreal 2026-09-04, Christopher Ming Solo Blueprint 视频):
- 试了 8 种 player_client,只有 mediaconnect / android_creator / android_music / tv_embedded / android_producer 能列出 1080p60
- 每一次下载都 403,URL host 恒定 `sn-aj3pm5-55`
- Range=0-1M 稳过, Range 大块或全量恒 403
- 最终接受 360p (338MB),12/13 张 slide 图仍可读,3 张 UE 编辑器截图糊但 writer 已用文字步骤自足

