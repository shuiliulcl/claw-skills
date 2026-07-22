---
name: p4-bypass-unshelve
description: 将一个或多个 Perforce Shelved CL 取到当前 X6Game Workspace；为每个来源 CL 创建独立目标 CL，使用 `p4 unshelve --bypass-exclusive-lock` 跳过 exclusive file 锁，并按“资产接受 CL 版本、代码三方合并”处理 Resolve。用户提到“强行 shelve/unshelve”“跳过独占 checkout”“批量 Unshelve CL”“把这些 CL 取到当前分支”或处理这些目标 CL 的 Resolve 时使用。
---

# P4 跳过独占 Unshelve

严格按以下流程操作。此技能负责 Unshelve 和 Resolve，不 submit、不 revert、不 force-sync。

## 输入

- 接受以空格、逗号、中文逗号或换行分隔的 Shelved CL 列表。
- 去重但保留输入顺序。
- 若用户没有给出 CL，要求用户补充；不要猜测。

## 1. 确认 Workspace

1. 运行 `p4 info` 和 `p4 client -o <当前客户端>`。
2. 确认客户端 Root 覆盖当前工作目录；不覆盖时查找正确客户端。对于 `F:\shuiliu_Stb_2.8` 使用 `shuiliu_Stb_2.8`。
3. 记录 `P4PORT`、`P4USER`、客户端名、Root 和 Stream。
4. 若 P4 离线、客户端不匹配或客户端没有 Stream，停止并报告；不要修改文件权限。

## 2. 只读预检全部来源 CL

对每个来源 CL 执行 `p4 -ztag describe -S <CL>`：

- 必须存在 shelved files；不存在则单独报告并跳过。
- 记录来源用户、描述和 depot files。
- 同一 depot file 出现在多个来源 CL 时，只保留到最先输入的 CL，并报告重复项。
- 先完成所有 CL 的预检，再创建任何目标 CL。

## 3. 计算 X6 跨流映射

以本机经过验证的实现为规则来源：

- `E:\ShuiliuTools\Public\X6P4VTools\CommonModule\x6_p4tool.py` 的 `get_ref_stream_types`、`get_stream_by_filepath`、`unshelve_by_cls`。
- 当前目标 Stream 及其 `Paths`/`Components` 决定主工程、配置、Dialogue、Proto 和 GameFeature 对应的目标流。
- 每个来源文件必须能映射到当前 Workspace 引用的同类型目标流。不能映射的文件要报告并排除，禁止凭字符串猜目标路径。
- 为每个来源 CL 生成独立 branch view：`<来源 depot file> <目标 depot file>`。

需要核对实现时只读上述文件相关函数，不修改 `E:\ShuiliuTools`。

## 4. 逐个创建目标 CL 并 Unshelve

仅在预检成功后，对每个仍有有效文件的来源 CL：

1. 用 `p4 change -o`/`p4 change -i` 创建独立 pending CL。描述包含：
   `Unshelve shelve CL <来源CL> to <目标Stream>`，以及原作者和原描述。
2. 创建唯一临时 branch spec，名称包含当前用户、来源 CL 和随机短后缀，避免覆盖已有 branch spec。
3. 执行：
   `p4 unshelve -s <来源CL> -c <目标CL> -b <branchSpec> --bypass-exclusive-lock`
4. 用 `p4 opened -c <目标CL>` 验证结果。
5. 若目标 CL 为空，删除该空 CL；不要删除非空 CL。
6. 删除本次创建的临时 branch spec。若删除失败，报告其名称，不要强制处理。

## 5. 按类型处理 Resolve

Unshelve 完成后，对每个目标 CL 先运行 `p4 resolve -n -c <目标CL>`，再按以下固定规则处理：

- **资产与数据文件**：以 Shelved CL 版本为准，放弃本地版本。对 `.uasset`、`.umap`、`.xlsx`、`.xml` 以及其他非代码文件使用 `p4 resolve -at -c <目标CL> <文件>`。
- **代码文件**：保留双方有效改动并执行三方合并。代码包括 `.lua`、`.cpp`、`.c`、`.h`、`.hpp`、`.cs`、`.py`、`.go`、`.js`、`.ts`、`.usf`、`.ush` 等源文件。
- 对代码先使用 `p4 resolve -am -c <目标CL> <文件>` 尝试无冲突合并。若仍未解决，读取 yours/base/theirs，逐处人工合并；不得简单接受 yours 或 theirs。
- 人工合并后检查语法、重复逻辑和 `<<<<<<<`、`=======`、`>>>>>>>` 冲突标记，再按 P4 的合并结果流程标记 resolved。
- 最后对所有目标 CL 再运行 `p4 resolve -n -c <目标CL>`；只有待 Resolve 数为 0 才算完成。

若用户明确给出不同 Resolve 规则，以用户本次指令为准。始终禁止自动 Submit。

## 6. 错误与权限

- `--bypass-exclusive-lock` 被服务器拒绝时，保留已创建的非空目标 CL，停止该来源 CL，并原样报告权限错误。
- 单个来源 CL 失败不应回滚或破坏其他成功 CL。
- 不使用默认 changelist 承载结果。
- 不 submit、revert、unlock、reopen 用户已有文件，也不清理任务开始前已存在的 branch spec。

## 7. 结果报告

输出：

- 当前客户端与目标 Stream。
- `来源 CL -> 新目标 CL` 映射。
- 每个目标 CL 的文件数。
- 被跳过的无效、重复或无法映射文件。
- 资产接受 CL 版本的数量、代码合并数量、剩余待 Resolve 文件和任何 P4 warning/error。
- 最后运行 `p4 opened` 核实，不隐瞒 `must sync/resolve` 警告。
