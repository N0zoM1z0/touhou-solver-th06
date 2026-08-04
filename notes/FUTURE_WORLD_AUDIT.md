# TH06 Future-World And Offline/Online Audit

Snapshot refreshed 2026-08-04 through repository checkpoint `16cf0c0` and the
following measured barrage-policy experiment.  Authoritative source remains
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
  time-zero ECL and both relevant EnemyManager slot-order cases.  Persistent
  nominal world insertion remains unsupported.
- Deterministic stage-timeline children are now inserted into the Hard world:
  their source record is decoded, newborn time-zero ECL runs inline, and the
  child is advanced through the remaining Hard interval. Random-coordinate
  timeline children fail closed at their first unresolved RNG dependency.
- Timeline boss-interrupt records are applied before the affected live boss
  update. The sensor now retains every installed live interrupt target graph,
  including targets whose `ENEMYINTERRUPTSET` instruction precedes the
  captured current ECL pointer.
- `MSGREAD`/`MSGWAIT` timing uses the captured live GUI message VM plus the
  immutable message bytecode. The forecast takes the safe minimum across the
  snapshot priority-11 / GUI priority-12 boundary rather than treating
  dialogue duration as a fixed stage constant.
- A future-created laser may be skipped only when source timers prove it
  cannot become collidable inside the requested window.  Otherwise creation
  fails closed; future laser geometry is not yet inserted.

### Physical evidence

- `stage5_f8447_final_frame_enemy_create.json` proves a final-Hard-frame child
  creation can be audited as immediately hazard-neutral.
- `stage5_f8456_persistent_enemy_create.json` proves the retained children can
  be audited through the remaining Hard window while nominal persistent
  insertion still stops.
- Adjacent physical history has been used to check player movement, existing
  bullet transitions, and newborn bullet geometry.  The current generic
  stateful parity rung deliberately excludes live enemies, spawners, lasers,
  and despawning bullets.
- In the fixed-RNG Stage 5 diagnostic, the captured timeline remained at 3373
  through f3613, advanced to 3374 at f3614 and 3375 at f3615, while the live
  boss interrupt executed across that adjacent boundary. Hard retained all 18
  actions and no authority stop occurred. The 75-second diagnostic reached
  f4320 with no HIT and no Bomb, but is not a default clear.

## Coverage gaps found in this audit

### 1. Stage timeline Hard insertion is bounded; nominal insertion remains
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

This closes the identified deterministic Hard-4 omission. It does not yet
install those children into the nominal continuation used for deeper soft
ranking. Random-coordinate timeline records still require a shared-RNG world
envelope and therefore stop Hard coverage at the unresolved transition.

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

### 5. Persistent world insertion and future lasers are incomplete

### Source/current-code fact

- `ENEMYCREATE` Hard auditing does not install a lasting child in the nominal
  emitter collection.
- Nested child mutation, exact free-slot selection, and shared RNG interaction
  remain unsupported.
- Future laser create/aim/store/rotate/test/cancel lacks a persistent laser
  world state and exact geometry.
- Deterministic future stage-timeline enemies are inserted only in the bounded
  Hard forecast, not in nominal continuation; random-coordinate records stop
  at the unresolved RNG transition.

### 6. Nominal RNG is exact only within the modelled consumer set

### Source/current-code fact

The current nominal world preserves captured RNG state across modelled active
emitters.  It does not yet compose every possible shared consumer, including
random stage-timeline placement, unsupported external instructions, exact
future world insertion, and every action-conditioned damage/callback path.
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

## Smallest useful direction

The evidence order for future work is now:

1. Retain the new deterministic timeline enemy/message/interrupt Hard
   coverage and obtain another adjacent physical spawn transition; add a
   source-bounded envelope for random timeline coordinates rather than a
   nominal point.
2. Insert the next source-defined persistent world families one at a time:
   ECL child, then future laser, retaining exact slot/update order.
3. Make nominal future births candidate-path conditioned and preserve shared
   RNG/world state per causal branch, including damage/kill/callback effects.
4. Extend adjacent-frame parity only for each newly supported transition.
5. Profile the integrated online path, then compile immutable ECL/timeline
   blocks offline or move a measured stable kernel to native code without
   changing semantics.

Every promotion still requires one source or physical falsifier, focused
parity, and a default fail-close physical rerun.  Stage data may select the
source program being executed; it must not select safety laws, horizons,
ranking mechanics, or route actions.
