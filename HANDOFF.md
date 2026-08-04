# TH06 Current Handoff

Snapshot: 2026-08-04. The active foundation is named by annotated tag
`phase-route-foundation-20260804`; the complete retired line is named by
`pre-phase-route-pivot-20260804`.

Read `AGENTS.md` first. This file records only the current state and next
experiment; `notes/PHASE_ROUTE_PIVOT.md` contains the decision audit.

## Mission

Physically clear TH06 v1.02h Hard with Reimu-A in one default fail-close run:

- no HIT;
- no Hard-authority loss;
- no Bomb bit `0x02`;
- reach and validate the source-defined result/replay path.

Practice, fixed RNG, continue-on-failure, offline simulation, and patched-life
runs are diagnostics, not a route clear.

## Current architecture

The universal online planner has been removed from the main line.

```text
fresh coherent snapshot
    -> route-neutral source future + delivery-aware Hard-4
    -> exact route key (difficulty/character/shot/stage)
    -> stable source phase
    -> phase-local source-clock policy state
    -> route-selected short policy primitive
    -> intersect with fresh Hard
    -> publish one action
```

`scripts/th06/solver.py` is now the small shared authority/dispatch layer.
`scripts/th06/routes/` owns strategy. Missing routes stop with
`route-unavailable`; an identified but unauthored phase stops with
`phase-unavailable`. There is no anonymous fallback planner.

The first route is `hard-reimu-a-stage4`. Its pre-boss phase manifest is
audited against the installed Stage 4 ECL timeline. Each section now owns an
isolated state machine (`parent-entry`, `child-circle`, `horizontal-band`,
`tail`, and similar source states). A state owns its local primitive, horizon,
target, commitment, and provenance; only the selected phase machine executes.
The current machines use the retained local policy-volume primitive. Boss ECL
phases are intentionally uncovered.

The historical Stage 4 clear solver was inspected in a detached worktree. Its
useful dense-wave evidence has been extracted without restoring its global
scene classifier: the old f2625--f2709 h6 publication/escape behavior belongs
only to the t2388 horizontal-band and t2712 dense-aimed states. The physically
measured t1004 and t1514 states remain h8. Every decision now logs
`policy_state` separately from the stable source `phase_id`.

The common layer retains sole authority over collision/source physics,
Hard eligibility, unknown fail-close, input delivery, and no-Bomb. A route
intent cannot add an action to Hard.

## Source and offline support

- Supported EXE SHA-256:
  `9f76483c46256804792399296619c1274363c31cd8f1775fafb55106fb852245`.
- Authoritative ignored clone:
  `reference/GensokyoClub-th06/` at
  `cc475a0bc3fef38683b0f02224c87ddba0a021d9`.
- Ignored stage archive:
  `reference/th06_dat/th06_ST.DAT`.

`scripts/inspect_th06_route.py` now reads `ecldataN.ecl` directly from the
installed PBG3 archive. The Stage 4 file contains 404 ordinary timeline
instructions followed by the source four-byte terminal sentinel. The pilot's
timeline boundaries are verified against those source records.

Runtime boss phase identity maps relocated instruction pointers back to stable
ECL subroutine indices and includes boss ID, life/timer callbacks, and spell
state. Absolute addresses are never route keys.

The retained barrage_lab can replay physical state, future timeline/ECL births,
RNG, enemies, bullets, and lasers. The next phase workload must additionally
model any candidate-conditioned aim, damage/kill/retirement, callback, item,
or Power transition that changes its policy. Offline results remain soft until
physically tested.

## Cleanup and verification

Retired from the main line:

- adaptive universal effort/cost/publication ladder;
- universal progressive planner orchestration;
- cross-frame guidance target state;
- universal attack/route-reference mixing;
- `tests/test_th06_policy.py` and solver-integration contracts tied only to
  that architecture.

Retained algorithm tests cover source physics, Hard and delivery semantics,
future world behavior, native/reference parity, and local primitives that a
phase may deliberately select.

Current checks after the state-machine extraction:

- Linux: 273 tests passed, 25 skipped;
- Windows/native: 273 tests passed, no skips/failures;
- rebuilt `build/th06_safety.dll` SHA-256:
  `e8ab022e4091bb17df0a1bc01f0a98e7ab1eea131ff1cb6ca7c06992e187e1a2`.

The first post-pivot default Practice Stage 4 run stopped alive at f1329 in
`timeline:t1004:subs2-3` with no HIT or Bomb. Its provisional h12 phase query
cost 16.762 ms median/27.718 ms maximum, caused 17 stale publications and 46
timeouts, then missed a downward correction while holding `up`. Stateful
physical-battle replay kept h8/h12/h16 alive for 32 frames on the retained
roots, but h8 used fewer commands, had better mean minimum clearance than h12,
and produced the missed f1320 downward correction. Its h8 rerun crossed the
old boundary with 317 decisions, zero stale results, zero timeouts, and 5.926
ms median solve time. The next stop was alive at f1615 in
`timeline:t1514:sub10`: h12 measured 19.785 ms median with 10 stale results and
18 timeouts. Offline retained-root replay kept all compared horizons alive for
32 frames, while h8 used materially fewer commands. t1514 is now h8 and its
f1615 boundary maps specifically to policy state `child-circle`; the next
physical rerun crossed it.

The first state-machine physical rerun used ordinary RNG and default
fail-close. It crossed f1615, completed `t1514/child-circle`, and stopped alive
with no HIT or Bomb at f1931 in `t1878/sub3-aimed-stream`. The consequential
decision preceded the terminal empty Hard set: at phase entry f1878 the h12
policy chose `down_fast` from `(204.24, 392.24)`, then repeated 17--24 ms
queries timed out while delivery carried the player to the lower boundary.
Installed timeline/ECL shows alternating sub3 spawns every ten ticks, each
with a Hard 9x2 aimed fan and a rank-adjusted interval whose ECL base is 50;
the delayed interval starts from an RNG-selected timer offset.

On four retained physical roots from this sub3 group, h6's first action agreed
between the static native policy and the candidate-conditioned compact combat
world on 4/4 roots. h8 disagreed on 2/4. The causal queries cost 7.20 seconds
for four roots versus 0.265 seconds for the static queries, confirming that
they belong offline. Only the t1878 sub3 state is now h6; the source transition
to sub2 at t2108 remains h12 and awaits its own evidence.

## Immediate experiment

Run exactly:

```bat
run_th06_practice.bat --practice-stage 4 --seconds 300
```

Use ordinary RNG, default fail-close, non-PTY launch, and no diagnostic flags.
Expected outcomes after the t1878 sub3 h6 correction:

1. a pre-boss policy fails first, in which case the trace must name its exact
   `route_id`, `phase_id`, and `policy_state`; or
2. pre-boss play reaches the first boss, where the deliberate
   `phase-unavailable` stop must report the stable boss ECL phase.

For a pre-boss failure, trace backward to the earliest still-viable route
proposal. Build a stateful phase corpus from the physical entry history and
installed timeline/ECL, compare a few phase-specific policies/parameters, and
change only that phase. For a boss coverage stop, audit and author that exact
ECL subroutine/callback phase before rerunning.

After the run, release every input, stop the exact trial PID, and verify no
`th06`, agent, or high-CPU process remains. Do not use a PTY.
