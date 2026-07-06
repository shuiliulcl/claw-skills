---
name: x6-euw-style
description: X6Game Editor Utility Widget and editor-tool UI workflow/style rules. Use when creating or modifying EUW/UMG editor tools under X6Game/Content/Editor/Tools, especially dynamic Lua-bound panels, InitDynamicPanels wiring, EditorUtilityWidgetBlueprint assets, button/text styling, layout overlap fixes, and ECA/ECABridge Blueprint inspection or editing.
---

# X6 EUW Style

Use this skill when working on X6 editor utility widgets, especially `EUW_*` tools and dynamically-created child widgets.

## Workflow

1. Read the workspace `AGENTS.md` and follow P4 rules before editing project files.
2. Use ECA/ECABridge first for Blueprint/Widget asset lookup, widget tree inspection, graph/function/node inspection, and UMG edits. Do not rely on broad binary searches for Blueprint assets when ECA can query them.
3. For EUW logic that needs Lua, follow the existing dynamic-panel pattern:
   - Keep the `EditorUtilityWidgetBlueprint` as the host.
   - Create a child `UserWidget` WBP under the editor tool's `WidgetData` area.
   - Add UnLua interface/module name on the child WBP.
   - In the host EUW `InitDynamicPanels`, `ClearChildren` on the container, `CreateWidget` the child WBP, then `AddChild`.
4. Compile and save every edited Widget Blueprint with ECA after UMG changes.
5. Re-check widget hierarchy and slot order with ECA `GetWidgets`.
6. If the widget is visible in editor, verify with a screenshot or user-provided screenshot when layout/overlap is in question.

## Source Control

- X6 project assets are P4-managed; use the correct client, such as `shuiliu_Stb_2.8` for `F:\shuiliu_Stb_2.8`.
- New `.uasset` and Lua files under the project should be opened/added in P4 promptly.
- Do not modify Toolset files with P4; Toolset is git-managed.

## Typography

Match existing editor utility widgets instead of using UMG defaults.

- Normal editor-tool text: copy style from `/Game/Editor/Tools/Utility/WidgetData/WBP_StateList.WBP_StateList:WidgetTree.TB_StateList` or `WBP_RejectLog`.
  - Font: Roboto Regular
  - Size: 8
  - Letter spacing: 0
  - Color: white
- Section headers: copy style from existing EUW headers.
  - State header example: `TB_StateLabel`, text format `── 当前状态 ──`, Roboto Regular 8, color `(0.6, 0.8, 1.0, 1.0)`.
  - Reject-log header example: `TB_LogLabel`, text format `── 拒绝日志 ──`, Roboto Regular 8, color `(1.0, 0.6, 0.4, 1.0)`.
  - New sections should use the same divider text format, for example `── 交互DA预览 ──`.
- Do not leave new TextBlocks at UMG defaults such as Roboto Bold 24.

## Buttons

Do not use default gray UMG `Button` styling in X6 EUW tools.

Preferred options:

1. Reuse `/Game/Editor/Tools/Utility/WidgetData/EUW_SimpleConsoleButton` when a simple editor command button fits.
2. For toolbar buttons that should match controls such as `Enable Ability` or `Common`, instantiate `EUW_SimpleConsoleButton_C` directly and bind to its inner `Button.OnClicked`; set the label through its inner `Text`.
3. If a custom child WBP must use a raw `Button`, copy the visual style from `EUW_SimpleConsoleButton:WidgetTree.Button` and `EUW_SimpleConsoleButton:WidgetTree.Text`.

Button style baseline:

- Button class/style source: `EUW_SimpleConsoleButton:WidgetTree.Button`.
- Visual: dark box brush, subtle hover/pressed variants, 4px rounded corners.
- Button text source: `EUW_SimpleConsoleButton:WidgetTree.Text`.
- Text: Roboto Regular 8, white.
- When adding a new button beside existing buttons in a custom child WBP, copy the text font and text color from a neighboring button TextBlock, not from body/detail text and not from UMG defaults.
- Text button slot padding: left 4, top 2, right 4, bottom 2.
- Text alignment: center horizontally and vertically.
- The existing `EUW_SimpleConsoleButton` size is `75 x 25`; match that footprint when the surrounding layout expects console-style buttons.

When copying complex `ButtonStyle` or `SlateFontInfo`, prefer ECA/editor reflection that copies the existing struct from the source widget. Generic property setters may update only part of a complex struct.

## Layout

- Prefer `VerticalBox`, `HorizontalBox`, `ScrollBox`, and `SizeBox` for editor-tool panels.
- Avoid `CanvasPanel` as a dynamic child root unless it has a stable desired size. A Canvas-root child may fail to reserve vertical space when added to a host `VerticalBox`, causing later sections to overlap.
- If a legacy dynamic child does not report desired height, reserve height in its host container slot or wrap it in a `SizeBox`.
- For repeated text logs, reserve enough space for the configured max line count.
- After adding a new section, check the actual host order. A typical order is:
  - command/tool controls
  - current task-specific preview or inspector
  - state/debug panels
  - logs
- Do not add large title fonts, oversized padding, or marketing-style cards to editor utility tools.

## Lua Child Widgets

- Place child Lua modules under `X6Game/Content/Script/Editor/Tools/Utility/Widgets` unless the surrounding tool has a more specific existing convention.
- Keep the child WBP module name aligned with existing editor tool modules, such as `Editor.Tools.Utility.Widgets.WBP_Xxx_C`.
- In Lua, follow `x6-lua-style`: use `UE`, use `_G.PaperScopeMgr:IsUObjectValid(...)` or a cached method form for UObject validity, and avoid `a and b or c`.
- Editor-only APIs such as `UEditorLevelLibrary`, `UEditorAssetLibrary`, or editor subsystems should stay in editor-tool Lua paths.
- For Content Browser locating while PIE may be running, prefer the project helper `UX6EditorBlueprintFunctionLibrary.FindInContentBrowser(packageName)`.
  - Pass the package name, for example `/Game/Path/Asset`, not the object path `/Game/Path/Asset.Asset`.
  - `UEditorAssetLibrary.SyncBrowserToObjects(TArray<FString>)` checks `IsInEditorAndNotPlaying()` and can silently no-op during PIE.
  - `UAssetToolsHelpers.GetAssetTools()` may be script-visible, but `SyncBrowserToAssets` is not reliably exposed to Lua/Python in this workspace.

## Verification

Before finishing, report:

- Which WBP assets were compiled/saved by ECA.
- Which widgets/slots were inspected or changed.
- P4 opened state for touched project files.
- Any runtime limitation, such as not testing Lua `Construct` because PIE/UnLua state was unavailable.
