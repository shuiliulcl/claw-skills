---
name: weekend-birding
description: 周末观鸟一条龙编排。当用户说"周末观鸟""周末去X观鸟/出个攻略""这周去哪看鸟""把今天/这次看到的鸟记一下/提交了""整理观鸟记录"等，启动整合闭环：行前出攻略并标可加新种、行后把手机便签清洗成记录提交到观鸟记录中心。本 skill 编排 birdwatching-guide（攻略）与 birdreport-logger（提交），并维护个人人生鸟单与出行档案。用户全程只用自然语言对话，不碰脚本和模板。
---

# 周末观鸟 · 整合闭环

把"行前攻略 → 现场速记 → 行后提交"串成一条龙。用户每周末出行一次，现场用**手机便签随手记**，回来把便签整段发来即可。你（主 Agent）负责清洗、解析、调度，用户不接触脚本/模板/ID。

依赖另两个 skill 的脚本（绝对路径）：
- 攻略：`C:\Users\<user>\.claude\skills\birdwatching-guide\scripts\`
- 提交/鸟单：`C:\Users\<user>\.claude\skills\birdreport-logger\scripts\`

共享数据目录 `~/.birdwatch/`（`C:\Users\<user>\.birdwatch\`）：
- `lifelist.json` —— 个人人生鸟单缓存（来自观鸟记录中心）

**Obsidian vault**（`~/ObsidianVault`，env `BIRDWATCH_VAULT`）下的 `观鸟/`：
- `species/<鸟名>.md` —— 每种一篇，frontmatter 含 taxon_id/科/首次记录，正文用 Dataview 汇集"在哪见过"
- `trips/<date> <地点>.md` —— 每次出行笔记（见下格式）
- `观鸟仪表盘.md` —— Dataview 统计（人生鸟单/出行/今年新增/各科）
- 用 `scripts/obsidian_sync.py` 从 lifelist.json 生成/刷新物种笔记与仪表盘（只新建，不覆盖已有物种笔记）。

### Obsidian 笔记格式

**出行笔记** `观鸟/trips/2026-05-31 世纪公园.md`：
```markdown
---
type: 观鸟出行
date: 2026-05-31
地点: 世纪公园
point_id: 120
省市: 上海市/徐汇区
鸟种数: 12
新增种: 3
tags: [观鸟/出行]
---
# 2026-05-31 世纪公园
天气：晴 21–30°C
## 鸟种记录
- [[白头鹎]] ×3
- [[乌鸫]] ×2
## 本次新增 ⭐
- [[XX]]
```
鸟种写成 `[[鸟名]]` 双链——物种笔记的反链/Dataview 会自动汇集"在哪见过"。新增种 = vault 的 species/ 下原本没有该笔记的种。

## 判断在闭环的哪一步

- 用户在**计划/出发前**（"周末去X""出个攻略"）→ 走【行前】。
- 用户**回来了**、给出看到的鸟（一段便签、"今天看到…"）→ 走【行后】。
- 不确定就问一句。

## 行前流程

1. **刷新人生鸟单**（确保"可加新"准确）：
   `python <logger>\scripts\lifelist.py`
   （若报 token 失效，提示用户重新复制 BIRDREPORT_TOKEN，见 birdreport-logger/SKILL.md。）
2. **生成攻略**：调用 birdwatching-guide 流程（eBird 热点/高光鸟种 + 和风天气），地点用用户指定地。
3. **标记可加新/已解锁**：读 `~/.birdwatch/lifelist.json` 的鸟种集合，与攻略里出现的鸟种比对——人生单里没有的标「⭐可加新」，有的标「已记录」。这是对用户最有价值的一块。
4. **建出行笔记** `观鸟/trips/<date> <地点>.md`（vault 内，格式见下）：写入 frontmatter（date/地点/**point_id**/省市，point_id 提前查好存上供行后提交用）、天气最佳时段、目标可加新种清单（用 `[[鸟名]]` 双链）。
5. 把攻略 HTML 路径给用户。

## 行后流程

1. **收便签**：用户把手机便签整段发来（格式随意，如"白头鹎仨 乌鸫一对 还有俩珠颈斑鸠 btb一只"）。
2. **清洗成规范清单**：你来把口语数量词转成数字（一对=2、仨=3、"几只"则向用户确认具体数）、去重合并、识别鸟名。**拿不准的数量或鸟名一定问用户，不要猜**。
3. **补全出行信息**：从对应的 trip 档案取 point_id、日期、时段；缺则问用户。
4. **写成 logger 模板**临时文件，跑 **dry-run** 预览：
   `python <logger>\scripts\submit.py <临时模板>`
   把解析结果（观测点、时段、每种鸟+taxon_id+数量）给用户核对。
5. **用户确认后提交**：
   `python <logger>\scripts\submit.py <临时模板> --submit`
   （红线：只提交用户真实观测的数据。）
6. **收尾**：提交成功后 ① 重跑 `lifelist.py` 更新人生鸟单 ② 重跑 `obsidian_sync.py` 为新增种生成物种笔记 ③ 把当天实际记录写进 vault 的出行笔记（鸟种用 `[[鸟名]]` 双链，新增种标 ⭐）。告诉用户这次人生单净增哪些种。
7. **同步 GitHub**：把 vault 改动推到远程——
   ```bash
   git -C "~/ObsidianVault" add -A && git -C "~/ObsidianVault" commit -m "观鸟: <date> <地点> 记录" && git -C "~/ObsidianVault" push origin main
   ```
   远程 `github.com/shuiliulcl/ForObsidian`，分支 main。
   注意：用户的 Obsidian Git 插件可能也在自动提交，本步是兜底；若 push 报"non-fast-forward"，先 `git -C "~/ObsidianVault" pull --rebase` 再 push。提交信息按惯例结尾加 Co-Authored-By。**push 属于向远程发数据，执行前按全局规则知会用户。**

## 触发为专用命令

用户可直接说「周末观鸟」「出周末攻略」「提交今天的记录」等触发本 skill。本 skill 是编排层，具体取数/提交交给被编排的两个 skill 的脚本完成。

## 移动端入口：飞书 CC-Connect（本机）

用户在手机飞书 DM 本机的 **CC-Connect bot** = 直接调用本机 Claude Code（即本 skill 全套可用），无需另造 bot 服务。经此渠道触发时：
- 输出按移动端形态交付（飞书消息精简摘要 + HTML 文件 + 存进 vault 同步），详见 birdwatching-guide 的「飞书/移动端交付」。
- 出攻略只读 eBird/天气 + 缓存的人生鸟单（`lifelist.json`），**不需要 birdreport token**，最适合先验证渠道。
- 提交记录切片需 birdreport token。**token 几天才过期，登录要图形验证码、无法全自动**，但已做到近乎一键：
  - `python <logger>\scripts\grab_token.py`：用专属 Chrome 配置打开会员页、拦截真实 X-Auth-Token、**写入 config.json**。登录态有效则全自动；过期则在弹出的 Chrome 里登录一次（填验证码）。
  - **token 存进 config.json 后，脚本运行时即读取，cc-connect 无需重建**。
  - 用户也可直接对我说"刷新 token"，我来跑 grab_token。

> 本节"移动端入口/飞书"整体是**可选**（config `ccconnect.enabled`）。核心脚本都能独立 CLI 跑，不依赖飞书。

## 配置与凭证（统一）

所有 key/路径集中在 **`~/.birdwatch/config.json`**（单一来源，env 作回退），便于多机部署。详见 `birdwatching-guide/DEPLOY.md`、模板 `config.example.json`。
- 必填：`ebird_api_key`、`qweather.*`（+ 本地 Ed25519 私钥）
- 个人记录：`birdreport.token`（grab_token 自动写）、`birdreport.member_id`
- 可选开关：`obsidian.enabled`（默认关）、`ccconnect.enabled`（默认关）
