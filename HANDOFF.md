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

The next ordinary-RNG default fail-close physical run promoted this candidate
for the t1514 source phase. Targeted h7 crossed both old f1714/f1782 states and
completed the sub10 tail. Across 118 tail policy rows it recorded 24 stale
retries; fresh solve times were 11.468 ms median, 17.553 ms p90, and 23.100 ms
maximum. The run continued through t1878 sub3, entered t2108 sub2, and stopped
alive without HIT or Bomb at f2200 in
`timeline:t1878:subs3-2/sub2-aimed-stream`.

The new stop is deliberately deferred, not claimed solved. Its terminal has
no repairable action, but the earliest visible consequential run is around
f2163, where repeated fresh h8 decisions move downward toward the boundary
before a late correction. Exact adjacent replay matched all 241
player/combat/RNG transitions, 33,155 fired-bullet steps, 2,703 spawning
steps, 13,580 player-shot steps, and 60 enemy transitions. Preserve this as
the next Stage 4 causal investigation; do not turn the terminal frame into a
special case or a corpus contract before tracing the first still-viable wrong
decision.

## Immediate experiment

Stage 1 setup and the t128 sub0/sub1 body/resource stream are now authored and
physically promoted. The ordinary-RNG default fail-close run completed both
without HIT, Bomb, or Hard-authority loss and stopped exactly as designed at
f641/t641 with `phase-unavailable` for
`timeline:t640:subs2-3-aimed-stream`. The boundary retained all 18 Hard-safe
actions at `(192,384)`, Power 2. The first phase used only three input
transitions; its 528 route decisions measured 1.884 ms median, 4.307 ms p90,
and 7.051 ms maximum.

The captured f641 entry now has exact low-Power causal replay: authoritative
Reimu-A rank 1 was compiled, after which all 255 adjacent player-attack,
enemy-combat, shot, RNG, item, and Power transitions matched. Stateful sweeps
selected target-free policy-volume h8 for t640--t1219. h4 failed all eight
complete-phase seeds; h6/h7/h8 survived all eight, and h8 retained the best
clearance for essentially the same command count as h7. Target-free h8 also
survived all eight complete roots and 32/32 warmup-derived delivery cases,
with materially fewer commands than the bottom target.

The ordinary-RNG default fail-close run physically promoted the t640 aimed
stream. It completed all aimed fans and the compressed tail without HIT,
Bomb, or Hard-authority loss, then stopped exactly at f1220/t1220 with
`phase-unavailable`. The entry is `(174.444,242.929)`, Power 2, 80 bullets,
and all 18 Hard-safe actions. There was one stale retry; 511 fresh h8 calls
measured 4.943 ms median, 10.251 ms p90, and 22.474 ms maximum. All final 241
adjacent combat/RNG transitions and 10,465 bullet steps matched exactly.

The t1220 exact-root sweep selected bottom-target `target-only` h4 through
t1599. Targeted h4/h6/h8 were identical and survived all eight 379-frame
delivery seeds. Target-free h4 also survived, but its mean minimum clearance
fell from 14.85 to 4.73 and its worst case reached 0.62. The ordinary-RNG
default fail-close run physically promoted the targeted h4 candidate: it
completed both source states without HIT, Bomb, stale publication, timeout,
or Hard-authority loss, then stopped exactly at f1600/t1600. The boundary is
`(197.331,379.355)`, Power 3, one bullet, and all 18 Hard-safe actions. The
final 255 adjacent combat/RNG/item/Power transitions, 3,289 hostile-bullet
steps, and 1,765 player-shot steps all matched exactly with no unsupported
transition.

The exact f1600 battle-world sweep now selects bottom-target `target-only` h4
through t2007. Targeted h4/h6/h8 were identical across all eight complete
407-frame delivery seeds, so deeper continuation adds no information.
Target-free h4 also survived 8/8 but consistently moved upward; the retained
bottom-center proposal agrees with the historical Stage 1 clear's positioning
lesson and the current resource/midboss objective. Its ordinary-RNG default
fail-close run completed both states without HIT, Bomb, timeout, or authority
loss and stopped exactly at f2008/t2008. The boundary is
`(192.887,382.225)`, Power 6, no bullets, and all 18 Hard-safe actions. The
source sub8 slot has not executed yet, so the stable phase remains the timeline
entry rather than a boss identity.

The final adjacent replay exposed and fixed one general source omission:
`RunEclTimeline` performs its periodic +100 subrank transition at
`timelineTime % (2400 - livesRemaining * 240) == 0`. The f1920--f1921 update
now matches, bringing the retained window to 255/255 exact combat/rank/RNG/
item/Power transitions with no unsupported state. Inspect sub8's installed
ECL and author the smallest t2008 insertion bridge; after the newborn enemy
sets its boss state, switch to the stable source boss identity and leave the
first unaudited midboss state fail-visible.

The sub8 audit is now explicit. Its local t0 sets boss/death/life/timer
callbacks, local t60 enables damage and collision, and local t160 emits the
first Hard player-aimed 16-by-5 circle. Only the one-frame t2008 timeline
insertion is authored with bottom-target h4 and a one-frame commitment.
Physically falsify it with ordinary RNG/default fail-close. Expected success
is an alive stop on stable `boss:0:sub8:life_cb9:timer_cb7:nonspell` identity
at the next snapshot; `timeline:t2009:sub8-midboss-missing` is the explicit
failure if source publication does not match the model.

The ordinary-RNG run validated that identity handoff. Its f2008 transition
used a still-fresh one-frame input lease; at f2009 the exact sub8 boss identity
appeared and the route stopped alive with all 18 Hard-safe actions at
`(192.343,382.569)`, Power 5, no bullets. No HIT, Bomb, or earlier authority
loss occurred. The adjacent transition exposed one future-world ordering bug:
SpawnEnemy's time-zero RunEcl was incorrectly receiving manager bounds and a
boss-timer tick. Inline ECL is now separate from the ordinary same-frame slot
pass; all 255 retained enemy/combat transitions match exactly and a focused
offscreen-boss regression fixes ECL time 2/boss timer 1/bounds false.

Use the exact f2009 boss root for the next offline comparison. Author only the
source-local entry state through local t159 (before the first aimed circle at
local t160), unless the complete causal sweep proves a slightly larger state
boundary. Keep the local-t160 attack and later movement/attack states
independently fail-visible.

The first sweep correctly failed closed when retained Power items raised the
entry from Power 5 to 8 at f2092. Authoritative Reimu-A rank 2 is now compiled:
one 48-damage straight shot every five fire ticks and two 14-damage homing orb
shots every 30 ticks. Ranks 3--8 remain unsupported. Focused source tests pass;
require adjacent physical parity for these newborn rank-2 shots on the next
run rather than treating the source table alone as promotion evidence.

The completed f2009-to-local-t160 sweep found targeted h4/h6/h8 identical on
all eight delivery seeds; target-free h4 retained `up` instead of restoring
the bottom route. Only sub8 `ecl_time < 160` is now authored as bottom-target
h4 state `entry-movement`. Its ordinary-RNG default fail-close run reached
f2167/local t160 alive, then stopped exactly as `phase-unavailable` under the
same stable boss identity before the first aimed circle. There was no HIT,
Bomb, stale publication, timeout, or earlier authority loss. The boundary is
`(194.603,379.740)`, Power 9, no hostile bullets, one boss, and all 18
Hard-safe actions.

The 155 fresh entry decisions measured 0.945 ms median, 1.098 ms p90, and
1.246 ms maximum. Adjacent replay matched all 254 player/combat/RNG/rank/item/
Power transitions and all 1,886 player-shot steps, including 56 exact births
across the Power 4-to-9 window, with no unsupported combat state. This
physically promotes only `entry-movement`.

The complete candidate-conditioned sweep now authors only
`160 <= ecl_time < 414` as target-free policy-volume h8 state
`first-circle-movement`. On the exact root h4/h6/h8 all survived eight
254-update delivery seeds, but h4 aliased every seed to its incoming `right`
lease. A 32-world high-pressure corpus derived by 1,072 Hard-safe warmup
updates exercised 2,560 source births, seven enemy-combat states, 32 player-
attack states, and seven RNG states. h4 lost one world to lease authority;
target-free h6/h8 survived 32/32, with h8 raising mean minimum clearance from
7.37 to 9.23 for 0.25 additional mean commands. Target-free also removed the
large command churn seen with the bottom waypoint.

The ordinary-RNG default fail-close run physically promoted this candidate.
It completed the first circle and movement without HIT, Bomb, stale
publication, timeout, or earlier authority loss, then stopped exactly at
f2421/local t414 before the next opcode-69 instruction. The boundary has all
18 Hard-safe actions at `(197.029,259.456)`, Power 9, 64 live bullets, and the
sub8 boss at life 4140.

All 214 fresh h8 decisions published at 3.789 ms median, 4.437 ms p90, and
12.525 ms maximum. Adjacent replay matched all 255 player/combat/RNG/rank/
item/Power transitions, 17,075 fired-bullet steps, 3,980 spawning steps, 180
births, 116 removals, six graze transitions, and all 43 boss life-change
frames with no unsupported state or position error.

Use the exact local-t414 root for the next source/offline comparison. Treat
the t414 and t444 aimed attacks as one candidate state only if their complete
source transition and physical-root sweep support it; keep the later
t738/t768 attack state independently fail-visible. Preserve candidate-
conditioned aim, player damage, boss life/callback, and RNG in every branch.

That comparison now supports one bounded state. The complete exact-root sweep
to local t738 kept h4/h6/h8 alive on 8/8 delivery seeds, but h4 again aliased
its incoming lease and retained only 1.78 clearance. A high-pressure corpus
retained 29 complete battle worlds after 1,000 Hard-safe warmup updates and
3,920 source births, spanning five enemy-combat, 29 player-attack, and ten RNG
states. Across 31 viable 128-frame cases, h4 survived 27; h6/h8 survived all
31. h8 raised clearance from 5.44 to 7.77 for 0.84 additional mean commands.

Only `414 <= ecl_time < 738` is now authored as target-free h8 state
`paired-circles-movement`. Run ordinary RNG/default fail-close. Expected
success is an alive stop at local t738 before the next attack, or an earlier
fail-visible stop if the source life callback changes the stable subroutine to
sub9. Require exact adjacent parity before promoting either boundary.

The run reached the local-t738 boundary under sub8 and physically promoted the
state. It stopped alive at f2745 with all 18 Hard-safe actions at
`(188.551,225.213)`, Power 9, 41 bullets, and boss life 2364. There was no HIT,
Bomb, stale publication, timeout, or earlier authority loss. All 272 h8
decisions were fresh at 3.918 ms median, 5.643 ms p90, and 8.061 ms maximum.

Adjacent replay matched all 255 player/combat/RNG/rank/item/Power transitions,
19,062 fired-bullet steps, 1,800 spawning steps, 120 births, 222 removals, 16
graze transitions, and all 42 boss life-change frames. Use this exact
local-t738 root for the next source/offline comparison. The t738/t768 attacks
and the now-near life threshold must remain candidate-conditioned; a switch
to sub9 is a stable phase boundary, not an error to suppress.

The source audit shows t840 jumping back to local t192, not ending sub8. An
exact 299-update sweep kept h4/h6/h8 alive on 8/8 seeds; h8 raised clearance
from h6's 3.68 to 6.90 with slightly fewer commands. A bounded h8 probe crossed
the rewind on all eight branches and entered sub9 after 299--362 updates,
always at exact life 500 but at candidate-dependent frames. Minimum clearance
remained 5.03--8.71.

A 31-world high-pressure corpus derived through 1,070 Hard-safe updates and
4,000 source births retained h6/h8 on 32/32 viable delivery cases versus
29/32 for h4. h8 clearance was 6.85 versus h6's 4.62 with essentially equal
command count. The route now authors `738 <= ecl_time <= 840` as target-free
h8 `late-circles-loop`; after the jump, the existing h8 source states repeat.

Run ordinary RNG/default fail-close. Expected success is an alive stop when
stable identity first changes from sub8 to sub9, not at the t840 rewind.
Require adjacent parity for the loop, accumulated bullets, candidate damage,
callback life 500, ECL identity/timer publication, and RNG before authoring
any sub9 spell state.

The run physically promoted the loop and stopped exactly at the source phase
change: f3044 published `boss:0:sub9:life_cb9:timer_cb6:spell`, matching the
earliest callback frame in the offline delivery probe. The boundary has all
18 Hard-safe actions at `(192.260,208.083)`, Power 9, no old bullets, and boss
life 500. Life threshold is cleared, timer callback is sub6/1320, and ECL plus
boss timers are both 2. No HIT, Bomb, stale publication, timeout, or earlier
authority loss occurred.

All 237 post-t738 h8 decisions were fresh at 3.976 ms median, 5.699 ms p90,
and 7.655 ms maximum. Adjacent replay matched all 254 player/combat/RNG/rank/
item/Power transitions, 21,519 fired-bullet steps, 3,020 spawning steps, 100
births, 197 removals, 11 graze transitions, and all 45 boss life changes.

Use the exact f3044 sub9 spell root next. Audit its local t0--t120 protected
entry, Hard t120 circle/interval and two source lasers, then author only the
smallest state whose future laser and bullet transitions are completely
modeled. Sub9 is a new stable phase; do not inherit sub8 route intent merely
because the same enemy slot remains alive.

The source entry audit is complete. Sub9 local t0 cancels old bullets,
disables damage, installs timer callback sub6/1320, and moves for 120 ticks.
Local t120 re-enables damage, configures the Hard 42-way delayed pattern, and
creates two lasers. On the exact local-t2 root, bottom-target h4/h6/h8 all
survived 8/8 complete 118-update seeds; h4 used no new command versus eleven
for h6/h8. Target-free h4 was identical, so the bottom waypoint is retained
for spell positioning.

Only sub9 spell `ecl_time < 120` is authored as target-only h4 `spell-entry`.
Its ordinary-RNG/default fail-close run physically completed the protected
entry and stopped exactly at f3433/local t120 before the bullet/laser
transition. Candidate-conditioned damage moved spell start to f3313 rather
than the earlier f3044 root, while stable phase dispatch remained correct.
There was no HIT, Bomb, stale publication, timeout, or authority loss. All 112
entry decisions were fresh at 0.958/1.433/2.345 ms median/p90/maximum; the
boundary has all 18 Hard-safe actions at `(191.799,382.049)`, Power 9, with no
live bullets or lasers.

Adjacent replay exposed one nominal-world omission on f3313--f3314: source
opcode 93 converted 89 bullets into point-item slots 19..107, after which the
same ItemManager pass collected two overlapping births. The source-exact
nominal transition now models ordered allocation, same-frame collection,
laser retirement, and spell-damage state; Hard retains its conservative
bullet authority. The minimized independent corpus case is
`stage1-f3313-spell-start-point-conversion`. Corrected parity is exact for all
252 adjacent combat/item/Power/RNG transitions, 9,900 fired-bullet steps,
1,704 spawning steps, and 2,446 player-shot steps.

Use exact f3433/local-t120 next. First run the smallest offline transition
that executes the Hard 42-way delayed pattern and both fixed-angle lasers.
Require exact source slot allocation, delayed-interval RNG, laser timers and
motion, then physically capture a short adjacent window before authoring a
larger spell policy state. Do not infer the remaining spell from source alone.

That smallest transition is now authored, but not yet physically promoted.
The exact t120 step allocates fixed-angle laser slots 0/1, consumes the
delayed-interval RNG, and births the Hard 42-way circle on the third update.
Across eight exact-root delivery seeds, targeted h4/h6/h8 were identical and
survived all 30 updates to local t150. Only `120 <= ecl_time < 150` is exposed
as target-only h4 `laser-pattern-start`; t150 remains fail-visible before the
t150/t151 rotation loop.

Run ordinary RNG/default fail-close. Expected success is an alive stop at
local t150 with exact laser slots/timers and the first circle present. Require
adjacent parity for delayed RNG, every bullet birth/motion transition, both
laser births and all first 30 timer updates before promotion.

The run physically promoted `laser-pattern-start` and stopped exactly at
f3500/local t150 with no HIT, Bomb, stale publication, timeout, or earlier
authority loss. The boundary has all 18 Hard-safe actions at
`(194.846,379.581)`, Power 9, 42 bullets, and laser slots 0/1 at source state 0
timer 30. All 27 fresh queries measured 1.181/2.428/3.070 ms
median/p90/maximum.

Adjacent replay is exact for all 252 combat/RNG/item/Power transitions, 9,388
fired-bullet and 2,334 spawning-bullet steps, both laser births, and all 58
laser transitions. Use the exact local-t150 root next. Audit the t150/t151
opposed opcode-88 rotation loop and the imminent state-0-to-state-1 laser
transition; expose only the smallest source-clock state that can be validated
against the next physical boundary.

The complete exact-root sweep to local t211 rejects h4 and selects target-free
h6 as the next falsifier. h6/h8 survived all 8 exact 180-update seeds; h4
survived only 3. A 27-world high-pressure corpus derived through 2,082
Hard-safe updates and 2,562 births kept h6/h8 on 30/32 measured cases, with
one paired win each and one common loss. h6 used fewer commands and retained
slightly more aggregate survival, so h8 has no measured causal advantage.

Only the source `t150/151` register-controlled rotation is authored as
target-free h6 `rotating-laser-loop`, followed by the independently visible
`t152..210` h6 `laser-retirement-tail`. Run ordinary RNG/default fail-close.
Expected success is an alive stop at local t211. Require adjacent parity for
every opposed angle mutation, the state-1-to-state-2 transition, laser
retirement, accumulated aimed circles, combat, and RNG before promotion.

The ordinary-RNG run physically promoted both states and stopped exactly at
local t211 (absolute f3490 under this run's earlier callback). There was no
HIT, Bomb, stale publication, timeout, or earlier authority loss. The boundary
has all 18 Hard-safe actions at `(223.657,381.480)`, Power 8, 112 bullets, no
lasers, and boss life 256. Rotation h6 measured 4.074/4.944/6.236 ms and the
retirement tail 3.029/4.884/14.496 ms median/p90/maximum.

Adjacent parity is exact for all 254 combat/RNG/item/Power transitions, 12,650
fired-bullet and 3,444 spawning-bullet steps, 326/326 retained-laser
transitions (including 236 ECL angle mutations), and both source laser
removals. Use exact local-t211 next. Audit the movement and subsequent spell
attack boundary from installed ECL before exposing another state.

The local-t211 audit finds source random-in-bounds movement at speed 2 for 120
ticks, followed by a t331 jump back to t120. Target-free h6/h8 survive all
eight exact movement cycles. A 32-world high-pressure corpus derived through
1,072 updates and 756 births keeps both at 32/32; h6 uses fewer commands and
h8 has no survival win. Only `211 <= ecl_time < 331` is now authored as
target-free h6 `random-movement`.

The first promotion run stopped earlier on a torn f3063 native root. Its
EnemyManager prefix was between `HandleLifeCallback` and sub9 `RunEcl`, while
the later bullet/item pool already represented the completed same-frame spell
start. This was not a route phase: source places both operations in one
EnemyManager update. Native sensing now reads `BulletManager.time` before the
large EnemyManager-to-BulletManager copy and requires it to equal the copied
tail timer, retrying the whole root if the calc chain advanced during the
copy.

The ordinary-RNG rerun physically promoted `random-movement` and stopped alive
exactly at f3822/local t331 before the rewind. There was no HIT, Bomb, stale
authority stop, timeout, or earlier fail-close. The boundary has all 18
Hard-safe actions at `(236.052,379.228)`, Power 7, 70 bullets, no laser, and
boss life 308. All 119 fresh movement decisions measured
3.078/4.747/6.154 ms median/p90/maximum. Retained adjacent parity is exact for
all 255 combat/RNG/item/Power pairs, 19,453 fired-bullet steps, 4,242 spawning
steps, 2,132 player-shot steps, all 182 laser transitions, and both laser
removals.

Use exact local-t331 next. Audit only opcode 2's rewind to local t120 and the
same-update source instructions which recreate the Hard pattern/laser cycle.
Require a physical adjacent boundary before reusing the already promoted
`laser-pattern-start`; do not generalize over later cycles or the eventual
spell-end callback.

That smallest offline audit is complete. Source opcode 2 rewinds t331 to t120
and the interpreter continues in the same update through the already modeled
Hard pattern/interval/two-laser setup. From exact f3822, target-free h4/h6 are
identical across eight four-update branches and survive 8/8 with 27.43 minimum
clearance. Only exact `ecl_time == 331` is authored as h4 `cycle-rewind`, with
one-frame commitment; clocks above 331 remain fail-visible.

Run ordinary RNG/default fail-close. The retained history must contain the
physical t331 rewind and exact adjacent parity for ECL dispatch, interval RNG,
laser allocations/timers, bullets, combat, and player state. Stop at the next
genuinely uncovered source phase (expected eventual sub6 spell end or an
unsupported later callback), not at an invented absolute frame.

`cycle-rewind` is physically promoted. The retained second transition is
f4148/t331 to f4149/t121: boss life/position stay 100 and
`(238.549,144.000)`, RNG generation stays 3996, the existing interval timer
advances 33 to 34, and laser slots 0/1 are reborn at state 0/timer 1. Adjacent
parity is exact across 254 combat/RNG/item/Power pairs, 20,717 fired-bullet
steps, 4,116 spawning steps, 2,822 player-shot steps, both laser births, all
182 laser transitions, and both removals. The run later fail-closed at exact
f4237/sub6 local t0 after a post-RunEcl death callback; do not confuse that
legitimate pending callback state with the earlier torn life-callback read.

Before authoring sub6, resolve the earlier route-level counterexample exposed
by another ordinary run: sub8 timed out to sub7 at f3449 with life 1248 on the
preceding frame. Its retained history already had life 2496 at local t537 and
lost all damage once the boss moved right near t717. Live-boss-x tie-breaking
inside equal h8 continuations did not robustly fix it, and constant right is
too slow while faster chasing collides. Capture a modern exact local-t160 root
with an explicit diagnostic fail-close, then compare candidate-conditioned
future damage/kill/lead policies over the complete life-versus-timer race.
Hard and h8 continuation authority must remain unchanged.

The exact diagnostic root is f2167/local t160 with boss life 5916, timer 159,
Power 10, no hostile bullets/lasers, and complete attack/RNG/item state. A
full eight-seed offline race now reproduces the problem: target-free h8 reaches
sub9 on 7/8 but seed 7 times out to sub7 at life 526; successful callbacks
take 862--1110 updates. Live boss-x chasing is not a repair. Using the
captured source movement destination (`move_start_x + move_interp_x` while
interpolating, live x otherwise) reaches sub9 on 8/8 in 845--959 updates with
1.247--5.155 minimum clearance.

That destination is now only a soft tie-break inside the unchanged h8
continuation winners for all three damaging sub8 policy states. Hard-4,
horizon, commitments, and physics are unchanged. Run ordinary RNG/default
fail-close next. Promotion requires sub9 rather than the sub7 timeout, no HIT,
Bomb, stale authority stop, or publication regression. If it succeeds, then
return to the retained f4237/sub6 local-t0 SpellEnd boundary.

The ordinary-RNG run physically promoted the source-destination attack lead.
Sub8 ran from f2167 through its last fresh decision at f3011, retained a safe
in-flight action at f3012, and published complete sub9 spell state at f3013—
about 845 updates, matching offline evidence and leaving about 435 updates of
timer margin. It later stopped only at exact f3499/sub6 local t0. There was no
HIT, Bomb, stale authority stop, timeout, or earlier fail-close. The 687 fresh
sub8 decisions measured 3.523/5.060/7.916 ms median/p90/maximum.

Retained adjacent parity is exact for all 255 combat/RNG/item/Power pairs,
21,637 fired-bullet steps, 3,780 spawning steps, 3,244 player-shot steps, both
laser births, all 180 laser transitions, and both removals. Use the newer
f3499 sub6 root next: boss life 0, interactable false, spell still published,
opcode 47 pending, 88 bullets and two active lasers. Audit the post-RunEcl
death-callback publication and following SpellEnd conversion as its own
source transition before authoring the rest of sub6.

That source audit is now implemented as a physical candidate, not yet
promoted. `ECL_OPCODE_SPELLCARDEND` is no longer treated as nominally neutral:
when the captured spell is active, the exact combat world applies
`DespawnBullets(12800, 1)` in ECL order. Every occupied bullet produces a
state-1 Point item and becomes state 5; every active laser produces the
source's separate origin item plus its 32-pixel offset walk, resets to
state 2/timer 0, and clears its hitbox-end delay. ItemManager then advances
the allocated items before BulletManager moves the converted bullets at half
velocity and advances the retiring lasers. Hard forecasting remains
conservative and does not remove a current hazard because of this soft exact
transition.

On exact f3499, the nominal prediction for the following root is f3500/sub6
local t1 with no active bullets, 88 despawning bullets, both lasers at
state 2/timer 1, and 127 live item slots 113--239: 122 Point items, one Big
Power, and four Small Power. DROPITEMS consumes the expected 20 RNG
generations, from 3764 to 3784, and Power remains 8. All 18 actions are still
Hard-4 certified under the conservative hazard world. Only exact
sub6/t0/spell-active is authored as one-frame `spell-end-conversion`; sub6 t1
remains uncovered.

Run ordinary RNG/default fail-close next. The expected stop is complete sub6
t1 immediately after this conversion. Promotion requires exact adjacent
parity for the ECL instruction pointer/time, 88 state-5 positions/timers, both
laser transitions, item slot order/type/motion, RNG, Power, player attack,
and player state. Do not infer the state-5 tail from this first update: the
donut ANM VM is not captured, so subsequent despawning-bullet lifetime remains
unsupported.

The first such physical attempt was intercepted earlier by a new ordinary-RNG
Stage 1 counterexample. It stopped alive at f1330 in the source t1220 random
body insertion with no HIT or Bomb. The terminal empty Hard set is downstream:
f1325 and f1327 still had 17 Hard-safe actions, then the old bottom-center
target repeatedly selected alternating diagonals near y=380; f1329 carried a
stale `up_right` and f1330 had seven repairable actions but no ordinary
Hard-4 action. All 246 retained battle transitions are exact, including
enemy/player-shot/RNG/item/Power state, 13,999 fired-bullet steps, and 558
spawning steps, so the root is suitable for exact stateful replay.

From exact f1270 over 80 updates and eight delivery seeds, old h4 plus the
bottom target survived 6/8, while target-free h4 survived 0/8: removing the
target without adding continuation evidence is not enough. Target-free h6 and
h8 both survived 8/8; h6 used 15--19 commands versus 25--28 for the old policy
and had 5.013--9.264 minimum clearance. H8 provided no survival win. A second
corpus derived 16 complete worlds from f1220/f1240/f1260/f1280 through 160
safe updates, covering 11 enemy/RNG and 16 player-attack states. Both policies
survived its shorter 64-update window, but h6 reduced aggregate commands from
259 to 236 and removed the old policy's late-root 1.313-clearance tail.

Only `random-insertion` (source t1220--1400) is now the next physical
candidate: target-free h6 `policy-volume`. The later source tail remains the
old target-only h4 state, common Hard-4 is unchanged, and the compact physical
CE is stored independently. Rerun ordinary RNG/default fail-close. Promotion
requires crossing f1330 without a publication regression; if the run reaches
sub6, validate the already-authored SpellEnd transition in the same trial.

That default ordinary-RNG run physically promoted both pending candidates. It
crossed t1220--1400 with no HIT, Bomb, stale decision, timeout, or authority
loss. The 133 fresh `random-insertion` decisions measured 7.265 ms median,
13.998 ms p90, and 17.508 ms maximum; every root retained at least 15 Hard
actions and seven h6 winners. It then completed the already-promoted sub8/sub9
route and stopped exactly as designed at f3980/sub6 local t1, after executing
the one-frame SpellEnd state.

Physical f3979 had 105 active bullets, no despawning bullets or lasers, no
items, Power 9, RNG generation 3936, active spell publication, and sub6
local t0/op47. Physical and nominal f3980 agree exactly: the same 105 bullet
slots are state 5 with exact half-velocity positions and timer 154; there are
no active bullets or lasers; 110 item slots 118--227 contain 105 Point, one
Big Power, and four Small Power items with exact same-frame ItemManager state;
RNG is seed 2992/generation 3956; Power remains 9; spell is false; and sub6 is
local t1/op59. The minimized physical transition is now an independent corpus
case. This physical instance does not validate active-laser point conversion,
because both spell lasers had already retired before f3979.

Across the retained 253-pair window, all player/combat/RNG/item/Power worlds,
19,515 fired-bullet steps, 4,242 spawning steps, 2,523 player-shot steps, all
322 laser transitions, and both laser removals are exact. Next audit sub6
local t1 through its source t40 move and t160 despawn. Pre-existing state-5
ANM lifetime remains unavailable to nominal replay, but those bullets are
nonlethal; do not invent their retirement or pool reuse if later source events
need it.

That sub6 tail is now physically promoted. A source-grounded dynamic Power
target, evaluated only inside fresh Hard-4, collected the Big Power and one
Small Power in the new ordinary-RNG world, raising Power 8 to 17. The crossing
of Power 16 physically exercised the newly compiled authoritative Reimu-A
Rank-3 shot table; the paired 30-damage births and subsequent shot steps have
exact adjacent parity. Sixteen exact delivery branches from f3687 all survive
through boss removal and finish at Power 17.

Installed ECL still contains nominal t160 opcode 1, but physical execution
removes the boss earlier: its t40/120-tick move toward `(192,-64)` leaves the
source bounds after local t140, and `EnemyManager` despawns it before the next
`RunEcl`. The default run stopped safely at f3827 immediately after that
removal, with no HIT, Bomb, stale authority, timeout, or earlier fail-close.
The retained 255 pairs match all player steps, 8,169 fired-bullet steps, 1,890
spawning steps, and 2,502 player-shot steps. Item and Power stepping matches
all 244 supported combat pairs; eleven unrelated post-midboss enemy-slot
worlds remain explicitly unsupported rather than claimed exact.

The next experiment is the actual post-midboss timeline rooted at physical
t3827. Three nonboss sub2/sub3 emitters are already live and the next installed
timeline spawn is t3848. Replace the obsolete no-boss fallback label only
after auditing the source timeline section and replaying this exact root.
Do not route by the old t2009 insertion boundary once the midboss has been
removed; timeline time continued advancing during the fight.

That source/offline audit now selects the next physical candidate. Installed
t2408--4298 alternates 64 sub2/sub3 aimed parents every 30 ticks; the physical
f3827 root has three live parents and next inserts at t3848. A native 671-frame
screen through t4498 keeps h4/h6/h8 alive on 8/8 delivery seeds, but h8 raises
mean minimum clearance to 5.709 and its worst case to 3.463, versus h6's
3.587/1.608 and h4's 2.254/0.839. A derived seven-world combat corpus covers
1,520 warmup updates and 558 source births; h6/h8 both survive 12/12 96-frame
cases, with h8 retaining the higher mean clearance.

Only the no-boss post-midboss timeline before t4498 is authored as target-free
h8 `policy-volume`. Run ordinary RNG/default fail-close next. Promotion needs
to cross the complete residual aimed stream with no HIT, Bomb, stale authority,
or timeout and stop at the distinct t4498 sub0 resource formation. Common
Hard-4, hazard semantics, and the already promoted boss route are unchanged.

The next physical run took a later boss/timeline interleaving and therefore
did not exercise that h8 candidate: the midboss remained active past t4498.
The run stayed fail-close and stopped alive at f4637 after sub6 removed the
boss, with no HIT, Bomb, authority loss, or timeout. Two stale retries occurred
earlier in already promoted boss/timeline phases and recovered fresh Hard; no
post-midboss h8 decision was published. Keep that phase as an offline candidate,
not a physical promotion.

The active root is now inside source t4498--4978. The 62 sub0 parents have life
3 and random-item drops; their difficulty-mask `0x08` bullet instruction is
inactive on Hard. F4637 has Power 6 plus one Big and four Small Power items.
Exact 641-frame replay through the t5278 dialogue boundary keeps 32/32 dynamic
delivery branches alive, raises Power to 25--29, uses 66--120 commands, and
never reaches unsupported Rank 4. The old bottom target reaches only Power
18--20 and uses roughly 241--246 commands.

The next physical candidate covers only no-boss t4498<=timeline<t5278 as
target-only Hard-4 with live Power-item priority. Dialogue at t5278 remains
uncovered and separate from movement. Run ordinary RNG/default fail-close;
promotion requires actual Power gain plus a safe stop at the dialogue boundary.

That ordinary-RNG default fail-close run promoted both outstanding no-boss
sections. Target-free h8 was genuinely selected for 391 fresh decisions from
f4005 through t4497, so it is no longer merely an offline candidate in the
early-boss-removal world. The resource policy then published 705 decisions
through f5277 and raised Power 11->26. The only authority stop was the intended
uncovered t5278 dialogue boundary; there was no HIT, Bomb, earlier authority
loss, or timeout. Final 255-pair adjacent replay is exact for player, combat
enemy, player shot, RNG, item, and Power state. The exact PID was stopped and
inputs were released.

Continue from t5278 by auditing the authoritative dialogue/main-boss sequence,
not by extending movement blindly. Source timeline control is t5278 message
start followed by the t5279 boss insertion sequence. Dialogue/advance control
must remain separate from player movement, and the first new experiment should
stop at the smallest newly understood boss root.

That audit now opens only the no-boss t5278/t5279 bridge. EnemyManager starts
message 0 before Gui runs; t5279 MSGWAIT holds for a proved minimum six updates
until ECLRESUME, then the same EnemyManager update inserts sub10. Movement stays
bottom-center target-only Hard-4, while the existing independent dialogue
skipper owns Ctrl/Z. The exact physical t5278 artifact has 18 Hard-safe actions
with the future message delay and sub10 insertion present. Sub10 itself remains
uncovered, so the next default fail-close run should stop on its first stable
snapshot rather than entering the boss pattern.

The first attempt stopped before dialogue at f5060 in the resource phase. The
terminal empty Hard set was an effect: at f5054 bottom/item targeting still
selected down although its h8 policy volume was 8 versus the fresh best 9; by
f5056/f5058 down had no constant h8 continuation, and the f5059 reversal could
not be published from the stale snapshot. This relation shrinks to one physical
enemy body and is stored as an independent corpus case.

The repaired resource candidate uses h8 policy volume, then the dynamic Power
target only as a tie-break. Hard remains unchanged. Physical-battle replay from
f5020 changes 4/16 h4 lease stops into 16/16 h8 survival; three later roots each
survive 32/32 delivery seeds for 64 updates. Production-budget evaluation
completes h8 on all 255 retained resource snapshots with no policy timeout.
Run default fail-close again; dialogue and sub10 are still deliberately bounded
exactly as above and have not yet been physically promoted.

That run promoted the repair and bridge. Resource h8 published 584 fresh
decisions, raised Power 18->32, and crossed 23 certified stale retries without
authority loss. Message 0 became active at f5279 with Ctrl skip, held timeline
t5279 through f5285, and released the predicted same-update insertion at f5286.
The route then stopped cleanly on `boss:0:sub10` local t2 with no HIT or Bomb;
inputs were released and exact PID 60580 stopped.

The f5286 root still has an active message and 48 proved waits at the t5280
timeline MSGWAIT. It also reaches Power 32, beyond the compiled Power-16--31
Reimu-A attack band used in the preceding offline work. Audit and compile that
shot rank together with the sub10 entry ECL before authoring the first boss
movement interval. Do not treat the still-active dialogue as a quiet boss
root, and do not extend through the first source attack speculatively.

That audit now opens only sub10. Authoritative ECL disables boss damage and
collision, starts its 60-tick entry move, installs interrupt 0 -> sub11, and
contains no hostile birth opcode. The still-active message proves a 48-wait
earliest-transition lower bound before t5281 can apply that interrupt; sub11
immediately enables collision and damage and remains uncovered. The exact
f5286 target-only Hard-4 query has all 18 actions safe and selects `down_left`
toward bottom center.

Authoritative Reimu-A Rank 4 (Power 32--47) is compiled. Retained physical
parity is exact for 255/255 player-attack transitions, 145 shot births, and
3,227 shot steps. Full nominal combat parity rises from 15 to 248 of 255
adjacent pairs; the seven unsupported pairs are precisely the active-message
timeline waits and remain explicit. Route-neutral forecasting sees no hostile
birth through 120 frames and fails closed at lead 137 when candidate damage
can reach sub11's unaudited life callback.

Run ordinary RNG/default fail-close next. Promotion requires sub10 movement
to remain under fresh Hard authority with no HIT/Bomb and an intentional stop
on the first stable sub11 snapshot. Do not issue an unaudited sub11 action.

That physical run promotes sub10. Power was 30 at entry. Sixty-one fresh
sub10 decisions through f5349 retained all 18 Hard actions and measured
0.884 ms mean/0.900 ms median/1.500 ms maximum, with no HIT, Bomb, stale
publication, timeout, or authority loss. The 48 waits were correctly only a
lower bound: a source WAIT kept the bound at 38 long enough for the boss to
reach local t60. F5344 exactly completed the move at `(192,96)`; f5345 ran the
t60 animation/bounds instructions with no hostile birth and collision/damage
still disabled. Message 0 ended at f5348 and t5281 applied interrupt 0 on the
f5350 update.

F5350 is the intentional stop: sub11 local t1 at `(192,96)`, life 7000,
damageable/collidable, Hard callbacks 22/22, all 18 Hard actions available,
and no unaudited action issued. All 63 adjacent sub10 emitter transitions are
source-exact, including t60. The retained window has 255/255 exact player
attack transitions and 185/185 exact supported combat transitions; 53 active
message-wait pairs remain explicitly unsupported. Across the full run CSV,
no player-dead state or Bomb bit appears, and f5350 is the only authority stop.

Next audit sub11 and the called sub12 pattern from this exact root. Account for
candidate damage, the Hard callbacks 22/22, and the source t100 call before
authoring its first nonspell interval. Offline work should stop where damage
can first change callback timing; do not treat the current empty screen as the
whole nonspell.

That audit now selects the first main-boss nonspell candidate. Sub11 enables
damage/collision, installs life 7000 and Hard callbacks 22/22, then calls sub12
at local t100. Sub12 starts a 60-tick random-in-bounds move and emits seven Hard
aimed-fan groups at t12--t60. Hard difficulty mask 0x04 gives group sizes
10/10/10/10/20/30/40, totaling 130 bullets at base speed 5; the earlier
200-bullet count was the mask-0x08 Lunatic stream. At t180 it consumes the RNG
branch: values zero/one CALL sub13/sub14, while value two falls through to CALL
sub15. These callees contain no RET, so a taken conditional CALL does not return
to the later sub15 instruction. All later pattern states remain uncovered.

The exact f5350 battle world compares only through the t180 boundary. Plain h8
policy-volume survived 7/8 delivery seeds; h8 `count-clearance`, which ranks
deduplicated terminal volume before terminal hazard clearance, survived 8/8
with 20.16--28.03 minimum clearance. A wider screen kept it alive on 64/64
complete 278-update RNG/Power-30-or-32/delivery worlds. Hard-safe warmup then
derived 32/32 complete worlds spanning 23 enemy-combat, 32 player-attack, and
32 RNG states; another 128/128 measured 64-update delivery worlds survived.

Production `Solver.decide` on the resulting trajectory completed 278 authored
queries at 2.105 ms median, 2.562 ms p90, 3.578 ms p99, and 3.679 ms maximum,
with no policy timeout. The following two snapshots stopped as designed after
the unauthored t180 branch. The online h8 projection includes source-future
births inside its short window, but future aimed origins are nominal; the
stateful outer sweep is what conditions each subsequent ECL aim, player shot,
boss damage, and RNG transition on the actual candidate path.

Only sub11 through t100 and sub12 through t179 are now candidate-authored.
Run ordinary RNG/default fail-close. Promotion requires crossing every aimed
fan without HIT, Bomb, timeout, stale authority loss, or earlier fail-close,
then stopping alive at the first stable sub12 t180 or sub13/sub14/sub15 source
identity. Require adjacent physical parity for the t100 CALL, random movement,
all births/motion, player attack, boss damage, and RNG before extending the
branch.

That default run physically promotes both states. It crossed sub11 and all 130
Hard sub12 births, then stopped exactly at f5629 on stable sub14 local t1 with
all 18 Hard actions available. The full run contains no dead state, Bomb,
timeout, or earlier authority stop. In the 279-frame authored window there
were 246 fresh count-clearance decisions, 33 one-frame input-lease checks, zero
stale decisions, and zero timeouts. Every fresh decision retained all 18 Hard
actions; solve time was 3.196 ms median, 4.375 ms p90, 5.655 ms p99, and 12.424
ms maximum. Peak hostile bullet count was 130 and measured minimum current-
bullet clearance in the retained window was 27.882.

The retained 254 adjacent pairs are exact for player state, all 254 Reimu-A
attack transitions, 159 player-shot births, 5,691 player-shot steps, 130
hostile births, 13,135 mature-bullet steps, and 1,950 spawning-bullet steps.
The ordinary parity command correctly labels full combat unsupported while the
timeline still holds opcode 12. Under the source-proved phase shaping that
removes only this boss-removal wait, all 254 combat/enemy/damage/RNG/rank/item/
Power transitions and all 49 boss-life changes are exact with no unsupported
state. The f5628->f5629 transition consumes the modeled RNG and enters sub14;
no unaudited route decision is issued there.

Use exact f5629 next. Audit sub14's time-zero movement and first Hard attack,
plus its exclusive t200 CALL branches, before opening another bounded state.
Keep sub13 as a separate RNG sibling even though this physical run selected
sub14.

That bounded sub14 audit is now a physical candidate. Source time zero chooses
a random-in-bounds direction, speed 3, and 60-tick motion. Hard mask 0x04 emits
an aimed 5x16 fan at local t80 and an aimed 24x2 circle at t110. At t200 the
source draws a three-way integer: values zero/one CALL sub13/sub12, while value
two falls through to CALL sub15. The callees do not RET. Only `ecl_time < 200`
is opened; sub13, sub12 re-entry, sub15, and life
callback sub22 stay fail-visible.

The previous count-clearance h8 policy fails one exact delivery branch in this
phase, confirming that policy does not leak across source states. Exact-root
and warmup-derived screens select target-free constant-frontier h10: 8/8 exact
branches and 62/62 branches from 31 source-valid worlds reach t200 or a stable
called subroutine. The 31 worlds came from 2,263 Hard-safe warmup updates and
1,456 births and span 29 enemy-combat, 31 player-attack, and 22 RNG states.
The worst measured clearance is only 0.354, so this remains a narrow physical
falsifier. Full Hard-4 plus constant-h10 native queries measured 1.337 ms
median, 1.644 ms p90, 2.073 ms p99, and 2.383 ms maximum on 199 consecutive
candidate states.

Run ordinary RNG/default fail-close. Expected success is an alive stop on the
first stable t200 branch or an earlier source life callback, with no sub13/
sub12/sub15 strategy action. Require exact adjacent parity for both aimed
births, movement, candidate damage, callback timing, and t200 RNG/CALL state.

The first run did not exercise sub14. It stopped alive at f5628 on sub12 local
t180 because no input command happened to be in flight. The preceding run had
crossed the same boundary only under a one-frame Hard lease, so `<180` made
source progress depend on incidental publication state. F5628 still has all
18 Hard actions, Power 30, boss life 4858, and 62 bullets. One shaped nominal
step under the observed `up_right_fast` enters sub13 local t1 and advances the
captured RNG exactly through the modeled time-zero work.

Sub12 t180 is now its own one-frame h4 `first-nonspell-branch-dispatch` state.
Sub14 t200 receives the symmetric one-frame `branch-redispatch` state. These
states authorize only the understood source transition; every destination
remains independently fail-visible. Rerun default fail-close. Expected success
is an alive stop on stable sub13/sub14/sub15 after t180, or—if sub14 is chosen—
after crossing its two attacks at the next unauthored destination.

Do not continue opportunistically into the deferred Stage 4 f2200 stop while
Stage 1 is the active route. The route packs are intentionally independent;
physical promotion of one phase must not alter another phase's policy.

After the run, release every input, stop the exact trial PID, and verify no
`th06`, agent, or high-CPU process remains. Do not use a PTY.

The rerun crossed the new sub12 t180 dispatch, selected sub14, and crossed both
sub14 attacks. It then stopped default fail-close at f5765 with an empty Hard
set, no HIT, and no Bomb. The terminal was an effect. At f5746--f5747 there
were still twelve/ten constant-h10 actions, but `constant-frontier` treated
them as an undifferentiated tie and selected slow down-left motion. The same
fresh snapshots' terminal-count evidence uniquely selected
`down_right_fast`; the selected route through the gap became consequential at
f5747. By f5759 no constant-h10 action remained, and the later downward hold
could no longer be repaired.

This is a policy counterexample rather than missing source physics. Under the
already source-proved shaping that removes only the active boss-removal
timeline wait, all 255 retained adjacent pairs match player attack, combat,
enemy damage, RNG, Rank, item, Power, and graze state. They include 128 hostile
births, 19,093 mature-bullet steps, 4,010 spawning steps, 106 player-shot
births, 4,058 shot steps, and 37 boss-life changes, with no unsupported shaped
transition. The shaping remains invalid after boss retirement.

The corrected phase primitive is `constant-frontier-count`: first retain the
full unchanged-action reserve at the route-selected horizon, then rank only
inside that reserve by deduplicated terminal reachable-state count. It does
not add an action to Hard and has no frame, coordinate, bullet-count, or
counterexample branch. The phase uses h12. From exact sub14 entry f5630, h8
survived 57/64 complete delivery sequences; h10 and h12 survived 64/64. H12
raised mean/worst minimum clearance to 10.033/1.329 versus h10's 8.390/0.569.
The heavier full-control replanning h8 also survived 64/64 but had lower
8.505/0.938 clearance and substantially greater sweep cost.

The high-pressure diagnostic derived 59 complete worlds through 4,410 varied
Hard-safe warmup updates and 2,784 source births, spanning 50 enemy-combat, 59
player-attack, and 35 RNG states. Both h10 count-clearance and the new primitive
survived 61/64 fifty-frame recovery trials. The three shared stops were traced:
two delivery seeds restart from the same f5748 state where every tested metric
and h6/h8/h10/h12 horizon has only the same `down_fast` first proposal, while
the third is horizon-sensitive and is recoverable at h8/h12. These arbitrary
late roots are retained as stress evidence; they do not replace the correct
entry-to-boundary test because their warmup policy may already have entered an
unrecoverable state.

Production `Solver` now resets soft ranker commitment whenever `(route_id,
phase_id, policy_state)` changes, so a previous source state cannot leak into
the next one. An actual-Solver f5630-to-t200 closed loop survived 16/16 delivery
sequences. Across 2,041 fresh decisions it measured 8.334 ms median, 10.685 ms
p90, 12.902 ms p99, and 13.229 ms maximum. Seventy-four soft h12 queries missed
their internal budget and correctly became `constant-frontier-count-timeout-
hold`; fresh Hard eligibility was unchanged and every sequence survived.

Linux validation is 273 tests plus 217 subtests passed with 25 native skips.
Windows/native validation is 298 tests passed. The next experiment is a new
ordinary-RNG, default fail-close Practice Stage 1 run. Success means crossing
sub14 to its t200 dispatch and stopping alive at the stable sub13/sub12/sub15
destination (unless the life callback fires first), with no HIT, Bomb, stale
authority loss, or earlier stop. Recheck shaped adjacent parity and diagnose
the earliest consequential state if it fails. Release input and stop the exact
PID afterward.

Checkpoint `6850396` made that run possible, but the run exposed an earlier
integration dependency instead of reaching sub14. Default fail-close stopped
alive at f1362 in `timeline:t1220:random-subs0-1-body-stream/random-insertion`
with an empty Hard set, no HIT, and no Bomb. Input was released and exact PID
60704 was stopped. No trial or offline worker remained.

The empty terminal was again downstream. At f1345 there were 17 Hard actions;
target-free h6 policy volume kept the observed `left` among fifteen tied soft
proposals, while h8/h10 continuation evidence already uniquely selected
`down_fast`. At f1357 h6 again retained `left`, while h8 allowed only
`right/right_fast`. The late f1358/f1360 stale retries carried left input into
the f1362 stop. This physically rejects the old h6 ranking for the whole source
state; it does not justify a frame or coordinate branch.

The captured model is authoritative for this comparison. All 240 retained
adjacent pairs matched player, combat enemy, Reimu-A attack, RNG, graze, Rank,
item, and Power transitions. All 11,341 mature-bullet steps, 378 spawning
steps, 41 player-shot births, 936 shot steps, and 24 enemy transitions were
exact, with no unsupported transition.

Exact-entry f1220 stateful sweeps compared complete 180-frame worlds through
t1400. Policy-volume h6/h8/h10/h12 each survived 32/32, but h8 used the fewest
commands and raised mean clearance from h6's 4.831 to 8.542. At h8,
count-clearance achieved 19.855 mean and 14.615 worst clearance but its actual
pipeline measured 9.963/13.425/19.327 ms median/p90/p99 and was rejected for
publication cost. Constant-frontier h8 survived 64/64 but had only 0.988 worst
clearance.

The selected primitive is target-free `constant-clearance` h5: certify the
unchanged-action h5 reserve, then rank that reserve by its own minimum path
clearance. Hard-4 remains the sole eligibility authority. It has no branching
continuation search and no scene-dependent condition. H4, h5, h6, and h8 each
survived 64/64 complete entry worlds; h5 provides the measured cost/clearance
balance at 14.023 mean and 8.973 worst clearance. Across 5,668 actual Hard plus
h5 pipeline decisions it measured 2.162 ms median, 3.102 ms p90, 4.816 ms p99,
7.576 ms maximum, and zero calls above 12.5 ms. The independent compact CE is
`tests/corpus/counterexamples/stage1_f1362_random_insertion_clearance.json`.

Current validation is 276 Linux tests plus 218 subtests passed with 25 native
skips, and 301 Windows/native tests passed. Rerun ordinary RNG/default
fail-close Practice Stage 1. First require crossing f1362 and the t1220 state
without stale authority loss. If it reaches the already authored boss route,
the outstanding sub14 expectation remains an alive stop after t200 at stable
sub13/sub12/sub15 (or an earlier life callback), with no HIT or Bomb. Diagnose
the earliest consequential state of any new failure and clean up the exact PID.

That run crossed f1362 and the full t1220--t1400 insertion, then stopped alive
at f1488 on `input-lease-unsafe`, with no HIT or Bomb. The f1487 command was a
four-edge `down_right` to `up_left` transition; f1488 physically observed its
`left` sorted-key prefix. The original Hard proof already covered exactly that
prefix followed by the settled target. The lease path instead treated `left`
as a new command source and invented another pickup window. Physical bullet
slot 101 leaves only 0.113 clearance if left is held once more, versus 1.527
when the already-issued up-left target completes. InputLease now retains the
issued source action and narrows an observed prefix to `delivery_delays=(0,)`;
an unchanged source input remains conservatively current/prefix/target. The
stateful replay now rechecks each delivery seed's realized next movement under
the same no-second-command invariant. The compact physical CE is
`stage1_f1488_input_lease_prefix.json`.

The earlier route cause was the t1401 residual tail's bottom target, which
produced high-frequency reversals while live bullets drained. From exact f1401
through t1600, target-only h4 survived only 34/64 native production-Solver
delivery worlds and stopped as early as update 69, with 0.371 worst clearance.
Target-free constant-clearance h4 survived 64/64 complete 199-update worlds,
with 11.370 worst clearance. Its 6,797 fresh native decisions measured
0.962/2.262/4.129 ms median/p90/p99, 5.204 ms maximum, and zero over 12.5 ms.
The route tail now uses that existing smallest h4 primitive; the phase contract
is `stage1_f1401_random_tail_clearance.json`.

After validation and checkpoint, rerun ordinary-RNG/default fail-close Stage
1. It must first cross f1488 and t1600. Diagnose the earliest consequential
state of any new failure; do not resume Stage 4 opportunistically. Release all
input, stop the exact PID, and check for leftover game/agent/high-CPU workers.

This integrated checkpoint passes 304 Linux tests with 25 native-only skips
and all 304 Windows/native tests.

The next ordinary-RNG/default fail-close run physically promoted the f1488
lease fix and t1401 tail. It crossed f1488, t1600, the midboss/spell, the later
timeline, sub12, and both sub14 attacks, then stopped alive exactly at f6010 on
stable uncovered sub15 local t1. There is no dead state, Bomb, timeout, or
earlier authority stop in the complete CSV. Exact PID 62008 was stopped, all
input was released, and no game/agent/offline worker remained.

The retained f5742--f6010 history has exact parity for all 242 adjacent player
steps, 25,100 mature-bullet steps, 2,478 spawning steps, 130 hostile births,
111 Reimu-A shot births, 5,049 shot steps, and 20 boss-life changes. Removing
only the source-impossible live-boss timeline wait makes all 242 combat enemy,
shot, RNG, graze, Rank, effect, item, and Power transitions exact with no
unsupported state. Do not use that shaping after boss retirement.

The next root is f6010 at `(27.657,408.348)`, Power 32, Rank 25, boss life 2758,
56 residual bullets, RNG seed 47821/generation 7022. Audit and solve sub15 as a
new source state; do not inherit the sub12/sub14 route policy.

Sub15 is now source-audited and candidate-authored. Time zero points boss
movement relative to the current player, initializes a 16-iteration counter,
and draws one of two rotation signs. Hard uses a variable-angle aimed fan; ECL
float updates plus `JUMPDEC` repeat it every two local ticks. Local t124 draws
a three-way branch to sub13/sub14/sub12. Life callback sub22 can occur earlier
from the f6010 boss life 2758 root. These destinations remain separate states.

Target-free policy-volume h8 reaches a stable destination in 16/16 complete
exact-entry delivery worlds, with 3.487 worst minimum clearance. Hard-safe
warmup derived another 47 complete sub15 roots through 3,568 updates and 3,356
births, spanning 11 enemy-combat, 47 player-attack, and 29 RNG states; h8
reaches a stable destination 47/47 with 0.487 worst clearance. Its 3,165 fresh
native production decisions measure 2.267/3.090/4.578 ms median/p90/p99,
9.538 ms maximum, and zero over 12.5 ms. H5 is cheaper but falls to 1.427 worst
clearance on exact entry; frontier-count h8 adds no survival or clearance and
is slightly slower. Run ordinary-RNG/default fail-close and require an alive
stop or independently covered transition at the first stable sub12/sub13/sub14
or callback-22 identity, with no HIT, Bomb, or earlier authority loss.

This candidate passes 304 Linux tests with 25 native-only skips and all 304
Windows/native tests.

The ordinary-RNG default fail-close run physically promotes sub15. It crossed
the complete variable-angle loop and its source-local t124 RNG dispatch, then
stopped alive exactly at f5782 on stable uncovered sub13 local t1. The last
authored sub15 decision at f5781 still had five h8 policy winners and 19.462
current-bullet clearance; the sub13 stop retained seventeen Hard-4 actions.
The complete 5,618-row CSV has no player-dead state, Bomb bit, timeout, or
earlier authority stop. All input was released, exact PID 60040 was stopped,
and no game, agent, or offline worker remained.

The retained window contains 254 adjacent physical pairs. Player state and
motion, all 22,778 mature-bullet steps, 960 spawning steps, 64 hostile births,
109 Reimu-A shot births, 4,233 shot steps, and 31 boss-life changes are exact.
Removing only the source-impossible live-boss timeline wait gives 254/254 exact
combat enemy, player-shot, RNG, graze, Rank, effect, item, and Power
transitions, with no unsupported state. This shaping remains invalid after
boss retirement.

Use exact f5782 next: player `(124.956, 412.184)`, Power 26, Rank 24, boss at
`(83.813, 103.478)`, 56 residual bullets, RNG seed 59094/generation 7118.
Audit sub13 independently from installed ECL and authoritative interpreter
semantics. Do not copy sub12/sub14/sub15 policy merely because sub13 is one of
their RNG destinations; first identify its movement, complete attack schedule,
branch/callback boundary, then pressure-test the smallest source-clock state.

That audit now selects a bounded sub13 candidate. Installed sub13 performs one
random-in-bounds direction choice at local t0, moves at speed 3 for 60 ticks,
then executes seven opcode-69 `BULLETCIRCLEAIMED` groups at t60, 68, 76, 84,
92, 100, and 108. The Hard-mask groups contain 24, 32, 24, 32, 48, 32, and
48 bullets respectively (240 total); each birth aims from its then-current
boss position at the candidate-conditioned player position. At t228 a
three-way RNG value CALLs sub12/sub14 or falls through to sub15. Those callees
do not RET, while life callback 22 remains an independently stable boundary.

Exact f5782 delivery sweeps reject copying sub12's count-clearance policy:
count-clearance h8 stops on one of eight branches. Target-free
constant-frontier-count h8 reaches a stable t228 destination on 8/8 exact
branches with 2.879 worst minimum clearance. Stateful Hard-safe warmup then
derived 35 complete sub13 worlds from 64 requests through 3,755 updates and
4,432 source births, spanning 28 enemy-combat, 35 player-attack, and 25 RNG
states. H8 reaches a source destination on 70/70 measured delivery worlds;
h9/h10 add no survival. Policy-volume h6 and h8 stop on two and one of those
same 70 worlds respectively, so the frontier constraint is material rather
than cosmetic.

The route now authors stable nonspell sub13 as target-free
constant-frontier-count h8. On sixteen complete exact-entry production-Solver
worlds it reaches sub12/sub14/sub15 16/16. Its 2,789 fresh decisions measure
2.783 ms median, 3.505 ms p90, 5.603 ms p99, and 6.829 ms maximum, with zero
over 12.5 ms and no timeout. Common Hard-4, candidate combat/RNG semantics,
and every destination's independent route remain unchanged. Run ordinary
RNG/default fail-close next; promotion requires crossing all seven aimed
groups and stopping or continuing only at an independently covered stable
destination, with no HIT, Bomb, timeout, or earlier authority loss.

That integrated run took an earlier route dependency and therefore did not
physically promote sub13. It crossed the early Stage 1 route and midboss but
stopped alive at f4773 in
`timeline:t4498:sub0-random-item-resource-formations`, with no HIT or Bomb.
The complete 4,657-row CSV contains one fail-close authority stop. Exact PID
60332 was stopped, input was released, and no game or offline worker remained.

The first model discrepancy was source-defined. At f4498 a life-zero,
non-interactable death-mode-1 boss still occupied enemy slot zero with
`isBoss=true`, but the timeline nevertheless created its two sub0 children.
Authoritative `EnemyManager::RunEclTimeline` gates opcodes 0--7 on
`g_Gui.BossPresent()`, while `Enemy::Despawn` clears `g_Gui.bossPresent` even
when death mode 1 retains the enemy slot. Native capture now reads the fresh
GUI byte at `Gui + 0x20`; older artifacts retain `None` explicitly. Nominal
timeline insertion uses that byte, while Hard suppresses only a current-frame
spawn proved absent by fresh `true` state and conservatively retains farther
future births. The compact physical contract is
`stage1_f4498_gui_boss_gate.json`.

With the physical resource interval shaped only by the successful source
spawn evidence (`bossPresent=false`), all 226 adjacent steps now match player,
enemy transitions, Reimu-A attack, RNG, graze, Rank, item, and Power state.
All 22 enemy-transition steps are exact; the previous three mismatches were
exactly the missing t4498/t4514/t4530 formation pairs. The nominal hot path now
batches source-commutative ECL slices before and after a timeline write, but
falls back to framewise execution on shared RNG or child creation. This keeps
the same 226/226 parity while removing the measured replay cost spike.

The f4773 empty Hard set was downstream. The earliest material policy error is
f4703: all 18 actions remain Hard-4 safe; h8 policy volume is tied at score 17,
so the live Small Power target selects `up`. Targeted constant-clearance h5
instead selects `down_left` from the same fresh world and continues to rank
Power only inside its clearance-best reserve. The compact physical contract
is `stage1_f4703_resource_clearance.json`. It also selects `right`, not the
old unsafe `down`, in the independent f5054 resource-body CE.

H4 is cheaper but fails two of 64 late-root delivery worlds at f4803/f4818.
H5 survives 64/64. A separate source-state warmup generated 48 complete worlds
through 2,488 updates, covering 11 enemy-combat, 48 player-attack, and five RNG
states; 47 retained fresh initial Hard authority and h5 survived 47/47 for 64
frames. Target removal adds no survival and roughly doubles commands, so the
Power target stays. Across 94 consecutive retained physical snapshots, the
actual production Solver with the h5 route measures 2.878 ms median, 4.638 ms
p90, 6.765 ms maximum, and zero calls above 12.5 ms; every decision is fresh
`ok/constant-clearance`.

The resource phase now uses targeted constant-clearance h5. Current validation
is 307 Linux tests passed with 25 native-only skips and all 307 Windows/native
tests passed. The next experiment is an ordinary-RNG, default fail-close
Practice Stage 1 run. It must first cross f4703/f4773 and finish the resource
formation without stale authority loss. If it reaches the boss route, sub13
still requires its first physical promotion; no result from this resource fix
is evidence that sub13 itself has cleared.

The subsequent Practice Stage 1 run crossed the repaired resource phase and
physically completed all seven sub13 aimed-circle groups. It later re-entered
sub12 and stopped alive at f6730 with an empty Hard set, without HIT or Bomb.
The exact retained window has 255/255 adjacent parity across player, enemy,
Reimu-A attack, RNG, graze, Rank, item, and Power transitions, including 130
hostile births and no unsupported transition.

Full battle replay initially refused this boss interval because the timeline
pointer is parked at opcode 12 while boss slot zero remains occupied.
Authoritative `EnemyManager::RunEclTimeline` decrements the timer on that wait,
then the frame-end timer tick restores the same published previous/current
pair. Nominal replay now retains both the raw instruction pointer and timer,
hides records behind the wait from the current forecast, and fails closed for
unresolved/message waits. Focused source tests cover only this occupied-slot
case. With that correction, the f6730 combat world has exact adjacent parity.

The first offline response—one constant-frontier-count h10 policy for all of
sub12—was not promoted. A following ordinary-RNG default full-route run crossed
the complete early Stage 1 route, resource phase, and boss states, then
physically falsified that whole-subroutine hypothesis. It stopped alive at
f6597/sub12 local t132 with no HIT or Bomb; f6466 is the stable sub12 re-entry
and f6526/local t61 is the earliest source-defined residual-tail boundary. All
250 available adjacent physical pairs match combat, attack, RNG, graze, Rank,
item, and Power state, with 150 hostile births and no unsupported transition.

Installed sub12 emits its seven Hard aimed fans only at local t12, t20, t28,
t36, t44, t52, and t60. It emits no later attack before the t180 RNG dispatch.
The route therefore uses two isolated source-clock states rather than a
physical-frame or CE branch:

- local t0--t60 `first-nonspell-aimed-fans`: target-free constant-frontier h7;
- local t61--t179 `first-nonspell-residual-stream`: constant-frontier h8 with
  phase-local right-lane waypoint `(376,320)`.

The active-emission state survives 64/64 complete exact-entry deliveries and
60/60 viable source-valid warmup worlds; h6 loses one varied world and h8 adds
no survival. The residual state survives 64/64 complete exact-tail deliveries
and 63/63 viable varied tail worlds. On that identical varied corpus, the
rejected whole-phase h10 frontier-count policy survives only 33/63. Center
crossing, a lower right-lane anchor, delivery-filtered ranking, and deeper
h9/h10 residual horizons were all falsified before the route change.

The actual Windows production Solver over the retained f6466--f6597 window
uses only the constant-frontier primitive at h7/h8. Median/p90 solve time is
about 1.5/2.2 ms. The old f6483 root still produces one over-budget soft query;
it becomes a fresh-Hard hold and is deliberately left for the integrated
physical falsifier rather than hidden by offline averages. Current validation
is 309 Linux tests passed with 25 native-only skips and all 309 Windows/native
tests passed.

Checkpoint the source wait correction and split sub12 candidate, then run an
ordinary-RNG default fail-close Practice Stage 1. It must cross both f6526 and
f6597 and reach the t180 dispatch or an independently modeled callback without
HIT, Bomb, timeout-driven authority loss, or earlier fail-close. Any new stop
must be traced from its earliest still-viable consequential decision. Release
input, stop the exact PID, and verify no game or high-CPU worker remains.
