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
- One 110-second Stage 1 run reached frame 6508 with no observed death or Bomb.
  Input pickup was consistently one or two frames.

Known gaps are current-bullet-only safety, unsupported lasers/future emissions,
and missed decisions on slow dense frames. The zero-death run is a baseline,
not proof of a clear. See `README.md` for the compact details and module map.

## How to continue

Repeat or extend a physical Hard run and treat its first hit—or its successful
next milestone—as the main evidence. Explain one concrete failure from native
state and source, make one small change, run the focused check, then test it
physically. Timing, future emissions, lasers, ranking, or another mechanism may
be next; choose from evidence rather than this document.

```bat
run_th06_baseline.bat --seconds 120
run_th06_observe.bat 30
```

```bash
./check_th06_baseline.sh
```

The Windows launchers use the current machine defaults. Override them without
editing scripts via `TH06_GAME_DIR` and `TH06_PYTHON`.
