# TH06 Current Handoff

Snapshot: 2026-08-04, code checkpoint `52ed4ac` (`Preserve input when local
ranking is incomplete`). This file is the volatile current-state handoff.
Read `AGENTS.md` first for binding rules, then this file, then `STRATEGY.md`
for the stable research direction. `README.md` is primarily the implementation
map and chronological evidence ledger.

## Mission and success criterion

The goal is a physically validated TH06 1.02h Hard clear. A clear means one
default fail-close physical run from the start with:

- no HIT;
- no Hard-authority loss;
- no Bomb (`0x02`) emitted; and
- the source-defined result/replay path reached and validated.

Practice clears isolate stages but do not prove a route clear. Fixed-RNG,
continue-on-failure, offline, and time-limited runs are diagnostic evidence
only. The runtime life patch cannot excuse a HIT; on a zero-HIT run it is
inert. Lunatic is out of scope until Hard is reliable.

## Non-negotiable authority boundaries

1. Hard safety alone decides which actions may execute. Unknown hazards fail
   closed.
2. Adaptation changes compute effort, never safety eligibility.
3. Attack, collection, position, global guidance, learning, and other soft
   values may rank only among currently Hard-allowed actions.

The adaptive layer must remain general and budget-driven. Do not add branches
keyed by stage, spell, frame, coordinates, RNG seed, bullet count, boundary
distance, or counterexample identity. Each progressive continuation rung is
complete-or-discard. Deduplicate reachable physical states: different action
sequences and boundary clamping can alias.

Bomb is forbidden in every mode. Menu/dialogue control remains separate from
movement. A fail-close stop is lack of authority, not proof that collision was
inevitable; trace backward to the earliest still-viable consequential choice.

## Exact local target and source assets

- Supported `th06.exe` SHA-256:
  `9f76483c46256804792399296619c1274363c31cd8f1775fafb55106fb852245`.
- Default game directory: `D:\Entertainment\Game\Touhou\th06`; override with
  `TH06_GAME_DIR` without editing launchers.
- Authoritative ignored source clone: `reference/GensokyoClub-th06/`, currently
  at `cc475a0bc3fef38683b0f02224c87ddba0a021d9`.
- Ignored copied game archives: `reference/th06_dat/th06_{CM,ED,IN,MD,ST,TL}.DAT`.
  `th06_ST.DAT` is the barrage/ECL archive used by offline tools.
- The optional runtime life patch changes process memory at VA `0x428DEC`
  (`01 -> 00`); it never modifies the EXE on disk and never turns a run into a
  clear.

Do not commit the game, source clone, DAT files, traces, logs, build output, or
caches. Reverse-engineering claims must come from this source clone, existing
IDA material, or controlled runtime/physical evidence. Do not use REA or
LeanToken MCP.

## Current solver design

The runtime is a small synchronous, source-grounded anytime reach-avoid loop:

```text
fresh versioned native snapshot
    -> source-shaped hazard projection
    -> Hard-4 action eligibility across measured input-pickup delays
    -> progressively completed exact continuation rungs
    -> ranking only for the deepest completed evidence
    -> fresh publication/delivery validation
    -> one physical input transaction
```

Current work is centered on exact local survival. It first proves Hard-4, then
uses measured residual decision budget to extend constant and turn-capable
reachable states through ordinary rungs. Shared projections may be reused, but
a deeper rung cannot pre-empt completion and ranking of its shallower rung.
Incomplete work never masquerades as evidence.

The key publication rule added at the current checkpoint is: when exact local
membership completed but robustness ranking did not, preserve the already held
action if it remains in that fresh viable set. If it is no longer viable, all
fresh survivors remain eligible. Soft attack/position guidance must not turn
membership-only evidence into an arbitrary direction switch.

The current horizon ladder, terminal metric, target representation, and Python
versus native split are hypotheses, not architecture doctrine. Change them
when a measured physical counterexample falsifies them; do not build a TH08-
style framework in anticipation of future needs.

## Latest causal chain and checkpoints

The recent Stage 5 work fixed general scheduling/publication defects rather
than adding scene-specific exceptions:

| Evidence | Earliest useful diagnosis | General correction | Commit |
| --- | --- | --- | --- |
| Earlier f2928 path | Exact membership consumed all residual time, leaving no terminal ranking authority | Reserve ranking budget after exact viability | `31e4371` |
| f3045-family failure | Deeper work could begin before a shallower continuation rung had been fully ranked | Enforce atomic exact-then-rank completion before promotion | `36f6abe` |
| Terminal f6229 top-boundary dead end | At f6210, h12 had a narrow viable set and uniquely ranked `up_right_fast`, but speculative deeper projection starved h12 publication | Prepare only the next rung; extend after it completes | `fac6ec7` |
| Terminal f3171 bottom failure | At f3140 after a stale retry, incomplete p8 robustness exposed a broad membership set to soft ranking, switching from viable held `up` to `down_left` | Preserve held input when fresh local ranking is incomplete | `52ed4ac` |

These commits are useful bisect/checkpoint anchors. The counterexamples justify
source semantics or general algorithm changes only; they must never receive a
main-solver branch of their own.

Relevant implementation/tests:

- `scripts/th06/solver.py`: continuation scheduling, budget admission,
  ranking, and incomplete-evidence publication.
- `tests/test_th06_policy.py`: focused scheduling/publication contracts.
- `tests/corpus/counterexamples/*.json`: independent, minimized physical
  solver regressions loaded by the generic corpus test.

Do not append large runtime fixtures to `tests/test_th06_baseline.py`. Add a
corpus JSON only after the failure is understood and reduced to a stable,
minimal contract. Keep algorithm tests in their owning focused module.

## What is actually validated

### Historical physical evidence

Practice Stages 1--4 reached their result paths without HIT, authority stop, or
Bomb on earlier solver checkpoints. Those runs established many source and
delivery semantics, but the solver has changed materially since then. They are
not current-version regression clears and do not prove a full route.

### Strongest current-version evidence

The latest run was an explicit fixed-RNG diagnostic:

```bat
run_th06_practice.bat --practice-stage 5 --seconds 150 --rng-seed 0x6382
```

It ended cleanly because the 150-second window expired while gameplay was
still active, at f8981. The trace contains 8,225 sampled rows: 8,168 `ok`, 57
`stale-decision-retry`, zero authority stops, and zero Bomb bits in native or
desired input. It crossed the previously problematic f3045/f3171/f6229
regions in this run. This means those failures did not reproduce on that
trajectory; it does not prove universal correction.

This is **not a Stage 5 clear**: the initial RNG seed was forced and the stage
result path was not reached. The source RNG generator and consumer order
remain unchanged; only the initial seed was fixed. Final gameplay must work
with ordinary runtime RNG.

Current ignored artifacts:

- `artifacts/th06_practice_stage5_rng6382_latest.csv`: the successful 150-second
  window above.
- `artifacts/th06_failure_rng6382_latest.json`: still contains the older f3171
  failure because a successful time window does not overwrite a failure JSON.
  Always inspect `snapshot.frame` before treating a `*_latest` artifact as the
  latest run.

The Linux and Windows suites last passed 294 tests at checkpoint `52ed4ac`.
Stage 5 has not yet reached its result path on the current solver; Stage 6 and
a full current-version Hard route are unvalidated.

## Offline source-grounded experiment loop

Offline tools accelerate hypothesis testing; physical play remains the truth.
Use physical snapshots as stateful seeds, source-valid ST.DAT/ECL behavior to
expand them, compare algorithms on identical cases, minimize the first causal
difference, then rerun the integrated solver physically.

Broad source-shaped barrage and planner differential fuzzing:

```bash
PYTHONPATH=scripts python3 scripts/stress_th06_barrages.py \
  reference/th06_dat/th06_ST.DAT --seeds 1000 --planner
PYTHONPATH=scripts python3 scripts/stress_th06_barrages.py \
  reference/th06_dat/th06_ST.DAT --seeds 1000 --planner --guidance
```

Stateful closed-loop replay from a physical failure, optionally with
source-valid synthetic ECL births and shrinking:

```bash
PYTHONPATH=scripts python3 scripts/replay_th06_stateful.py \
  artifacts/th06_failure_latest.json \
  --archive reference/th06_dat/th06_ST.DAT \
  --seeds 500 --frames 240 --birth-events 4
PYTHONPATH=scripts python3 scripts/replay_th06_stateful.py \
  artifacts/th06_failure_latest.json \
  --archive reference/th06_dat/th06_ST.DAT \
  --compare-metrics count,replanning-count --shrink
```

The supporting modules live under `scripts/th06/barrage_lab/`. Native options
are Windows-only and require the parity-checked `build/th06_safety.dll`.
Offline simulation currently does not reproduce the whole Windows game loop,
all ECL instructions, OS scheduling, or real publication latency. Treat a fuzz
win as algorithm evidence, not a clear or a substitute for physical rerun.

## Running and cleanup

Linux checks:

```bash
./build_th06_native.sh
./check_th06_baseline.sh
```

Default fail-close Practice isolation:

```bat
run_th06_practice.bat --practice-stage 5 --seconds 300
```

`--rng-seed` and `--continue-on-failure` are explicit diagnostics only. The
normal next validation should omit both. Full-route validation uses
`run_th06_baseline.bat`; replay saving must be checked on a non-Practice result
because the source sends Practice results directly to the main menu.

When launching from WSL, use non-PTY execution. A PTY can stall `cmd.exe`
before the game and agent attach correctly. The batch launcher verifies the
exact process identity, releases input, and stops that exact trial PID on exit.
After every abnormal interruption, explicitly verify that no key is held and
that no leftover `th06.exe`, agent, or high-CPU fuzz process remains. Never use
a broad process kill.

## Next work, in order

1. Run a longer fixed-seed Stage 5 diagnostic only to see whether the current
   path reaches the Practice result and to map any later first failure. This is
   a continuity check, not validation.
2. Run Stage 5 under ordinary RNG, default fail-close, without
   `--continue-on-failure`. Repeat enough independent runs to expose the next
   earliest failure rather than optimizing the last terminal HIT.
3. For each failure, trace back through snapshot history to the earliest
   still-viable consequential decision. Classify it as missing source/hazard
   semantics, continuation/ranking error, stale publication/delivery, budget
   estimation, or a true modeled dead end before changing code.
4. Make the smallest general, falsifiable correction; add one focused unit or
   minimized corpus regression; verify Python/native semantic parity; then
   rerun physically.
5. Investigate the 57 stale retries only if a physical failure makes them
   causal. Measure the hot path first; do not optimize by skipping work, using
   stale projections, or changing safety semantics.
6. Once Stage 5 reaches its result path under ordinary RNG, isolate Stage 6.
   Then regress Stages 1--4 on the current solver before attempting the full
   Hard route.
7. Expand ECL/future-birth modeling only when source inspection plus a physical
   CE identifies a missing behavior. Move deterministic source work offline
   where parity can be proved, but keep runtime RNG/state inputs fresh.

## Known risks and reminders

- Future ECL birth/instruction coverage is incomplete. Unknown forecast
  behavior must fail closed.
- The command lease is based on an observed two-frame pickup bound; rare older
  observations showed longer snapshot/decision ages, so delivery authority is
  not a route-level proof.
- Fixed RNG is useful for causal A/B checks but can overfit. Final evidence
  requires ordinary RNG and default fail-close behavior.
- A terminal empty Hard set is usually an effect. Do not patch its coordinates
  or scene; inspect the earlier viable fork.
- Do not let a soft target deadline shorten survival lookahead. Do not let
  global/attack/position objectives override materially stronger fresh local
  continuation evidence.
- Non-spell enemy pressure may justify aggressive attack as a soft objective
  because earlier kills reduce future births; spell survival may rank pure
  avoidance. Neither may change Hard eligibility, and no named-scene routing
  belongs in the main solver.
- No clear is currently claimed. The next valuable result is a falsifiable
  physical Stage 5 outcome, not a refactor or a broader framework.

## Restart checklist

1. Confirm `git status --short` and current `git log -5 --oneline`.
2. Re-read `AGENTS.md`, this handoff, and `STRATEGY.md`.
3. Confirm the EXE hash/source commit and inspect any `*_latest` artifact's
   actual frame before using it.
4. Run the focused offline/test check required by the intended change.
5. Run one non-PTY, default fail-close physical experiment.
6. Release all input, stop the exact PID, inspect the first causal failure, and
   save only an understood minimized regression.
7. Commit each coherent checkpoint; leave artifacts and external assets
   ignored.
