# TH06 Future-World And Offline/Online Audit

Snapshot: 2026-08-04, repository HEAD `05b5648`, solver code checkpoint
`52ed4ac`, authoritative source `cc475a0bc3fef38683b0f02224c87ddba0a021d9`.

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

## Coverage gaps found in this audit

### 1. Stage timeline is sensed but not part of hazard forecasting

### Coverage inference

`native.py` captures `timeline_time`, a bounded prefix of remaining timeline
instructions, completion state, and subroutine traits.  The only production
consumer of these fields is currently soft suppression/attack.  Bullet,
laser, body, Hard, viability, and guidance forecast call sites do not consume
the stage timeline.

Consequently, the current world forecast advances already-present emitters
but does not generally insert:

```text
future timeline instruction
    -> SpawnEnemy
    -> newborn time-zero ECL
    -> possible same-manager-pass update
    -> newborn bullet/laser/body hazard
```

If such an event can fall inside the next Hard-4 updates, this is a potential
Hard soundness gap rather than only a soft-ranking limitation.  Boss/dialogue
gates, random timeline positions, exact source update alignment, and snapshot
phase must be resolved before promoting that inference to a bug claim.

### 2. Same frame number does not by itself prove one calc-chain phase

### Source-proved gap; implementation pending physical parity

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

The implementation now copies the BulletManager timer with the native hazard
pools, rejects a mismatched active phase, and reads separately stored player
and global state only after that pool witness.  Adjacent physical parity is
still required before this implementation is promoted from source proof to
physical evidence.

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
- Future stage-timeline enemies are not inserted at all.

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
- The independent planner oracle and stateful runner are valuable algorithm
  falsifiers.  They are not replacements for full source-world execution or
  physical play.
- Online sensing caches immutable ECL instruction/program graphs per stage,
  and ECL forecasting caches compiled instruction maps and decoded bytes.
  This removes repeated work but is runtime caching, not full offline asset
  compilation.

## Smallest useful direction

The evidence order for future work is:

1. Establish the source phase and complete Hard-4 world coverage, beginning
   with the next stage-timeline event rather than a longer planner horizon.
2. Insert one source-defined future world family at a time: timeline enemy,
   persistent ECL child, then future laser, retaining exact slot/update order.
3. Make nominal future births candidate-path conditioned and preserve shared
   RNG/world state per causal branch.
4. Extend adjacent-frame parity only for each newly supported transition.
5. Profile the integrated online path, then compile immutable ECL/timeline
   blocks offline or move a measured stable kernel to native code without
   changing semantics.

Every promotion still requires one source or physical falsifier, focused
parity, and a default fail-close physical rerun.  Stage data may select the
source program being executed; it must not select safety laws, horizons,
ranking mechanics, or route actions.
