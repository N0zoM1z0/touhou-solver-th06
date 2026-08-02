# TH06 Solver Strategy

This is a compact research strategy, not an architecture specification or a
history ledger. `AGENTS.md` owns the working rules; `START_HERE.md` owns the
volatile checkpoint.

## Objective

Reach a physically validated TH06 1.02h Hard NMNB clear. The work is physical
iteration, source-grounded model exploration, and measured solver
optimization. Code, tests, documents, and native backends matter only when
they enable the next causal experiment or remove a measured bottleneck.

The central approach is:

```text
authoritative source + coherent native state
    -> one fail-closed action authority
    -> budgeted anytime reach-avoid proposals
    -> one version-consistent issue transaction
    -> first physical counterexample
    -> one general falsifiable correction
```

TH08 contributes research methods, mathematical ideas, and negative evidence.
It does not contribute a software architecture to copy.

## Authority flow

1. **Hard safety authority** alone decides which actions may execute. It owns
   current and forecast hazard semantics, collision geometry, input pickup and
   publication uncertainty, and no-Bomb.
2. **Adaptive solving** spends measured compute progressively inside the Hard
   set. It changes effort, never eligibility. Adaptation should emerge from
   budget, frontier contraction, ambiguity, and completed dependencies—not
   stage/spell IDs or hand-written scene bands.
3. **Soft proposals and learning** may order or rank only Hard actions.
   Position, attack, collection, free-space targets, and learned values have
   no independent action authority.

These boundaries are stable. The current horizon ladder, target
representation, terminal metric, and planner are hypotheses and may change
when physical evidence falsifies them.

## Physical research loop

Use the default fail-close loop for causal work:

```text
run one focused physical workload
    -> stop at the first HIT or authority failure
    -> trace backward from the terminal dead end
    -> find the earliest still-viable consequential decision
    -> classify the responsible model/solver/delivery layer
    -> make the smallest general change
    -> retain one minimized regression
    -> rerun physically
```

Different-RNG outcomes are observations, not causal A/B results. A full-stage
continue-on-failure run is useful for mapping failure distribution and seeing
whether authority loss actually leads to HIT, but it never counts as a clear.

After a stage first passes under default fail-close, rerun the route from the
start as the regression gate. Use Practice to isolate the next unresolved
stage. Full-route runs are for material integrated changes, stage transitions,
and resource history—not every edit.

## General solver direction

The baseline remains a small synchronous anytime reach-avoid solver:

- compute Hard authority first;
- reuse one prepared source-grounded hazard projection;
- extend constant and turn-capable continuations progressively while the
  measured budget permits;
- deduplicate aliased reachable states;
- preserve fresh local survival evidence before applying soft terminal value;
- publish exactly one action through the current input/delivery contract.

Do not confuse an endpoint score with a bridge. Clearance, target distance,
boundary reserve, recovery distance, and raw path count are soft evidence; none
alone proves a collision-free continuation.

When the modeled winning set is genuinely empty, the first general fallback
candidate to test is lexicographic reach-avoid value:

1. maximize guaranteed collision-free physical frames;
2. maximize bottleneck signed clearance;
3. then apply control simplicity and other soft objectives.

This is a retained TH08 hypothesis, not yet a promoted TH06 implementation.
It should be compared against current terminal optionality on a causal CE
before integration.

## Global and local reasoning

Global reasoning is long-horizon/topological proposal, not a second
controller. It may identify a connected viable basin, terminal invariant,
free region, or future gate. Local reasoning executes precise action tubes
from the current continuous position under fresh hazards and delivery timing.

The intended dataflow is:

```text
one fresh snapshot and version
    -> one shared hazard timeline
    -> optional global/topological terminal proposal
    -> exact local continuation over Hard candidates
    -> fresh issue validation
    -> one published action
```

Global and local work must not use incompatible snapshots, clocks, clamp
semantics, or publication ages. A soft global target may expire, but its
deadline must not shorten ordinary survival lookahead. It may guide among
strong fresh continuations; it may not overrule them merely to reduce target
distance.

Only a future exact, versioned long-horizon proof could gain hard authority.
Until then, global guidance remains soft and failure to compute it must not
disable the local Hard loop.

## Retained TH08 hypotheses

Explore these only when a physical CE reaches their boundary:

- **Source-complete future modeling.** Execute ECL events, bullet/laser/body
  births, action-conditioned aim, and captured RNG causally. Never attach a
  recorded future after action divergence. Unsupported semantics fail closed.
- **Query-local adaptive refinement.** If a coarse representation is proved
  ambiguous, refine only the root-relevant reachable tube and completed
  dependency closure. Never refine the complete field merely because one
  coarse query is empty. Timeout cannot publish unfinished lower authority.
- **Action factorization.** Expand direction into hold duration and
  focus/unfocus/refocus only after a CE shows the focused fixed-duration space
  omits a real continuation.
- **Kill-before-saturation.** Among survival-feasible actions, an executable
  shot/enemy model may prefer a causal earlier kill that prevents later hostile
  births. Boss alignment or distance is not damage evidence.
- **Early Power and phase progress.** Collection and attack may improve later
  survival, but only through a completely viable bridge. They remain soft.
- **Contextual learning or search proposals.** Beam search, MCTS, learned
  values, or mixture proposals may order exact work and terminal values. They
  cannot prune Hard branches, manufacture authority, or substitute for source
  semantics.
- **Representative roots.** Reuse minimized physical snapshots to branch
  actions causally and validate a winner on another root/workload. Do not build
  a persistent native wind-tunnel service until a measured iteration blocker
  requires it.
- **Delivery-aware cancellation or computation guards.** Computation is a
  physical held-input interval. Add stronger cancellation, leases, background
  publication, or held-action guards only after measured solve tails show the
  current synchronous budget contract is insufficient.

Route/phase context may eventually select soft damage, Power, or
reference-region objectives after the general survival baseline is stable.
It must never select Hard laws, horizon rungs, planner mechanics, or safety
exceptions. Source-defined event state is physical input; a spell-name branch
is not.

## TH08 designs not to import

- uniform coarse global corridors or nearest-cell authority;
- full-field fine refinement;
- independent global and local controllers;
- stale asynchronous policy publication;
- scalar boundary reserve or endpoint recovery distance as viability;
- rolling waypoints or proxy objectives as physical truth;
- route IDs as planner or horizon gates;
- dormant prewarm services, publication lanes, and lease hierarchies;
- large schema/report/framework projects ahead of a physical need;
- different-RNG hit totals as promotion evidence.

TH08 showed that a more precise frozen policy can be physically worse when it
arrives late. End-to-end survival and delivery dominate empty-set counts,
offline optimality, test volume, and benchmark speed in isolation.

## Hypothesis ladder

This is a trigger order, not a roadmap to implement eagerly:

1. correct source semantics, future hazards, sensing, input, and publication;
2. improve general multi-segment reachability and survival value;
3. if a CE proves local short-sight, test a small shared-projection global
   basin or topology terminal value;
4. if a CE proves resolution ambiguity, test query-local refinement;
5. if the action alphabet is the blocker, add duration/focus factors;
6. after survival is stable across stages, test combat, Power, and phase
   progress inside the viable set;
7. add learned/contextual proposals only after the general solver and corpus
   are trustworthy.

At every rung, first name the causal CE and smallest falsifier. Reject the
idea if it wins only through hidden future knowledge, stale state, missed
deadline, weakened safety, a proxy metric, or one accidental RNG path.

## Optimization

Measure before optimizing. Prefer source-exact reuse and small native hot
kernels over architectural layers:

- prepare hazard timelines once;
- flatten hot geometry and keep scalar state inside loops;
- deduplicate reachable states;
- prune only with proved feasibility, dominance, or spatial bounds;
- stop work whose result cannot arrive in time;
- preserve Python/reference parity for native implementations.

An optimization is promoted only when semantics match, focused tests pass,
Windows timing improves, and physical evidence shows it helps the real
iteration boundary. Keep confirmed measurements in
`OPTIMIZATION_STRATEGY.md`.

