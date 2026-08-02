# TH06 Next-Agent Plan

This plan turns the current checkpoint into the next physical iteration. It is
not a commitment to build a complete game simulator or a new solver
architecture. Each phase has an evidence gate; later phases run only when the
first causal counterexample justifies them.

The immediate objective is:

> Explain and correct the earliest consequential decision leading to the
> default fail-close Stage 1 stop at f11505, using authoritative source and
> controlled runtime evidence, without a scene-specific rule.

The physical goal remains a default fail-close TH06 Hard NMNB clear. Hard
safety owns eligibility, adaptation owns compute effort, and soft or learned
reasoning may only rank Hard-certified actions.

## Phase 0: Preserve and Reproduce the Baseline

Before changing code:

1. Read `AGENTS.md`, `START_HERE.md`, and `STRATEGY.md`.
2. Inspect `artifacts/th06_failure_latest.json` and preserve it as the f11505
   analysis root. Do not overwrite it with an exploratory run.
3. Identify the exact decision-history interval retained before f11505, the
   last issued actions, snapshot/issue ages, input pickup, Hard candidates,
   completed anytime rungs, and failure reason.
4. Run the existing offline suite once. Rebuild the native kernel only if its
   inputs or implementation will be investigated.
5. Check for and stop leftover trial or high-CPU processes before and after any
   physical run. Use non-PTY Windows launch only.

Exit gate:

- the saved failure is readable and its timing/action history is understood;
- the existing suite passes, or every pre-existing failure is recorded before
  solver work begins;
- no game input or trial process remains active.

## Phase 1: Find the Earliest Causal Error

Do not begin from the final empty Hard set. Trace backward through the saved
history and find the earliest state that was still physically viable but where
the integrated solver made a consequentially worse choice.

### 1.1 Branch the retained root states offline

For candidate roots before f11505:

- replay every Hard-4 root action through the existing delivery/prefix model;
- extend each surviving branch progressively with the existing h6/h8/h12/h16
  constant and multi-segment continuations;
- deduplicate terminal physical states;
- record guaranteed survival frames, bottleneck signed clearance, reachable
  terminal-state count, completed rungs, cost, and forecast coverage;
- separate current-hazard-only, current world-forecast, and nominal proposal
  results when this helps isolate the cause. None of these offline variants may
  be mistaken for Hard authority.

The question is not whether a deeper offline action looks prettier. The test is
whether an alternative action has a source-consistent collision-free bridge
that remains available under physical delivery timing.

### 1.2 Attribute the divergence

Classify the first divergence as one of:

1. incorrect source semantics or collision/update order;
2. incomplete future bullet, laser, enemy-body, or ECL forecast;
3. missing action-conditioned aim or RNG causality;
4. overly conservative uncertainty/fail-close envelope;
5. local short-sight, aliased frontier, or inadequate survival value;
6. stale snapshot, publication latency, or input-delivery mismatch;
7. no demonstrated earlier continuation—a true dead end under the current
   evidence, or insufficient retained history to decide.

For every nearby hazard that affects the classification, identify its source
update function, native fields, active ECL opcode/control path, and collision
timing. Use only the authoritative source clone, existing IDA material, and
controlled runtime evidence. Do not use REA.

Exit gate:

- one earliest consequential root is identified, or the artifact is proved too
  short and the exact additional observation needed is specified;
- the cause is assigned to a model, solver, delivery, or evidence gap;
- the next change has one falsifiable prediction.

Do not write a regression fixture until the cause and stable contract are
understood.

## Phase 2: Close a Proven World-Model Gap

Run this phase only if Phase 1 demonstrates a model or forecast problem.

### 2.1 Perform a narrow source-coverage audit

Audit the hazard semantics actually reachable around the causal root:

- current bullet state, movement, and active EX flags;
- current laser lifecycle, geometry, motion, and collision window;
- current enemy-body motion, easing, collidable state, and callbacks;
- future ECL control flow and hazard-producing instructions;
- RNG consumption and player-dependent aim;
- update order from instruction execution through collision.

Mark each relevant behavior as exact, conservatively bounded, hazard-neutral,
or unsupported/fail-closed. The existing classification of all 136 ECL opcodes
is the starting point; do not build a second opcode framework or implement
unreachable semantics merely for completeness.

### 2.2 Converge on one minimal forecast contract

Where the causal fix requires it, make the existing modules agree on a small
contract equivalent to:

```text
forecast(snapshot, candidate_player_path, horizon, authority_mode)
    -> per-frame bullet hazards
    -> per-frame laser hazards
    -> per-frame enemy-body hazards
    -> coverage, uncertainty, and failure reason
```

Required properties:

- Hard, viability, and guidance share one snapshot version and time origin;
- aimed future hazards use the candidate player path when source semantics do;
- static ECL instructions/control flow are decoded once where useful, while
  timer, mutable state, player variables, and RNG remain causal runtime input;
- exact, bounded, and unsupported intervals are explicit;
- nominal and Hard forecasts may treat uncertainty differently but may not use
  contradictory physics;
- incomplete Hard coverage fails closed with an inspectable reason;
- pattern-specific source physics remains in the owning hazard module, not in
  the main solver.

This is a behavioral boundary, not a request for a generic IR, service, event
bus, or class hierarchy. Extend only the hazard families and source paths
needed by the causal root.

### 2.3 Verify source/native agreement

Add the smallest focused reference check for the corrected semantic unit. If a
native hot path implements it, compare Python/reference and native results on
the same inputs, including update-boundary cases.

Exit gate:

- the Phase 1 root changes exactly as predicted;
- unsupported future intervals remain fail-closed rather than silently absent;
- no stage, spell, frame, coordinate, bullet-count, or CE identity branch was
  introduced;
- focused tests and the generic corpus pass.

Then proceed directly to Phase 5. Do not add solver complexity unless the
corrected model still demonstrates a solver failure.

## Phase 3: Test a General Survival-Value Improvement

Run this phase only if Phase 1 shows that the model and delivery contract are
adequate but the budgeted solver selects a short-sighted continuation.

### 3.1 Build the falsifier offline first

Compare the current terminal optionality ranking with a general lexicographic
reach-avoid value over Hard-certified roots:

1. maximize guaranteed collision-free physical frames;
2. maximize bottleneck signed clearance;
3. maximize deduplicated reachable terminal states or another demonstrated
   continuation measure;
4. only then apply control simplicity, position, attack, or other soft value.

Use the existing budgeted constant and multi-segment frontier. Do not select
horizons or algorithms from scene features. Constant-action count is not a
robustness measure when different actions reach the same clamped state.

### 3.2 Integrate only if the offline comparison is causal

Promotion requires that the proposed value:

- selects a demonstrated viable bridge at the Phase 1 root;
- preserves or improves existing minimized counterexamples;
- fits the measured physical decision budget;
- leaves Hard-4 eligibility unchanged;
- does not use future information unavailable at issue time.

If it fails these conditions, reject or revise the hypothesis rather than
adding a gate around the failure.

Exit gate:

- one general solver change explains the CE;
- current corpus and focused algorithm tests pass;
- measured cost remains compatible with the delivery deadline.

Then proceed to Phase 5.

## Phase 4: Add Global/Topological Guidance Only If Proven Necessary

This phase is conditional and is not part of the initial implementation. Enter
it only after a physical CE shows that correct multi-segment local reachability
and survival value repeatedly enter a locally attractive but globally dead
basin.

Test the smallest shared-projection proposal that can falsify this hypothesis:

- one fresh snapshot and version;
- one shared hazard timeline;
- optional long-horizon basin, gate, or terminal-region proposal;
- precise local continuation over current Hard candidates;
- one fresh issue validation and one published action.

The global component remains soft. It may rank terminal reachable states but
cannot change Hard eligibility, shorten local survival lookahead, publish
independently, or reuse stale state. Do not import a TH08 global controller,
coarse corridor framework, full-field grid, or asynchronous policy lane.

Exit gate:

- the CE demonstrates a collision-free bridge that local ranking missed;
- global and local results use the same snapshot, projection, clamp semantics,
  and delivery timeline;
- the added compute has measured physical benefit within budget.

## Phase 5: Retain One Regression and Validate Physically

After an understood model or solver correction:

1. Minimize the stable physical contract into one independent JSON file under
   `tests/corpus/counterexamples/` when it is a solver CE.
2. Put focused algorithm semantics in the owning Python test module; do not
   expand `tests/test_th06_baseline.py` with another large snapshot fixture.
3. Run focused tests, the generic corpus, the complete Linux suite, and the
   Windows checks relevant to changed native/runtime behavior.
4. Run default fail-close Hard Practice Stage 1 with non-PTY launch.
5. Stop immediately at the first HIT or authority failure and preserve that
   artifact as the new causal root.
6. Release input, stop the exact trial PID, and verify no high-CPU process was
   left behind.

Success means crossing the old causal root for the predicted reason. It does
not mean Stage 1 is cleared unless the default fail-close run reaches its
source-defined result path with no HIT, authority loss, or Bomb.

If Stage 1 clears, run the Hard route from the beginning as the regression
gate. Then use Practice to isolate the next unresolved stage and repeat this
same causal loop. Do not advance because a continue-on-failure diagnostic
reached the result screen.

## Phase 6: Optimize Only a Measured Bottleneck

Optimization may occur earlier only when profiling shows that correct work
cannot finish before the physical issue deadline. Measure on the current causal
workload, then prefer:

1. reuse one prepared hazard timeline across horizons and candidates;
2. flatten hot per-frame geometry and keep scalar state inside inner loops;
3. deduplicate aliased reachable states;
4. apply only proved feasibility, dominance, or spatial pruning;
5. stop work whose result can no longer arrive before publication;
6. move only stable, measured hot kernels to C/C++;
7. preserve a small Python/reference implementation for parity.

Reject speedups that omit required hazards, use stale projections, change
collision semantics, or merely shift latency to publication. Record only
confirmed reusable findings in `OPTIMIZATION_STRATEGY.md`.

## Explicitly Deferred

Do not implement these without a new causal trigger:

- a complete replacement ECL VM or exact implementation of every opcode;
- exact models for all bullet EX modes never reached by the current workload;
- a second independent global controller;
- route/stage/spell strategy profiles;
- action-duration and focus expansion without an action-alphabet CE;
- attack, collection, Power, or kill-before-saturation authority;
- learning, beam search, MCTS, or contextual policy selection;
- a persistent simulation service, broad schema, or general framework;
- bulk migration of old test fixtures during solver behavior work.

These remain hypotheses in `STRATEGY.md`. Promote only the smallest one needed
to explain the next physical counterexample.

## First Working Sequence

The next agent should therefore execute this order:

```text
Phase 0 baseline preservation
    -> Phase 1 f11505 causal analysis
    -> Phase 2 only for a proven model gap
       OR Phase 3 only for a proven solver gap
       OR a small delivery correction for a proven delivery gap
    -> Phase 5 default fail-close physical validation
    -> repeat on the new first failure
```

Phase 4 and Phase 6 are evidence-triggered tools, not milestones that must be
completed before physical play.
