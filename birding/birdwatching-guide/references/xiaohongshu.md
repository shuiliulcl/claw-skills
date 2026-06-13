# 小红书数据采集

**没有公开官方 API。** 小红书帖子提供"最新鸟况、出行/封控提醒、拍摄机位"这类社区情报，是 eBird/天气给不了的，但它是整个流程**最脆弱、合规风险最高**的一环。属于「增强数据源」——拿不到就跳过。

## 接入方式：MediaCrawler（已封装为 `scripts/xhs_search.py`，默认关闭）

开源项目，用 Playwright 模拟浏览器 + **你本人扫码登录**抓公开笔记：
- 仓库：https://github.com/NanmiCoder/MediaCrawler

### 一次性安装（用独立 venv，别污染全局 playwright）
```bash
git clone --depth 1 https://github.com/NanmiCoder/MediaCrawler.git
cd MediaCrawler && python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.txt
./.venv/Scripts/python.exe -m pip install "xhshow==0.1.9"   # ⚠️见下方版本坑
./.venv/Scripts/python.exe -m playwright install chromium
```
建议改 `config/base_config.py`：`ENABLE_GET_COMMENTS=False`（关评论更轻）、`CRAWLER_MAX_NOTES_COUNT=10`。

### ⚠️ 关键版本坑（踩过）
`requirements.txt` 写 `xhshow>=0.1.9`，pip 会装到 **0.2.0**，但 MediaCrawler 的签名补丁
（`media_platform/xhs/playwright_sign.py` 的 `_patch_xhshow_a3_hash`）是按 0.1.x 写的——
0.2.0 的 `build_payload_array` 多了个 `hex_md5_path` 参数导致 `TypeError: got multiple values for 'sign_state'`，
**抓取直接崩**。**务必锁定 `xhshow==0.1.9`**。

### 启用与调用
在 `~/.birdwatch/config.json` 配 `xiaohongshu`：
```json
"xiaohongshu": { "enabled": true, "mediacrawler_path": "D:/AITool/MediaCrawler", "max_notes": 10 }
```
然后用封装脚本（自动跑 MediaCrawler + 解析 jsonl + 返回摘要）：
```bash
python scripts/xhs_search.py --keywords "<地点> 观鸟" [--location 滨江森林,滨森] [--top 8]
python scripts/xhs_search.py --no-crawl --location 滨森   # 只解析上次抓取，不再请求平台
```
首次抓取会弹 Chromium 让你扫码（窗口可能被挡，Alt+Tab 找"Chromium"窗口）；登录态存在
`MediaCrawler/browser_data/`，之后换关键词**免扫码**。`assemble_guide.py` 启用后会自动把最近
一次抓取的笔记并入攻略「🔴 鸟友情报」板块（组装时**不联网**，只读已抓的 jsonl）。

## ⚠️ 合规与风险提示（务必读）

1. **遵守平台规则**：抓取可能违反小红书用户协议。仅做个人小规模、低频使用，不要批量/商用/二次分发。
2. **登录态风险**：用个人账号登录抓取存在账号风险，自行评估。
3. **稳定性差**：平台反爬策略常变，工具可能随时失效。**不要把攻略的成败押在它身上。**
4. **不要硬刚**：遇到验证码、封控、失败，直接放弃本数据源并标注，不要写绕过验证码/反检测的代码——那超出本 skill 的正当用途。

## 子 Agent 该带回什么

成功时，子 Agent 只返回**结论性摘要**（不要把帖子原文整段搬回）：
- 近期（按帖子时间）该地点鸟况关键词，如"最近来了XX鸟""XX湖鸟很多"
- 出行/封控/门票/路况提醒
- 推荐拍摄机位或路线（如帖子有提）

失败或没配置时，返回"小红书情报本次未接入/获取失败"，主 Agent 会在 HTML 标注。

## 更轻量的替代

如果用户不想折腾 MediaCrawler，可以让用户自己在小红书 App 搜一下，把看到的关键信息口述给你，你直接填进攻略。很多时候这比维护爬虫更省心。
