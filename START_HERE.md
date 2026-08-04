# TH06 Start Here

Read in this order:

1. `AGENTS.md` — binding authority and iteration rules.
2. `HANDOFF.md` — current checkpoint and next physical experiment.
3. `STRATEGY.md` — the route/phase design and offline/online split.
4. `README.md` — repository map and commands.

The mission is one physical TH06 1.02h Hard Reimu-A clear with no HIT, no
Hard-authority loss, and no Bomb. The previous universal-planner line is
preserved at annotated tag `pre-phase-route-pivot-20260804`; it is no longer
the main design.

The current shape is:

```text
authoritative source + offline phase analysis
    -> Hard/Reimu-A/stage/phase route pack
    -> short state-conditioned proposal
    -> common fresh Hard certification
    -> one input transaction
    -> physical evidence
```

Fixed facts:

- supported EXE SHA-256:
  `9f76483c46256804792399296619c1274363c31cd8f1775fafb55106fb852245`;
- ignored authoritative source clone:
  `reference/GensokyoClub-th06/` at
  `cc475a0bc3fef38683b0f02224c87ddba0a021d9`;
- Bomb bit `0x02` is never permitted;
- unknown hazards fail closed;
- offline success, forced RNG, and continue-on-failure are diagnostics, not
  clears;
- no REA, REA tooling, or LeanToken.

Common checks:

```bash
./build_th06_native.sh
./check_th06_baseline.sh
```

Current physical pilot:

```bat
run_th06_practice.bat --practice-stage 4 --seconds 300
```

Windows launch from WSL must be non-PTY. After every run, release input, stop
the exact PID, and verify that no game or high-CPU worker remains.
