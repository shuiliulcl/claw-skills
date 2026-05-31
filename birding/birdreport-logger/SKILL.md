---
name: birdreport-logger
description: 快速向中国观鸟记录中心（birdreport.cn）提交个人观鸟记录。当用户说"记一笔观鸟记录""提交/上传观鸟记录""录入今天看到的鸟""帮我报记录到观鸟记录中心""把这次观鸟填进 birdreport"，或给出一份"地点+日期+看到哪些鸟各几只"想录入时使用。把极简模板自动映射成平台要的完整字段并提交，省去小程序里手动选时间、填一堆冗余选项的麻烦。仅用于提交用户真实观测的数据。
---

# 观鸟记录快速提交

把一份极简模板（日期/地点/时段/鸟种+数量）自动映射成 birdreport.cn 的提交请求，替代繁琐的小程序录入。鸟种名自动解析成 taxon_id、点位自动补全、冗余字段自动填默认值。

## 红线：只提交真实观测

这是真实公民科学数据库。**只提交用户真实看到的鸟**，绝不提交编造/测试/凑数的记录——会污染科学数据并违反平台规则。默认 dry-run 预览，用户确认后才真正提交。

## 前置：凭证（缺则先配）

- `BIRDREPORT_TOKEN`：登录 https://www.birdreport.cn/ 后，F12 → Network → 点任一 `api.birdreport.cn` 的 xhr 请求 → Request Headers 里复制 `X-Auth-Token`。**会过期**，失效（接口报 401/403）就重新复制。
- `BIRDREPORT_MEMBER_ID`：你的会员 id（数字）。

## 工作流

1. **拿到/写好模板**：照 [assets/record-template.txt](assets/record-template.txt) 的格式。用户口述时，帮他填进模板。
   - 地点：填 `point_id` 最稳（如 上海植物园=3、世纪公园=120）；填名字也行，脚本用 `point/list` 模糊查，多个候选时会让用户改填 id。
   - 鸟种：每行「名字 数量」，名字支持中文名 / 拼音 / 首字母（btb→白头鹎）。
2. **dry-run 预览**：
   ```bash
   python scripts/submit.py 记录.txt
   ```
   打印解析后的观测点、时段、每个鸟种+taxon_id+数量，**不发送**。和用户核对。
3. **确认后提交**：
   ```bash
   python scripts/submit.py 记录.txt --submit
   ```
   先建活动（saveReport 拿 activity_id），再逐个鸟种 push。完成后让用户到网页/小程序核对。

## 鸟种表

`scripts/taxonomy.json` 是当前版本（Z4）的 1519 种鸟，含 name/拼音/首字母→taxon_id，本地匹配。
平台换分类版本时需更新：拉 `/member/system/taxon/list`，取 version 前缀为当前版的条目重建。详见 [references/api.md](references/api.md)。

## 接口与字段细节

逆向所得的端点、提交 payload、AES 解密、ID 体系等全部记录在 [references/api.md](references/api.md)。改接口或排查失败时看它。
