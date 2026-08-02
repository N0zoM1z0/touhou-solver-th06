# TH06 Handoff

## What we are doing

First make TH06 1.02h Hard reliably clearable; ignore Lunatic for now. Start
with the simplest correct baseline and let physical counterexamples determine
what gets added next. Do not recreate TH08 or turn this into a software-
engineering project.

The working idea has three strict layers:

1. **Hard safety authority:** only actions certified safe may execute.
2. **Adaptive solver:** spend measured compute budget progressively without
   weakening safety or mapping scene features to a strategy.
3. **Learning proposal/ranking:** learning may rank only inside the safe set;
   it is currently disabled until the general solver is physically stable.

This separation is the idea; the algorithms are intentionally not fixed.

## Current baseline

- Exact EXE SHA-256:
  `9f76483c46256804792399296619c1274363c31cd8f1775fafb55106fb852245`
- Ignored local source: `reference/GensokyoClub-th06/`, initially pinned at
  `cc475a0bc3fef38683b0f02224c87ddba0a021d9`
- Runtime-only no-life-decrement patch: VA `0x428DEC`, byte `01 -> 00`
- Hard/Reimu-A menu start and independent dialogue skipping work physically.
- Hard Practice Stage 1 now reaches its source-defined result path and stops
  cleanly with no death or Bomb. The complete run reached frame 12567, decoded
  up to 422 bullets and 6 simultaneous lasers, and used the native C++ safety
  kernel. Input pickup and hazardous-state decision intervals remain bounded
  to two observed frames each. A later pickup-aware repair rerun also completed
  at frame 11383 with no death, authority stop, or Bomb after the two-segment
  proposal began covering both command pickup windows.
- Hard Practice Stage 2 also completes without a death or Bomb after adding
  source-layout enemy-body sensing. It covered up to 20 simultaneously lethal
  enemy bodies and 334 bullets; current bodies now participate in hard safety.
- A second complete Stage 2 validation now serializes physical movement
  commands until native pickup, uses non-blocking dialogue edges, and shares
  one native hazard rollout between hard and soft scans. It sampled 15,984
  states with no death or authority stop; hazardous and dialogue decision gaps
  were at most two and one frames respectively.
- A post-Stage-4 full-route regression exposed three active lasers appearing
  in previously empty pool slots. A source-shaped radial envelope now proves
  a newborn short beam unreachable at every possible angle for Hard-4 or fails
  closed; the next frame resumes slot-based motion tracking. The focused
  Practice Stage 2 rerun then completed again without HIT, Bomb, or stop.
- Hard Practice Stage 3 now also reaches its source-defined result path. Its
  17,962 sampled states had no death, authority stop, or Bomb and covered up to
  615 bullets and 19 lethal enemy bodies. Source-exact timed direction-change
  bullets, delivery-aware soft effort, and a hard-set-only two-segment proposal
  were each added only after separate physical counterexamples.
- Hard Practice Stage 4 now reaches its source-defined result path too. The
  successful run sampled 23,674 states through frame 24520 with no HIT,
  authority stop, or Bomb, covering up to 637 bullets, 8 lasers, and 8 lethal
  enemy bodies. Its physically found fixes remain narrow soft-ranking and
  delivery changes; Hard-4 eligibility is unchanged.
- The old density, boundary, laser, and CE-shaped adaptive gates have now been
  removed. The replacement always computes Hard-4 first, then climbs a
  measured-cost 6/8/12/16 frontier one rung at a time. An affordable h8
  two-segment MPC proposal is a normal rung because action count alone cannot
  reveal dynamically aliased states. Once the constant-action frontier starts
  shrinking, the same recursive policy-volume search may deepen to h12/h16;
  each rung is admitted by its recent horizon-specific measured cost and
  remaining deadline. Old deep-rung samples decay continuously toward a
  prediction from the freshly measured lower rung, so a past expensive scene
  cannot disable that rung indefinitely. Earlier stage clears do not physically
  validate this replacement, so validation restarts at Stage 1.
- Constant and turn-capable work is interleaved by rung: c6, c8, p8, c12,
  p12, c16, p16. This prevents a complete distant constant scan from consuming
  the deadline before the ordinary p8 proposal. An unaffordable policy rung
  disables deeper policy work for that decision; it cannot be skipped over.
- The first restarted Stage 1 trial then stopped safely at f8609 on an ECL
  `MOVERANDINBOUND` followed by a 120-frame timed move. The hard envelope had
  applied the entire unknown endpoint radius on the setup frame. It now grows
  by source easing progress and encloses sampled exact RNG paths; the focused
  corpus is fixed, but the integrated change still awaits physical rerun.
- A later Stage 1 run stopped at a real current-bullet dead end at f6986. At
  f6963, physical execution had only afforded p8 and chose up-right; saved-state
  p12 uniquely chose down. Interleaving the same existing rungs reproduces the
  deeper proposal within budget. This scheduling change also awaits rerun.

Known gaps include future ECL births/instructions, a guaranteed command lease
beyond the observed two-frame pickup bound, and physical coverage of Stages 5--6.
Stage 3 also observed rare three-frame hazardous decision and snapshot-to-issue
ages, so the four-frame authority is not yet a complete delivery guarantee.
Actual replay file creation also still needs a non-Practice result. This is a
Stage 4 checkpoint, not proof of a route clear. See `README.md` for compact
details and the module map.
Use `notes/TH08_CE_GUIDE.md` only as a warning list when a matching TH06
counterexample appears; do not recreate the TH08 architecture from it.
See `OPTIMIZATION_STRATEGY.md` for the short list of measured optimizations and
unconfirmed candidates.

## How to continue

Run Hard Practice Stage 1 with the new general solver and stop on its first
HIT/authority CE or its source-defined result path. Explain one concrete
failure from native state and source, make one small general change, run the
focused check, then test it physically. Do not restore a feature threshold or
CE-specific branch to regain an earlier clear.

```bat
run_th06_baseline.bat --seconds 120
run_th06_practice.bat --practice-stage 1 --seconds 120
run_th06_observe.bat 30
```

The exact game does not offer replay saving after Practice: its source sends a
Practice result directly back to the main menu. Validate replay saving only on
a non-Practice result screen. The full-run launcher reserves the first empty
slot and validates the written replay before exit. Every launcher stops the
exact verified trial process after releasing input.

```bash
./build_th06_native.sh
./check_th06_baseline.sh
```

The Windows launchers use the current machine defaults. Override them without
editing scripts via `TH06_GAME_DIR` and `TH06_PYTHON`.
When calling them through WSL automation, do not allocate a PTY.
