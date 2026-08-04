# TH06 Start Here

Read in this order:

1. `AGENTS.md` — binding working, safety, and experiment rules.
2. `HANDOFF.md` — current checkpoint, physical evidence, artifacts, and next
   experiments.
3. `STRATEGY.md` — stable solver/research direction.
4. `README.md` — implementation map, run details, and historical evidence.

The objective is a physically validated TH06 1.02h Hard clear. Keep the
implementation small, source-grounded, and driven by the next falsifiable
physical experiment. Do not recreate the TH08 architecture.

## Fixed facts

- Exact supported EXE SHA-256:
  `9f76483c46256804792399296619c1274363c31cd8f1775fafb55106fb852245`.
- Authoritative ignored source: `reference/GensokyoClub-th06/`, currently
  `cc475a0bc3fef38683b0f02224c87ddba0a021d9`.
- Hard safety alone authorizes actions; adaptation changes effort only; soft
  objectives rank only among Hard actions.
- Bomb bit `0x02` is forbidden. Unknown hazards fail closed.
- Fixed RNG, continue-on-failure, offline fuzzing, and time-limited play are
  diagnostics, never clears. The runtime life patch cannot excuse a HIT.
- Do not use REA, REA-provided tools, or LeanToken MCP.

## Common commands

```bash
./build_th06_native.sh
./check_th06_baseline.sh
```

```bat
run_th06_practice.bat --practice-stage 5 --seconds 300
run_th06_baseline.bat --seconds 120
run_th06_observe.bat 30
```

The Windows launch path must be non-PTY. Override machine defaults with
`TH06_GAME_DIR` and `TH06_PYTHON`. Every physical run must release input, stop
the exact trial PID, and leave no high-CPU worker behind.

Do not infer the current task from the historical ledger below `README.md`.
`HANDOFF.md` is the authority for what is in progress and what has actually
been validated at the current checkpoint.
