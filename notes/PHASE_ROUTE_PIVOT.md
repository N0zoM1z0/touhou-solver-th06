# Phase/Route Pivot Audit — 2026-08-04

The follow-up historical/source audit is in
`notes/LEGACY_POLICY_AND_STAGE5_AUDIT.md`. It explains why the old Stage 1--4
`if` line contained useful phase knowledge, why its global composition failed
in Stage 5, and the non-interference contract for recovering that knowledge.

## Preserved checkpoint

The complete pre-pivot repository is retained by annotated tag
`pre-phase-route-pivot-20260804` at commit `7a35efa`. The tag message records
the decision, retained assets, exact physical evidence, and recovery command.

The strongest immediately preceding Stage 4 evidence was diagnostic, not a
clear:

- `4a4635c`: stopped at f4019 with 17 stale publications and repairable Hard
  loss;
- `16d54fa`: reached f4130 with 93 stale publications and repairable count 0;
- `7a35efa`: stopped at f2762 with 16 stale publications and repairable count
  11;
- no Bomb occurred in those audited runs;
- no current-version Stage 4 clear was established.

An older checkpoint had physically completed Practice Stage 4, but later
general-solver changes regressed integrated behavior. That contrast is itself
important evidence: improving universal model/search components did not
monotonically improve the fixed route.

## Audit conclusion

The repository had accumulated a 3122-line `solver.py`, a 3348-line universal
policy test, progressive horizon/cost adaptation, global/local target state,
attack mixing, and many scheduling counterexamples. Much of the underlying
physics work is valuable, but the online orchestrator was trying to discover
stage strategy under the same 60 Hz deadline used for sensing and publication.

Three facts motivate the pivot:

1. TH06 stage timelines and ECL are fixed programs and can be decoded before
   play.
2. The strategically important branches are structured: RNG, player-relative
   aim, damage/kill timing, callbacks, items/Power, and phase entry state.
3. A universal online search paid repeatedly for known stage structure while
   still struggling to express resource and boss-phase objectives; deeper
   accuracy also caused publication latency.

Therefore the correct unit of strategy is
`difficulty/character/shot/stage/source-phase`, while safety physics remains
common.

## What was retained

- coherent native snapshot capture and exact EXE guard;
- authoritative-source/IDA/runtime evidence boundary;
- bullet, laser, enemy-body, timeline, ECL, RNG, item, and player-attack state;
- future timeline enemy, ECL child, and mutable future-laser work;
- delivery-aware Hard certification and input lease;
- native/reference parity infrastructure;
- barrage_lab stateful replay and source-derived generators;
- compact source/model counterexamples and reusable local planning primitives.

These are infrastructure and experimental assets. They no longer dictate one
universal policy architecture.

## What was retired from the main line

- the adaptive universal effort ladder and its cost EMA/publication recovery;
- universal progressive constant/policy/global scheduling;
- cross-frame guidance target acquisition;
- universal attack/route-reference mixing;
- old tests whose contract was the retired orchestration rather than source
  physics, Hard authority, delivery, or a reusable phase primitive.

The tag, rather than dead production files, is the archive.

## Source findings used by the first pilot

`EnemyManager::RunEclTimeline` in the authoritative clone defines opcodes 0--7
as enemy spawns, 8/9 as message control, 10 as a boss interrupt, 11 as Power,
and 12 as a wait for a boss slot. `EclManager::RunEcl` executes each enemy's
source program and callbacks. Runtime snapshots already expose difficulty,
character, shot type, timeline time/instructions, ECL subroutine bases and
instruction state, boss ID, and life/timer/death callbacks.

The new asset decoder reads the shipped four-byte terminal sentinel and 404
ordinary Stage 4 timeline instructions directly from `ecldata4.ecl`. The
initial phase manifest is checked against those installed source times. Boss
identity is relocation-stable: the current absolute instruction pointer is
mapped back to its source subroutine index.

## Current hypothesis

The common online core should do only coherent sensing, route-neutral future
physics, Hard-4/delivery certification, route dispatch, Hard intersection,
and publication. A phase pack may select a local horizon/algorithm/target or
provide compiled action preferences. Missing route or phase coverage is
explicit and stops rather than falling into an anonymous universal policy.

The initial Stage 4 pre-boss entries use the retained exact local policy-volume
primitive at route-selected horizons. This is a bootstrap, not a claim that
those values are tuned. The next physical run must reveal the first actual
phase boundary, after which stateful offline search should replace that
phase's placeholder with measured policy.

Boss phases are intentionally uncovered. Candidate-conditioned aim,
damage/kill/retirement/callback/RNG causality will be implemented only along
the source path demanded by the next authored phase and parity-checked before
physical promotion.

## First post-pivot physical iteration

Checkpoint `bb66973` ran ordinary-RNG, default fail-close Hard/Reimu-A
Practice Stage 4. It stopped alive at f1329 in
`timeline:t1004:subs2-3` with an empty Hard set, zero Bomb, and no prior HIT.
The exact PID 12680 was stopped, all input was released, and no trial process
remained.

The phase's provisional h12 query measured 16.762 ms median and 27.718 ms
maximum over 159 phase decisions. It produced 17 stale publications and 46
complete-query timeouts. At f1313 it selected `up`; f1315/f1320/f1322/f1325
then retained `up` after timeouts, moving Reimu from y=364.686 to y=344.686.
The last complete f1327 result was stale, and Hard was empty at f1329. The
terminal stop was therefore preceded by a missed replanning window.

Native stateful physical-battle replay retained exact parity for all 148
adjacent player/combat/RNG steps and 8235 fired-bullet steps in the saved
history. On f1290/f1300/f1310/f1313 roots, h8, h12, and h16 each survived the
32-frame replay set; h8 used fewer commands and had mean minimum clearance
6.292 versus h12's 4.921. On the closest f1320 root, h8 proposed `down` while
h12 proposed `down_right`; the physical h12 query timed out and published
neither. The smallest falsifier is therefore phase-local h8, not a new common
fallback or a weakened Hard set.

The h8 physical rerun crossed the old f1329 boundary. Across 317 t1004
decisions it recorded zero stale publications and zero policy timeouts, with
5.926 ms median solve time. It next stopped alive at f1615 in
`timeline:t1514:sub10`, again with no HIT or Bomb. That phase's h12 placeholder
measured 19.785 ms median, produced 10 stale publications and 18 timeouts, and
missed its late correction window. On seven retained f1568--f1607 battle
roots, h8/h12/h16 all survived 32 frames; h8 used 2.64 mean commands versus
h12's 4.50 and h16's 8.93. The next phase-local falsifier changes only t1514
to h8.

## Legacy-policy extraction

The historical Stage 4 clear checkpoint `17fd93a` and the complete pre-pivot
checkpoint were inspected in a detached temporary worktree. The clear solver
contained no `snapshot.stage` branch; its 840 lines used global combinations
of bullet density, lasers, enemy count, boundary relief, Hard-set width, and
continuation cost as implicit phase classifiers. By the later Stage 5 line the
same approach had reached 3122 solver lines and competing scheduling rules.

The replacement now represents each Stage 4 source phase as an isolated,
seekable source-clock state machine. It logs a stable `phase_id` and a separate
`policy_state`. t1514, for example, progresses from `parent-entry` to
`child-circle` at source t1584 because sub10 reaches ENEMYCREATE sub1 at local
ECL t70; the physical f1615 boundary is in that state. Historical dense CEs
f2625--f2709 map before the midboss to the t2388/t2712 source phases, so their
bounded h6 primitive is now owned only by `horizontal-band` and
`dense-aimed-stream`. No bullet-count condition was restored.

The state representation is intentionally deterministic under offline seek:
replaying t2458 directly selects the same state without mutable controller
history. Future RNG/resource/callback machines may implement the same private
intent contract, while common Hard authority remains unchanged.

## First state-machine physical counterexample

The ordinary-RNG default fail-close Stage 4 run after `04f8058` crossed the
old f1615 stop and completed `t1514/child-circle`. It stopped alive without a
HIT or Bomb at f1931 in `t1878/sub3-aimed-stream`. The terminal empty Hard set
was downstream: at f1878 the h12 proposal selected `down_fast` from y=392.24,
and repeated 17--24 ms policy queries timed out while the delivered commands
carried the player to the lower boundary.

The installed timeline spawns sub3 from alternating sides every ten source
ticks from t1878 through t2008. Its Hard ECL instruction is a 9x2 aimed fan,
enabled with a delayed, rank-adjusted interval whose ECL base is 50 and whose
starting timer offset consumes RNG. On retained physical roots f1878, f1890,
f1901, and f1911, one-step native h6 proposals agreed with the compact
candidate-conditioned combat-world proposal on all four roots. h8 disagreed
on two roots. Four static queries took 0.265 seconds; the causal counterparts
took 7.20 seconds, so the causal model is an offline discriminator rather than
an online primitive.

The falsifier changes only `sub3-aimed-stream` to h6. At timeline t2108 the
source switches to sub2, so a separate `sub2-aimed-stream` state retains h12
until physical/offline evidence supports a change.

## Horizontal-band primitive correction

The next ordinary-RNG default fail-close run crossed the corrected t1878
sub3 state and the separate t2108 sub2 state. It stopped alive without a HIT
or Bomb at f2649 in `t2388/horizontal-band`. The terminal empty Hard set was
again an effect: at f2648 there were still four Hard-safe actions. Earlier,
the recursive h6 policy repeatedly reversed vertical direction near y=380,
then committed downward into the lower strip. This identifies unstable local
proposal continuity, not missing Hard authority, as the first falsifiable
cause.

The installed timeline creates two sub11 enemies at t2388 from the top and
two sub13 enemies at t2412 from the sides. Authoritative ECL for both children
emits a fixed non-aimed circle at local t70 and reverses movement at t78.
Candidate-conditioned aim therefore cannot explain this counterexample.
Physical adjacent-frame replay retained exact player, combat, RNG, enemy,
player-shot, fired-bullet, and spawning-bullet parity for all 221 retained
pairs, including 30,258 fired-bullet and 8,868 spawning-bullet transitions.

The historical Stage 4 clear did not use the current recursive
`policy-volume` behavior in this band. Its useful primitive retained only
Hard-4 actions whose unchanged-action path also survived to h6, often keeping
the already held corridor until it ceased to exist. Barrage lab now exposes
both exact `policy-volume` and `constant-frontier` metrics so the production
primitive and this legacy local primitive can be compared without restoring
the old global classifier.

On five retained physical roots, both h6 policies survived 64 frames, while
constant-frontier used 4.2 mean commands versus policy-volume's 10.0. On 20
paired delivery seeds, policy-volume survived 18/20 and constant-frontier
20/20; the latter won the only two differing seeds and lost none. Its smaller
minimum-clearance proxy is an explicit tradeoff, and the delivery model does
not reproduce all compute/publication timing, so the result remains soft.
Only `t2388/horizontal-band` now selects target-free h6
`constant-frontier`; common Hard-4 authority and all other phase states are
unchanged. The next default physical run is the falsifier.

## Sub2 aimed-stream publication correction

The next ordinary-RNG default fail-close run followed a different physical
branch and did not reach t2388. It stopped alive without a HIT or Bomb at
f2227 in `t2108/sub2-aimed-stream`; the terminal state had 11 repairable
actions. From f2119 onward, h12 queries repeatedly took approximately 18--23
ms, returning timeout or stale holds. At f2138 the last newly published h12
proposal selected `right_fast`, and delivery plus later corrections traversed
large horizontal and vertical distances before the terminal stop.

This is not grounds to copy the preceding sub3 h6 policy. Installed ECL makes
the source distinction concrete: on Hard, sub2 emits an immediate 8x2 aimed
fan while sub3 emits 9x2. Ten retained sub2 physical roots were replayed for
64 frames in the complete compact battle world. h8 and h12 each survived
10/10, but h8 used 7.8 mean commands versus h12's 15.3; h6 failed one root.
At the earliest retained divergence f2138, static h8 selected `up_right` and
candidate-conditioned h8 selected `up_right_fast`, while both rejected the
physical/static h12 `right_fast` direction. One causal h8 query took 20.97
seconds, confirming its role as an offline discriminator only.

The smallest falsifier changes only `sub2-aimed-stream` from h12 to h8. The
preceding sub3 state remains h6, the following horizontal-band state remains
target-free h6 constant-frontier, and common Hard-4 authority is unchanged.

Before physical promotion, a higher-pressure phase corpus derived 56 complete
battle worlds from eight captured roots using 697 varied Hard-safe warmup
updates. Those worlds contained 450 source-valid births and covered 19 unique
enemy-combat, 53 player-attack, and 35 RNG states. Across 62 viable 96-frame
delivery cases, policy-volume survived 56 at h8, 58 at h9, 58 at h10, 57 at
h11, and 59 at h12. The deeper result is not directly promotable: h12 already
failed its physical publication deadline, and the sets were not monotonic in
seed identity.

The same paired corpus screened local primitives at h8. Replanning-count
survived 59/62 but used 22.16 mean commands versus policy-volume's 13.56,
cost about 1.5x offline, and selected the causally rejected `right` direction
at f2138. Constant-reserve survived 55/62, winning one policy-volume seed and
losing two. h9/h10 also selected `right` at f2138; h11 selected
`up_right_fast` but had lower corpus survival and near-h12 effort. Thus the
screen did not prove h8 policy-volume globally best. It eliminated the known
alternatives and retained h8 as the only lower-cost candidate that agrees
with the f2138 candidate-conditioned upward direction. Physical play remains
the required falsifier.

## t2712 sub5 target-loop counterexample

The next ordinary-RNG default fail-close run physically crossed the corrected
t2108 sub2 stream and, for the first time, the target-free t2388 horizontal
band. It entered `timeline:t2712:subs5-4-3` and stopped alive without a HIT or
Bomb at f2746. Repeated h6 decisions had only one strongest continuation, but
stale publications held the downward command until fresh Hard authority was
empty. The terminal state was not used as the explanation: the consequential
route transition began at f2713 and the first target-conditioned policy
divergence was f2723.

Installed `ecldata4.ecl` makes the phase subdivision authoritative. t2712
through t2842 spawns sub5, whose Hard instruction is an immediate 2x3 aimed
fan with speeds 1.5/0.7 and 10-degree spacing. t2942 changes to sub4's base
3x2 fan; t3172 changes to sub3's rank-adjusted base 5x2 fan. The route now
names these as three independent states. Evidence from the f2746 failure is
applied only to sub5.

Physical adjacent-frame replay matched 178/178 player steps, all 33,360 fired
bullet steps and 9,720 spawning-bullet steps, and all 178 enemy, player-shot,
and RNG combat-world transitions. There was no unsupported combat transition.
The offline `--target x,y` experiment option reproduces route soft-target
ranking only inside the metric-preferred Hard set; it cannot change Hard
eligibility.

On eleven exact physical roots, target-free h6 policy-volume survived 11/11
64-frame delivery cases versus 10/11 with `(192,380)`. Mean commands fell from
22.09 to 6.36 and mean minimum clearance rose from 1.98 to 4.84. On the f2713
root both policies initially selected `down_right`; at f2723 they diverged.
The bottom-target path stopped after 53 frames with 16 commands at y391.6,
while target-free survived all 64 with five commands and ended at y328.8.
Target-free constant-frontier also survived but held `down_right` to y414.1,
so its lower command count did not justify the weaker exit state.

A higher-pressure screen derived 25 complete battle worlds through 940 varied
Hard-safe warmup updates, 4,017 source births, 21 enemy-combat states, 25
player-attack states, and 24 RNG states. Across 30 viable 96-frame paired
delivery cases, target-free survived 28 and bottom-target survived 26. The
target-free policy won four seeds, lost two, tied 24, gained 129 aggregate
survival frames, used 684 fewer commands, and raised mean minimum clearance
from 2.08 to 4.23. This is not universal dominance; together with the exact
physical CE, it selects the smallest next falsifier: keep sub5 h6
policy-volume and remove only its soft target.
