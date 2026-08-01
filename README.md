# Touhou Solver TH06

A deliberately small TH06 1.02h solver baseline.  It starts from native state
and the reconstructed source instead of carrying the TH08 planner forward.

New Codex sessions should begin with [`START_HERE.md`](START_HERE.md); the
compact working rules are in [`AGENTS.md`](AGENTS.md).

## Exact target and reference

- **Observed:** local `th06.exe` SHA-256 is
  `9f76483c46256804792399296619c1274363c31cd8f1775fafb55106fb852245`.
- **Observed:** this is the exact binary supported by GensokyoClub/th06.
- The authoritative local reference is the ignored clone at
  `reference/GensokyoClub-th06/`, pinned initially at commit
  `cc475a0bc3fef38683b0f02224c87ddba0a021d9`.
- IDA and source agree that `Player::OnUpdate` decrements lives with the byte at
  VA `0x428DEC`.  The runtime patch changes only `01 -> 00`; the EXE on disk is
  never modified.

## Baseline contract

The implementation is intentionally small, with one module per responsibility:

- `native.py`: exact process identity, process-only patch, and state decoding.
- `safety.py`: the only module allowed to certify actions.
- `solver.py`: adaptive horizon and layer composition.
- `ranking.py`: proposals and online preferences inside the certified set.
- `actuator.py`: foreground-guarded physical keyboard output.
- `menu.py`: source-grounded Hard/Reimu-A startup using only Up/Down/Z.
- `dialogue.py`: native dialogue sensing and isolated Ctrl/Skip ownership.
- `agent.py`: the thin runtime loop.

The three solver layers are:

1. **Hard current-hazard authority:** enumerate nine focused directions and
   reject any that collide with an observed native bullet over a short horizon,
   across input pickup delays 0, 1, and 2 frames.
2. **Adaptive solver:** use an 8, 12, or 16 frame horizon according to current
   bullet proximity and density.
3. **Proposal/ranking:** rank only the surviving actions using clearance,
   a conservative bottom-center position, mild continuity, and a tiny
   death-penalty preference. Mere survival is deliberately not rewarded.

Shot and Focus are held during certified control.  Bomb (`0x02`, X) is absent
from the actuator mapping and is never emitted.

During a native active, skippable `GuiMsgVm`, `dialogue.py` holds Left Ctrl,
which the shipped controller maps to `TH_BUTTON_SKIP`. It releases Ctrl outside
that exact phase. For an active but unskippable WAIT, it creates a fresh Z edge
every 250 ms because the shipped code requires `WAS_PRESSED(SHOOT)`; an already
held Z cannot advance it. Neither operation changes a movement proposal.

This is not yet a route-level safety proof.  **Known unsupported authority:**
future ECL births and active lasers.  An active laser returns no action instead
of silently passing through the hard filter.  The first physical runs exist to
validate native layouts, timing, actuation, and this narrow authority before we
add either missing model.

The native gameplay gate also excludes pause/retry menus, replay playback, and
the built-in demo.

The shipped field named `isInMenu` is counterintuitive: source and runtime both
show that it is `1` during an active gameplay calc chain.

## Run

From Windows, run:

```bat
run_th06_baseline.bat --seconds 120
```

The launcher starts the exact game, verifies its path and hash, applies the
process-memory-only life patch, selects Hard/Reimu-A from native menu state,
and releases every held key on exit.  The latest compact trace overwrites
`artifacts/th06_baseline_latest.csv`.

Observe without sending input:

```bat
run_th06_observe.bat 30
```

Run the small platform-independent tests from WSL/Linux:

```bash
./check_th06_baseline.sh
```

Set `TH06_GAME_DIR` or `TH06_PYTHON` to override the Windows launcher defaults
without editing either script.

## First physical checkpoint (2026-08-01)

**Observed:** an exact Hard/Reimu-A game-start trial ran for 110 seconds through
Stage 1 frame 6508 with zero death transitions and zero Bomb inputs. The 99
stable physical direction changes were visible in native input after one frame
61 times and after two frames 38 times, matching the filter's 0–2 frame pickup
branches.

The first dialogue became active at frame 5279 with native
`dialogueSkippable=0`. Twenty-eight isolated Z pulses advanced it; dialogue
ended at frame 5690 and bullets resumed at frame 5804. This physically validates
the independent dialogue controller, not only its offline state decoder.

The run processed 5,685 decisions. Median solve time was 2.79 ms, p95 was
29.02 ms, and maximum was 73.89 ms; 771 native frames were not sampled. This is
the main measured baseline limitation alongside future-birth and laser
coverage. The zero-death result is one observational run, not route closure.
