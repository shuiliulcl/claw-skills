---
name: sync-ecabridge
description: 从程序哥 GitLab 同步或开发 ECABridge/ToolsetRegistry/Toolsets/X6Toolsets,支持 pull/push/upstream 三种同步模式,以及在 VibeUeToolset 等 ECA Toolset 中补 AI 可调用接口,特别是 UserDefinedEnum 元数据/ToolTip/Lua XML 导出片段相关接口
---

# 同步 ECABridge / ToolsetRegistry / Toolsets / X6Toolsets

从程序哥个人 GitLab 空间(团队成员有 read 权限)同步四个仓库:三个引擎级 + 一个项目级。

## 仓库映射

| 仓库 | 远程地址 | 本地目录 | 类型 |
|------|---------|---------|------|
| eca-bridge | `git@xy-gitlab.diezhi.net:chengxuge/eca-bridge.git` | 优先 `Engine/Plugins/UnrealAI/ECABridge`,不存在则用 `Engine/Plugins/Experimental/ECABridge` | Engine |
| toolset-registry | `git@xy-gitlab.diezhi.net:chengxuge/toolset-registry.git` | `Engine/Plugins/Experimental/ToolsetRegistry` | Engine |
| toolsets | `git@xy-gitlab.diezhi.net:chengxuge/toolsets.git` | `Engine/Plugins/Experimental/Toolsets` | Engine |
| x6toolsets | `git@xy-gitlab.diezhi.net:chengxuge/x6toolsets.git` | `<X6Project>/Plugins/X6Toolsets` | **Project** (依赖 UnLua/PaperLuaFramework) |

团队仓库作为 upstream remote(仅前三个有团队仓库,x6toolsets 暂无):
- `git@xy-gitlab.diezhi.net:paper-agent-team/eca-bridge.git`
- `git@xy-gitlab.diezhi.net:paper-agent-team/toolset-registry.git`
- `git@xy-gitlab.diezhi.net:paper-agent-team/toolsets.git`
- x6toolsets: 暂无团队 upstream,只走 origin (chengxuge 个人仓库)

## 路径定位

- **引擎根目录**:从当前工作目录向上查找包含 `Engine/Binaries` 的目录,前三个仓库的目标基础路径 = `<引擎根>/Engine/Plugins/Experimental/`
- **X6 项目根目录**:从当前工作目录向上查找包含 `X6Game.uproject` 的目录,x6toolsets 目标 = `<X6项目根>/Plugins/X6Toolsets`

执行前确认对应根目录存在,不存在则报错退出(eca-bridge/toolset-registry/toolsets 缺引擎根则跳过这三个;x6toolsets 缺项目根则跳过这一个)。

注意:**x6toolsets 默认分支是 `main`**(其他三个仓库历史上是 `main` 或 `master`,实际 push/pull 时按各自远端默认分支处理)。

## 操作模式

### 模式 1: 拉取同步 (参数: `pull` 或无参数)

从个人 GitLab 拉取最新代码到本地目录:

对每个仓库执行:
1. 如果本地目录不存在,`git clone <个人仓库地址> <本地目录>`
2. 如果本地目录已存在但不是 git 仓库,报错跳过
3. 如果本地目录已存在且是 git 仓库:
   a. 确认 origin 指向个人仓库,如果不是则修正
   b. 确认 upstream 指向团队仓库,如果不存在则添加(x6toolsets 跳过此步)
   c. `git fetch origin` 获取远程更新
   d. `git status` 检查本地是否有未提交修改
   e. 如有未提交修改,先 stash
   f. `git pull origin <default-branch>` 拉取最新
   g. 如有 stash,pop 恢复
4. 报告每个仓库的同步结果(当前 commit、文件数变化)

### 模式 2: 推送修改 (参数: `push`)

将本地修改推送到个人 GitLab:

对每个仓库执行:
1. `git status` 查看改动
2. 如有改动,`git add` + `git commit`(让用户确认 commit message)
3. `git push origin <default-branch>` 推送到个人 GitLab
4. 报告结果

### 模式 3: 从团队仓库同步 (参数: `upstream`)

从团队仓库拉取更新并合并:

对每个仓库执行(x6toolsets 跳过 — 无团队仓库):
1. `git fetch upstream main`
2. `git log --oneline main..upstream/main` 查看新提交
3. 如有新提交,`git merge upstream/main --no-edit`
4. 如有冲突,提示用户手动解决
5. 合并成功后 `git push origin main` 推送到个人仓库
6. 报告结果

## 注意事项

- Git 操作在 WSL 中用 `git -C <目录>` 执行
- ECABridge 路径选择:先检查 `Engine/Plugins/UnrealAI/ECABridge` 是否存在,存在则使用它;不存在才 clone 到 `Engine/Plugins/Experimental/ECABridge`
- upstream remote 为可选:如果无法访问团队 GitLab(权限不足或网络问题),跳过 upstream 相关操作,不影响 pull/push 主流程。仅在执行 `upstream` 模式时才需要团队仓库访问权限
- 添加 remote 前先用 `git ls-remote <url> HEAD` 测试连通性,超时 5 秒则跳过并提示
- **x6toolsets 是 Project Plugin 集合**,跟前三个 Engine Plugin 不同:依赖 UnLua/PaperLuaFramework 等项目级 plugin,只能放在 `<X6Project>/Plugins/` 下。如果当前工作目录不在 X6 项目内(比如纯引擎工作流),就跳过这个仓库
- 所有操作完成后汇总报告四个仓库的状态(其中 x6toolsets 可能因不在 X6 项目内被跳过)

## Toolset 开发:UserDefinedEnum 接口

当需要让 AI 直接操作 UE 枚举资产,优先在 `toolsets` 仓库的 `VibeUeToolset` 里补 `UFUNCTION(BlueprintCallable)` 接口,不要依赖 Slate UI 点击枚举编辑器或带弹窗的 X6 菜单。

推荐能力拆分:
1. 读取接口:返回 enum 的 `index/internal/friendly/value/tooltip/version`,用于确认 UE 内部名和导出元数据。
2. 写入接口:批量设置 `UUserDefinedEnum` 枚举项 `ToolTip` metadata。key 同时支持 friendly name、internal name、`EnumName::InternalName` 和数值字符串,避免调用方先做映射。
3. 片段接口:只为指定 enum 构造 `PaperBPEnumConfig.lua` 的 Lua block 和 `paper_bpenum_config.xml` 的 XML block,不写文件、不扫全量、不弹窗。调用方再把返回片段 patch 到生成文件,这样可以只保留本次 enum diff。

实现要点:
- 路径优先放在 `Engine/Plugins/Experimental/Toolsets/VibeUeToolset/Source/VibeUeToolset/`。
- 复用 `LoadObjectByContentPath` 风格,允许 `/Game/Path/Enum` 和完整 object path。
- 读取枚举数量时跳过 UE 自动 `_MAX`: `Enum->ContainsExistingMax() ? NumEnums - 1 : NumEnums`。
- 对 `UUserDefinedEnum` 写 ToolTip 用 `UserEnum->SetMetaData(TEXT("ToolTip"), *Value, Index)`,随后 `MarkPackageDirty()` 和 `PostEditChange()`;如接口提供保存参数,再用 `UPackage::SavePackage` 保存。
- 生成 XML alias 时按 X6 导出工具规则处理:ToolTip 重复则追加 `-value`,alias 等于 name 时置空,并替换 `&/< />`。
- 生成 Lua/XML 片段时只返回字符串,不要直接改 `PaperBPEnumConfig.lua` 或 `paper_bpenum_config.xml`;项目配置文件仍按 X6Game P4 规则由调用方 checkout/sync/patch。

验证方式:
- 先运行 `git diff --check`。
- 编译 `VibeUeToolset` 模块。若 UE 编辑器正在运行,可能在 link 阶段因占用 `UnrealEditor-VibeUeToolset.dll` 报 `LNK1104`;只要 UHT 和 compile 已通过,可说明代码编译通过但需要关闭编辑器后完成链接。
- 提交 MR 时只提交 Source 下源码文件,不要混入 `Binaries/` 或 `Intermediate/` 产物。

$ARGUMENTS
