# TH06 Future-World And Offline/Online Audit

Snapshot refreshed 2026-08-04 through repository checkpoint `91ab12b` and the
following measured physical-battle experiments and source-grounded work.
Authoritative source remains
`cc475a0bc3fef38683b0f02224c87ddba0a021d9`.

This is a source-coverage audit, not an implementation roadmap and not clear
evidence.  It records which future-world claims are already supported, which
follow directly from current code paths, and which still need controlled
runtime or physical validation.  `AGENTS.md` and `HANDOFF.md` remain the
working and current-state authorities.

## Central boundary

The useful offline/online split is:

```text
offline: authoritative source and assets -> verified transition program F
online:  fresh physical state + action/delivery/RNG -> instantiate F
```

Offline work may compile immutable ECL/timeline structure, source update
semantics, static expressions, dependency summaries, and parity-checked hot
kernels.  It must not preselect a route or attach a recorded future after the
player action, RNG stream, damage history, pool allocation, or publication
timeline has diverged.

Online work must retain all causal inputs: the versioned native root, update
phase, current input and lease, ECL contexts and stacks, timers and callbacks,
pool occupancy, player path, rank/difficulty, and shared RNG state.  Hard
authority must stop before any unsupported interval.  Nominal or learned
future evidence may rank only inside the fresh Hard set.

The concise rule is: precompute the source program, not a future trajectory.

## Evidence levels

- **Source/current-code fact:** directly established by the authoritative
  clone and current implementation.
- **Coverage inference:** follows from current call sites or unused captured
  state, but has not yet been shown to cause a physical failure.
- **Physical evidence:** supported by a retained runtime transition or
  fail-closed counterexample.

## Current source-grounded coverage

### Source/current-code facts

- The source calc order is GameManager, Stage, Player, EnemyManager,
  BulletManager, then GUI.  Candidate player movement therefore precedes ECL
  births and bullet/laser collision in the same source update.
- Current bullets have separate source-shaped motion for supported EX flags;
  unsupported behavior is conservatively bounded or fails closed.
- Current lasers model warning, active, and despawn phases, moving segments,
  and the shipped midpoint-hitbox bugs.
- Current enemy bodies model axis, accelerated-angle, interpolation movement,
  source clamps, and the source body-collision dimensions.
- Active emitters retain ECL instruction state, locals, stack, callbacks,
  timer/life/shoot state, movement state, rank effects, and subroutine tables.
- All 136 ECL opcodes have one deliberate classification: modelled,
  source-proved hazard-neutral, or fail-closed with a specific reason.
- Hard birth forecasting uses abstract RNG and radial envelopes.  Nominal
  forecasting advances captured RNG state and active emitters frame-first and
  slot-second where the model is complete.
- Source `ENEMYCREATE` can be audited inside the Hard window through newborn
  time-zero ECL and both relevant EnemyManager slot-order cases. Nominal
  forecasting now keeps persistent children in the 255-slot EnemyManager
  world, including the source distinction between a lower already-visited
  slot and a higher same-pass slot.
- Deterministic stage-timeline children are now inserted into the Hard world:
  their source record is decoded, newborn time-zero ECL runs inline, and the
  child is advanced through the remaining Hard interval. Random-coordinate
  timeline children fail closed at their first unresolved RNG dependency.
- Nominal stage-timeline children are now also inserted before the source
  slot loop. Their time-zero ECL, ordinary same-pass update, deterministic or
  shared-RNG position, life override, invert-X write, boss suppression, and
  continuation offset are preserved. This is proposal evidence; Hard still
  rejects an unresolved random coordinate.
- Timeline boss-interrupt records are applied before the affected live boss
  update. The sensor now retains every installed live interrupt target graph,
  including targets whose `ENEMYINTERRUPTSET` instruction precedes the
  captured current ECL pointer.
- `MSGREAD`/`MSGWAIT` timing uses the captured live GUI message VM plus the
  immutable message bytecode. The forecast takes the safe minimum across the
  snapshot priority-11 / GUI priority-12 boundary rather than treating
  dialogue duration as a fixed stage constant.
- Future-created lasers now retain source pointer/store state, execute
  create/aim/store/rotate/re-aim/offset/test/cancel/clear in ECL order, then
  enter the later BulletManager phase. Hard uses rotated AABBs for fixed
  angles and an all-angle union for candidate-dependent aim. Cross-emitter
  stale-pointer/pool aliases that cannot be composed exactly still fail
  closed.

### Physical evidence

- `stage5_f8447_final_frame_enemy_create.json` proves a final-Hard-frame child
  creation can be audited as immediately hazard-neutral.
- `stage5_f8456_persistent_enemy_create.json` originally exposed the missing
  persistent child. The current nominal model now carries those children.
- From retained f8441, two source updates predict the f8443 parent plus six
  children in slots 0..6, every ECL time, and RNG seed/generation exactly;
  child positions differ only by about `1.4e-5`. This validates inline child
  ECL, shared RNG, and the higher-slot same-pass rule on that transition.
- Adjacent physical history has been used to check player movement, existing
  bullet transitions, and newborn bullet geometry.  The current generic
  stateful parity rung deliberately excludes live enemies, spawners, lasers,
  and despawning bullets.
- In the fixed-RNG Stage 5 diagnostic, the captured timeline remained at 3373
  through f3613, advanced to 3374 at f3614 and 3375 at f3615, while the live
  boss interrupt executed across that adjacent boundary. Hard retained all 18
  actions and no authority stop occurred. The 75-second diagnostic reached
  f4320 with no HIT and no Bomb, but is not a default clear.
- From physical f1774, the newly inserted nominal timeline transition creates
  the two f1784 children at `(32,-44)` and `(352,-44)` with ECL time 3, exactly
  matching their positions and ECL phase. The full slot world does not yet
  match: nominal allocation uses 9/10, while the game reuses 0/1 after older
  enemies retire. That mismatch is retained evidence for future
  damage/retirement modeling, not a parity claim.

## Coverage gaps found in this audit

### 1. Stage timeline insertion exists; full nominal occupancy causality is
incomplete

### Source/current-code fact

`native.py` captures the remaining timeline, ECL program/subroutine table,
message stalls, and live boss interrupt graphs. The Hard world now consumes
these fields and inserts deterministic timeline children and boss interrupts:

```text
future timeline instruction
    -> SpawnEnemy
    -> newborn time-zero ECL
    -> possible same-manager-pass update
    -> newborn bullet/laser/body hazard
```

This closes the identified deterministic Hard-4 omission. Nominal forecasting
also installs the children and can consume exact captured RNG for random
coordinates. Random-coordinate timeline records still require a shared-RNG
world envelope for Hard and therefore stop Hard coverage at the unresolved
transition. Nominal slot identity remains contingent on every earlier enemy
despawn, player-shot kill, and callback, which is not yet modeled completely.

### 2. Same frame number does not by itself prove one calc-chain phase

### Source/current-code fact with physical transition evidence

The frame epoch is checked before and after decode, and hazard pools are copied
in one native read.  Player state and other globals are read separately.  The
source calc callbacks can still mutate state sequentially while the stage
frame scalar remains unchanged.  The authoritative initialization and update
chain supply a stronger invariant: `GameManager.gameFrames` and
`BulletManager.time` are both initialized to zero, the former increments at
priority 4, and the latter increments at the end of priority 11 after bullet,
laser, and collision work.  At the supported 1x rate, a controllable complete
hazard root therefore requires equality; `gameFrames == bulletTime + 1` is the
otherwise invisible mid-chain phase.

The implementation copies the BulletManager timer with the native hazard
pools, rejects a mismatched active phase, and reads separately stored player
and global state only after that pool witness. The f3613--f3615 dialogue and
interrupt transition retained fresh Hard authority across the expected source
phase. Broader adjacent parity is still required for each newly inserted
enemy/laser transition; one successful boundary does not validate all of
them.

### 3. Deep exact search runs on a partly nominal future world

### Source/current-code fact

Hard birth coverage is fail-closed for the first four frames.  Beyond that,
the shared planner timeline uses nominal births.  If nominal coverage ends,
future birth/body frames become empty proposal evidence rather than an
authority stop.  Current bullets, bodies, and lasers continue to project.

Thus `exact continuation` currently means exact reachability, delivery
branching, and state deduplication over the prepared forecast.  It does not
mean that the prepared physical future is source-complete.  This does not
enlarge current Hard eligibility, but it can misrank Hard roots and cause an
avoidable later authority cliff.

### 4. Future aim is not candidate-path conditioned

### Source/current-code fact

All production world-forecast call sites currently pass the current player
position repeated across the requested horizon.  Hard radial envelopes remain
conservative.  Nominal aimed births instead use a frozen player position even
when candidate actions move the player before the source emission.

A source-complete proposal forecast must evaluate Player movement before the
corresponding EnemyManager/ECL birth and must retain separate world/RNG states
when two action histories generate different aimed hazards.  Once this is
implemented, reachable-state deduplication cannot use player endpoint alone.

### 5. Persistent world insertion has advanced; future lasers remain incomplete

### Source/current-code fact

- `ENEMYCREATE` and stage-timeline children now persist in the nominal emitter
  collection with exact free-slot selection for the represented world and one
  shared ECL RNG stream.
- A newborn that itself creates another enemy inline still stops coverage;
  exact future slot occupancy also needs enemy retirement and player damage.
- The persistent future-laser world now covers the source create/mutation and
  BulletManager transition sequence. It remains per-emitter for Hard, with
  explicit cross-emitter pool/alias guards; candidate-specific rotated aim is
  still proposal-only because shared Hard must retain the all-angle union.
- Random-coordinate stage records remain fail-closed in Hard even though the
  nominal proposal path can instantiate their captured RNG branch.

### 6. Nominal RNG is exact only within the modelled consumer set

### Source/current-code fact

The current nominal world preserves captured RNG state across modelled active
emitters.  It does not yet compose every possible shared consumer, including
non-ECL RNG consumers, unsupported external instructions, future lasers, and
every action-conditioned damage/callback path.
Nominal RNG therefore remains proposal evidence and cannot gain Hard authority.

## Offline assets and current limitations

### Source/current-code facts

- `barrage_lab/assets.py` implements the source PBG3 format and catalogues
  literal bullet opcodes from the shipped `th06_ST.DAT`.
- Generated individual volleys use source instruction semantics, but their
  synthetic composition is not claimed reachable in a named ECL route.
- `horizontal-bands` selects source-defined aimed fan opcodes by geometry, not
  stage identity, and matures multiple independently aged volleys into dense
  lateral layers. A diagnostic-only band counter never enters Hard or online
  ranking. At 384 bullets the first 12 generated seeds contained 18--23 bands;
  the physical f2940--f2959 worlds contained 17--20 by the same measure.
- Stateful replay can either condition generated worlds on all captured
  player/input/rank/density frames, or start from every complete captured
  bullet world. The latter deliberately removes enemy/laser/timeline state and
  is labelled a physical-bullet ablation, never a complete battle forecast.
- A second `--physical-battle-world` rung retains complete captured bullets,
  ECL emitters, lethal bodies, timeline, slot occupancy, and nominal RNG, then
  advances player pickup, ECL births, and BulletManager state closed-loop. It
  rejects live lasers, despawning bullets, and unresolved timeline waits. It
  is explicitly nominal because player shots, sprite-bound enemy retirement,
  and non-ECL RNG consumers are not yet reproduced.
- `--battle-warmup-frames N` now turns those complete roots into a generated
  battle corpus instead of merely replaying static snapshots. Each case first
  follows a deterministic 1..N-frame closed loop with real 0..3-frame command
  pickup and lease checks. Its exploratory policy samples only Hard-4 allowed
  actions and deduplicates boundary-clamped terminal states before sampling.
  The resulting world therefore carries a distinct player/input history,
  source aim, bullet ages, bullet slots, enemy ECL/timeline state and shared
  nominal RNG. `--minimum-horizontal-bands` filters only corpus coverage and
  never enters Hard or online ranking.
- The independent planner oracle and stateful runner are valuable algorithm
  falsifiers.  They are not replacements for full source-world execution or
  physical play.
- Online sensing caches immutable ECL instruction/program graphs per stage,
  and ECL forecasting caches compiled instruction maps and decoded bytes.
  This removes repeated work but is runtime caching, not full offline asset
  compilation.

## Horizontal-band causal and fuzz evidence

### Physical causal trace

The fail-closed artifact reaches f2959 at `(115.25, 432.0)` with 495 bullets
and no Hard-4 action. Two mature fan bullets plus the bottom boundary are
sufficient for the terminal empty set, but that is only the effect. At f2945
all 18 Hard actions remain; h16 prefers `left_fast`. Physical pickup holds
that command from f2947, while a fresh turn is already needed by f2949 and is
not published. The successful diagnostic reaches the corresponding region at
`(36.0, 405.62)` with 484 bullets, having entered a different lower-left
corridor earlier. Thus it passed the visible strip by preserving a different
stateful corridor, not by recognizing a named pattern.

### Offline differential and stateful results

- 256 generated, physical-density-conditioned horizontal-band worlds (98,637
  bullets total) matched the independent Hard oracle at h8 with no mismatch.
- The physical history supplies 153 adjacent pairs: all 153 player steps,
  48,648 fired-bullet steps, and 7,324 spawning-bullet steps match exactly;
  maximum position error is zero, with 534 births and 485 removals.
- On 24 complete physical bullet worlds, raw h16 terminal multiplicity stops
  early on seeds 8, 11, and 16; exact next-publication filtering survives all
  24. Seed 8 starts at physical f2689 and shrinks from 401 bullets to three,
  with no synthetic birth: raw count chooses `down_right_fast` and loses
  authority after 12 updates, while delivery-aware filtering chooses
  `down_fast` and survives the 24-update replay. The compact regression is
  `stage5_f2689_horizontal_band_stateful.json`.
- A 64-seed source-generated closed-loop run produced 28 initially Hard-4
  viable cases. Raw count survived 21. A coarse one-replan filter improved six
  but regressed seed 51 by forcing a new unleaseable command. Replacing it with
  exact repeated-pickup membership fixed that case; retaining the ordinary
  constant-survival witness when the exact membership set is empty removed
  the remaining regression. The resulting experimental policy survived 26,
  stopped at f23 instead of f4 on one raw failure, and postponed the other
  stop from f2 to f3: five full-sequence conversions plus two longer partial
  survivals, with no losses against raw count in this finite corpus.

These results support the production ordering already intended by the solver:
fresh repeated-pickup continuation first, deep terminal volume second, and an
understood constant witness when the stronger optional rung is empty. They do
not justify making the experimental barrage policy a new online controller,
nor do offline survivors count as a physical clear.

### Full physical-battle stateful results

Eight retained roots at f1733, f1774, f1784, f1804, f1840, f1880, f1920, and
f1929 were replayed for 180 updates at h8/h12/h16 with captured bullets,
emitters, timeline and source-valid future births. Raw terminal count stopped
once: the f1920/h12 case lost lease authority after 158 updates. Exact
repeated-pickup filtering survived all 24 root/horizon cases, converting that
case to 180 updates (+22) with no paired survival loss. Raw h16 also survived
all eight and had substantially better mean minimum clearance than raw h12,
so the experiment supports deeper future evidence without declaring one fixed
horizon sufficient.

The workload took about 135 seconds for raw count and 146 seconds for the
delivery-filtered policy on Windows. It is deliberately a high-intensity
offline falsifier. Its retained f1774 slot divergence proves that the next
modeling target is not more synthetic bullet volume: action-conditioned
damage/kill/callback and source enemy retirement are required before the
battle rung can claim physical world parity.

### Generated full-battle horizontal corpus

A high-intensity run used the latest ordinary-RNG Stage 5 physical history,
required at least eight mature lateral strips per source root, and requested
64 nominal warm-ups of at most 48 updates. It retained 55 complete battle
worlds drawn from 64 distinct physical roots. Before policy measurement the
warm-ups advanced 1,543 battle updates and inserted 2,032 bullets through the
continued ECL/timeline world; no standalone synthetic birth schedule was
used. This is materially different from regenerating isolated volleys or
repeating one captured bullet image.

That run also falsified the lab's first implementation of
`delivery-filtered-count`: the lab asked only for the final h16 membership and
fell back to an unrelated constant h6 witness when it was empty. Production
instead completes h8, h12 and h16 as indivisible membership/rank pairs and
retains the last complete nonempty rung. A generated f1854 world exposed the
difference: the old lab fallback chose `up` and stopped after four updates,
while the progressive oracle removed that survival regression and reached 37
updates, matching raw count's duration. The lab now mirrors the production
ladder; a focused regression fixes this contract.

With the corrected oracle, a fresh 16-case run generated 15 battle worlds
from 16 physical roots. Its warm-ups advanced 500 updates and inserted 440
source-world bullets. All 16 initially viable cases survived the subsequent
120-update closed loop under delivery-aware h8, h12 and h16. Against raw
terminal count it converted 1, 3 and 3 failures respectively, for paired
survival gains of +103, +228 and +247 updates, with no loss in that run.

The larger discovery run still provides negative evidence. Two retained
worlds at f1844/h8 and f1850/h12 let raw count survive 120 updates while the
delivery filter stopped after 72 and 50 for one concrete pickup schedule.
Across pickup seeds 0..15, raw survived both worlds 16/16; the filter survived
15/16 and never beat raw there. Their first divergences reject `up_fast` and
`down_right` respectively because those actions lack worst-case repeated-
pickup membership even though the sampled delivery succeeds. These are
general robustness/ranking counterexamples, not a reason to weaken Hard or
special-case their coordinates. They remain nominal and should not become a
large committed physical-CE fixture before damage/retirement and candidate-
conditioned aim close the known world gap.

## Latest physical causal trace

The first integrated run after persistent ECL-child insertion was a fixed-RNG
default fail-close diagnostic and stopped at f1948, before the f8442 child
transition. It therefore neither validates nor falsifies that child model.
At f1774 the controller changed from `up_right` to `left`: local h12/h16/h20
were tied and the soft suppression target at x=22 broke the tie. The old
nominal forecast ended at the timeline enemy transition eight frames ahead,
so deeper ranks silently contained no later birth/body evidence. By f1804,
exact p8 terminal volume already preferred the rightward family, but the
online budget completed only membership and preserved the held left input.
At f1943 h12/h16 excluded left; f1945 and f1947 were stale retries, and fresh
Hard-4 became empty at f1948. Thus the terminal stop is an effect of a long
left-wall commitment plus a missed correction window, not evidence that the
horizontal strip itself was inevitable.

The next ordinary-RNG default fail-close run stopped without a HIT at f1874,
at `(8.0, 103.30)` with 487 bullets. The terminal empty Hard set is again an
effect. At f1804, after the route had reached the left wall, every action still
passed complete repeated-pickup h8 membership, but exact h8 terminal volume
already preferred the rightward family; the live budget published membership
only and correctly preserved the still-viable held `up_left_fast` rather than
allowing a soft target to manufacture a switch. By f1833 exact h12--h20
preferred a down-right correction. At f1849 the held `up_fast` action left the
h8 membership set; without a completed survival rank the soft attack target
selected `up_left`. Exact terminal evidence at that state preferred down or
right families. By f1869 only local `up_left` remained and h12+ was empty;
f1871 had no modeled continuation and f1874 lost Hard authority. The earliest
clear correction opportunity in the retained evidence is therefore the
unpublished terminal rank at f1804, while f1849 shows the separate unresolved
problem of ranking a complete membership set after the held action is
excluded. Neither supports a boundary or frame special case.

## Smallest useful direction

The evidence order for future work is now:

1. Retain the new Hard and nominal timeline/ECL-child insertion and validate
   another adjacent timeline spawn with exact slot occupancy; add a
   source-bounded Hard envelope for random timeline coordinates.
2. Model the smallest action-conditioned combat transition needed by the
   f1774 slot mismatch: player shot hit geometry, damage, kill/despawn, and
   callback entry. Keep attack soft; only source world state changes.
3. Make nominal future aim candidate-path conditioned and preserve shared
   RNG/world state per causal branch; then insert future laser state.
4. Extend adjacent-frame parity only for each newly supported transition,
   including enemy retirement and bullet-pool insertion/removal.
5. Profile the integrated online path, then compile immutable ECL/timeline
   blocks offline or move a measured stable kernel to native code without
   changing semantics.

Every promotion still requires one source or physical falsifier, focused
parity, and a default fail-close physical rerun.  Stage data may select the
source program being executed; it must not select safety laws, horizons,
ranking mechanics, or route actions.

## Player-attack transition audit (2026-08-04)

The next combat slice now has a source-grounded online root.  The native
snapshot retains all 80 occupied `PlayerBullet` slots, Reimu-A homing state,
the previous-frame last-enemy target, focus/orb and fire timers, live shot and
enemy sprite dimensions, the active spell/bomb bits, enemy death animation
and drop fields, random-drop indices, and conservative effect/item pool active
upper bounds.  The two pool bounds cost only two four-byte reads; the online
hot path does not copy either 512-entry presentation pool.

The authoritative Player order is movement/orb state, existing-shot update,
last-target reset, then fire-timer spawn.  EnemyManager later visits slots in
ascending order, applies shot collision/damage/death, and updates the new
homing target.  Reimu-A rank-9 static shot data is compiled into the offline
stateful model as source physics, selected by character/shot/power state and
not by stage.  Other power ranks remain explicit unsupported states rather
than silently borrowing rank 9.

Two controlled ordinary-RNG Practice Stage 5 diagnostics corrected and then
validated this transition.  The first exposed that GUI-message state gates
`StartFireBulletTimer`, and a short follow-up exposed the source switch break
when `ORB_FOCUSING` reaches `ORB_FOCUSED`.  After those general source fixes,
162/162 adjacent active attack states, 132/132 newborn shots, and 3,370/3,370
existing-shot transitions matched physical state; player and shot position
error was zero in that sample.  A preceding 30-second sample also matched all
1,590 newborn shots and all 63,918 existing-shot positions.  These are
diagnostic transition results, not a stage clear.

Damage remains the next boundary.  `CalcDamageToEnemy` mutates each non-laser
shot during the ascending enemy-slot loop, caps raw per-enemy damage at 70,
then applies spell reduction.  A successful hit also allocates effect 5;
EffectManager priority 10 consumes two global RNG values for every allocated
effect 3--11, after all priority-9 ECL work.  Enemy death effects, ECL
`EFFECTPARTICLE`, random item drops, and item-pool capacity share this causal
path.  A damage model that merely subtracts life would therefore corrupt the
next frame's ECL RNG and is not eligible for exact/physical-CE claims.

## Candidate-conditioned combat transition (2026-08-04)

The nominal one-frame world now executes the source priority chain needed by
candidate-conditioned Reimu-A combat.  A candidate position/focus changes orb
positions, existing homing shots, and newborn shots before EnemyManager runs.
Enemy slots then advance in ascending order through sprite-bound retirement,
life/timer callbacks, ECL, player contact damage, player-shot collision, the
70-damage cap, spell reduction, death mode, callback entry, explicit/random
item drops, and slot retirement.  Timeline and ECL children now retain their
source `itemDrop`; ECL effect/item requests and boss `ENEMYKILLALL` are world
events rather than presentation no-ops.  Unsupported event ordering still
fails closed.

Shipped assets exposed a source RNG consumer omitted by the first draft.
`SpawnParticles` immediately runs the selected ANM script.  Offline parsing of
`etama4.anm` shows a time-zero `SetRandomSprite` for effect IDs 4--11 and 19,
so each such allocation consumes one u16 before later priority-9 work.  The
priority-10 callbacks then consume their own f32 values.  All six stage effect
ANMs were also checked; the stage-specific effect 16 script has no time-zero
random sprite.  The model now preserves this ordering instead of adding an
aggregate RNG correction at frame end.

Four ordinary-RNG, non-PTY Stage 5 Practice diagnostics used the exact EXE and
native-C++ backend.  Each launcher/agent pair agreed on the exact PID and hash,
printed the formal Hard/Reimu-A/Stage-5 menu selection, released every input,
and stopped that PID before offline comparison.  The latest 25-second sample
captured 1,058 snapshots and 927 physical adjacent pairs.  Among 747 supported
alive combat steps, all 747 complete player-shot states matched.  It contained
231 observed enemy birth/removal/life-change frames; 228 matched the full
enemy transition before the next two general source gaps were isolated.

The retained adjacent pairs explain those gaps rather than hiding them:

- f440->441 proved that `SpawnEnemy`'s zeroed callback-sub fields are 0 even
  while their thresholds are -1; the source template was corrected.
- f458->459 had exactly three shot impacts.  Effect-5 allocation plus its
  ANM/callback path requires 3 * (1 + 4) = 15 RNG generations; the corrected
  transition matches enemy life, all shot mutations, effect count, seed, and
  generation on the original physical pair.
- f1042->1043 proved that a future child whose center is inside the playfield
  is already source-in-bounds independent of unknown sprite extent.  This
  general geometric proof fixes the transition without assuming the observed
  15x16 sprite.  Exact outside-center retirement still needs ANM-derived
  extent.
- f604->605 has no live enemy but advances RNG by three while one hostile
  bullet retires.  This is external/global ANM state, not candidate damage.
  It remains an explicit exogenous-RNG boundary: deep nominal branches must
  capture/compile those pending consumers or use a physical exogenous draw
  tape; they may not call the RNG continuation exact yet.

These diagnostics validate the newly modeled local combat transitions over
their supported domain, not a Stage clear and not yet a stable multi-frame
physical CE.  The next barrage-lab promotion must preserve the external RNG
boundary, use candidate paths for aim and damage, and compare deeper branches
only when their source RNG dependencies are complete.

## Candidate-conditioned stateful corpus promotion (2026-08-04)

The barrage lab now has two explicit proposal-only causal metrics.  The full
`causal-world-count` oracle advances every bounded delivery/prefix branch and
every fixed-segment continuation through the compact battle world, deduplicates
complete `Snapshot` states, and counts no unsupported transition.  The cheaper
`causal-split-count` advances the first four physical delivery frames through
that same world, then starts the existing terminal planner from the resulting
branch-specific state.  In both cases Hard supplies the candidate set; neither
metric changes safety eligibility.

A focused integrated regression makes the causal contract concrete without a
stage or coordinate branch in the solver.  From one synthetic source-valid ECL
world, `left_fast` and `right_fast` aim the same opcode-67 bullet differently.
Only the right candidate's newly spawned rank-9 main shots overlap the enemy,
so only that branch applies damage, enters death mode 1, installs the captured
death callback, consumes the modeled effect RNG, and emits the callback bullet
on the following frame.  This exercises candidate path -> aim/shot -> kill ->
callback -> future hazard/RNG in one independent test.

Runtime diagnostic artifacts containing selected parity snapshots can now be
used directly as physical battle roots.  A Windows-native smoke run from
physical f1042 preserved the adjacent parity report and replayed the full
battle world.  A 32-seed, 32-frame native sweep of that root took 23.07 s:

- h4 stopped on lease authority in 8/32 histories at update 20 and survived
  all 32 updates in the other 24;
- h8 and h12 survived all 32/32 histories;
- mean minimum clearance was 2.95, 5.34, and 13.51 for h4/h8/h12;
- h8 beat h4 in the same eight delivery seeds.  This is a repeatable offline
  algorithm family, not physical clear evidence.

Varied Hard-safe nominal warmup from f1042 generated 26/32 complete worlds over
up to 64 updates (four authority stops and two lease-authority stops), with 192
future bullet births, 22 enemy combat signatures, 26 player-attack states, and
22 RNG states.  Corpus conditioning now measures candidate causality itself:
it retains a root only when the current Hard-4 actions, continued for a stated
proposal horizon, produce multiple enemy combat states.  The filter is generic
and has no stage/frame/coordinate/bullet-count key.  In this sample no root
forked enemy state by h4 or h8; one of 26 forked by h16, with two enemy states,
two RNG states, and 17 player-attack states.

That one conditioned root did not yet justify promotion.  Over an eight-update
paired replay, static `count` and `causal-split-count` both first chose `left`,
issued two commands, survived all eight updates, and had the same 7.55 minimum
clearance.  Static ranking took 0.159 s; causal split took 6.40 s.  The causal
model therefore exposes real branch state but has not improved this physical
root's decision.  More physical combat roots are required; tuning this result
would be a counterexample special case.

Measured Python cost also constrained the implementation.  The initial full
h8 causal frontier exceeded 25 s per decision and retained about 330 MB through
a zero-hit whole-Snapshot transition cache.  Removing that cache kept only
frontier state deduplication.  Replacing reflective `dataclasses.replace` on
flat hostile/player-shot records and the general margin-distance calculation
for exact current-frame AABB overlap preserved 356/356 hostile-bullet, 116/116
player-shot, and all retained enemy-transition adjacent parity.  A single h8
oracle candidate fell from about 2.6 s to 0.68 s; the full 18-candidate oracle
is still about 20 s and remains a reference, not a hot path.  Further native
work is justified only after more conditioned roots show that this causal
ranking changes useful decisions.

### Fresh physical combat corpus (2026-08-04)

A subsequent default fail-close, ordinary-RNG Hard/Reimu-A Practice Stage 5
trial used the exact supported EXE, native-C++ solver, and the diagnostic life
patch.  It stopped at f2973 on `hard-safe-set-empty`, with the player still in
the alive state.  The agent released every key, stopped exact PID 55676, and a
process audit found no game or agent left running.  This was an authority stop,
not a HIT and not a clear.  The ignored failure artifact retains 256 complete
attack/world roots from f2635--2973.

The 176 adjacent physical pairs in that history materially extend combat
coverage:

- hostile fired bullets matched 57,835/57,835 and spawning bullets matched
  7,855/7,855, with zero maximum error;
- complete player-shot transitions matched 10,396/10,396 and all 176 attack
  states matched; maximum shot position error was 3.05e-5;
- all 176 supported enemy steps matched, including all 99 frames containing
  one of 114 life changes, two slot births, or four removals;
- combat RNG matched 145/176.  The first mismatch, f2665->2666, advances four
  exogenous generations while all five enemy slots and every modeled combat
  transition match.  This is the same uncaptured global-ANM boundary, not a
  damage/kill mismatch.

Ninety-nine adjacent roots actually changed enemy life or occupancy, but none
of eight selected low-life/death roots forked enemy state inside the first four
candidate frames.  This is expected: existing Reimu-A shots largely inherit
the previous target/path; current movement changes newborn main/orb shots and
needs several frames to alter damage.  Conditioning the same current Hard-4
candidate set with a 16-frame proposal continuation retained four physical
roots (f2711, f2716, f2720, f2724).  They reached as many as three enemy combat
states, three RNG states, and 18 player-attack states.  The conditioning horizon
changes corpus selection only; it does not extend Hard eligibility.

One-decision paired replay changed first action on two of those four roots:
static `count` chose `up_right/up_right/up/up_left`, while causal split chose
`up_right/up/up/up`.  Eight-update independent follow-ups gave mixed evidence:

- f2716: both survived; causal `up` raised minimum clearance from 9.46 to
  10.78, but issued three commands instead of zero and cost 4.48 s versus
  0.17 s;
- f2724: both survived with identical 13.23 clearance; causal `up` used one
  command instead of static `up_right`'s two, but cost 10.59 s versus 0.20 s.

Thus the candidate-conditioned model now finds real solver decision divergence
on physical battle states, but this sample proves neither survival benefit nor
an online-affordable implementation.  Keep it offline, enlarge the physical
conditioned corpus, and diagnose the earliest causal differences before any
production ranking or native combat-kernel promotion.

## Deferred graze RNG and item-state closure (2026-08-04)

The 31 RNG mismatches above had a discrete residual vocabulary: +1, +4, +6,
and +8 source generations, never a negative residual.  Authoritative source
inspection identified the missing chain.  BulletManager priority 11 moves a
fired bullet, performs the one-shot `isGrazed` check, then calls `ScoreGraze`.
That call creates effect 8, adds 500 score, and calls `IncreaseSubrank(6)`.
`SpawnParticles` immediately executes the effect ANM, whose time-zero random
sprite costs one u16 generation.  EffectManager has already run at priority
10, so the new effect retains timer `(-999, 0)` at the frame boundary; its
random-splash callback consumes two f32 values, or four u16 generations, on
the following update.  This explains the residual shape without a recorded
draw tape or correction constant.

Checkpoint `4006e3f` captures the physical state needed by this transition:
the bullet `isGrazed` byte, GameManager rank/subrank bounds and remainder, the
actual occupied effect-slot count, and the IDs of effects whose timer proves a
post-priority-10 birth.  The offline world now executes deferred callback RNG,
candidate-conditioned graze collision, the one-shot flag, rank carry, and the
same-frame ANM draw.  It also models the later-than-EffectManager player-death
effect timing for branches that enter a collision.  Visual effect state is not
copied into the model.

The first ordinary-RNG default fail-close Stage 5 run after that checkpoint
stopped alive at f2034 on `hard-safe-set-empty`.  Its 124 supported adjacent
combat steps matched enemy state, complete player-shot state, pending effect
state, and RNG 124/124; the former first RNG mismatch disappeared.  Detailed
rank parity then exposed three independent item transitions (-3, -3, +3), not
a remaining graze defect.  Source says ItemManager runs before the hostile
bullet loop, decreases subrank by three when an item exits at y=464, and
changes rank/power according to the acquired item type.

Checkpoint `2a5c25c` therefore adds compact occupied `Item` records and the
source pool cursor.  The one-frame battle world now advances interpolation,
falling and gravity, full-power attraction, candidate-conditioned collection,
out-of-bounds removal, power, and rank/subrank; enemy-death drops are inserted
through source slot allocation.  ECL item events that expose only a count but
not yet type/position remain explicit unsupported state, as do acquisitions
that newly trigger `TurnAllBulletsIntoPoints`.  They are future insertion work,
not silently neutral events.

A second ordinary-RNG default fail-close Stage 5 run used the exact EXE and
native-C++ Hard solver, stopped alive at f2024 on `hard-safe-set-empty`, then
released all keys and stopped exact PID 43236.  No game, agent, or high-CPU
trial process remained.  In its retained 100 adjacent combat steps:

- fired hostile motion matched 16,583/16,583 and spawning motion matched
  2,792/2,792; maximum hostile error was 1.19e-7;
- complete player-shot world state, enemy world state, RNG, graze flags,
  rank/subrank, pending effects, current power, and item slots each matched
  100/100;
- the sample contains five physical `isGrazed` transitions, four item-slot
  births, three item-slot removals, and 59 enemy life/occupancy transition
  frames;
- item position/state initially matched 98/100.  Both errors were the same
  source detail: velocity 2.989996 receives +0.03 and overshoots to 3.019996
  for one update before the next frame's `else` clamps it to 3.  Reproducing
  that order raised item parity to 100/100 on the same physical sample.

The latest trace has 1,572 rows: 1,560 `ok`, 11 stale retries, and one
fail-close stop.  Mean recorded solve time was 9.82 ms, p95 16.32 ms, maximum
35.32 ms.  The effect and item pool reads enlarge sensing and should not be
promoted as free: this single trajectory does not isolate their latency from
barrage/solver cost.  Their purpose is currently high-fidelity physical corpus
capture and offline causal replay.  Any permanent online use should be
measured against a tail-latency baseline or moved to a small native extraction
kernel once the offline causal solver proves useful decisions.

These transition results validate a substantially more faithful offline
fuzzer world; neither run is a Stage clear.  The terminal Hard-empty states are
effects and have not been used as the diagnosis for this slice.  The next
model boundary is source-complete future item insertion (including ECL drops
and full-power bullet conversion), followed by future laser state and a
measured use of the enlarged causal corpus to find an earlier consequential
solver decision.

## Exact item insertion and live-laser transitions (2026-08-04)

Authoritative ECL item births are now events rather than counts.  Opcode 119
draws two source f32 values per item for its offset and emits one big Power
item followed by small Power items below full power, or Point items at full
power; opcode 124 emits its explicit type at the enemy position.  Nested ECL
children propagate these events into the same priority-9 enemy pass, and the
priority-11 ItemManager inserts them through the captured 512-slot cursor.
The integrated synthetic regression covers two random-drop items plus one
explicit item and observes the exact eight RNG generations and slot order.

The 127-to-128 Power boundary now reproduces source
`RemoveAllBullets(true)`: the acquisition remains present while later item
slots are allocated, every active hostile bullet is replaced by a state-1
Point item at its pre-BulletManager position, and later allocated slots are
updated in the same live ItemManager pass.  A focused regression verifies the
rank, Power, item timer, pool cursor, and bullet removal.  No physical
low-Power crossing was captured, so this boundary has source/unit evidence,
not physical parity.  The corresponding live-laser conversion remains
explicit unsupported instead of silently deleting beams or manufacturing
items.

The offline battle world now also advances existing source `Laser` records.
It preserves the two shipped midpoint-hitbox bugs during warmup and despawn,
both switch fallthrough transitions, timer resets, repeated 12-frame laser
graze, rank/effect RNG, length clamping, and natural removal.  A formal
adjacent-frame report isolates retained lasers whose origin and angle were not
mutated by the earlier ECL pass.  On the ignored physical Stage 1 artifact
`th06_failure_stage1_f10068_action_factor.json`, all 658 such transitions
match exactly, including start/end offsets, state and timer; maximum numerical
error is zero, and the history also contains six laser births.  This validates
the BulletManager state machine only.  ECL laser creation, pointer ownership,
rotation, aimed rotation, offset, test, cancel, and clear-all are the next
future-world boundary and must remain unsupported until their same-frame
ordering is modeled.

Checkpoint work after `adc5857` closes that exact nominal boundary.  Each
captured enemy now carries its 32 raw laser-pool pointer identities and
`laserStore`; inactive pointers are retained because a later pool reuse can
make them alias a new live laser.  The shared nominal world allocates the
first free slot in the source 64-entry pool and executes opcodes 85--92 and
134 in ECL order: create/aimed create, store selection, relative rotation,
candidate-conditioned re-aim, offset, liveness test, cancel, and pointer-table
clear.  A created beam then joins BulletManager's later priority-11 pass in
the same update.  Focused tests verify both pointer/mutation order and the
same-frame `endOffset 20 -> 22`, `timer 0 -> 1` transition.

Hard forecasting initially retained its earlier fail-closed boundary when a
newly created laser could become collidable inside the certified window.  The
next checkpoint replaces that blanket stop for source create/aimed-create:
the future beam now advances its phase, offsets, length clamp, timer, and both
shipped midpoint-hitbox bugs from the same-frame BulletManager pass onward.
A fixed-angle beam is inserted as the conservative AABB of its rotated source
rectangle.  Because the current Hard ECL forecast is shared across candidate
paths, an aimed beam uses the union over every possible aim angle rather than
borrowing one nominal player path.  Laser-store writes are retained, and a
cancel may conservatively keep the pre-cancel hazard alive.  Future rotate,
offset, re-aim, and liveness-dependent control flow still fail closed at their
first mutation; they are not silently projected as static.

A raw scan of the authoritative installed ST.DAT gives the practical scope:
the shipped ECL contains 140 opcode-85 creates, 14 aimed creates, 139 store
writes, 79 rotations, 15 offsets, and five cancels; opcodes 89 and 91 do not
occur.  Thus the new Hard insertion covers many create/warning intervals and
same-time multi-create sequences, while rotation remains the dominant real
future-laser boundary.  The aimed angle-independent AABB is deliberately
conservative and may contract Hard more than a future per-candidate rotated
stream; it cannot create false safety.

A 30-second ordinary-RNG, default fail-close, non-PTY Stage 5 diagnostic then
validated the enlarged native capture against the exact supported EXE.  It
ended only because the time window expired, after reaching f1500 with no HIT
or authority stop.  The run exercised snapshots containing one to six enemy
slots without a pointer-layout, phase, or coherence failure.  All inputs were
released, exact PID 55288 was stopped, and no game, agent, or high-CPU worker
remained.  This is capture/integration evidence, not a Stage clear and not
physical parity for a future laser creation event.

The same shared pool closes the previously explicit full-Power laser gap.
`RemoveAllBullets(true)` changes each live laser below state 2 to state 2,
resets its timer, emits one state-1 Point item at every 32-unit offset in the
half-open `[startOffset, endOffset)` beam segment, and sets
`hitboxEndDelay = 0`; already-despawning lasers emit no items but still lose
their hitbox delay.  Allocation uses laser pool order and the live ItemManager
loop, so newly allocated later item slots advance during that same update.
The focused 65-unit regression produces offsets 0, 32, and 64 in item slots
1--3, all at state 1/timer 1, while the source laser reaches state 2/timer 0
before its later BulletManager pass.  This boundary still lacks a naturally
captured 127-to-128 physical transition and therefore retains source/unit,
not physical-parity, status.

## Mutable Hard future-laser world and Stage 4 probe (2026-08-04)

The first default fail-close Stage 4 capture after pointer insertion stopped
alive at f2607 with no live laser. Its 176 adjacent roots retained exact
combat-world parity, including the newly captured default laser pointer/store
state. This was a capture smoke, not future-laser physical parity and not a
diagnosis of the terminal empty Hard set.

An explicit ordinary-RNG `--continue-on-failure` Stage 4 diagnostic then ran
to f5601. It recorded eight Hard authority losses and two physical HITs, so it
is diagnostic evidence only. The full 4,265-row trace contained no live laser
at all (`max_lasers=0`); it therefore cannot validate laser creation or
mutation. The final sensor error, `incoherent boss pointer at enemy slot 6`,
is a separate capture-authority observation. The launcher released all input,
stopped exact PID 22184, and left no game or high-CPU trial process behind.

The authoritative ST.DAT sequence audit explains why the remaining mutation
boundary matters even though that physical route did not reach a beam. Stage
1 sub 18 is six aimed creates eight ECL ticks apart and is normally handed to
fresh physical roots. Stage 4 subs 28--35 instead perform create, rotate, and
store writes in the same ECL update; Stage 7 also contains same-update
create/rotate/offset and next-frame cancel sequences. Waiting for the next
snapshot cannot certify those priority-9 writes before the priority-11 laser
collision pass.

Hard now first tries the existing batched forecast and switches to a compact
mutable laser world only when a reachable laser mutation stops that batch.
The retry runs one source frame at a time:

```text
candidate-independent ECL state
    -> pointer/store create and mutation in instruction order
    -> BulletManager segment/phase/timer update
    -> conservative Hard AABB for that same collision phase
```

Fixed-angle mutations retain rotated geometry. Aimed create, re-aim, or an
abstract angle remains an all-angle union; no repeated current-player position
is promoted into Hard fact. Pool exhaustion, two emitters mutating one current
aliased beam, a dereferenced stale pointer that may alias a future allocation,
or cross-emitter allocation after a future retirement fails closed. This
keeps the implementation smaller than a second global battle simulator while
making the represented paths source-ordered and conservative.

A focused integrated regression proves same-frame create -> rotate -> offset
places the first BulletManager hitbox at the mutated origin/angle and keeps an
aimed beam angle-independent. Direct execution of installed
`ecldata4.ecl` subs 28--35 now covers all four requested Hard frames for every
subroutine; each reachable path creates four source beams and no longer stops
at opcode 88. Stage 7 sub 58 still fails earlier on the uncaptured ECL Z
coordinate, so no laser result is claimed across that authority boundary.

The laser-state refactor preserves the retained physical Stage 1 report:
658/658 stable adjacent laser transitions still match with maximum numerical
error zero and six observed births. On 64 laser-bearing physical Stage 1
roots, 640 repeated Hard-4 forecasts all retained coverage four; mean isolated
birth-forecast time was 0.131 ms on this host. The full focused suite passes
343 tests with 28 skipped. These are source, unit, asset, and retained physical
transition results. A naturally reached physical same-frame ECL laser
creation/mutation remains the required adjacent-frame parity experiment.

## Boss identity versus stage-timeline pointer capture (2026-08-04)

The first default Stage 1 run after the mutable-laser checkpoint stopped alive
at f1217 on an empty Hard set, before any live laser. Two explicit
`--continue-on-failure` diagnostics then reached roughly f3450--f3520. One
transient trace contained two live lasers and no new authority loss while
they were present, but that artifact was overwritten by the next ordinary-RNG
path and is not adjacent-frame parity evidence. The diagnostics instead
exposed a repeatable sensor failure: `incoherent boss pointer at enemy slot
0`. Retrying a whole coherent snapshot did not repair it; five reads across
physical frames 3519--3522 observed the same mismatch. Every run released
input and stopped its exact PID. None is a clear.

The source makes the old capture invariant invalid. Stage timeline opcode 10
writes directly through `EnemyManager::bosses[id]`, whereas actual boss
identity belongs to `Enemy::flags.isBoss` plus `Enemy::bossId`. A manager
pointer that names an occupied non-boss slot is still real timeline state; it
does not turn that Enemy into a boss and cannot be classified as a permanently
torn snapshot.

Native capture now preserves the eight manager pointers separately as enemy
slot identities. A non-boss is decoded solely from its own flag. A true boss
also reads the source byte at Enemy offset `0xE40` and must map back through
its own boss id; only a mismatch in that true-boss publication interval is
retried as a torn `BOSSSET`. Hard timeline opcode 10 selects a captured live
emitter through the raw pointer slot, including a stale pointer to a non-boss.
A deterministic future timeline child which executes `BOSSSET` before the
interrupt records its predicted binding in the child world, so an all-null
physical pointer table at the earlier root does not suppress that future
transition. Older corpus snapshots without the new field retain their prior
boss-id fallback.

Focused regressions cover stale-pointer/non-boss capture, true-boss
publication, raw-pointer interrupt selection, and future child
`BOSSSET -> timeline interrupt`. The complete suite now passes 347 tests with
28 skipped. The capture distinction is source- and unit-grounded; the next
physical diagnostic must cross the former f3522 failure before it counts as
runtime validation.

The first post-fix physical diagnostic reached f3438 with two live lasers and
no boss-pointer coherence failure. It then stopped on an `IndexError` in soft
native preparation, not on a HIT or Hard authority decision. The traceback
identified an independent forecast contract bug: extending a completed
nominal prefix with a partial tail represented "no body hazards" as one empty
tuple for the entire tail, then concatenated it as though it were already a
frame array. Thus `covered_frames` could exceed the length of
`body_hazards`. The extension now materializes the compact empty sentinel to
one empty body frame per forecast frame and rejects any other misalignment.
A focused partial-tail regression raises the complete suite to 348 tests with
28 skipped. Exact PID 43308 was stopped, input was released, and no trial
process remained. This run confirms the stale-pointer capture correction on
that trajectory and exercises live-laser integration, but still does not
provide adjacent-frame future-laser parity or a clear.

The following 90-second continue diagnostic reached f5319 without either
capture or forecast-contract failure. Its 4,321-row trace contains 366 sampled
rows with two live lasers from f3418 through f4571. It also contains 16
recorded Hard authority losses and four physical HITs, so it is strictly
diagnostic. The first laser-window authority loss was f3445. An offline
ablation on that exact captured snapshot was decisive: the full world had
0/18 Hard-4 actions, while removing only the emitter, removing only the two
lasers, or retaining bullets alone each had 18/18. This isolated the
interaction to the forecast ECL mutation of existing beams rather than the
terminal bullet set.

The source program at that root reaches two opcode-88 writes at ECL time 151,
rotating slots 0 and 1 by fixed signed constants. The beams are 500-pixel
diagonals forming a V with real free space between them. Mutable Hard preserved
their source time and angle, but then converted each rotated rectangle to an
axis-aligned AABB; those two large boxes falsely filled the V. This was a
geometry representation error, not evidence that collision was inevitable.

Fixed-angle, position-exact future laser segments now remain oriented
`LaserHazard` records through the world forecast and both Python/native safety
consumers. Angle-unconstrained aimed/re-aimed beams and position-uncertain
beams still use the conservative AABB union. The distinction is based only on
represented source certainty, not a stage, frame, beam count, or
counterexample identity. Replaying the exact f3445 snapshot through the
Windows native kernel changes Hard-4 from 0/18 to 18/18 while f3444 remains
18/18. Focused tests cover same-frame create/rotate/offset geometry and both
safety consumers; the complete suite passes 349 tests with 28 skipped. A new
physical run and adjacent-frame comparison are still required before claiming
runtime parity for the opcode-88 transition.

The post-checkpoint ordinary-RNG physical rerun supplies the integrated
effect. It ran to f5315 under explicit continue diagnostics. The only 12
recorded authority losses were the already separate early f1217--f1387
cluster. Across 563 sampled live-laser rows from f3373 through f4528 there was
no authority loss and no HIT; the process also crossed the prior f3445 false
empty region and the later repeated-HIT region without either event. This is a
strong trajectory-level improvement, but because earlier authority was lost
the run is not a clear.

A diagnostic-only `--capture-history` option now serializes the retained 256
snapshots only after releasing input and stopping the exact trial. A 62-second
ordinary-RNG capture stopped PID 56428 and retained physical frames
3277--3579, including both beam births and the whole opcode-88 rotation onset.
The existing source BulletManager report has 208 adjacent pairs, 60/60
unmutated laser steps at zero error, and classifies 104 rotated steps as
external ECL mutations. A new direct world-transition comparison covers all
52 adjacent mutation pairs (both slots, 104 oriented transitions): predicted
origin, angle, center offset, length, and half-width match the following
physical snapshot with maximum error zero and no mismatch. This closes
adjacent-frame parity for the fixed-angle opcode-88 path represented here;
aimed/uncertain AABB paths still retain only conservative source/unit evidence.

The capture flag requires `--stop-game`; focused and complete checks now pass
350 tests with 28 skipped. All physical input was released, both exact trial
PIDs were stopped, and no game or high-CPU trial process remained.

## Random timeline world envelope and Stage 1 f1217 (2026-08-04)

The next ordinary-RNG default fail-close Stage 1 run stopped alive at f1217,
with 61 bullets and all 18 current actions otherwise viable.  Tracing the
world forecast, rather than interpreting the terminal empty Hard set, found
the exact authority boundary: the timeline was at 1217 and its time-1220
opcode-6 record would create sub 0 at random x, fixed y -32.  At f1216 the
transition was still four frames away and Hard covered four; at f1217 it was
three frames away and the old world stopped after three with
`random stage timeline enemy position needs a world envelope`.  This was not
a soft route decision or a proved collision dead end.

The authoritative ranges are smaller than the nominal constants previously
used by this repository.  `GameManager::AddedCallback` initializes
`playerMovementAreaSize` to `(368,416)`.  `EnemyManager::RunEclTimeline`
opcodes 4--7 pass those two sizes directly to `Rng::GetRandomF32InRange`; they
do not add `playerMovementAreaTopLeftPos`.  `Rng.hpp` implements the draw as a
zero-to-one value times the supplied range.  Therefore the complete bounded
source worlds are x in `[0,368]` and y in `[0,416]`, independently for the
axes selected by the opcode.  The nominal model's former 384/448 draws were
also source-incorrect and are now 368/416.

Hard now instantiates a random timeline child at the midpoint of each random
axis and carries the half-range as forecast-only axis uncertainty.  ECL reads
of enemy position, aimed angle/distance, absolute movement, body geometry,
bullet origins and future laser origins preserve or conservatively consume
that interval.  A physical snapshot never gains this synthetic field.  It is
only an internal representation of every source-possible not-yet-born world;
no RNG point is guessed and safety eligibility is not relaxed.

The actual f1217 artifact now covers all requested 16 frames and retains all
18 Hard-4 actions.  At physical f1227 the diagnostic child in slot 1 has
source position `(295.130249,-18.0)`, ECL time 8 and half-size 9.333333.  The
f1217 Hard projection for that same physical frame is x
`[-9.333333,377.333334]`, y `[-27.333333,-8.666667]`, which contains the
complete observed body.  A focused source test additionally checks 32 exact
nominal RNG seeds against the common Hard body envelope.  The independent
physical f1217 corpus case, focused birth/attack/counterexample suites, and
the complete checkpoint pass: 351 tests, 28 skipped.  This is source,
retained-transition, and offline replay evidence; the integrated default
physical rerun remains required.

## General safety versus stage-conditioned route policy (2026-08-04)

The historical Stage 1--4 Practice results are material evidence and must not
be dismissed merely because current authority is stricter.  They also do not
yet prove that Hard physics or the online planning algorithm must be tuned per
stage.  The first Stage 1 clear checkpoint `408a68b` used a small observable
scene classifier for effort: lasers selected h16; clearance below 48 or at
least 220 bullets selected h16; clearance below 120 or at least 100 bullets
selected h12; otherwise h8.  By the Stage 4 result checkpoint `17fd93a`, that
had grown into many bullet-count, boundary, enemy-count and laser branches,
including thresholds at 100, 220, 350 and 400 and several comments tied to
individual physical frames.  It did not use a literal stage ID, but its
threshold combinations functioned as an implicit scene table and mixed
route/latency repair into planner mechanics.

The current evidence supports a narrower split than either “one universal
value function” or “put the old ifs back”:

```text
general, source-grounded online authority
    physics + phase + future-world envelope + delivery -> allowed actions

offline stage/shot policy data
    ECL phase + Power/items + enemy life/kill deadlines + route value-to-go
        -> rank only those currently allowed actions
```

Stage context may select immutable ECL-derived soft data, a reference route
tube, phase-conditioned terminal value, expected kill deadlines, and
Power/item value-to-go.  It must not select collision laws, Hard horizon,
planner rungs, publication rules, or exceptions.  Fixed scalar weights alone
are unlikely to be enough: Power before a boss, a kill before the next volley,
and an item with or without a safe return bridge have nonlinear and
phase-dependent value.  A compact phase-conditioned value/route policy is the
more faithful form of agent “backboard”.

The falsifiable comparison after the f1217 authority rerun is:

1. replay historical clear decisions through the current source-grounded Hard
   model where retained roots exist;
2. separate old actions which remain Hard-legal from progress that depended on
   an unmodelled transition or weaker fail-close contract;
3. treat the former as route-policy demonstrations and compare a compact
   offline phase/value prior against the current soft ranker on the same roots;
4. require unchanged Hard eligibility, another RNG workload, and a default
   physical run before promotion.

If the old decisions remain legal and consistently preserve firepower,
position and kill tempo, that is positive evidence for stage-conditioned
soft policy.  If their apparent progress crosses states that current Hard
cannot yet model, the next work remains source coverage.  In either case the
result does not justify a counterexample branch in the main solver.
