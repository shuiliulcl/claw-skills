---
name: ue-interactable-collision-audit
description: Audit Unreal Engine interactable Blueprint collision and overlap settings. Use when Codex needs to inspect a BP/uasset interactable, list every component's Generate Overlap Events and collision configuration, identify marker/trigger/blocking/mesh components, and judge whether overlap or collision settings are probably necessary, redundant, or risky.
---

# UE Interactable Collision Audit

## Workflow

1. Normalize the requested Blueprint into a `/Game/...` asset path or object path.
2. Run `scripts/inspect_interactable_bp_collision.py` inside the open UE editor with `UcpToolset.UcpToolset.ExecutePython`.
3. Prefer writing the full Markdown/JSON report to `Saved/CollisionAudit` or a user-specified temp folder, then summarize only the high-signal findings in chat.
4. Explain necessity using evidence from the report: component type, tags, transform, collision profile, channel responses, text references in `Content/Script` / `Source`, and naming intent.

## Editor Invocation

Use one MCP call that loads and executes the bundled script:

```python
script_path = r"C:\Users\banqiang\.codex\skills\ue-interactable-collision-audit\scripts\inspect_interactable_bp_collision.py"
BP_ASSET_PATH = r"/Game/Path/To/BP_Example.BP_Example"
OUTPUT_DIR = r"F:\shuiliu_Dev_2.8\Temp\CollisionAudit"
SCAN_TEXT_REFERENCES = True
exec(open(script_path, "r", encoding="utf-8").read())
```

For a raw `.uasset` path, pass the full filesystem path as `BP_ASSET_PATH`; the script attempts to convert it to a `/Game/...` asset path.

## Analysis Rules

- Treat `Generate Overlap Events` as necessary only when the component is configured to overlap at least one relevant channel and there is evidence of overlap use: component name references, tag references, trigger naming, or known gameplay role.
- Treat hidden primitive components with `Block` responses and no overlap responses as blocking proxies; they usually do not need overlap generation.
- Treat components tagged `TargetLocation`, named like `JumpTarLocation`, or used only through `GetComponentsByTag(..., "TargetLocation")` as marker components. Keep the component class if code searches by class, but collision and overlap can usually be disabled.
- Treat components named like `GainWeightTrigger`, `DetectiveCollision`, `LaunchCollision`, or `Trigger` as likely overlap volumes. Verify they are referenced or have overlap binding before recommending changes.
- Do not recommend deleting a component solely because text references are absent; Blueprint graphs, native code, or data-driven systems may still use it. Phrase those as "needs Blueprint graph confirmation."
- When a component has `CollisionEnabled = NoCollision`, any overlap generation setting is ineffective.
- When a component has no overlap channel responses, `Generate Overlap Events` is usually redundant even if enabled.

## Output

Match the user's language in the final response. For Chinese-speaking users, summarize:

- global collision statistics: enabled modes, profiles, object types, and channel responses
- items whose overlap events can probably be disabled
- items whose overlap events should be kept
- items that should keep only blocking/query collision
- items that need Blueprint graph confirmation
- concrete risk notes, especially class/tag coupling such as `GetComponentsByTag(UCapsuleComponent, "TargetLocation")`
