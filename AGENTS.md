# TH06 Working Rules

Read `START_HERE.md` first. Use `README.md` and the ignored
`reference/GensokyoClub-th06/` only as needed for the current question.
Do not use REA or any REA-provided tooling for this project.
Do not use REA or any REA-provided tool. Base reverse-engineering claims only
on the authoritative source clone, existing IDA material, and controlled
runtime/physical evidence.

The goal is a physically validated TH06 Hard clear. Keep the implementation
small, correct, and source-grounded. **Physical iteration, model exploration,
and measured solver optimization are the work; software engineering is not the
goal.** Prefer the next falsifiable experiment, physical run, causal analysis,
or measured hot-path improvement over refactoring, framework construction,
documentation polish, or architectural generalization. Do not build broad
abstractions or a TH08-style architecture in anticipation of future needs.
Engineering work is justified only when it directly enables the next physical
iteration, makes an understood behavior testable, or removes a measured
bottleneck without changing semantics.

Keep these authority boundaries:

1. Hard safety decides which actions are allowed.
2. Adaptation changes compute effort, never safety eligibility.
3. Learning proposes/ranks only among allowed actions.

These are boundaries, not a fixed implementation roadmap. Change the model
when physical evidence disproves it. Survival is hard; attack, collection, and
position are soft. Bomb bit `0x02` must never be emitted. Unknown hazards fail
closed.

The adaptive layer must be general and budget-driven. Do not select a horizon,
planner, or ranking rule from stage/spell IDs, bullet-count bands, boundary
thresholds, or a counterexample-specific condition. Extend the Hard-certified
frontier progressively while measured compute budget remains. Generic bounded
continuation is an ordinary budgeted rung, not a scene-triggered fallback; a
constant-action count can hide aliased reachable states. A counterexample may
fix source semantics, authority, cost estimation, or a general algorithm, but
must not receive its own branch in the main solver.

## Do not

- Do not explain a failure from the final HIT or empty Hard set alone. Trace
  backward to the earliest still-viable state where the solver first made a
  consequentially wrong decision. The terminal dead end is usually an effect,
  not the cause.
- Do not add main-solver conditions keyed by stage, spell, frame, coordinates,
  RNG seed, bullet count, boundary distance, or counterexample identity. A
  physical CE may expose incorrect source semantics, missing hazard modeling,
  authority or publication latency, cost estimation, or a general algorithmic
  flaw; fix that cause instead.
- Do not mix pattern-specific source semantics with route strategy. When a
  hazard family genuinely has different source-defined physics, isolate that
  model in its hazard module. Do not encode where to move for a named scene.
- Do not allow attack, collection, position, free-space targets, target
  distance, learning, or any other soft/global proposal to change Hard
  eligibility, shorten ordinary survival lookahead, or override materially
  stronger fresh continuation evidence. Global and local reasoning must use a
  consistent fresh snapshot, hazard projection, and publication timeline; do
  not build independent controllers that can disagree through stale state.
- Do not treat raw path multiplicity as independent robustness. Boundary
  clamping and different action sequences can alias to the same reachable
  state; deduplicate reachable states or use another physically meaningful
  continuation measure.
- Do not turn a soft target deadline into the survival horizon. A commitment
  may expire a proposal, but it must not collapse the general budgeted
  lookahead as the deadline approaches.
- Do not relax safety eligibility merely to avoid a fail-close stop. The
  default physical loop stops on the first HIT or authority failure. Any
  continue-on-failure run is explicit diagnostics only: release input, publish
  no uncertified action, record the event, and resume only after fresh Hard
  authority returns. Bomb remains forbidden in every mode.
- Do not equate fail-close with proof that a HIT is inevitable. It means the
  current model lacks sufficient authority; the cause may be a true physical
  dead end, unknown source behavior, latency, or an overly conservative
  envelope. Diagnose it from source and physical evidence.
- Do not call a continue-on-failure result path a clear. Only a default
  fail-close run with no HIT, no authority loss, and no Bomb physically
  validates a stage or route.
- Do not freeze the current horizon ladder, target representation, ranking
  metric, or solver architecture into permanent doctrine. The authority
  boundaries are stable; algorithms remain hypotheses and must change when
  physical evidence disproves them.
- Do not choose between speculative complexity and artificial simplicity.
  Avoid frameworks built for imagined future needs, but use deeper planning,
  ECL/RNG forecasting, better algorithms, or native C/C++ hot paths when a
  measured physical CE or bottleneck justifies them. Add only the smallest
  falsifiable piece needed for the next iteration.
- Do not optimize by changing semantics. Native rewrites, flattened storage,
  projection reuse, and pruning require measurement plus reference/native
  parity. Do not use stale hazard projections, unproved pruning, or omitted
  work as hidden speedups.
- Do not turn tests into an application framework. Keep runtime CEs compact
  and independent, keep focused algorithm tests in their owning modules, and
  avoid unrelated refactors or bulk fixture migration during a solver-behavior
  iteration.
- Do not leave physical control or compute behind after a run. Release every
  input, stop the exact trial PID, and check for leftover high-CPU processes.
  Never use a PTY for the Windows launch path.

For each iteration:

- use source/IDA/runtime evidence to explain the first physical failure;
- make the smallest falsifiable change;
- add only the focused regression needed for an understood bug;
- rerun physically when the integrated behavior changes.

Store understood physical solver counterexamples as independent JSON files in
`tests/corpus/counterexamples/`. The generic corpus test should load and replay
them; do not keep appending long runtime snapshot fixtures to
`tests/test_th06_baseline.py`. Keep algorithm unit tests in focused Python test
modules, and put only stable, minimal regression contracts in corpus data.
Gradually migrate older understood physical fixtures to this corpus during a
dedicated test-only cleanup, not while changing integrated solver behavior.

Offline checks cannot replace physical play. Do not hardcode a stage or spell
before a general cause has been tested. Keep menu and dialogue control separate
from movement. Do not commit the game, source clone, traces, logs, or caches;
release input and stop all trial processes after a run.

When launching the Windows game from WSL, use non-PTY execution. A PTY can
stall `cmd.exe` before the game and agent attach correctly.
