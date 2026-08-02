# Touhou Solver TH06

A deliberately small TH06 1.02h solver baseline.  It starts from native state
and the reconstructed source instead of carrying the TH08 planner forward.

New Codex sessions should begin with [`START_HERE.md`](START_HERE.md); the
compact working rules are in [`AGENTS.md`](AGENTS.md).
The distilled, non-architectural lessons from the older TH08 workspace are in
[`notes/TH08_CE_GUIDE.md`](notes/TH08_CE_GUIDE.md).

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
- `hazards/bullets.py`, `hazards/lasers.py`, and `hazards/enemies.py`: separate
  source-grounded hazard motion and collision semantics.
- `safety.py`: the only composition layer allowed to certify actions.
- `kernels/safety.cpp`: the general dense collision scan only; hazard semantics
  remain in the separate Python modules and have a Python reference path.
- `solver.py`: Hard authority plus deadline-driven progressive effort.
- `ranking.py`: short proposal commitment inside the certified set. Learning
  is deliberately disabled until a contextual proposal has physical evidence.
- `viability.py`: the bounded two-segment proposal used only when a longer
  constant-action proposal has no survivor.
- `actuator.py`: foreground-guarded physical keyboard output.
- `menu.py`: source-grounded full-run and Practice Hard/Reimu-A startup using
  only Up/Down/Z.
- `dialogue.py`: native dialogue sensing and isolated Ctrl/Skip ownership.
- `input_lease.py`: one in-flight movement command and native-pickup timeout.
- `trial.py`: first-HIT and Practice-result lifecycle checks.
- `agent.py`: the thin runtime loop.

The three solver layers are:

1. **Hard current-hazard authority:** enumerate nine focused directions and
   reject any that collide with an observed native bullet, laser, or lethal
   enemy body over the
   fixed four-frame issue window, across input pickup delays 0, 1, and 2
   frames. This is the current authority window, not a route-level timing
   proof; the Stage 3 checkpoint observed rare three-frame snapshot/decision
   gaps and records that limitation below.
2. **Budgeted anytime effort:** after Hard-4, progressively extend only its
   surviving frontier through 6, 8, 12, and 16 frames. The next rung is chosen
   from measured rollout cost and the remaining decision deadline, never from
   stage/spell IDs, bullet-count bands, wall thresholds, or a saved CE.
3. **Proposal/ranking:** an affordable eight-frame, two-Hard-segment MPC rung
   ranks reachable policy volume inside the existing Hard-4 set. It is a normal
   anytime rung rather than a scene-triggered fallback: physical Stage 1 showed
   that constant actions can alias to one clamped state before their count
   contracts. A one-segment commitment prevents frame-to-frame chatter while
   every fresh Hard check and preferred proposal still permits it. Clearance
   and current-input continuity are only deterministic soft tie-breaks.

Shot and Focus are held during certified control.  Bomb (`0x02`, X) is absent
from the actuator mapping and is never emitted.

During a native active, skippable `GuiMsgVm`, `dialogue.py` holds Left Ctrl,
which the shipped controller maps to `TH_BUTTON_SKIP`. It releases Ctrl outside
that exact phase. For an active but unskippable WAIT, it creates a fresh Z edge
every 250 ms because the shipped code requires `WAS_PRESSED(SHOOT)`; an already
held Z cannot advance it. The 50 ms release/re-press is a non-blocking state,
so dialogue control cannot stall safety sampling. Neither operation changes a
movement proposal.

This is not yet a route-level safety proof. Future ECL births/instructions are
not yet modeled. The four-frame issue window is physically measured; a command
lease prevents another direction from being sent until the native input shows
the exact focused movement, and fails closed if pickup exceeds two frames. In armed control, an
empty/unknown hard authority or the first physical HIT releases input and ends
the trial instead of silently continuing a previously held direction.

The native gameplay gate also excludes pause/retry menus, replay playback, and
the built-in demo.

The shipped field named `isInMenu` is counterintuitive: source and runtime both
show that it is `1` during an active gameplay calc chain.

The chronological checkpoints below retain measurements from earlier solver
versions. Their descriptions of density, boundary, laser, or fixed-horizon
gates are historical evidence, not the current adaptive contract.

## Run

From Windows, run:

```bat
run_th06_baseline.bat --seconds 120
```

The launcher starts the exact game, verifies its path and hash, applies the
process-memory-only life patch, selects Hard/Reimu-A from native menu state,
releases every held key, and stops only that identity-verified process on exit.
The latest compact trace overwrites
`artifacts/th06_baseline_latest.csv`.

On a non-Practice result, the launcher also skips high-score naming, advances
the final statistics, selects the first empty replay slot, enters `TH06`, and
validates the saved magic, 1.02 version, and original checksum algorithm before
stopping the game. Pass `--replay-slot 1..15` or `--replay-name NAME` to
override the defaults; an occupied requested slot fails closed.
An initial physical Scores-screen probe found the heap `ResultScreen` through
the source-defined calc chain and decoded Supervisor state 6 plus result state
0 at runtime, validating the dynamic-state reader before route use. Actual file
creation still requires a non-Practice game result.

Start any unlocked Hard/Reimu-A Practice stage with:

```bat
run_th06_practice.bat --practice-stage 1 --seconds 120
```

Its trace is isolated as `artifacts/th06_practice_stageN_latest.csv`. The exact
1.02h source deliberately makes a completed Practice result exit directly to
the main menu, so Practice cannot save a replay; replay automation is validated
on a non-Practice result screen instead.

Observe without sending input:

```bat
run_th06_observe.bat 30
```

Run the small platform-independent tests from WSL/Linux:

```bash
./build_th06_native.sh
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

## First fail-closed iteration (2026-08-01)

The first isolated authority stop at Stage 1 frame 2462 was a false empty safe
set: all nine actions were rejected by one fired `exFlags=0x14` acceleration
bullet about 100 pixels away. The old generic dynamic envelope let that bullet
move in every direction. `BulletManager::OnUpdate` instead adds one fixed
`ex4Acceleration` vector until its timer clears bit `0x10`; the corrected bound
enumerates each possible clear frame and preserves the native acceleration
vector.

The physical rerun changed frame 2460 from zero to nine safe actions and then
continued without a hit or Bomb to frame 8968, where it stopped on the next
unsupported authority: an active laser. The run sampled 6,877 states, missed
2,039 native frames, and had a 100.86 ms maximum solve time. Laser geometry is
the next correctness gap; the measured Python cost is also now strong evidence
for a narrow native safety kernel once that geometry is correct.

## Complete Practice Stage 1 checkpoint (2026-08-01)

The laser pool is now decoded from the source-defined `Laser` layout. Its
warning, active, despawn, moving segment, rotated player transform, and shipped
midpoint-hitbox bugs are isolated in `hazards/lasers.py`. Bullet semantics are
independently isolated in `hazards/bullets.py`. A Windows C++ DLL performs only
the dense nine-action collision scan; synthetic bullet and laser cases matched
the Python reference at 4/6/16-frame horizons during parity checks.

Two physical empty-safe-set counterexamples separated the fixed issue window
from adaptive effort. At f7185 every action survived three frames and seven
survived four, but no single constant action survived six; the observed issue
interval is two decision frames plus two pickup frames. At f6364 a short-term
clearance choice had entered the bottom-right corner even though earlier
16-frame survivors existed. Longer rollout survival is therefore now the
primary ranking signal among—not instead of—the fixed hard-safe set.

The next physical run completed Hard/Reimu-A Practice Stage 1 at frame 12567:
12,337 sampled states, zero dead rows, zero authority stops, and no Bomb bit in
native or desired input. It covered up to 422 bullets, up to 6 simultaneous
decoded lasers, and 472 laser-bearing decisions. The maximum hazardous-state
decision gap remained two frames. Native solve timing was 2.21 ms median,
10.71 ms p95, 17.50 ms p99, and 33.83 ms maximum. This validates integrated
Stage 1 behavior and clean Practice-result termination, not later-stage or
full-route safety.

## First Stage 2 HIT and body coverage (2026-08-01)

A full route first entered Stage 2, then the first physical HIT occurred at
f2248 while all nine remaining fired bullets were at least about 70 pixels from
the player. Source inspection showed two post-update explanations: a colliding
bullet immediately becomes despawning state 5, which the lethal snapshot had
omitted, or `EnemyManager::OnUpdate` can collide a lethal enemy body through
the same `Player::CalcKillBoxCollision` path.

The sensor now retains despawning bullets as diagnostics, keeps the complete
previous snapshot in first-failure JSON, and decodes current lethal bodies from
the authoritative `Enemy` layout. The layout has an independent address check:
`0x4B79C8 + 0xEE5EC == 0x5A5FB4`, exactly the separately mapped enemy calc-chain
global. Source collision dimensions reduce to `hitboxDimensions / 3` per side;
current axis, accelerated-angle, and interpolation movement are isolated in
`hazards/enemies.py` and merged into the existing AABB kernel.

The first integrated Hard Practice Stage 2 run then completed at frame 15494:
15,320 sampled states, zero dead rows, zero authority stops, and no Bomb bit.
It covered up to 334 bullets, 20 simultaneous lethal enemy bodies, and 226
simultaneous despawning-bullet witnesses. Native solve timing remained 3.52 ms
median, 11.20 ms p95, 15.27 ms p99, and 25.18 ms maximum. This physically
validates the layout and integrated current-body model; a same-route full run
is still needed to make the f2248 causal A/B strong.

## Stage 2 physical-input checkpoint (2026-08-01)

A later full-route HIT at Stage 2 frame 9790 isolated an input-pipeline bug. The
colliding state-5 bullet was at `(64.375, 380.635)` while the player was at
`(65.029, 383.775)`. At the preceding frame the solver selected right, but the
game sampled an older down-left command. Branching only over delays of the
current native direction could not represent this queued intermediate action.

Physical movement commands are now serialized: a newly selected direction is
held until the exact focused direction appears in native input. While pending,
the already issued full certificate remains authoritative and a one-frame
current/leased recheck covers newly observed hazards. Pickup beyond the
observed two-frame bound fails closed. The lease timestamp is read after the
actual `SendInput`, which fixed a separate false timeout caused by the old
blocking dialogue pulse advancing three native frames before command issue.

Two attempted timing fixes were physically falsified rather than retained.
Extending the constant-action hard horizon to five produced an empty safe set
at frame 3687, where the four-frame authority still had down, down-left, and
down-right available. Hard eligibility therefore remains four frames. Dialogue
Z edges are now non-blocking, and the native wrapper builds the maximum-horizon
hazard buffer once for both the hard and adaptive scans; a saved 154-bullet
Windows replay of the calculation preserved both action sets while reducing
median paired scan time from 4.48 to 3.57 ms.

The final integrated Hard Practice Stage 2 run reached its result path at frame
16059 after 15,984 sampled states, with zero dead rows, zero authority stops,
and no Bomb bit in native or desired input. It covered up to 337 bullets, nine
lasers, and 13 lethal enemy bodies; 654 rows exercised an in-flight command and
32 non-blocking dialogue edges completed. Both the overall and hazardous-state
decision gaps were at most two frames, while the dialogue gap was at most one.
Native solve time was 2.85 ms median, 9.68 ms p95, 13.77 ms p99, and 31.04 ms
maximum. This validates Stage 2 input timing; later stages and non-Practice
replay saving remain physical gaps.

## Complete Practice Stage 3 checkpoint (2026-08-01)

The first full-route regression cleared Stages 1 and 2, then stopped in Stage 3
on a torn bullet publication: `SpawnSingleBullet` writes `state=FIRED` before
its collision size and motion tail. The sensor now re-reads only that exact
slot tail and accepts it only after the source-defined fields form a valid
geometry; a persistent inconsistency still stops with raw evidence.

Two later Practice stops separated delivery and proposal problems. A 284-bullet
16-frame soft scan took 38.5 ms and let its proof age before input issue; at
220 bullets the adaptive layer now spends only eight soft frames while hard-4
eligibility remains unchanged. Another linear-bullet run held down as the hard
set shrank `4 -> 2 -> 1 -> 0` after constant-action effort became empty. The
native two-segment proposal therefore ranks possible replanning exits only
inside the hard set. On the reduced witness, Python and C++ agreed on scores
`down=0, right=6, down-left=0, down-right=3`; the native scan cost 5.14 ms
median.

The next stop was a false empty set over 210 fired `exFlags=0x42` bullets. The
source shows that `0x40` follows a timed decelerate-and-rotate schedule, not the
old arbitrary-direction fallback. Decoding its timer, interval, count, speed,
and rotation and reproducing `BulletManager::OnUpdate` removed that false
authority loss.

The integrated Hard/Reimu-A Practice Stage 3 run then reached its result path
at frame 18340 after 17,962 sampled states, with zero dead rows, zero authority
stops, and no Bomb bit in native or desired input. It covered up to 615 bullets,
19 lethal enemy bodies, and 449 despawning witnesses; the two-segment proposal
was selective on eight rows. Solve time was 3.39 ms median, 13.57 ms p95,
19.90 ms p99, and 35.42 ms maximum. Overall and hazardous-state decision gaps
were at most three frames, and one changed command was issued from a snapshot
three frames old. Those rare timing ages remain an explicit unresolved bound;
the successful Practice run is not permission to weaken hard safety. A fresh
full route from Stage 1 is the next regression.

## Pickup-aware repair checkpoint (2026-08-02)

That full-route regression exposed a linear-bullet trap in Stage 1: the
two-segment proposal selected a viable first segment at f10724, but ordinary
ranking discarded it one frame later. A repair proposal is now retained for
one four-frame segment only while it remains in every fresh hard-safe set.

The focused Practice rerun then found a second, distinct optimism at f7210.
At f7208 the nominal two-segment scan uniquely preferred right while native
input was still up-left. The command took two frames to appear in native input;
at f7209 up-left still survived eight frames, while right no longer survived a
fresh four-frame rollout. Once right was sampled at f7210, no action survived
three frames. The two-segment proposal had modeled both commands as immediate.

The Python reference and native C++ proposal now branch over the measured
0/1/2-frame pickup delay for both the first and continuation commands. A first
action receives the minimum continuation count across its possible pickup
states. This changes proposal ranking only; the hard-safe set is unchanged.

The next Hard/Reimu-A Practice Stage 1 run reached its result path at frame
11383 after 11,276 sampled states with zero dead rows, authority stops, or Bomb
inputs. It covered up to 433 bullets, six lasers, and 18 enemy bodies. The
pickup-aware repair scan ran on 24 rows; its median solve time was 13.00 ms and
maximum was 25.53 ms. Overall solve time was 1.92 ms median, 14.30 ms p99, and
27.20 ms maximum; hazardous decision gaps and command issue ages were at most
three and two frames respectively. Per the one-time iteration order, Practice
Stage 4 is next, followed by a full route from Stage 1.

## Complete Practice Stage 4 checkpoint (2026-08-02)

Stage 4 was developed by stopping on each first physical authority loss. The
counterexamples separated dense-scan publication latency, source-normal-speed
laser corridors, pickup slack across a fast/focused transition, and several
bottom-boundary proposal errors. Each change remained in the soft effort or
ranking layer: the four-frame hard-safe set and the Bomb prohibition did not
change.

The final two failures exposed the same general timing mismatch at different
distances. At f16163 a 12-frame proposal still considered a tangent path
durable after the 20-frame boundary warning had begun; the bounded moderate-
density boundary effort now uses the same 20-frame view. At f16924 the player
had not entered that warning yet, but a narrowed h12 corridor would enter it
within the proposal window. Reusing the already prepared hazards for a
two-segment score preferred down-right with five continuations over down with
four. This extra native ranking pass cost 1.48 ms median on the saved witness
and never adds an action to Hard-4.

The integrated Hard/Reimu-A Practice Stage 4 run reached its source-defined
result path at frame 24520 after 23,674 sampled states, with no HIT, authority
stop, or Bomb input. It covered up to 637 bullets, 8 simultaneous lasers, 8
lethal enemy bodies, and 316 despawning bullets. Solve time was 3.78 ms median,
17.33 ms p99, and 71.36 ms maximum. The stale-publication guard retried 130
decisions; observed command issue age stayed at most two frames, although one
hazardous decision age reached five frames. That timing tail remains an
explicit gap. The next required check is a fresh full Hard route from Stage 1.

## Post-Stage-4 full-route regression (2026-08-02)

The first regression cleared Stage 1 and reached Stage 2 f10221, where three
active lasers appeared in empty native pool slots. Their angle motion could not
yet be inferred from a previous sample, so the unknown-laser guard correctly
stopped. Runtime showed each source `Laser` at timer 1 with `endOffset=4`,
`speed=4`, and its origin about 297 pixels from Reimu. Even allowing every
future angle, the beam, player movement, and both hitboxes cannot span that
distance within Hard-4. The laser module now evaluates that conservative radial
envelope on a newborn slot; a possibly reachable unknown beam still fails
closed, and an unreachable one is tracked normally from its second sample.

The focused Hard/Reimu-A Practice Stage 2 rerun observed all three beams and
reached the source-defined result path after frame 16680 with no HIT, authority
stop, or Bomb. The next action remains a fresh full route from Stage 1.
