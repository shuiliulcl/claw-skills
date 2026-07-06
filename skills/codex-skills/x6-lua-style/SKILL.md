---
name: x6-lua-style
description: "X6Game Lua coding standards for Unreal Engine/UnLua scripts. Use when creating, modifying, reviewing, or explaining Lua files under X6Game/Content/Script, especially GameBP/Logics/UI/Config scripts, BP_*_C Lua classes, PaperEvent usage, UObject validity checks, callbacks, annotations, naming, default values, P4-safe Lua edits, and Lua code that reads or depends on config tables/enums. When Lua work touches PaperEnum.Cfg, self:GetDataCfg(), CfgTypes, DesignerConfigs, or generated config data, also use x6-config-wiki."
---

# X6 Lua Style

## 使用方式

修改或 review X6Game Lua 前, 先读取项目 `AGENTS.md` 的 P4 和搜索规则; 本 skill 只覆盖 Lua 代码风格和常见工程约定。已有文件局部风格和本规则冲突时, 优先保持周边一致, 但不要违反下面的硬约束。

如果本次 Lua 修改、review 或解释涉及配置读取、`PaperEnum.Cfg.*`、`self:GetDataCfg().TbXxx`、`CfgTypes.lua`、`DesignerConfigs` / `DesignerConfigurations`、导表或配置生成链路, 必须同时读取 `$x6-config-wiki`, 先从配置源和生成产物确认表名、字段、枚举名和版本规则。

Review 含中文注释的 Lua 文件时, PowerShell 读取必须显式使用 `Get-Content -Encoding UTF8`; 行号和关键代码定位优先用 `rg -n` / `Select-String` 复核。不要根据乱码输出判断注释是否吞掉代码或行内容是否相连。

## 行为边界

- 只实现当前明确需要的行为, 不默认增加 "`0` 表示任意"、"未配置兜底"、"多来源 fallback" 等额外语义; 除非工程里已有同类约定或用户明确要求。
- 不默认用 `or 0` / `or ""` / `or false` 给可选入参补防御默认值。尤其是 tag / id / enum 字段, `nil` 表示未配置时就只判断 `nil`; 不要擅自引入 `0` 也表示无效、空字符串也表示无效等额外语义。需要默认值时先直接取入参, 再用显式 `if value == nil then value = defaultValue end` 表达。
- 不要跨对象或跨层隐式读取 BP 字段作为底层参数默认值。调用方负责把业务配置显式写入 options / params; 例如需要距离阈值时, 由 `BP_SpawnerGroupPlayAnim` 将 `BP_NikkiRadius` 写入 `AnimalGroupAnimBuildFromTableOptions.AlertDistance`, 底层 Processor 不再读取 `BaseActor.BP_NikkiRadius`。
- 信任 `PaperEvent` 的事件契约: 参数类型按 `EventConfig` 和发事件处的约定使用, 不做无根据的 `tonumber` / 多类型兼容。
- 逻辑明确作用于当前主控角色时, 优先使用项目约定对象如 `_G.CCR`; 不要随手增加多角色、多来源 fallback。
- 生命周期函数如 `Init` / `DeInit` / `ReceiveBeginPlay` / `ReceiveEndPlay` 不要轻易早退。优先先完成成员初始化、解绑、释放和置空等完整生命周期动作, 再用 guard block 包住后续业务逻辑; 避免 `return` 跳过未来新增的清理或初始化步骤。

## UObject 和 BP 成员

- 在 Lua 代码中不使用关键字 `UE4`, 统一使用 `UE`。
- 不使用 `UE.UObject.IsValid` 进行 `UObject` 判空, 统一使用 `_G.PaperScopeMgr:IsUObjectValid(...)`。
- 当有必要使用 `_G.PaperScopeMgr:IsUObjectValid(...)` 或其缓存函数判断某个 `UObject` 是否有效时, 不需要额外先判断该对象是否为 `nil`; 直接写 `if not _G.PaperScopeMgr:IsUObjectValid(Object) then ... end` 或 `if not self:__fnIsValid(Object) then ... end`。
- 如果在同一个局部作用域或类中多次使用 `_G.PaperScopeMgr:IsUObjectValid(...)`, 先在本地缓存函数引用: `self.__fnIsValid = _G.PaperScopeMgr.IsUObjectValid`。调用时用 method 形式 `self:__fnIsValid(X)`, `ReceiveEndPlay` / `__DeInit` 末尾置 `self.__fnIsValid = nil`。
- 蓝图里定义的变量 `self.BP_Xxx` 在 Lua 中不会为 `nil`, BP 会给类型默认值; 不需要写 `if self.BP_Xxx == nil then ... end` 判空。业务默认值优先通过蓝图变量配置表达, 不要在 Lua 中额外自造 nil 兜底。
- 蓝图里声明的 EventDispatcher `self.OnXxx` 在 Lua 中不会为 `nil`, 直接 `self.OnXxx:Broadcast(...)` / `self.OnXxx:Clear()` 即可。
- `ActorComponent` 取 `self:GetOwner()` 后不需要判空; 仅在 detach / destroy 流程或跨帧异步回调里才考虑加 `_G.PaperScopeMgr:IsUObjectValid(owner)`。
- 跨帧异步回调的游离 `UObject` 如 `X6AsyncTask`, 若宿主没有 `UPROPERTY` 锚定, 在 `OnTaskStart` 开头调 `_G.UnLua_Ref(self)`, 在 `OnTaskFinishEvent` 对称调 `_G.UnLua_UnRef(self)`。Actor / ActorComponent 天然被父 UObject 强引用, 不需要 Ref / UnRef。

## 命名和格式

- 局部变量和参数使用完整表意的驼峰命名, 不使用 `cb` / `ctx` / `mgr` / `tmp` 等短缩写; 写作 `CallBack` / `Context` / `Manager` 等。循环游标 `i`, 二元迭代 `k, v`, 上下文显然的 `row` / `item`, 框架约定的 `self` 可以保留。
- 简单功能优先保持直线流程, 尽量少拆私有函数。只有逻辑被复用、分支复杂度明显升高、生命周期边界清晰, 或抽出后能显著降低阅读成本时, 才新增 helper。
- 成员缓存必须有后续使用理由。只缓存真正需要跨函数、跨帧或跨生命周期复用的状态; 初始化过程里的中间对象优先用局部变量, 不要为了“可能有用”保存成 `self.__Xxx`。
- 明确只处理单个目标时, 不要写循环再 `break`。对 `TArray` 这类容器先判断数量, 再显式取第一个元素处理, 例如 `if Actors:Num() > 0 then Actor = Actors:Get(1) end`。
- 函数名里的 `Get` 只用于无副作用的读取或计算。会查找对象、创建对象、缓存成员、绑定监听、修改可见性或初始化状态的函数, 改用 `Init` / `TryInit` / `Ensure` / `Refresh` 等能体现副作用的动词, 例如 `__InitBackgroundMeshComponent`。
- 布尔变量命名按当前命名风格走: 驼峰命名可以使用 `bUseXxx` / `bHasXxx`; 下划线命名不使用 `b_` 前缀, 改用 `use_xxx` / `has_xxx` / `is_xxx` / `enable_xxx` 等完整语义名。例如用 `use_flying_movement`, 不要写 `b_use_flying_movement`。
- `if ... then ... end` 不写在一行, 拆成三行, 即使 body 只有 `return` 一句。
- 连续卫语句之间不加空行; 只有从卫语句段落进入实际业务动作、或语义明显切到新段落时才空一行。
- 匿名 `function` / closure 一律用多行风格: `function(...)` 后换行, body 缩进, `end` 独占一行。哪怕 body 只有一句也不要写单行 `function() foo() end`。
- 不要用 `a and b or c` 表达二选一, 改用显式 `if / else`, 避免 `b` 为 `false` / `nil` 时误走 `c`。
- 遍历 `TArray` 统一使用 `pairs(arr)`, 不要用 `TArrayIterator`。
- 逗号后无论中英文都加一个空格: `func(a, b, c)`, 注释里也写 `..., 后续...`。
- 注释里中英文混用时, 中文和英文单词 / 标识符之间不加空格, 例如 `spawner完成同帧Agent还没MarkReady`。英文语境里的中文补充可按英文规则保留空格。

## 注释和类型标注

- 不要新增给人类阅读的英文注释。面向人阅读的注释默认用中文; 代码标识、外部协议、引擎/API 原文、既有英文上下文可保留。
- 如果文件里没有中文 debug 日志输出, 不要加 `--#ignore_file` / `#ignore_file`。
- 字段较多, 3 个及以上的纯 Lua table, 如果会通过函数参数传递, 必须用 `---@class` + `---@field` 写清 table 结构, 并在对应函数参数上用 `---@param Xxx ClassName @说明` 标注。
- table 参数注释风格参考:

```lua
---创建并显示界面的一些可选项配置
---@class PanelOptional
---@field IgnoreCinematicMode bool 即使在电影模式也要显示该界面 默认false
---@field SkipPushInCinematic bool 在电影模式中就跳过Push该界面 默认false
---@field BlockInput bool 在界面加载完成前或者淡入完成前阻挡用户输入 全屏界面默认为true, 其他界面默认false
---@field InsertHint UUserWidget|string|int 指示你的界面需要插入在栈中的哪个位置。如果存在提示的界面, 则新界面插入在提示界面之上, 否则置于栈顶
---@field Independent bool 是否独立控制UI的显隐, 默认为false

---@param Optional PanelOptional 可选项配置 @[opt]
```

## PaperEvent 和回调

- 反注册 `PaperEvent` 监听默认用 `self:UnregisterAllListenEvent()` 一把清, 不要一条条写 `self:UnregisterListenEvent(eventName, handler)`。仅当组件存在分段订阅, 中途主动 unregister 某个事件再重绑时, 才单独 `UnregisterListenEvent`。
- `RegisterListenEvent` / `UnregisterListenEvent` 调用写在一行, 不要为了对齐参数拆成多行。例: `self:RegisterListenEvent(PaperEvent.GamePlay.GiantCityPollution.AreaPolluteStateChanged, self.__OnAreaPolluteStateChanged)`。
- 对外暴露接口需要传入 callback 时, 按调用方区分两种风格:
- 纯 Lua 调用: 直接传 `function` 类型参数, 接口内部直接 `callback()` 调用。
- 需要被蓝图调用: 改用 `callbackTarget + callbackFuncName` 成对入参, 接口内部走 `callbackTarget[callbackFuncName](callbackTarget)` 派发。
- 同一接口若 Lua 和蓝图都会调用, 优先使用 `(target, funcName)` 兼容蓝图, 并在 Lua 侧文档化传 `self, "__OnXxx"` 的模板。

## 配置和模块服务

- UI界面需要忽略光标显隐影响时, 优先改版本分片 `X6Game/Content/Script/Config/UIConfig_Version/UIConfig_<major>_<minor>.lua`, 没有对应分片就新建并 `p4 add`, 不要为了版本内新增项改主文件 `UIConfig.lua`。使用新格式 `CursorState`, 例如 `[PaperResource.UI.Xxx] = PaperEnum.EUIControlCursorState.None`; `None` 表示该UI不控制光标显隐, `Show` / `Hide` 才表示主动控制。参考 `UIConfig_2_5.lua` 保留 `BlockInputActionUIPaths`、`IgnoreFocusUIPaths`、`ReentryWhiteList` 等空表结构即可。
- `PS.*ModuleService` 是模块服务单例, 默认常驻有效; 不要写 `if PS.XxxModuleService == nil then ... end` 这类判空。需要判断业务状态时, 调用对应 ModuleService 暴露的查询接口。
- 配置表数据 `self:GetDataCfg().TbXxx` 不要缓存成 `self.__xxxCfg` / `self.__xxxData` 类成员。每次用时直接访问, 或同一函数内局部缓存 `local Config = self:GetDataCfg().TbXxx`。
- `self:GetDataCfg().TbXxx` 默认有效, 不需要 `if Config ~= nil then ... end` 判空。拼写写错时直接报 nil 索引错误更利于暴露问题。
