# 独立关卡重登恢复进度

## 关键飞书文档

- 独立关卡常用信息总结: https://papergames.feishu.cn/wiki/ENBNw9FsSiFBkkkGcP7cuO7ynfb
- 【1.2】独立关卡进度存储迭代: https://papergames.feishu.cn/wiki/HKK1dkdyFoCsxgxdXgccXy6JnPb
- 【规范】独立关卡Graph说明和配置: https://papergames.feishu.cn/wiki/QOD4wWo5Iiq30Bk3VkecXVnmnlg
- 独立关卡离线重登状态存储: https://papergames.feishu.cn/wiki/UA6UwPjPHigQqpkHfx4cTWmnnef
- 独立关卡制作checklist: https://papergames.feishu.cn/wiki/FzCOwGWMyirrvFkA89VcaxRWnsf
- 独立关卡常用GM：由“独立关卡常用信息总结”的 TeleportTag 章节引用。

## 代码路径

- `X6Game/Content/Script/Logics/LevelData/LevelDataModule.lua`
  - 恢复、保存、清理独立关卡进度的主逻辑。
  - 重要函数：
    - `GetLevelProcess`
    - `SetLevelProcess`
    - `HasPendingSaveDataByTeleportTag`
    - `ShowPendingSaveDataMessageBox`
    - `OnLeaveIndependentLevelEnd`
    - `CheckIndependentLevelDataConsistency`
    - `SetReplayIndepentLevel`
    - `__TryUpdateCheckpointBGM`
- `X6Game/Content/Script/Logics/LevelData/LevelDataModuleService.lua`
  - 对外暴露恢复进度相关服务接口。
- `X6Game/Content/Script/GameBP/Dialogue/CustomerNode/BP_EnterIndependentLevel_C.lua`
  - 对话进入独立关卡节点；已封装“是否恢复未完成进度”的弹窗。
- `X6Game/Content/Script/UI/SysChallenge/Portal/PortalIndependentViewModel.lua`
  - Portal 入口路径；检测未完成进度并弹出恢复提示。
- `X6Game/Content/Script/Logics/CheckPoint/CheckPointModule.lua`
  - 检查点数据和检查点传送依赖。
- `X6Game/Content/Script/UI/SysChallenge/PC/WidgetBp/HUD/WBP_Challenge_HUD_IndependentLevel_C.lua`
  - PC 侧离开/传送 UI 和保存进度提示。
- `X6Game/Content/Script/UI/SysChallenge/Mobile/Widget/HUD/WBP_Challenge_HUD_IndependentLevel_Mobile_C.lua`
  - Mobile 侧版本。
- `X6Game/Content/Script/UI/SysChallenge/Console/HUD/WBP_Challenge_HUD_IndependentLevel_Console_C.lua`
  - Console 侧版本。
- `X6Game/Content/Script/Logics/LevelData/LevelProcessor/`
  - 单关特殊恢复处理，例如 `LevelProcessor_3010208.lua`。
- `X6Game/Content/Script/Config/EventConfig.lua`
  - `IndependentLevelLevelProcessChange`, `IndependentLevelCheckpointChange`, `IndependentLevelDataInitialized`.
- `X6Game/Content/Script/Config/ResConfig.lua`
  - `DT.DT_IndependentLevelBGMRecover`.

## 恢复模型

独立关卡状态保存在服务器上。进入关卡时默认恢复进度；只有客户端主动发送 `CClearIndependentLevel` 时，进度才会清空。

保存的状态类型：

1. Graph 进度。它是最重要的恢复依据；弱网冲突时，以 Graph 进度为准恢复其他状态。
2. 最后一次触碰的检查点。
3. 交互物状态。
4. `LevelProcess`.

如果玩家恢复到了预期外检查点，系统会使用独立关卡检查点恢复表里的保底数据：

`//root/game/designconfig/DesignerConfigurations/map/独立关卡检查点恢复表.xlsx`

## 入口流程

- 通用传送门如果走公共路径，已经接入“恢复进度或重新开始”的弹窗。
- 对话进入独立关卡时，使用“对话结束后进入独立关卡”节点；实现文件是 `BP_EnterIndependentLevel_C.lua`。
- 新做自定义入口时，要接入 `HasPendingSaveDataByTeleportTag` 和 `ShowPendingSaveDataMessageBox`；如果刻意绕过恢复弹窗，需要明确记录原因。

## 排查

- 从大世界重新进入却没有提示“有未完成关卡进度”时，先确认关卡入口的隐形检查点是否被触发。
- 开启网络消息调试，进入独立关卡后查看是否收到 `SNotifyIndependentLevelInfo`，并确认其中包含独立关卡 ID 和检查点 ID。
- 恢复进度时的 BGM 由 `DT_IndependentLevelBGMRecover` 和 `__TryUpdateCheckpointBGM` 处理。

## 常用搜索

```powershell
rg -n "恢复进度|SaveData|PendingSaveData|CheckIndependentLevelDataConsistency|CClearIndependentLevel" X6Game/Content/Script
rg -n "IndependentLevelCheckpointChange|IndependentLevelLevelProcessChange|IndependentLevelDataInitialized|DT_IndependentLevelBGMRecover" X6Game/Content/Script
```
