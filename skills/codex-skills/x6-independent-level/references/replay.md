# 独立关卡复玩

## 关键飞书文档

- 【2.3】活动系统_独立关卡复玩: https://papergames.feishu.cn/wiki/DgkVwqVzPi8OFHkcAr4cJSEen9c
- 2.3 独立关卡复玩 活动总览+活动复玩+独立挑战【接入说明】: https://papergames.feishu.cn/wiki/GvMewh63RiouqNksmZXc4lW4nGf
- 【2.6】活动系统_独立关卡复玩优化: https://papergames.feishu.cn/wiki/BTdvw63HIi7FazklvM9c76HXn9Y
- 2.6 独立关卡复玩 藏宝图【接入说明】: https://papergames.feishu.cn/wiki/QaYFw4Hq2i4C7Pkd8UPcY0BQn6b
- X6_底层系统_条件池百科: https://papergames.feishu.cn/wiki/wikcn5jOTmXTo3VnD4Y3eC5DY3e#HCf5dWgQUo2m48xzC54ccGjmnqd
- 独立关卡常用信息总结: https://papergames.feishu.cn/wiki/ENBNw9FsSiFBkkkGcP7cuO7ynfb

## 代码路径

- `X6Game/Content/Script/GF/GF_EM_35_03/UI/LevelReplay/`
  - 2.3 活动复玩 UI 和辅助逻辑。
  - 重要文件：
    - `LevelReplayGamePlaySetHelper.lua`
    - `Widget/Main/WBP_35_03_LevelReplay_Main_C.lua`
    - `Widget/Main/WBP_35_03_LevelReplay_PopUp_C.lua`
    - `Widget/Main/WBP_35_03_LevelReplay_LevelChallenge_Main_C.lua`
    - `Widget/WBP_LevelReplay_GamePlaySet_Main_C.lua`
    - `Widget/WBP_LevelReplay_GamePlaySet_Item_C.lua`
- `X6Game/Content/Script/GF/GF_EM_35_03/UI/CheckInPoint/`
  - 复玩拍照打卡 UI.
- `X6Game/Content/Script/Logics/LevelData/LevelDataModule.lua`
  - `SetReplayIndepentLevel(LevelID, bReplay)` 设置复玩状态。
  - 清进度/重置流程里会发送 `CClearIndependentLevel`。
- `X6Game/Content/Script/Logics/LevelData/LevelDataModuleService.lua`
  - 对外暴露 `SetReplayIndepentLevel`。
- `X6Game/Content/Script/Logics/EventMap/EventMapSubfeatureMgr/`
  - `LevelReplayTaskSubfeatureMgr.lua`
  - `LevelReplayCollectStarSubfeatureMgr.lua`
  - `LevelReplayTreasureSubfeatureMgr.lua`
  - `LevelReplayCheckInPhotoSubfeatureMgr.lua`
- `X6Game/Content/Script/Config/EventConfig_Version/EventConfig_2_3.lua`
  - `PaperEvent.GamePlay.LevelReplay.Event_LevelReplayCheckInRewarded`.
- `X6Game/Content/Script/Config/PaperBPEnumConfig.lua`
  - `LevelReplayTask`, `LevelReplayCollectStar`, `LevelReplayTreasure`, `LevelReplayCheckInPhoto`.
- `X6Game/Content/Script/GenV2/Cfg/CfgTypes.lua`
  - 生成的配置结构：`LevelReplayGameSet`, `LevelReplayPhotoInfo`, `LevelReplayCheckInPhoto`, `LevelReplayTreasure`。

## 条件池锚点

这些条件在条件池百科里有说明，并出现在 `GenV2/Cfg/CfgTypes.lua` 生成结构中。实现可能在 C++ 或生成逻辑里，不一定有手写 Lua 文件。

- `InIndependentReplay`：独立关卡复玩中。
- `IndependentNotPassOrReplay`：目标关卡未通关或正在复玩中。
- `InIndependentStandardPlay`：目标关卡处于标准游玩，不是复玩；按文档语义，会排除未通关和通关后二周目的情况。

## 行为注意

- `WBP_35_03_LevelReplay_PopUp_C.lua` 会通过 `PaperEvent.Net.map.CClearIndependentLevel` 清掉独立关卡进度，然后调用 `PS.LevelDataModuleService:SetReplayIndepentLevel(self.LevelReplayID, true)`。
- 复玩活动模块接入在 EventMap 子活动体系里，改逻辑前要先确认活动配置。
- 不要把“重试”和“复玩”混成同一件事。重试通常是当前挑战重置；复玩是活动入口或二周目独立关卡流程。

## 常用搜索

```powershell
rg -n "LevelReplay|SetReplayIndepentLevel|CClearIndependentLevel|Event_LevelReplayCheckInRewarded" X6Game/Content/Script
rg -n "IndependentNotPassOrReplay|InIndependentStandardPlay|InIndependentReplay" X6Game/Content/Script
```
