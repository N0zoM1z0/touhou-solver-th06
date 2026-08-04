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
Most current machines use the retained local policy-volume primitive. The
t2388 `horizontal-band` state deliberately uses a target-free h6 constant
frontier, recovered and measured as a separate local primitive. The t2712
source group is split into sub5/sub4/sub3 fan states; only sub5 removes the
bottom target after a physical and high-pressure stateful CE. Boss ECL phases
are intentionally uncovered.

The historical Stage 4 clear solver was inspected in a detached worktree. Its
useful dense-wave evidence has been extracted without restoring its global
scene classifier: the old f2625--f2709 h6 publication/escape behavior belongs
only to the t2388 horizontal-band and the t2712 source states. The physically
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

`replay_th06_stateful.py --target x,y` reproduces route soft-target
tie-breaking only inside an already preferred Hard-safe set. Omitting it runs
the same primitive target-free; it cannot add an action to Hard.

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

Current checks after the sub5 target-loop corpus addition:

- Linux: 277 tests passed, 25 skipped;
- Windows/native: 277 tests passed, no skips/failures;
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
to sub2 at t2108 was deliberately kept separate pending its own evidence.

The next ordinary-RNG default fail-close run crossed both t1878/sub3 and
t2108/sub2, then stopped alive without a HIT or Bomb at f2649 in
`t2388/horizontal-band`. The consequential behavior came earlier: near y=380
the recursive h6 policy oscillated vertically, then selected a downward
sequence into the bottom strip. At f2648 it still had four Hard-safe actions;
the empty Hard set at f2649 was downstream. Physical adjacent-frame parity on
the retained history was exact for all 221 player/combat/RNG pairs and all
30,258 fired-bullet plus 8,868 spawning-bullet transitions.

Installed source shows t2388 creating sub11 at `(96,-32)` and `(288,-32)`,
then t2412 creating sub13 at `(-32,96)` and `(416,96)`. Both children emit a
fixed, non-aimed circle at local ECL t70 and reverse movement at t78, so this
phase does not require candidate-conditioned aim. Exact 64-frame replay on
five physical roots kept both h6 policy-volume and target-free h6
constant-frontier alive, but the constant frontier used 4.2 mean commands
versus 10.0. Across 20 paired delivery seeds, policy-volume survived 18/20;
constant-frontier survived 20/20, won the two differing seeds, and never lost.
The offline result is not a clear; it selects the next physical falsifier.

A subsequent ordinary-RNG default fail-close run did not reach t2388. It
stopped alive without a HIT or Bomb at f2227 in the separate
`t2108/sub2-aimed-stream`, with 11 actions repairable after the terminal Hard
loss. The sub2 h12 queries repeatedly took 18--23 ms and produced timeout or
stale holds. The earliest policy divergence retained for adjudication is
f2138: physical/static h12 chose `right_fast`, static h8 chose `up_right`, and
the candidate-conditioned h8 battle world chose `up_right_fast`. Thus both h8
models reject the consequential horizontal move while agreeing on the upward
direction.

Sub2 is an immediate Hard 8x2 aimed fan, distinct from sub3's 9x2 fan. On ten
retained physical sub2 roots, exact 64-frame battle replay kept h8 and h12
alive on 10/10 roots; h8 used 7.8 mean commands versus h12's 15.3. h6 lost one
root, so the preceding sub3 h6 result is not copied across the source
transition. Only `sub2-aimed-stream` now uses h8. The subsequent physical run
crossed both this state and the target-free t2388 constant frontier.

A higher-pressure screen derived 56 new complete battle worlds from eight
physical roots through 697 Hard-safe warmup updates, including 450 source
births, 19 enemy-combat states, 53 player-attack states, and 35 RNG states.
Across 62 viable 96-frame cases, h8 policy-volume survived 56 and h12 survived
59, with neither dominating all seeds. h12 is not promoted because the
physical run already measured it repeatedly missing publication. h9/h10 each
survived 58 but selected `right` at f2138; h11 selected the causal direction
but survived 57 and retains near-h12 effort. h8 replanning-count survived 59
but likewise selected `right`, used 22.16 mean commands, and cost about 1.5x
the h8 policy offline. Constant-reserve won one paired seed and lost two. h8
policy-volume is therefore the smallest publishable, causal-aligned physical
falsifier, not the offline survival champion.

That subsequent ordinary-RNG default fail-close run entered
`t2712/sub5-aimed-stream` and stopped alive without a HIT or Bomb at f2746.
Installed ECL splits the group into sub5's immediate Hard 2x3 aimed fan,
sub4's base 3x2 fan at t2942, and sub3's rank-adjusted base 5x2 fan at t3172.
Physical parity was exact for all 178 adjacent player/combat transitions,
33,360 fired-bullet steps, and 9,720 spawning-bullet steps.

On eleven exact roots, target-free h6 policy-volume survived 11/11 versus
10/11 with the old bottom target and used 6.36 versus 22.09 mean commands. At
the f2713 root, the first divergence was f2723; target-free survived 64 frames
with five commands, while bottom-target stopped after 53 with sixteen. A
higher-pressure screen derived 25 complete worlds through 940 warmup updates
and 4,017 source births. Across 30 viable 96-frame cases, target-free survived
28 versus 26, won four seeds and lost two, gained 129 aggregate survival
frames, used 684 fewer commands, and raised mean minimum clearance from 2.08
to 4.23. Only sub5 now removes the target; sub4/sub3 retain the previous
behavior pending their own physical evidence.

A later ordinary-RNG default fail-close run took an earlier branch and stopped
alive without HIT or Bomb at f1782 in the independent `t1514/sub10` tail, so
it did not physically promote the t2712 change. The terminal had ten
repairable actions; earlier f1778/f1780 still had 18/17 Hard-safe actions but
published stale results. Tail h8 queries produced 29 stale retries in 62
completed queries. An offline screen selected target-free h8 as the next
falsifier, but the subsequent physical run rejected it.

That target-free ordinary-RNG run stopped alive without HIT or Bomb at f1714.
From f1655 onward every fresh tail decision selected `up`, moving from y379.86
to y262.44; f1709 still had 18 Hard-safe actions, f1712 had three, and f1714
had no repairable action. Adjacent replay matched all 210 player/combat
transitions, 25,033 fired-bullet steps, and 1,158 spawning-bullet steps.

Targeted h6/h7/h8 survived 12/12 exact 64-frame roots. A new 63-world warmup
corpus covered 44 enemy-combat, 60 player-attack, and 47 RNG states through
1,051 updates and 5,488 source births; all three horizons survived 64/64
96-frame delivery seeds. Sixty native production queries measured h7 at 8.46
ms median, 10.17 ms p90, and 11.24 ms maximum versus h8 at 9.71/12.12/17.54
ms. The current physical candidate therefore restores the bottom waypoint
and uses h7 only in the t1649 tail. Parent-entry/child-circle remain targeted
h8 and common Hard-4 authority is unchanged.

## Immediate experiment

Run exactly:

```bat
run_th06_practice.bat --practice-stage 4 --seconds 300
```

Use ordinary RNG, default fail-close, non-PTY launch, and no diagnostic flags.
Expected outcomes after the t1514 targeted-h7 tail, t2108 h8, t2388
constant-frontier, and t2712 sub5 target-loop corrections:

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
