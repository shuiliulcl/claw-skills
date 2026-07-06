---
name: lua-code-writing
description: Lua code writing and review preferences for project gameplay scripts. Use when editing, reviewing, or proposing Lua code, especially Unreal/UnLua gameplay scripts, timers, state machines, animation callbacks, tick optimization, and interaction logic.
---

# Lua Code Writing

## Core Style

- Prefer simple, explicit control flow over table dispatch when the state set is small and hot-path performance matters.
- Keep functions short and named by intent, for example `__StartIdleTimers`, `__ClearIdleTimers`, `__ShowIdleBubble1`, and `__OnIdleJumpTimer`.
- Do not add defensive nil checks when an asset or reference is guaranteed by design and the user has said it does not need protection.
- Do not keep migration flags, compatibility branches, or old delayed fallbacks after the old path is intentionally removed.
- Avoid return values on command-style helpers when callers do not need them.

## Tick And Timer

- Avoid per-frame polling for scheduled behavior when timers can express the intent.
- For idle sequences, prefer enter and exit scheduling:
  - On entering the state, create timers and cache handles.
  - On leaving the state, clear cached timer handles.
  - Timer callbacks may still verify the current state to guard against queued callbacks.
- Use Tick only for genuinely frame-dependent behavior, such as curve-driven movement.
- Avoid creating temporary tables, closures, or unnecessary objects in Tick hot paths.

## State Machines

- Treat state variables as logic state, not animation state, unless an AnimBP still consumes them.
- If an AnimBP no longer reads a variable, keep it only when Lua gameplay logic still needs it.
- Make state transitions reset state-local timers, counters, queued next-state data, and other local state.
- Return immediately after a state transition when continuing the old state's logic would cause duplicate side effects.

## Animation And Montage

- Keep Montage section-link behavior in the Montage asset, not in Lua runtime code.
- Lua should decide when to play, jump sections, or accept notifies; the asset should express links such as `Start -> Loop`, `Loop -> Loop`, and `End -> None`.
- When migrating AnimBP state-machine transitions to Montages, preserve timing:
  - A jump notify starts Lua height or gameplay logic.
  - Lua curve completion decides when to jump to the end section.
  - A land notify should not end logic before Lua has requested the end section.
- Prefer direct command calls such as `Montage_JumpToSection` when no result is needed.
- Remove old delayed fallback calls once notifies are authoritative.

## Timers

- Prefer cached timer handles over token-only invalidation when the project timer API supports handles.
- Clear timers when leaving the owning state, during EndPlay or teardown, and when switching into interrupting states.
- Clamp or skip negative delays when scheduling relative timers such as `IdleTime - 2`.

## Review Heuristics

- Check whether behavior changed before judging whether the code is cleaner.
- For animation bugs, compare the Lua timeline, Montage sections, notifies, curve keys, and ABP slot or state usage together.
- Use ECA or ECABridge read-only inspection for Blueprint, Montage, CurveFloat, and AnimBP assets when available.
- Do not rely only on binary string grep when ECA can read reflected properties.
- When the user asks for analysis only, do not modify files.
