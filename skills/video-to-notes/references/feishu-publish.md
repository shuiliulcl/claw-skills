# 飞书 wiki 发布 — 踩过的坑全集

把本地 markdown 发到飞书 wiki 看似简单, 实则有几个非显而易见的陷阱。**正确路径在 SKILL.md Phase 6 已列**, 这里讲为什么这条路径正确, 以及别条路径为什么会翻车。

## 陷阱 1: import 自带占位图陷阱(最深的坑)

`lark-cli drive +import --file xxx.md --type docx` 看起来"成功", 但 markdown 里 `![](path)` 引用的本地图片**不会**真的传上去 — 飞书会创建 13 个**带 token 的占位图**, 内容是一张写着"无法导入该图片, 请从原文档中保存原图后重新上传"的灰色图。

下载占位图能蒙人(正常 PNG, 22KB, 不像 placeholder), 必须看图才能识别。

### 错误做法: media-upload + block_replace 替占位图

直觉的修法是: 拿到占位图的 block_id, 用 `media-upload` 传真实图换 token, 再用 `block_replace` 把 block content 改成新 token。

实测**这条路有内伤**: 替换后的 block 进入"幽灵态" — 后续:
- `block_delete` 返回 `degrade_code=1011 no_changes`
- `block_replace` 同样
- `str_replace` 同样(对该 block 内的文本)

但奇怪的是 `block_move_after` 还能动它。

后果: 如果你之后想清理这个 block(比如发现重复了), 就清不掉。只能 `overwrite` 整篇覆盖来解决。

### 正确做法: import → overwrite → media-insert

```bash
# 1. import 创建 docx (含占位图)
lark-cli drive +import --file ./notes.md --type docx --name "标题" --as user
# 拿到 docx_token

# 2. 立刻 overwrite 一遍, 用同一个 markdown 内容覆盖
#    这一步会清掉所有占位图 block (overwrite 不复用旧 block ID)
lark-cli docs +update --doc <docx_token> --command overwrite \
  --doc-format markdown --content @./notes.md --as user

# 3. 用 media-insert 在每个 caption 锚点前插真实图
#    每张图带 width=720 height=405 (16:9, 防方框留白)
lark-cli docs +media-insert \
  --doc <docx_token> \
  --selection-with-ellipsis "<caption text>" \
  --before --type image \
  --file <local.jpg> \
  --width 720 --height 405 \
  --as user
```

**为什么 overwrite 比直接 media-insert 好**: 
- 直接 import 后的占位图位置是对的, 但占位图本身在那
- 如果你不 overwrite 就 media-insert, 会变成"占位图 + 真实图"两张并排
- overwrite 把占位图全清, media-insert 只剩真实图

`overwrite` 警告"可能丢失图片、评论" — 在我们的场景里"丢失"的恰好是占位图, 求之不得。

## 陷阱 2: --width / --height 一定要带

`media-insert` 不带尺寸时, 飞书默认给 **512×512 方框**。1280×720 的 16:9 图片塞进方框就会上下留白。

业务图(720p 视频帧)统一用:
```
--width 720 --height 405
```
保持 16:9, 不会被方框挤压。其它分辨率按比例算。

## 陷阱 3: 飞书 `<title>` 三处绑死

飞书 docx 的标题不是单一对象, 而是三处同步:
1. 文件元数据 `name` (`drive +files patch` 修改的)
2. wiki 节点 `title` (展示在 wiki 树和面包屑)
3. 正文 `<title>` 块 (XML 第一个 block, render 在页面顶部)

**操作之间的联动**:
- 删 `<title>` 块 → 文件元数据 + wiki 节点 title 立即清空
- patch 文件元数据 title → `<title>` 块自动重建
- patch 时 docx 必须当前活跃, 不能在 wiki 移动中

**所以**:
- 想"只改 wiki 节点不动 docx 标题": **做不到**
- 想"删掉正文标题保留页面顶部 banner": **做不到**(都没了)
- 想"让标题渲染只出现一次": **做不到**, 飞书 wiki+docx 的渲染规则就是顶部 banner + 正文开头各显示一次

接受这个事实即可, 不要花时间研究怎么绕。

## 陷阱 4: 文件路径 only 接受相对路径

`lark-shared/SKILL.md` 里的安全规则: `--file`、`--content @file`、`--output` 这类参数**只接受 cwd 内的相对路径**, 绝对路径会报 `unsafe file path`。

对策: 操作前 `cd` 到项目目录, 用 `./xxx` 或 `xxx` 形式。或者用 stdin (`@-`) 传内容。

## 陷阱 5: --jq 解析要小心 banner

很多 lark-cli 命令在输出 JSON 之前先打一行进度横幅, 比如:
```
Uploading: slide_00-08-45.jpg (125500 bytes)
{
  "ok": true,
  ...
}
```

如果你 `... 2>&1 | python -c json.loads` 就会炸 — banner 不是 JSON。

正确做法:
```bash
lark-cli ... --jq '.data.file_token' 2>/dev/null
```
- `--jq` 让 CLI 自己解析并只吐字段, 不带 banner
- `2>/dev/null` 把 banner 重定向到 stderr 黑洞

## 陷阱 6: media-insert 的 selection-with-ellipsis 要找唯一锚

`--selection-with-ellipsis "<text>"` 是按文本定位, **doc 里这段文本只能出现一次**, 否则随机插一个位置。

我们的 caption 全部包含 `来源 HH:MM:SS` 时间戳, 每个时间戳唯一, 所以拿完整 caption 当锚比较稳。短的 `— 来源 00:12:03` 也够用, 因为时间戳唯一。

## 陷阱 7: 操作顺序, 在 wiki 移动之前完成所有编辑

- import 是创建在 drive 根目录的
- wiki +move 是把 docx 嵌进 wiki 的
- 编辑 / image-insert / title patch 都对 docx 有效, 不影响 wiki 关系

但是: **wiki 移动是个异步任务**, 完成前 docx 处于"可见但状态过渡"的中间态, 期间下编辑命令容易踩到不一致。所以推荐顺序:

```
import → overwrite → media-insert × N → title patch → wiki move
```

不要倒过来 wiki move 完了再回来调内容。

## 陷阱 8: overwrite 会清掉标题(图片重抽时必踩)

`docs +update --command overwrite --doc-format markdown` 把整个 docx 内容用 markdown 重写, **副作用是会重置 `<title>` 块为 `Untitled`**, 即使原 markdown 第一行是 `# 中文标题`。

这在初次 import 时不是问题(import 时 `--name` 直接定了元数据标题, 元数据 → title 块同步)。但**升级图片重抽走 overwrite 路径时会丢中文标题**, 退化成 "Untitled"。

修复办法:overwrite 完后用 `drive files patch --data '{"new_title":"<中文标题>"}'` 重新写一次元数据, 元数据会推回 title 块和 wiki 节点名。

**触发场景** — BlackEye 720p → 1080p 重抽时踩到。整个流程:

```bash
# 1. 重生成 feishu markdown
python scripts/to_feishu.py notes_full.md notes_for_feishu.md

# 2. overwrite 第一遍 (清旧 block, 留占位)
lark-cli docs +update --doc <token> --command overwrite --doc-format markdown --content @./notes_for_feishu.md --as user

# 3. overwrite 第二遍 (清占位)
lark-cli docs +update --doc <token> --command overwrite --doc-format markdown --content @./notes_for_feishu.md --as user

# 4. media-insert 全部 N 张图

# 5. *** 关键:patch 标题回中文 ***
lark-cli drive files patch --params '{"file_token":"<token>","type":"docx"}' --data '{"new_title":"<中文标题>"}' --as user
```

第 5 步漏了, 用户看到的飞书 wiki 节点名就变 "Untitled" 了。

## 速查命令汇总

| 任务 | 命令 |
|---|---|
| 解析 wiki URL → docx info | `drive +inspect --url '<wiki-url>' --as user` |
| 检查 docx 当前 XML 块结构 | `docs +fetch --doc <token> --as user --detail with-ids --jq '.data.document.content'` |
| 检查 docx 当前 markdown 视图 | `docs +fetch --doc <token> --as user --doc-format markdown --jq '.data.document.content'` |
| 改 docx 文件元数据标题 | `drive files patch --params '{"file_token":"<t>","type":"docx"}' --data '{"new_title":"X"}'` |
| 列 wiki 节点子项 | `wiki +node-list --space-id <s> --parent-node-token <p> --as user` |
| 改图块尺寸(已存在) | `docs +update --command block_replace --block-id <bid> --content '<img src="<token>" width="720" height="405"/>'` |
