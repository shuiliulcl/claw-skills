# 配图覆盖率(Figure Coverage)— 防止笔记图不够用

这是 video-to-notes 流程里**最容易踩**的坑,且不会自动报错。BlackEye 这一篇第一版只有 5 张图,正文密度比 Projectiles 那一篇明显低,看起来像"分析报告而不是知识分享"。后来手动补 5 张才到正常水平。

## 为什么会漏图

### 抽帧脚本的盲区

`extract_keyframes.py` 用 `scene>0.3` 检测画面切换。这套对**幻灯片切换**很准,但漏掉两类内容:

- **UI / Panel 演示**:专属界面被讲解时,背景视频不变,只有 panel 内的 knob/slider 在动 — scene 阈值打不出来
- **Demo 内的渐进切换**:同场景不同角色对话、镜头慢推、参数滑动 — 阈值不够

BlackEye 这一篇 1.5h 抽出 ~30 张候选,但 Black Eye Panel 整章(15:30-22:00, 6 分钟密集 UI 演示)只有 1 张候选,Cross Camera 章节 (36:00-38:00) 0 张候选。

### Writer 子 agent 的局限

writer 拿到候选池后逐张 Read 看图,按"实质帮助"选。它不知道**候选池本身有缺**,只能在已有图里选。结果是:候选少的章节被它"按图选文",写完就觉得没图也行。

### Reviewer pass 的覆盖盲点

主线程 reviewer 只 grep 数字 / API 名做事实核对,**不检查每章节是否有图**。漏图问题需要肉眼看完成稿才会发现,这时已经在飞书发过了。

## 持久解决方案

分三层防御,每层成本递增,但叠加效果最好:

### Layer 1:writer prompt 加章节覆盖率自检(零成本,必做)

让 writer 在选完图、写完正文后,**主动列出每个 H2 章节的图覆盖状态**,标注"无图章节"。已经写进 [writer-agent-prompt.md](writer-agent-prompt.md) 的"最终消息"部分,同时要求 writer 对 UI / Panel / 演示 / Demo / 对话 / Cross Camera 类章节给出"建议补图"提示,即使候选池里没合适的也要点出来。

### Layer 2:主线程 reviewer 加补图扫描(主线程做,~5-10K Opus)

writer 输出后,主线程除了 grep 文字事实,**还要扫一遍 markdown 里每个 H2 章节有没有图**。流程:

```bash
# 找出所有 H2 章节及它们的行号
grep -n "^## " notes_full.md

# 找出所有图片引用及它们的行号
grep -n "!\[" notes_full.md

# 对照: 哪些 H2 章节内 0 张图? 是否本应有图?
```

判断标准:

- **必须有图**的章节: 专属 UI / Panel / 工具截图 / 节点编辑器 / Sequencer / Blueprint / benchmark 表格 / 对话场景 / 复杂构图演示
- **可以无图**的章节: 纯设计哲学讨论 / Q&A 技术精华 / Related Concepts / 收尾

### Layer 3:定向补图(发现漏图后,~10-15K)

确认某章节漏图后,流程是:

```bash
# 1. 在 transcript.txt 里 grep 该章节关键词,找具体说话时间
grep -nE "panel|knob|slider" transcript.txt | head -20
# 输出形如: 1234:[00:15:30] So now in the Black Eye panel ...

# 2. 在该时间附近用 ffmpeg 定向提帧 (3-5 张候选, 间隔 10-30 秒)
for t in 00:15:30 00:15:58 00:16:30; do
  ffmpeg -ss $t -i full_720p_videoonly.mp4 -frames:v 1 -q:v 2 -y \
    "figures_full/renamed/slide_${t//:/-}.jpg"
done

# 3. Read 每张候选, 看哪张能配上这章的内容
# 4. Edit 笔记加图 + caption (含 "来源 HH:MM:SS")
# 5. 如果飞书已发过, str_replace 加 caption 文本 + media-insert 插图
```

**为什么不在 Phase 3 一开始就密抽?** 抽密(比如每 60s 一张)会把候选池从 30 张涨到 90 张,writer 看图成本翻 3 倍,但实际补的可能就 5 张 — 不划算。**Just-in-time 定向抽**才是性价比最高的。

## 检查清单

writer 跑完后,主线程必须按这个清单走一遍:

- [ ] grep `^## ` 列出所有 H2 章节
- [ ] grep `!\[` 列出所有图片
- [ ] 对照清单,标记 0 图的 H2 章节
- [ ] 对每个 0 图章节判断:它本就该有图吗?(看上面"必须有图"列表)
- [ ] 该有图但没有的:在 transcript 里找该章节时间区间,grep 关键词找具体时间
- [ ] 用 ffmpeg 定向提 3-5 张候选,Read 验证
- [ ] 选 1-2 张加到笔记,带 caption "来源 HH:MM:SS"
- [ ] 如果已发飞书:str_replace 加 caption + media-insert 插图

## BlackEye 的具体补图记录(参考)

这次实际补的 5 张,演示了上面流程怎么走:

| 章节 | 缺图原因 | 关键词 grep | 定向时间 | 最终选用 |
|---|---|---|---|---|
| Black Eye Panel | UI 演示, scene 检测不到 | "panel \| knob" | 00:15:30 / 00:15:58 | 入口 + 完整形态各一张 |
| Follow 模式 | demo 镜头连续, 都是同场景 | "pivot \| damping" | 00:33:10 | Final Pivot Point + Damping 三轴 |
| Cross Camera | 对话场景, panel 在动但视频不变 | "cross camera \| dialog" | 00:36:30 | OTS 构图截图 |
| Cloud Module | 3D 文字 + 多机位演示, 场景静止 | "cloud \| shotlist" | 00:59:25 | Outliner 6 机位 + 3D 文字 |

每张耗时:grep + ffmpeg 提 3 张候选 + Read 验证 ≈ 2-3 分钟。5 张总共 ~15 分钟。

## Inside Unreal StateTree 的补图记录:**场景类型决定流程**

BlackEye 是**单人演讲 + slide**, scene 检测命中率高, 补图只是补盲区。StateTree 这一篇是**4-5 嘉宾 podcast + 嘉宾偶尔屏幕共享**, 完全是另一种情况:

| 维度 | BlackEye(单人演讲) | StateTree(podcast) |
|---|---|---|
| 候选总数 | ~30 张 | 42 张 |
| 实际 VALUE 数 | ~10 张 | **4 张** |
| 命中率 | ~33% | **~10%** |
| 候选构成 | slide 切换 + UI 演示 | 5 人格栅 / 单人镜头 / UE logo 转场 / 5 张游戏画面 / 偶尔屏幕共享 |
| 写作前能不能用 | 能 | **不能, 必须先补抽** |

**根因**: scene 检测的 0.3 阈值是为"slide 切换"设计的。podcast 视频里 webcam 切换(主持人镜头 ↔ 全员格栅 ↔ 单嘉宾近景)同样能触发 0.3 阈值, 但这些镜头是没信息的。**屏幕共享内容反而是"画面缓慢变化"(滚动 / 鼠标移动 / 下拉展开), 触发不了阈值**, 所以真正有内容的帧抽不到。

### Podcast 类的正确流程: 跳过 scene 检测, 直接概念锚点定向抽

不要先跑 extract_keyframes 再补抽 — 跑出来的候选池 90% 是 talking head, writer 在干瘪池子上写完会觉得"没图也行"。直接:

```bash
# 1. transcript grep 找核心概念第一次被讲的时间
grep -nE "schema|transition|event|parameter|debugger|let me show|demo time" transcript.txt | head -30

# 2. 挑 8-15 个时间点, 每个核心章节 1-2 个
# 选点策略:
#   - 每个核心概念第一次被讲(grep 第一条)
#   - "let me show" / "if you click" 字样的时间(指 demo 操作)
#   - demo 段开始后 1-2 分钟(等画面稳定)
#   - demo 收尾总览镜头

# 3. 一次性 ffmpeg 单帧抽
for t in 00:16:30 00:19:10 00:22:40 00:25:40 00:28:50 00:44:30 00:50:30 01:04:30; do
  ffmpeg -ss "$t" -i full_1080p_videoonly.mp4 -frames:v 1 -q:v 2 -y \
    "figures_full/renamed/slide_${t//:/-}.jpg"
done
```

实测: StateTree 选了 13 个时间点, 11 张是 VALUE(命中率 84.6%), 写作前候选池就够用了。

### 怎么识别 podcast 类视频(写代码前 30 秒判断)

判断标志(任一满足):

- **Channel = "Unreal Engine"** 且 title 含 `Inside Unreal` / `Twitch`
- 视频时长 ≥ 90 分钟 + 多人嘉宾(看 yt-dlp metadata 或字幕第一段)
- 字幕第一段内出现 `introduce our guests` / `joining us today` / `let's go around the room` / 多次 `>>` 切换说话人

确认是 podcast 后, **直接跳到概念锚点定向抽**, 不跑 extract_keyframes(省 5-10 分钟 + 几百 MB 临时文件)。

### 候选池预评估(写作前必做, 哪种类型都做)

抽完帧不要直接 writer, 先看候选池**密度**:

```bash
ls figures_full/renamed/slide_*.jpg | wc -l                              # 总数
ls figures_full/renamed/slide_*.jpg | awk -F'[_.-]' '{print int($2)}' | sort -n | uniq -c   # 每 10 分钟分布
```

判断:
- 单人演讲: 每 10 分钟 ≥ 2 张, 总 ≥ 20 张 → OK
- Demo 录屏: 每 10 分钟 ≥ 1 张, 总 ≥ 12 张 → OK
- Podcast: 单看候选池数没用, 看**每个核心章节有没有 ≥ 1 张实质内容图**

某段 0 张但 transcript 表明有屏幕共享 → 当场补, 别等 reviewer 阶段。

### 历史数据点(用来校准命中率预期)

| 视频 | 类型 | 候选 | VALUE | 命中率 | 最终笔记图数 | 章节图覆盖 |
|---|---|---|---|---|---|---|
| Projectiles(Inside Unreal) | podcast(单人主讲多, 大量屏幕共享) | ~30 | ~12 | ~40%(估) | 10 张 | 高 |
| BlackEye(Camera) | 单人演讲 | ~30 | ~10 | ~33% | 5+5=10 张 | 中 |
| StateTree(Inside Unreal) | **podcast(4 嘉宾轮流讲)** | 42 | **4** | **9.5%** | 11 张(8 张定向补抽) | 60% |

> 注: Projectiles 的命中率是回顾性估计, 不是实测; BlackEye / StateTree 是实测数。后续跑新视频时如有更精确数据请回填本表。

Projectiles 比 StateTree 命中率高的原因: 演讲者有 ~半时间在屏幕共享 demo, 而 StateTree 的 4 嘉宾大部分时间是"对着摄像头讨论"。**嘉宾越多, 屏幕共享时间占比越低, scene 检测越没用**。

## 反例:什么时候不要补

- 章节是**纯概念**(比如"为什么要这样设计"、"取舍讨论"),没有视觉对应,补图就是凑数
- 候选时间区间内只有 talking head 镜头(主讲人对镜头),这种图无信息
- 演讲者讲的是抽象数学/算法,视频里没有对应可视化

补图的判断标准是"看完图能多理解一点正文",不是"章节没图就一定要塞一张"。

## 升级分辨率重抽的陷阱(必看)

video-to-notes 流程支持升级 720p → 1080p 重抽帧。BlackEye 升级时踩到一个**静默 bug**:

**症状**: 跑 `extract_keyframes.py` 用 1080p 视频抽帧,完成后图片**部分是 1080p 部分是 720p 旧版**, 飞书 docx 看起来还是糊的。

**根因**: extract_keyframes.py 的 dedup 在不同视频上得到的 keep 时间戳集合不完全一致(因为 1080p 的 scene 检测对像素更敏感, 阈值结果会偏)。脚本只覆盖同名 `slide_HH-MM-SS.jpg`, 不会清理上次产物。结果:

- 720p 时代抽出 30 张 (集合 A)
- 1080p 时代抽出 40 张 (集合 B)
- 集合差 A - B 那部分(720p 有但 1080p 没抽到的时间戳)的旧 jpg 残留在 renamed/ 里
- 此外,**手动定向补抽的图**(用 ffmpeg 直接提的, 没进 scene 检测) 不会被新跑覆盖, 全部停留在 720p

**修复**: extract_keyframes.py 现在在 Pass 2 之前清理 renamed/ 下所有 `slide_*.jpg`, 强制全部重抽。但定向补抽的图**不在 scene 检测命中**的话, 还要手动 ffmpeg 重抽:

```bash
# 升级分辨率重抽流程
yt-dlp -f 299 ...   # 下 1080p
mv full_720p.mp4 full_720p_old.mp4   # 备份
python scripts/extract_keyframes.py full_1080p_videoonly.mp4 figures_full/

# 关键: 验证 markdown 引用的所有图都已经 1920x1080
python -c "
import os
from PIL import Image
d = 'figures_full/renamed'
sizes = {}
for f in sorted(os.listdir(d)):
    s = Image.open(os.path.join(d,f)).size
    sizes.setdefault(s, 0)
    sizes[s] += 1
print('sizes:', sizes)
"
# 期望输出: sizes: {(1920, 1080): N}, 不能混 720

# 验证 markdown 引用的具体文件名都还在(scene 检测 dedup 可能让某些 timestamp 丢)
grep -oE "slide_[0-9-]+\.jpg" notes_full.md | sort -u | while read f; do
  [ -f "figures_full/renamed/$f" ] && echo "OK $f" || echo "MISS $f"
done

# 缺失的(MISS): 用 ffmpeg 定向重抽
# ffmpeg -ss <秒> -i full_1080p.mp4 -frames:v 1 -q:v 2 -y figures_full/renamed/slide_HH-MM-SS.jpg
```

**飞书侧也要全部重传**:旧 720p 已经上传到 docx, 不会自动更新。需要 `block_delete` 旧的 10 个 img block, 然后 `media-insert × 10` 用新 1080p 文件重新插。注意: 这条路径**不会**清标题(只 block_delete 不 overwrite), 比"overwrite × 2 + media-insert"省一步 patch new_title。

**验证飞书侧确实换成 1080p**:fetch docx, 找到 img 的 href(带 authcode 的临时 URL), curl 下来用 PIL 看尺寸:

```bash
lark-cli docs +fetch --doc <token> --as user --detail with-ids --jq '.data.document.content' > _xml.txt
python -c "
import re
content = open('_xml.txt', encoding='utf-8').read()
m = re.search(r'<img id=\"[^\"]+\" name=\"slide_TARGET\.jpg\" height=\"[^\"]+\" href=\"([^\"]+)\"', content)
print(m.group(1))
" > _url.txt && curl -s -o _check.jpg "$(cat _url.txt)"
python -c "from PIL import Image; print(Image.open('_check.jpg').size)"
# 期望 (1920, 1080)
```

**用户报告"还是糊"时**: 先按上面验证确认后端是 1080p; 如果是, 让用户 hard refresh / 退飞书重进。飞书 web/desktop 客户端会缓存图片预览, 不会自动拉最新。`drive +download --file-token` 不能下 docx 内嵌图(返回 403), 必须走 fetch href + curl 验证。

