# TH06 Route/Phase Strategy

## Decision

We are no longer trying to make one online planner discover the complete Hard
route under a 60 Hz publication deadline. Years of TH08/TH06 work produced a
valuable source-exact world model and safety kernel, but repeated integrated
regressions showed that deeper universal search trades accuracy against
publication time without expressing the strategic knowledge a fixed ECL
stage actually permits.

The replacement is deliberately asymmetric:

- one small shared runtime owns sensing, source physics, Hard eligibility,
  delivery, fail-close, and no-Bomb;
- one route pack per difficulty/character/shot/stage owns strategy;
- each source-defined phase inside that pack may use a different small
  algorithm and parameters;
- expensive causal work moves offline and becomes compact policy data or a
  measured native helper;
- online work conditions that policy on the actual state, Hard-filters it,
  and publishes one action.

This matches the game. ECL and stage timelines are fixed, while RNG, damage,
kill timing, resource history, and player position create branches within
that fixed program.

## Common authority substrate

The common layer retains only responsibilities that must be identical across
routes:

```text
coherent snapshot
    -> source-defined current/future hazards
    -> delivery-aware Hard action set
    -> route proposal intersected with Hard
    -> stable tie-breaking and publication
```

It must not know named stages or spells when computing collision safety. A
route pack cannot add an action to Hard, suppress an unknown hazard, change a
hitbox, shorten required delivery coverage, or emit Bomb.

If a route pack is missing or cannot identify the phase, the runtime does not
invent route strategy. It may retain the observed input only while freshly
Hard-certified; otherwise it stops. This makes incomplete route coverage
visible.

## Route and phase identity

The route key is `(difficulty, character, shot_type, stage)`. The phase key is
derived from source state, not a screenshot or absolute address:

- timeline section/event identity before a boss;
- boss ECL subroutine index and source-relative instruction/call state;
- life/timer/death callback transition;
- source spell-active state where relevant.

Timeline time can select source-authored sections because it is the ECL
timeline clock; opaque game-frame counterexamples cannot. Phase catalogs must
be generated or audited against the installed `ecldataN.ecl` and authoritative
`EnemyManager::RunEclTimeline`/`EclManager::RunEcl` semantics.

## Phase policy contract

A phase policy receives the fresh snapshot and the already certified Hard
actions. It returns a short, inspectable proposal:

```text
phase ID
preferred first actions (possibly ordered)
commitment bound
reason/provenance
optional diagnostics
```

For fixed timeline structure, prefer a small data-driven source-clock state
machine over a global scene-classifier tree. The route selects one phase
first; only that phase's state is evaluated. State names should express source
or tactical meaning (`child-circle`, `horizontal-band`, `laser-sweep`) and own
their primitive/horizon/target. A callback-, RNG-, or resource-conditioned
boss phase may use a private richer machine behind the same intent contract.
It must not add another common-solver branch.

A soft commitment is owned by its `(route, phase, policy-state)` tuple and is
discarded when that tuple changes. Carrying the preceding state's proposal
into a new state violates phase isolation and makes an offline fresh-state
comparison differ from online execution. The newly selected state may commit
again only from its own fresh proposal inside current Hard authority.

The policy may use phase-specific corridors, safespots, streaming rules,
damage alignment, item/Power value, future event timing, RNG-conditioned
branches, beam search, dynamic programming, or a tiny native evaluator. It
may choose a different horizon or algorithm from the next phase. All of this
is soft until the common Hard layer certifies the emitted action.

A useful route policy is not a fixed replay. It maps source phase plus current
continuous state, RNG/resource state, enemy state, and delivery state to a
proposal. Offline search should deliberately vary those inputs.

## Offline work

Offline is where we exploit everything knowable ahead of time:

1. decode timeline/ECL and build stable source phase manifests;
2. complete candidate-conditioned future-world semantics required by that
   phase, including aim, damage, kill/retirement, callbacks, items, and RNG;
3. seed stateful simulations from physical snapshots and source-valid stage
   entries;
4. search entry regions, command tubes, policy branches, objective weights,
   and robustness across RNG/resource/player-state distributions;
5. minimize causal disagreements and compile only the winning small policy;
6. parity-check every new source transition against adjacent physical frames
   when it can affect runtime authority.

The existing barrage_lab is useful infrastructure, but its workload must be
stateful and phase-shaped. Isolated synthetic bullet sets are insufficient for
route decisions involving future spawns, aimed attacks, kills, callbacks, and
Power.

## Online work

Online should remain bounded and predictable:

1. capture and validate one snapshot;
2. compute the common Hard set;
3. select the exact route pack and source phase;
4. evaluate that phase's compact policy under the current state and deadline;
5. intersect with Hard and choose one action;
6. validate publication age/input pickup and issue.

Do not spend the frame rediscovering the stage plan with a large generic
search. Small local search is welcome when the owning phase deliberately uses
it and its measured deadline fits.

## Stage 4 pilot

Stage 4 is the first route pack because it contains dense horizontal waves,
future timeline enemies, boss transitions, and lasers, and because earlier
checkpoints have both a historical clear and recent regressions. The first
milestone is not to encode every phase at once. It is:

1. compile an auditable Stage 4 timeline phase manifest;
2. land the route-pack dispatch and fail-visible uncovered-phase behavior;
3. author the first pre-boss horizontal-wave policy from source and stateful
   fuzzing;
4. physically test to the next uncovered or failing source phase;
5. repeat until Practice Stage 4 clears under the new architecture;
6. then begin the full route from Stage 1, preserving resource-conditioned
   entry state.

## Success and rejection criteria

A phase change is promoted only when its source provenance is recorded, its
offline comparison is causal, focused tests pass, and physical play improves
or falsifies the predicted boundary. Reject changes that work only through a
single RNG seed, hidden future knowledge, stale snapshot, weakened Hard rule,
or an unexplained captured-frame branch.
