---
name: ue-interactable-optimization
description: Optimize existing Unreal Engine interactables with Blueprint/Lua/AnimBP/SkeletalMesh/Collision/Tick performance concerns. Use when Codex is asked to analyze or improve an already-built UE interactable, especially if the task mentions 常态成本, Tick, AnimBP, Montage, Collision, Overlap, NPC/derived BP behavior, Trace/utrace profiling, P4 edits, or preserving current gameplay design while reducing cost.
---

# UE Interactable Optimization

Use this skill to optimize existing UE interactables without losing the original gameplay, animation, and level-design intent.

Detailed reference document:
https://papergames.feishu.cn/docx/DfuZdOpMxoGM3Vxw8ltcVGjgnHf

## Operating Rules

- Use `p4 edit` before modifying P4-tracked files.
- Put Codex changes into a dedicated pending CL, not the default CL.
- When changing this skill's optimization policy, also update the linked Feishu reference document in the same turn.
- Treat existing user or generated changes as intentional. Do not revert them unless explicitly asked.
- First document the current interactable logic; put optimization analysis in a separate section.
- Keep design unchanged unless the user explicitly approves design changes.
- When changing AnimBP state-machine behavior, first inspect original transition settings, Slot usage, notifies, blend settings, and interruption behavior.

## Workflow

1. **Map assets and inheritance**
   Identify the base BP, derived BPs, Lua/C++ scripts, AnimBPs, Montage assets, child actors/NPCs, collision components, and server/entity initialization path.

2. **Understand startup**
   Check `BeginPlay`, `ServerInit`, `OnBindEntity`, GameplayActor state machine callbacks, event binding, and local test paths. If a BP dragged into a map does not work, verify whether entity/server binding was bypassed.

3. **Define normal state**
   Separate:
   - idle with no player interaction,
   - self-running attract behavior such as NPC periodic jumps,
   - player interaction events,
   - broken/recover or special states.

4. **Analyze frame cost**
   Inspect every per-frame path:
   - Actor/component Tick,
   - Lua `ReceiveTick`,
   - spawned/child actor Tick,
   - SkeletalMeshComponent update,
   - AnimBP update/evaluate,
   - AnimNode exposed inputs or PropertyAccess,
   - collision/overlap updates.

5. **Prefer mechanism-equivalent optimizations**
   Good first passes:
   - Replace per-frame Lua tables/closures with explicit functions or override hooks.
   - Move one-shot transition animations from AnimBP state machines to Montages when behavior is unchanged.
   - Use direct `AnimInstance:Montage_Play(...)` when no callback is needed; avoid `CreateProxyObjectForPlayMontage`.
   - Keep stable poses in AnimBP; move one-shot starts/ends/breaks into explicit event-driven playback.
   - Replace EventGraph per-frame variable sync with event push or PropertyAccess when appropriate.
   - In Lua Tick hot paths, prefer project-side helpers such as `PaperMath.InterpTo` over `UE4.UKismetMathLibrary.FInterpTo` when behavior is equivalent, to avoid Lua-to-UE `UFUNCTION` call overhead.

6. **Audit collision carefully**
   Classify components as logic trigger, blocker, marker/target point, or visual mesh. Do not disable overlap on real logic triggers. Marker/target components often need their tag/transform but not Generate Overlap Events.

7. **Measure with comparable traces**
   Compare baseline and variant in the same map, view, instance count, and scenario. Split idle, self-running, player interaction, and recover/broken windows. Use union-style timing when nested timers would double-count.

## Output Shape

For non-trivial work, produce:

- current logic summary,
- hot paths and normal-state cost,
- proposed changes grouped by risk,
- implementation summary,
- verification performed,
- remaining risks or unverified editor/device steps.

## Animation Notes

- Montage migration should preserve original visual timing. Match original ABP crossfade duration and blend mode unless intentionally changing feel.
- Do not wait for a start Montage to end before switching logical/ABP state when the Montage is only an overlay for that transition.
- Do not add runtime Montage caches unless there is a measured need.
- Do not stop a Montage unless the original behavior required explicit interruption or the user asks for it.
