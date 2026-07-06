# 独立关卡辅助道路

## 关键飞书文档

- 【规范】独立关卡辅助道路配置和测试: https://papergames.feishu.cn/wiki/HwndwMggmixGG4kDwgHcXdHxnIe
- 辅助道路模型编号: https://papergames.feishu.cn/sheets/E7mtsYSEshyYx5tibrVcEHiznQc
- 独立关卡_检查点辅助道路关联+特效生成: https://papergames.feishu.cn/wiki/HIdXdyNKfodKTjx91yOcWuyvnUg
- 相关引用: 关卡静态资产设置Layer说明, 交互物进阶20：让交互物沿着指定轨道运动

## 代码路径

- `X6Game/Content/Script/Logics/LostAssister/LostAssisterModule.lua`
  - 主逻辑：迷路检测、NPC 引导、辅助道路 Layer 显示、出现特效、次数统计。
  - 关键函数：`StartCheckToSpawn`, `__OnCheckLostLoop`, `ShowCurrentRoomSubsidiaryPlatforms`, `__ShowLayer`, `PlayAppearEffect`。
- `X6Game/Content/Script/Logics/LostAssister/LostAssisterModuleService.lua`
  - 服务接口：`ShowCurrentRoomSubsidiaryPlatforms`, `AddTodayAssisterCount`, `ReqGetTodayAssisterCount`。
- `X6Game/Content/Script/Logics/LostAssister/IndependentLevelSkipProcessor.lua`
  - 独立关卡跳过/迷路提示处理器，同属 LostAssister 体系。
- `X6Game/Content/Script/Config/LostAssister/IndependentLevelSkip/WBP_IndependentLevelSkipV0_C.lua`
  - 跳过提示 UI 逻辑。
- `X6Game/Content/Script/Config/ResConfig.lua`
  - `DA.DA_LostAssisterConfig`
  - `DT.DT_Checkpoint2SubsidiaryPlatform`
- `X6Game/Content/Script/Logics/FuncEventNode/FuncEventNodeModule.lua`
  - `ShowCurrentRoomSubsidiaryPlatforms` 的函数节点触发点。

## 资产和配置锚点

- `DA_LostAssisterConfig`: `/Game/Config/LostAssister/DA_LostAssisterConfig.DA_LostAssisterConfig`
- `DT_Checkpoint2SubsidiaryPlatform`: `/Game/Config/LostAssister/DT_Checkpoint2SubsidiaryPlatform.DT_Checkpoint2SubsidiaryPlatform`
- 移动平台 BP：`/Game/Assets/W01/W01_A01_Shared/Interactables/INT_Bldg_Platform_42/GPP/BP_LevelAssistanceMovingPlatform.BP_LevelAssistanceMovingPlatform`
- Lua 中引用的特效管理类：`ABP_SubsidiaryPlatformEffectManager_C`

## 实现注意

- 辅助道路目前主要用于主线独立关卡，不默认覆盖关卡挑战、重组关卡等；不要擅自扩大语义。
- 道路模块默认应勾选隐藏，并在显示前关闭碰撞。
- 移动平台碰撞由 BP 处理；除非 BP 契约变化，否则不要让策划手动改碰撞语义。
- LostAssister 通过 `AcceptSubsidiaryPlatformDistance` 判断玩家是否足够接近辅助道路，从而进入检测。
- 检查点和辅助道路 Layer 的关联来自 `DT_Checkpoint2SubsidiaryPlatform`。

## 常用搜索

```powershell
rg -n "LostAssister|SubsidiaryPlatform|辅助道路|DT_Checkpoint2SubsidiaryPlatform|DA_LostAssisterConfig" X6Game/Content/Script
rg -n "ShowCurrentRoomSubsidiaryPlatforms|PlayAppearEffect|AcceptSubsidiaryPlatformDistance" X6Game/Content/Script
```
