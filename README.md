# TH06 Hard Route Agent

This repository targets one physically validated Touhou 6 v1.02h Hard
Reimu-A clear with no HIT, no Hard-authority loss, and no Bomb.

The active design is source-grounded route solving, not a universal online
planner:

```text
installed ECL + authoritative source + physical snapshots
    -> offline route/phase analysis and policy search
    -> short state-conditioned route intent
    -> common delivery-aware Hard certification
    -> one physical input transaction
```

Read [START_HERE.md](START_HERE.md), then [AGENTS.md](AGENTS.md) and
[HANDOFF.md](HANDOFF.md). The retired universal-planner checkpoint is preserved
at annotated tag `pre-phase-route-pivot-20260804`.

## Repository map

- `scripts/th06/native.py` captures one coherent native snapshot from the
  supported EXE.
- `scripts/th06/model.py` is the immutable runtime/source state model.
- `scripts/th06/hazards/` contains route-neutral source physics and future
  world forecasting.
- `scripts/th06/kernels/` and `native/` contain parity-checked Hard/local hot
  paths.
- `scripts/th06/solver.py` is the small common authority and route dispatch.
- `scripts/th06/routes/` contains route keys, source-phase identity, and the
  authored route packs. Hard/Reimu-A/Stage 4 is the first retained pilot;
  Stage 1 is now the active phase-by-phase route.
- `scripts/th06/routes/state_machine.py` contains isolated source-clock policy
  states; only the selected route phase can emit an intent.
- `scripts/th06/barrage_lab/` provides source-derived/stateful offline
  workloads. It is an experiment bed, not a clear oracle.
- `tests/corpus/counterexamples/` retains small understood shared-model and
  local-primitive counterexamples.
- `notes/PHASE_ROUTE_PIVOT.md` records the audit and architecture decision.
- `notes/FUTURE_WORLD_AUDIT.md` is the detailed historical source/model ledger.

## Authority

The exact supported executable SHA-256 is:

```text
9f76483c46256804792399296619c1274363c31cd8f1775fafb55106fb852245
```

The ignored authoritative source clone is
`reference/GensokyoClub-th06/` at
`cc475a0bc3fef38683b0f02224c87ddba0a021d9`. Installed archives under
`reference/th06_dat/` are ignored and must not be committed.

Reverse-engineering claims come only from that source, existing IDA material,
and controlled runtime/physical evidence. Do not use REA or LeanToken.

## Checks

```bash
./build_th06_native.sh
./check_th06_baseline.sh
```

Inspect source timeline sections for route authoring:

```bash
PYTHONPATH=scripts python3 scripts/inspect_th06_route.py \
  reference/th06_dat/th06_ST.DAT --stage 4
```

Run stateful offline replay from a physical snapshot:

```bash
PYTHONPATH=scripts python3 scripts/replay_th06_stateful.py \
  artifacts/th06_failure_latest.json \
  --archive reference/th06_dat/th06_ST.DAT \
  --seeds 500 --frames 240 --birth-events 4
```

For a captured physical battle world, `--metric policy-volume` replays the
current bounded recursive primitive and `--metric constant-frontier` replays
the unchanged-action frontier recovered from the historical clear. These are
phase-policy experiments only; neither can change Hard eligibility or count as
a physical result. `--target x,y` optionally reproduces the route's soft
target tie-break inside the metric-preferred Hard set; omitting it runs the
same primitive target-free.

Generic source-shaped barrage stress remains useful for shared primitives:

```bash
PYTHONPATH=scripts python3 scripts/stress_th06_barrages.py \
  reference/th06_dat/th06_ST.DAT --seeds 1000 --planner
```

## Physical play

Active Stage 1 route:

```bat
run_th06_practice.bat --practice-stage 1 --seconds 300
```

Retained Stage 4 pilot:

```bat
run_th06_practice.bat --practice-stage 4 --seconds 300
```

Full-route validation:

```bat
run_th06_baseline.bat --seconds 1200
```

`--rng-seed`, `--continue-on-failure`, and short time windows are diagnostic
only. Windows launch from WSL must be non-PTY. Every run must release input,
stop its exact PID, and leave no game/agent/high-CPU process behind.

## Current coverage

The common source model includes current bullets, lasers, enemy bodies,
timeline enemy insertion, bounded ECL children, future laser mutation, RNG,
and captured combat/resource state. Coverage is not equivalent to complete
causal battle simulation: candidate-conditioned aim, damage/kill/retirement,
callbacks, and resulting RNG/item effects still require phase-driven work.

The first Stage 4 route pack currently covers audited pre-boss timeline
sections with route-selected, source-clock policy states and bounded local
horizons. Boss ECL phases are deliberately reported as `phase-unavailable`
until authored. This fail-visible boundary is intentional; no anonymous
universal fallback hides missing route work.

Active development has returned to Stage 1 and will expose coverage one
source phase at a time. Until a Stage 1 phase is authored and physically
validated, its missing boundary remains visible rather than borrowing Stage
4 behavior or the retired universal strategy layer.
