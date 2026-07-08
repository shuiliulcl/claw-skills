---
name: x6-ue-visibility-debug
description: Debug Unreal Engine and X6Game PIE/runtime visibility problems for Actors, StaticMesh/SkeletalMesh components, Niagara effects, materials, culling, bounds, LOD, Level Streaming or World Partition loading, Blueprint call chains, Lua events, and spawner/entity lifecycle. Use when something is invisible, disappears by distance, appears only near the camera, has empty Niagara or material parameters, or may not be initialized by Blueprint/Lua/spawner logic.
---

# X6 UE Visibility Debug

## First Principle

Classify an invisible object by evidence, not by the first visual guess.

Use this order:

1. Level or streaming cell is not loaded or visible.
2. Actor does not exist in the PIE/runtime world.
3. Actor exists but is hidden, in the wrong level, or has an unexpected transform.
4. Render component exists but is hidden, inactive, unregistered, culled, or has invalid bounds.
5. Render component exists but runtime data is empty: mesh asset, material, Niagara user params, DI arrays, spawn count, animation pose, or dynamic material params.
6. Runtime data exists but an upstream Blueprint, Lua event, spawner, async callback, or state machine did not initialize or later overwrote the visual state.

Report findings in that same order.

## Tool Order

Prefer ECA/ECABridge dedicated tools when they exist. Use `UcpToolset.ExecutePython` when the task needs a custom runtime sweep, such as walking all levels, streaming levels, actors, components, Niagara arrays, or dynamic material parameters in one pass.

For `BP_Xxx_C`, search Lua under `X6Game/Content/Script` before assuming the Blueprint owns all gameplay logic. Use ECA for Blueprint asset, graph, function, variable, and runtime inspection before relying on binary asset searches.

For UE console commands, cvars, engine APIs, Niagara internals, or exact property names, verify against the current workspace engine source under `UnrealEngine/Engine/`.

## Runtime Checklist

### 1. World, Level, And Streaming

Start above the Actor. A missing Actor may be a level streaming problem rather than a spawn problem.

Check:

- Current PIE/game world vs editor world.
- Persistent level name and path.
- `world.get_levels()` loaded levels.
- `world.get_streaming_levels()` entries.
- Each `ULevelStreaming` state:
  - `is_level_loaded()`
  - `is_level_visible()`
  - `should_be_loaded()`
  - `should_be_visible()`
  - `get_loaded_level()`
  - loaded level actor count.
- Actor owning level with `actor.get_level()`.
- Whether the target Actor's expected level is absent, loaded but invisible, or loaded and visible.

If the project uses World Partition or custom streaming/spawner systems, also inspect loaded cells, streaming sources, grid ranges, and project-specific spawner/entity binding tables when available.

### 2. Actor Existence And Ownership

In the PIE/runtime world, enumerate by class, name, tag, spawner id, or expected location.

For each candidate Actor, record:

- Name, class, path, and owning level.
- Location, rotation, scale, and attachment parent.
- `is_hidden()`, `is_hidden_ed()`, `SetActorHiddenInGame` effects if visible through properties.
- Lifespan, pending kill/destroy state, and BeginPlay state when accessible.
- Relevant gameplay state fields: current state enum, switch booleans, arrays, object ids, spawner ids.

For X6 spawner-driven content, distinguish these cases:

- Config/spawner id exists but no runtime Actor.
- Runtime Actor exists but is not bound in the spawner/entity table.
- Async actor lookup only registered a pending callback.
- Actor exists but the dependent upstream Actor is missing.

### 3. Render Component State

For StaticMesh, SkeletalMesh, Niagara, particle, and custom render components, inspect:

- Component exists and is attached to the expected parent.
- `visible`, `hidden_in_game`, active/tick state, registered state, render state.
- Owner hidden state and parent hidden state.
- Bounds origin, extent, sphere radius, and whether bounds are unexpectedly tiny, zero, or far from the Actor.
- Cull distance, desired max draw distance, LOD settings, visibility based animation tick, and significance settings.
- Asset references: mesh, skeletal mesh, Niagara system, materials, animation instance.

If the component is hidden, inactive, unregistered, or has bad bounds, do not jump to Blueprint/Lua yet. First explain the component-level failure.

### 4. Runtime Render Data

If the component is alive and visible, inspect the data it uses at runtime.

For Niagara:

- System asset, component active state, and auto activate.
- User params that control spawn or geometry.
- Niagara data interface arrays with `NiagaraDataInterfaceArrayFunctionLibrary`.
- Spawn count or equivalent user params.
- Fixed bounds, local bounds, and culling settings.

For Mesh and material:

- Mesh asset and section count.
- Material slots and dynamic material instances.
- Opacity, alpha clip, dither, dissolve, scalar/vector params, runtime material overrides.
- LOD currently selected if accessible.

For SkeletalMesh:

- Skeletal mesh asset.
- Anim instance class and current animation state if accessible.
- Master pose / leader pose / copy pose links.
- Visibility based anim tick settings.

### 5. Manual Minimal Write Test

When the source Actor has data but the render component has empty runtime params, perform a safe minimal write test if the user accepts runtime probing or PIE can be restarted.

Examples:

- Copy Actor source arrays into Niagara `StartPositions` / `EndPositions`.
- Set Niagara `SpawnNum` from a source array length.
- Set a material opacity or dissolve param to a visible known-good value.
- Assign a known-good mesh/material only in PIE when this is safe.

Interpretation:

- Manual write makes it visible: parameter names, component receiving path, and data format are valid; normal update path did not run or was overwritten.
- Manual write changes params but not visuals: continue with bounds, culling, material, system logic, or asset issues.
- Manual write fails: verify parameter names, data interface type, component validity, asset setup, or API mismatch.

Do not leave manual runtime changes as a fix. Use them as evidence to locate the real owner of initialization.

### 6. Blueprint Call Chain

Use ECA to inspect the Blueprint graph after runtime evidence shows data is missing or the update function did not run.

Find:

- Function that writes render data.
- All callers of that function.
- Event dispatchers, interfaces, timers, timelines, latent actions, and state machine transitions.
- Parent class calls in overrides.
- Whether Construction Script, BeginPlay, PostSpawnerGroupSpawned, OnStateChange, or custom events are expected to initialize visuals.

Validate with breakpoints or temporary logs:

- Did the visual update function execute?
- Did the upstream state event execute?
- Did the parent implementation run?
- Did a later event clear or overwrite the params?

### 7. Lua, Spawner, And Entity Upstream

If Blueprint entry points are not reached, move upstream.

For X6/UnLua, inspect:

- Lua class binding for the Blueprint.
- `ReceiveBeginPlay`, registration, and event subscription logs.
- `PaperEvent` or project event dispatcher paths.
- Entity/spawner service queries by spawner id.
- Binding tables such as project-specific spawner actor maps.
- Async lookup callbacks and whether they are pending.
- Config existence vs runtime actor existence.

Keep logs on by default when the user requests debug logging in this context. Prefer concise tagged logs that include Actor name, spawner id, current state, ring/visible state, and whether the call is initialization or event-driven.

## Symptom Shortcuts

### Near Visible, Far Invisible

Prioritize:

- Level Streaming or World Partition not loaded/visible.
- Spawner/entity not generated at distance.
- Cull distance, HLOD, LOD, significance, bounds, and Niagara fixed bounds.
- Initialization event only fired when an upstream Actor streams in.

### Editor Visible, PIE Invisible

Prioritize:

- Runtime hidden flags.
- BeginPlay or Lua initialization clearing params.
- Dynamic material or Niagara user params not written.
- Runtime asset reference missing because soft load or cook reference differs.

### Actor Exists, Component Alive, Params Empty

Prioritize:

- The update function did not run.
- Source data lives on the Actor but was never copied to the render component.
- Upstream event, state sync, or async callback did not fire.
- A later call cleared the params.

### Actor Missing

Prioritize:

- Wrong world selected for inspection.
- Level/cell not loaded or visible.
- Spawner config exists but runtime binding missing.
- Actor spawned only near the camera or only after dependency initialization.

## Evidence Report Template

Use this compact shape in final/debug updates:

```text
World/Level:
- PIE world: <name/path>
- Target level: loaded=<bool>, visible=<bool>, should_load=<bool>, should_visible=<bool>

Actor:
- Found: <yes/no>
- Actor: <name/class/path>
- Owning level: <level path>
- Hidden/transform notes: <...>

Component:
- Component: <name/class/asset>
- Visible/active/registered/render state: <...>
- Bounds/cull notes: <...>

Runtime data:
- Source data: <fields and lengths/values>
- Render params: <fields and lengths/values>
- Manual write result: <if performed>

Call chain:
- Writer function: <function>
- Expected callers: <callers>
- Runtime evidence: <breakpoint/log/probe result>

Conclusion:
- Bucket: <level/actor/component/params/upstream>
- Next validation or fix: <one sentence>
```

## Case Pattern: Niagara Array Empty But Source Actor Has Data

This pattern is common for procedural effects.

Evidence to collect:

- Niagara component is active and visible.
- Source Actor arrays have non-zero length.
- Niagara user arrays are zero length.
- Manual write from source arrays to Niagara arrays succeeds.
- Blueprint writer function exists but is not reached.
- Upstream event or spawner Actor is missing at distance.

Conclusion:

The effect is not primarily a render culling issue. The normal initialization path failed before render data reached Niagara. Continue upward to Blueprint/Lua/spawner/level streaming.
