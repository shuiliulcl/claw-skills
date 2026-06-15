---
name: video-to-notes
description: 把英文视频(YouTube / tc-video.diezhi.net 内网 / 本地 mp4)整理成中文图文笔记, 可选发布到飞书 wiki。当用户说"把这个视频做成笔记""YouTube 视频整理""演讲转成中文文档""GDC video to notes""视频转飞书文档""Inside Unreal 整理""把这个 tc-video 整理"等, 或给出 YouTube URL / tc-video URL/ID / 本地视频路径想要图文笔记时使用。流程: 抽字幕 → 下视频(720p) → 场景检测抽帧 → Sonnet writer + reviewer → (可选)发布到飞书 wiki。tc-video 内网源走 [`tc-video`](../tc-video/SKILL.md) skill 下载后接入主流程。已经踩过的坑(yt-dlp dash + EJS / 飞书占位图陷阱 / 标题三处绑死 / writer 抄事实 / scene 检测对 UI 演示盲区导致章节漏图)在 references/ 下都有详细记录, 不要重新踩。
---

# Video → 中文图文笔记 工作流

把一个 60-100 分钟的英文技术演讲(YouTube / 内网 GDC / Inside Unreal 等)转成一份**高可读性、信息保留高、配图按需**的中文 Markdown 文档, 可选再发布到飞书 wiki 作为云文档。

核心理念: **主线程编排 + Sonnet 4.6 子 Agent 处理 token 大头**(写作 / reviewer)。Pro 用户全片成本约 200K Sonnet token, 折算 Opus ~40K, 远低于直接用 Opus 跑(150K Opus)。

## 先确认两件事

1. **输入是 YouTube URL 还是本地视频文件?**
   - YouTube: 走 yt-dlp 下载流程
   - 本地 mp4: 跳过下载, 直接进抽帧
2. **是否要发布到飞书 wiki?** 不发布就出 Markdown 即可

## Phase 0 · 工作目录

```
D:\Obsidian Vault\工具\video-notes\<slug>\
├── transcript.txt              # 清洁后的字幕全文
├── transcript_slice.txt        # (可选)切片字幕
├── full_720p_videoonly.mp4     # 视频源(YouTube 流程)
├── figures_full/
│   ├── timestamps.txt          # 场景检测时间戳
│   └── renamed/                # 按 HH:MM:SS 重命名的关键帧
├── notes_full.md               # 最终中文笔记
└── bin/
    └── deno.exe                # JS runtime (yt-dlp 必需)
```

`<slug>` 用视频内容关键词, 比如 `ue-projectiles` / `gdc-2025-rendering`。

## Phase 1 · 字幕优先(YouTube 流程)

字幕是结构骨架, 比视频先到。先扫字幕找章节锚点。

```bash
cd D:\Obsidian Vault\工具\video-notes\<slug>
yt-dlp --skip-download --write-auto-sub --sub-lang "en-orig" --sub-format vtt \
  --output "%(id)s.%(ext)s" "<youtube-url>"
```

如果 YouTube CC 不可用或质量差(内网视频通常都没字幕), 走 whisper.cpp 离线转写(本地 ggml-medium-q8_0 模型, ~500MB, 1-2× 实时)。

**清洗 VTT** — YouTube 自动字幕带每词时间戳和滚动重复, 必须去掉:

```bash
python scripts/clean_vtt.py <doc-id>.en-orig.vtt transcript.txt
```

清洗完用 grep 找方法/章节锚点, 比如:
```bash
grep -nE "method|first|second|next" transcript.txt | head -30
```

## Phase 2 · 下视频(YouTube 流程,踩坑最多)

> 详细排错见 [references/ytdlp-deno.md](references/ytdlp-deno.md), 直接命令如下:

**关键约束**: yt-dlp 下 720p dash 格式必须有 JS runtime 解 EJS 挑战, 默认 deno。如果没装:

```bash
python scripts/ensure_deno.py    # 探测 + 自动下载 deno binary 到 ./bin/deno.exe
```

下视频 — **不要用 `--download-sections` 切片**, 那会走 ffmpeg HLS 慢得离谱。直接整段下:

```bash
yt-dlp --js-runtimes "deno:./bin/deno.exe" \
  -f 299 \
  --output "full_1080p_videoonly.%(ext)s" \
  --no-progress -q --no-warnings \
  "<youtube-url>"
```

format 优先级: **299 (1080p60 mp4 dash) → 137 (1080p30 mp4 dash) → 298 (720p60 mp4 dash, 兜底)**。Inside Unreal 类视频通常只有 299 + 298, 没有 137。

**为什么默认 1080p**: 720p 下 Black Eye Panel 这种密集 UI 截图, knob 数值和小字基本模糊看不清; 1080p 下 panel 数值 (0.3 / 0.0 / 63.94 / 0.5) 清晰可读。文件代价: 1080p60 ~1.2GB / 1.5h, 720p60 ~650MB / 1.5h, 多 ~50%, 抽帧时间略增, 完全可控。飞书显示宽度仍是 720, 但**点击放大查看时**才显出分辨率优势。

format 298 (720p60) 仅在 1080p 不可用时降级使用。本地切片用 ffmpeg。**仅视频流, 不要音频**(写作不需要音频, 字幕已经覆盖)。

**1080p 下载偶发 HTTP 403**: YouTube 流签名时不时拒。直接重试 1-2 次基本就过, 不需要换 player_client (`--extractor-args "youtube:player_client=android"` 看不到 1080p)。

## Phase 1+2 替代路径 · tc-video.diezhi.net 内网源

如果输入是 **tc-video.diezhi.net URL 或裸 ID**(腾讯内网 UE/GDC 演讲库), 走 [`tc-video`](../tc-video/SKILL.md) skill 一次性下载, **完全绕过 yt-dlp / deno / clean_vtt 整套**。

前置: 浏览器登录 tc-video.diezhi.net 后, DevTools console 跑 `JSON.parse(localStorage.getItem('TC_VIDEO_TOKEN')).token` 拿 token, 写到 `~/.claude/skills/tc-video/tc_video.config.json`(token 30 天过期):

```json
{ "token": "eyJhbGci...", "base_dir": "D:/Obsidian Vault/工具/video-notes" }
```

下载:

```bash
python ~/.claude/skills/tc-video/tc_video_download.py 9048
# 或 https://tc-video.diezhi.net/video/9048
```

输出目录 `D:/Obsidian Vault/工具/video-notes/<title-slug> [tc<vid>]/`:
- `*.mp4` — 视频(已经是清流, 没有 dash/EJS 问题)
- `subtitles.en.raw.srt` — 英文字幕(SRT, 比 YouTube auto-CC 干净)
- `subtitles.zh.raw.vtt` — 中文字幕(可选用)
- `job.json` — 元数据(title / uploader / 年份)

**接入 video-to-notes 主流程**:

```bash
# 切到下载目录
cd "D:/Obsidian Vault/工具/video-notes/<title-slug> [tc<vid>]"

# 用 srt_to_txt 把英文 SRT 转成标准 transcript.txt
python C:/Users/banqiang/.claude/skills/video-to-notes/scripts/srt_to_txt.py \
  subtitles.en.raw.srt transcript.txt

# 重命名 mp4 为标准名
mv *.mp4 full_720p_videoonly.mp4   # 实际可能不止 720p, 名字仅为占位

# 直接进 Phase 3 (场景检测), Phase 1+2 都跳过
python C:/Users/banqiang/.claude/skills/video-to-notes/scripts/extract_keyframes.py \
  full_720p_videoonly.mp4 figures_full/
```

**为什么这条路径更省事**:
- 字幕服务端已经清洗过, SRT 不带每词时间戳和滚动重复, srt_to_txt.py 只做"合并多行 cue + 去连续重复"
- mp4 是直接流, 没有 dash + EJS, 不需要 deno
- 没有 yt-dlp 默认黑魔法(impersonation warning / format 协商)
- 通常带中文字幕, 后续有需要时用得上

**注意**:
- token 过期会 401, 重新拿
- tc-video 的 mp4 分辨率不一定是 720p, 实测可能是 1080p 或别的, 但跟我们流程兼容(场景检测和提帧都按视频实际分辨率走)
- 所有后续 phase(3 抽帧 / 4 writer / 5 reviewer / 6 飞书)**无需改动**

## Phase 3 · 场景检测抽关键帧

```bash
python scripts/extract_keyframes.py full_720p_videoonly.mp4 figures_full/
```

脚本内部:
1. ffmpeg `select='gt(scene,0.3)'` 检测 slide 切换
2. 5 秒窗口去重(剪掉 demo 镜头爆切簇)
3. **用亚秒精度时间戳**(浮点) 作 ffmpeg `-ss` 入参提帧 — 不要 int 截断, 0.5 秒偏移就会落到上一张 slide
4. 输出按绝对时间戳 `slide_HH-MM-SS.jpg` 命名

典型产出 25-30 张候选帧 / 1.5h 视频。

**已知盲区**: scene 检测对 UI/Panel 演示、同场景 demo 渐进切换抽不到 — 视频背景不变, 只有 panel 内 knob/slider 在动, 阈值打不出来。这种章节(专属界面 / 工具截图 / Sequencer / 节点编辑器演示)候选池可能为 0。**不在 Phase 3 一开始密抽**(每 60s 一张会让候选从 30 涨到 90, writer 看图成本翻 3 倍), 而是在 Phase 5 reviewer 扫描发现漏图后**定向补抽**。详见 [references/figure-coverage.md](references/figure-coverage.md)。

## Phase 4 · Sonnet writer 子 Agent

这是 token 大头(单次 ~110K-150K), 必须用 Sonnet 4.6 不要用 Opus(单价 5×, 质量差距对此任务可忽略)。

调用方式:

```python
Agent(
  description="Write Chinese teaching notes",
  model="sonnet",  # 不要省略 — 默认会用主线程模型(可能是 Opus)
  prompt=open("references/writer-agent-prompt.md").read().format(
    transcript_path=...,
    figures_dir=...,
    style_reference=...,  # 上次跑的笔记作风格基准, 第一次没有就传空
    output_path=...,
  )
)
```

完整 prompt 模板见 [references/writer-agent-prompt.md](references/writer-agent-prompt.md)。核心要求:
- 教学叙事(动机 → 思路 → 机制 → 取舍), 不按时间顺序流水账
- 中文为主, 技术术语保留英文
- 数字 / API 名 / 性能数据**全保留**
- 配图按"实质帮助"标准, 不凑数 — 子 Agent 会逐张 Read 看图判断
- 首次运行无风格基准时, 子 Agent 会按 prompt 默认风格出; 后续可把第一版作风格 reference 传入
- **风格基准只参考排版 / 措辞 / 章节组织, 事实(URL / 日期 / 时长 / 演讲者名 / 频道 / 数字)必须从本次 transcript 重新提取** — 历史踩坑: writer 抄 callout / blockquote 时把上一篇的 URL / 日期 / 演讲者名都抄过来了. prompt 模板里已经有专门警告块, 别删.

## Phase 5 · Reviewer pass

主线程做(便宜)。两件事必做:

### 5a. 文字事实抽查

抽 5-10 个具体技术点(数字 / 拼写易错的 API 名)在 transcript.txt 用 grep 反查, 找出 writer 漏掉的:

```bash
grep -nE "数字|API名|可疑拼写" transcript.txt
```

**重点核对 callout / blockquote** — 这两个区域最容易被 writer 从风格基准里抄错事实(URL / 日期 / 时长 / 人名). 即使 writer prompt 已经警告过, 主线程 reviewer 还是要扫一遍.

### 5b. 配图覆盖扫描(必做, 不要跳)

writer 选图凭"实质帮助"原则不会凑数, 但**它不知道候选池本身有缺**。专属 UI / Panel / 工具演示 / Sequencer / 节点编辑器 / 对话场景这种章节 scene 检测可能根本没抽到候选, writer 也就写完没图。**主线程必须扫一遍**:

```bash
# 列出所有 H2 章节及行号
grep -n "^## " notes_full.md
# 列出所有图片引用
grep -n "!\[" notes_full.md
# 对照: 哪些 H2 章节 0 张图? 是否本应有图?
```

判断"本应有图"的标准、定向补抽的具体命令、BlackEye 实际补图记录, 全在 [references/figure-coverage.md](references/figure-coverage.md)。

发现遗漏就用 Edit 修。一般文字补漏 2-5 处, 图片补抽 0-5 张。

## Phase 6 · (可选) 发布到飞书 wiki

> 完整流程 + 坑见 [references/feishu-publish.md](references/feishu-publish.md), 这里只列正确路径。

**双输出设计**: writer 出的 `notes_full.md` 是 **Obsidian 原稿**(带 frontmatter + `[[wikilinks]]`, 个人积累用)。发飞书前用 `to_feishu.py` 转换:

```bash
cd D:/Obsidian Vault/工具/video-notes/<slug>

# 转换: 剥 frontmatter + 把 [[slug/notes_full|Display]] 通过 registry 翻成 [Display](feishu_url)
python C:/Users/banqiang/.claude/skills/video-to-notes/scripts/to_feishu.py \
  notes_full.md notes_for_feishu.md
```

之后所有 lark-cli 命令用 `notes_for_feishu.md` 而不是 `notes_full.md`。

**前置: 维护 `D:/Obsidian Vault/工具/video-notes/registry.json`** — 这是 slug → 飞书 URL 的映射, 转换器需要它。新发一篇就往里加一条:

```json
{
  "<slug>": {
    "title": "...",
    "feishu_wiki": "https://papergames.feishu.cn/wiki/<token>",
    "publish_date": "...",
    "speaker": "...",
    ...
  }
}
```

发布完拿到飞书 wiki URL 后, 回填 `registry.json` 和**当前笔记 frontmatter 的 `feishu_wiki` 字段**。

**正确做法 = 不要走 import-then-replace, 走 import-then-insert**:

```bash
# 1. 解析目标 wiki 节点
lark-cli drive +inspect --url '<wiki-url>' --as user
# 拿到 obj_token + space_id + parent_node_token

# 2. 导入 markdown 为 docx (会创建 13 个"无法导入该图片"占位 — 没关系, 别管它们)
lark-cli drive +import --file ./notes_full.md --type docx \
  --name "<原视频英文标题>" --as user
# 拿到新 docx token

# 3. overwrite 一遍清掉占位图(关键步骤,绕过占位图陷阱)
lark-cli docs +update --doc <docx-token> --command overwrite \
  --doc-format markdown --content @./notes_full.md --as user

# 4. 用 media-insert 插真实图(每张 720x405, 16:9, 通过 caption 文本定位)
bash scripts/insert_images_feishu.sh <docx-token>

# 5. 移动到 wiki 节点下作为子节点
lark-cli wiki +move --obj-type docx --obj-token <docx-token> \
  --target-space-id <space-id> --target-parent-token <parent-token> --as user

# 6. (可选) patch 文档标题为中文直译
lark-cli drive files patch \
  --params '{"file_token":"<docx-token>","type":"docx"}' \
  --data '{"new_title":"<中文标题>"}' \
  --as user
```

**陷阱速查**(全在 references/feishu-publish.md 详述):
- 别用 `media-upload + block_replace` 替占位图: 替换后 block 进入"幽灵态", 后续 block_delete / str_replace 都会 1011 no_change
- 别用 `--download-sections` 切视频: ffmpeg HLS 拉一段死慢
- 别忘了 `media-insert` 加 `--width 720 --height 405`: 不加会变成 512×512 方框, 16:9 图片下面留白
- 飞书 docx 的 `<title>` 块、文件元数据标题、wiki 节点标题**三者绑死**: 删一个全没; patch 元数据会自动重建块; 想"只改一个"做不到
- 标题在飞书 UI 会出现两次(顶部 banner + 正文开头) — 这是飞书 wiki+docx 的渲染规则, 不是 bug
- **图片重抽时**走"overwrite × 2 → media-insert × N"路径会**清掉中文标题**变成 Untitled — 必须再 `drive files patch --new_title` 把中文标题写回, 否则 wiki 节点名也会变 Untitled

## Phase 7 · 收尾

- 推送通知: 跑完发 PushNotification(per `feedback_push_on_completion` 规则)
- 清理: 视频文件(几百 MB)如果不再用可删, 字幕和帧保留作存档

## 成本预算(Pro plan, Opus 主线程 + Sonnet 子 Agent)

| 阶段 | 主线程 (Opus) | 子 Agent (Sonnet) | 备注 |
|---|---|---|---|
| Phase 1-3 准备 | ~30K | 0 | 工具调用为主 |
| Phase 4 writer | ~25K (prompt + 结果) | ~150K | 一次跑 |
| Phase 5 reviewer | ~15K | 0 | 主线程 grep + 改 |
| Phase 6 飞书发布 | ~20K | 0 | 工具调用为主 |
| **合计** | **~90K Opus** | **~150K Sonnet** | 总 ~240K, Sonnet 折算约 30K Opus 等价 |

5h 配额(Pro)单次跑约用 ~120K Opus 等价 = 12% 配额。一天能跑 7-8 次。

## 不在本 skill 范围

- 中文视频(用户讲中文): 字幕和写作流程类似但术语策略不同, 本 skill 默认英→中
- 短视频 / vlog: 内容密度低, 直接看就行
- 实时直播流: 字幕和片源都还在录, 要等结束
