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
