# Legacy Policy and Stage 5 Audit — 2026-08-04

## Question

Can a source-phase route use ECL plus the live RNG/state to choose correctly,
or did the historical Stage 1--4 clears merely demonstrate a brittle set of
`if` statements that cannot extend to Stage 5?

The evidence supports a qualified **yes** to phase-local policies, but not the
stronger claim that ECL automatically determines a safe route. ECL determines
the causal barrage program. A policy must still choose positioning, streaming,
damage timing, collection, and local corrections under the actual entry state.

## What the old clear line actually was

The historical solver never selected a branch with `snapshot.stage`, a spell
ID, or a named scene. Its apparent generality came from using bullet count,
laser presence, enemy count, boundary relief, Hard-set width, and continuation
horizon as implicit scene classifiers.

| checkpoint | physical evidence | `solver.py` lines | conditional lines |
| --- | --- | ---: | ---: |
| `408a68b` | Practice Stage 1 clear | 84 | 11 |
| `5b275ce` | Practice Stage 2 clear/input timing | 122 | 15 |
| `ee8b2f4` | Practice Stage 3 clear | 155 | 19 |
| `b5fecb9` | pickup-aware Stage 1 regression clear | 161 | 19 |
| `17fd93a` | Practice Stage 4 clear | 840 | 84 |
| `05b5648` | later Stage 5 universal line | 3015 | 272 |

The Stage 4 clear solver contains no stage-keyed condition, yet its comments
name many Stage 4 physical frames and its branches combine thresholds such as
`bullets >= 400`, laser/non-laser, one versus many enemies, wall relief, broad
versus narrow Hard authority, and several different continuation scans. These
were useful causal repairs, but together they formed an implicit phase table
whose entries could overlap and whose compute costs interfered.

This distinction matters:

- the useful part was the repeated physical loop, source correction, delivery
  modeling, and discovery that different scenes need different continuation
  shapes and movement speeds;
- the non-transferable part was asking one global `if` tree to infer which
  scene it was in from incidental geometry and then share one publication
  budget among every accumulated remedy.

The new route/phase design should recover the former without restoring the
latter.

## What Stage 5 disproved

Stage 5 did not show that source-conditioned control is impossible. It showed
that the global universal controller was not compositionally stable.

At checkpoint `52ed4ac`, a forced-RNG diagnostic (`0x6382`) remained alive to
f8981 with no HIT, authority stop, or Bomb during its 150-second window. That
was not a clear, but it crossed multiple earlier failure regions. The retained
Stage 5 corpus contains failures from f579 through f9758. Their minimized
contracts repeatedly identify:

- a shallow continuation or endpoint count consuming the budget needed for
  the next useful rung;
- speculative deep projection delaying publication of a completed local
  result;
- nominal pickup restoring an action rejected by exact repeated-delivery
  modeling;
- a fast positional tie moving too far before the next correction;
- aliased wall-clamped action sequences being counted as independent routes;
- a global proposal and a local corner heuristic disagreeing through different
  control-state assumptions;
- future message/boss interrupts and child creation missing from the world.

These are largely interference, scheduling, state-coherence, and missing
source-transition failures. They are not evidence that one named Stage 5
pattern is unsolvable. They also explain why adding more general machinery did
not monotonically improve earlier stages.

The corpus is especially informative by source phase:

- f579 and f912 are early pre-boss entry/streaming choices;
- f1509 is inside the large t1442--t2102 wave group;
- f2572--f3339 cluster around the t2352--t2972 group and approach the t3372
  message/midboss interrupt;
- f8447/f8456 exercise final-frame and persistent ECL child creation after the
  t7704 boss entry;
- f8682/f9758 occur with the timeline stalled at t7707 in boss play.

One global threshold tree therefore mixed at least four source-distinct
control problems.

## Stage 5 source shape

The installed `ecldata5.ecl` contains 238 ordinary timeline instructions. Its
spawn groups begin at source times:

```text
440, 690, 1042, 1442, 2352, 3372, 3874, 6834, 7214, 7704
```

Notable structure:

- t690--t1182 streams mirrored side enemies;
- t1442--t2102 contains 36 spawns from subs 0/1/2;
- t2352--t2972 uses subs 3/4/5/6 and leads into the midboss;
- t3372 spawns sub 12, then message at 3372, message wait at 3373, and boss
  interrupt at 3374;
- t3874--t6634 contains 145 alternating spawns from subs 1/9/10/11;
- t7704 spawns sub 21, followed by message, wait, boss interrupt, boss wait,
  and the final message sequence.

The Stage 5 ECL catalogue also proves that different subroutines use different
aim families. Examples on Hard include fixed/offset fans (subs 1, 9, 10, 11),
player-aimed patterns with ECL variables (subs 0, 2--6), and boss subroutines
with aimed, random-angle, and random-speed families. Treating all of these as
one geometry class discards useful source structure.

Authoritative engine order explains what must remain online. The timeline can
spawn an enemy and `SpawnEnemy` immediately enters its time-zero ECL. During
each enemy update, movement/callbacks/ECL execute before player damage is
computed; damage and kill state can then change retirement, item drops, bullet
cancellation, and death callbacks. Aimed bullet setup reads the player
position at the ECL firing transition, while random ECL variables, delayed
shoot intervals, random patterns, item behavior, and some effects consume the
shared RNG stream. Thus a phase policy cannot be compiled as one fixed replay.

## Required non-interference contract

The intended unit is:

```text
exact route key
  -> exact source phase
     -> that phase's private policy/state machine
        -> ordered proposal under the live state
           -> common fresh Hard intersection
```

A phase policy may contain as many source-justified conditions as its measured
workload needs. Those conditions must not run for another phase. They should
read semantic state, not a captured failure identity:

- current player position/velocity/input delivery state;
- current RNG state or source-derived near-future RNG transitions;
- enemy positions, life, callbacks, and kill/retirement possibilities;
- Power/items when they affect the route objective;
- current bullets/lasers and source-defined unborn hazards;
- time remaining to the next source transition.

The output remains soft. No phase policy may add an action to Hard, weaken an
unknown-hazard stop, or emit Bomb.

## Offline/online feasibility boundary

Offline can precompute the fixed program graph, deterministic event schedule,
phase transitions, policy candidates, robust entry tubes, and compact decision
data across distributions of RNG/resource/player state. Stateful fuzzing can
then compare policies on identical source-valid worlds and minimize causal
differences.

Online must supply the branch values that depend on the real run: current RNG
stream position, exact aim point, damage and kill timing, item/Power history,
entry position, and command pickup/publication age. It should select and make a
small correction, not rediscover the whole stage.

This is feasible only to the extent that the offline world implements every
transition that changes the policy. The retained Stage 4 adjacent-frame battle
windows already have exact player/combat/RNG and fired-bullet parity for the
audited segments. That validates those segments, not all Stage 5 boss phases.
Missing candidate-conditioned aim, callback, or RNG consumption must be added
phase by phase and checked against physical adjacent frames.

## Decision

Proceed with isolated route/phase policies. Use the old clear line as a library
of hypotheses and counterexamples, not as production code:

1. identify the exact source phase before strategy runs;
2. replay the old policy and a small set of phase-specific alternatives on a
   stateful entry/RNG corpus;
3. retain source/Hard/delivery fixes globally;
4. move strategy conditions and tuned horizons into the owning phase only;
5. physically validate each phase boundary before authoring the next;
6. revisit Stage 5 with its own manifest after the Stage 4 pilot establishes
   the contract.

The claim to test is not "one policy clears every phase." It is "every fixed
source phase admits a compact state-conditioned policy whose live branches fit
the publication budget and whose actions remain Hard-certified."
