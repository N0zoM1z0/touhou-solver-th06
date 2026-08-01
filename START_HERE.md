# TH06 Handoff

## What we are doing

First make TH06 1.02h Hard reliably clearable; ignore Lunatic for now. Start
with the simplest correct baseline and let physical counterexamples determine
what gets added next. Do not recreate TH08 or turn this into a software-
engineering project.

The working idea has three strict layers:

1. **Hard safety authority:** only actions certified safe may execute.
2. **Adaptive solver:** vary horizon/effort with the situation without
   weakening safety.
3. **Learning proposal/ranking:** learn stage-dependent preferences only inside
   the safe set.

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
- Hard Practice Stage 3 now also reaches its source-defined result path. Its
  17,962 sampled states had no death, authority stop, or Bomb and covered up to
  615 bullets and 19 lethal enemy bodies. Source-exact timed direction-change
  bullets, delivery-aware soft effort, and a hard-set-only two-segment proposal
  were each added only after separate physical counterexamples.

Known gaps include future ECL births/instructions, a guaranteed command lease
beyond the observed two-frame pickup bound, and physical coverage of later stages.
Stage 3 also observed rare three-frame hazardous decision and snapshot-to-issue
ages, so the four-frame authority is not yet a complete delivery guarantee.
Actual replay file creation also still needs a non-Practice result. This is a
Stage 3 checkpoint, not proof of a route clear. See `README.md` for compact
details and the module map.
Use `notes/TH08_CE_GUIDE.md` only as a warning list when a matching TH06
counterexample appears; do not recreate the TH08 architecture from it.

## How to continue

Per the current one-time ordering decision, use Practice Stage 4 next and treat
its first hit or successful result as the main evidence. After Stage 4 passes,
run a fresh full Hard route from Stage 1. Explain one concrete failure from
native state and source, make one small change, run the focused check, then test
it physically. Timing, future emissions, lasers, ranking, or another mechanism
may be next; choose from evidence rather than this document.

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
