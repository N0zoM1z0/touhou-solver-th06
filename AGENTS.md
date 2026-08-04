# TH06 Working Rules

Read `START_HERE.md` first. Use the ignored authoritative clone at
`reference/GensokyoClub-th06/` for source claims. Do not use REA, any
REA-provided tool, or LeanToken.

The goal is one physically validated TH06 1.02h Hard Reimu-A clear with no
HIT, no authority loss, and no Bomb. Physical play is the final evidence;
offline search and tests accelerate iteration but never constitute a clear.

## Current design decision

The old single universal online planner is retired. Its preserved checkpoint
is the annotated tag `pre-phase-route-pivot-20260804`.

The active design is a small common authority substrate plus source-grounded
route packs selected by difficulty, character, shot type, stage, and
source-defined phase. A route pack may choose its planning algorithm,
lookahead, route target, combat/Power priorities, and offline policy data for
that phase. This is deliberate route knowledge, not an exception hidden in
the safety kernel.

Keep the boundary exact:

1. The common Hard layer alone decides whether an action may be emitted.
2. Route packs propose or rank actions only; they cannot change collision
   physics, uncertainty, delivery coverage, fail-close behavior, or no-Bomb.
3. Every proposal is checked against the same fresh snapshot and Hard set
   immediately before publication.
4. Unknown or incoherent hazards fail closed. Bomb bit `0x02` is forbidden in
   every mode.

Stage/phase specialization is now expected in `scripts/th06/routes/`, not in
the common solver or hazard modules. Source-defined physics that genuinely
differs by hazard family belongs in that hazard module, not in route strategy.

## Offline and online responsibilities

Use offline computation aggressively for work knowable before play:

- decode and audit stage timeline and ECL;
- name source phases and transitions;
- simulate candidate-conditioned aim, damage, kill/retirement, callbacks,
  items, Power, and RNG consumption where source coverage supports them;
- search phase entry states, robust command tubes, policy branches, and
  parameters over many RNG/resource states;
- compile small, inspectable route data and retain source provenance.

The online loop should only:

- capture one coherent physical snapshot;
- identify the route and current source phase;
- condition the phase policy on actual RNG, resources, player/enemy state,
  and recent delivery;
- request a short proposal;
- Hard-certify and publish one action.

Do not encode a blind `frame -> direction` replay. Policies must branch on the
physical state needed by the authoritative source behavior. Raw addresses are
not stable phase IDs; use stable subroutine indices, timeline events, callback
state, and source-relative instruction identity.

## How to iterate

Work one route and one source phase at a time. The active route is Hard /
Reimu-A / Stage 1. Stage 4 remains preserved at its f2200 counterexample and
must not be changed opportunistically during a Stage 1 phase iteration.

For each iteration:

1. audit the relevant authoritative timeline/ECL and record the phase
   contract;
2. reproduce or generate a stateful offline workload for that phase;
3. make the smallest route-policy or shared-source-model change with a clear
   prediction;
4. keep only focused tests for that understood behavior;
5. rerun the integrated physical phase or stage;
6. trace any failure back to the earliest still-viable wrong proposal, not
   merely the terminal HIT or empty Hard set.

A physical counterexample may change shared source semantics only if the same
semantic error is demonstrated. Otherwise it changes the owning route phase.
Do not add counterexample identity, RNG seed, or one captured frame as an
opaque branch. A source-derived phase boundary, spatial lane, timing window,
or RNG-conditioned policy is allowed when its provenance and offline evidence
are explicit.

Store small understood shared-model counterexamples independently under
`tests/corpus/counterexamples/`. Store route-phase tests with their route
module. Do not grow `tests/test_th06_baseline.py` with runtime snapshots.

## Physical-run safety

- Default physical play stops on the first HIT or authority failure.
- `--continue-on-failure`, fixed RNG, and time-limited runs are diagnostics.
- Menu/dialogue control stays separate from movement.
- Never launch the Windows path through a PTY.
- Release all input, stop the exact trial PID, and check for leftover game,
  agent, or high-CPU processes after every run.
- Do not commit the game, source clone, DAT archives, traces, logs, caches, or
  build products.

## Engineering restraint

The product is a clear, not a framework. Do not recreate a TH08-style
architecture, generic plugin platform, event bus, policy service, or broad
schema. Add only the smallest route contract and offline tool needed for the
next Stage 4 experiment. Optimize measured hot paths without changing
semantics and retain Python/reference versus native parity.
