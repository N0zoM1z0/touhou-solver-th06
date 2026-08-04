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

Do not continue opportunistically into the deferred Stage 4 f2200 stop while
Stage 1 is the active route. The route packs are intentionally independent;
physical promotion of one phase must not alter another phase's policy.

After the run, release every input, stop the exact trial PID, and verify no
`th06`, agent, or high-CPU process remains. Do not use a PTY.
