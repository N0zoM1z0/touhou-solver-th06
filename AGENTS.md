# TH06 Working Rules

Read `START_HERE.md` first. Use `README.md` and the ignored
`reference/GensokyoClub-th06/` only as needed for the current question.

The goal is a physically validated TH06 Hard clear. Keep the implementation
small, correct, and source-grounded. **Iteration and exploration come before
software-engineering work.** Do not build frameworks, broad abstractions, or a
TH08-style architecture in anticipation of future needs.

Keep these authority boundaries:

1. Hard safety decides which actions are allowed.
2. Adaptation changes compute effort, never safety eligibility.
3. Learning proposes/ranks only among allowed actions.

These are boundaries, not a fixed implementation roadmap. Change the model
when physical evidence disproves it. Survival is hard; attack, collection, and
position are soft. Bomb bit `0x02` must never be emitted. Unknown hazards fail
closed.

For each iteration:

- use source/IDA/runtime evidence to explain the first physical failure;
- make the smallest falsifiable change;
- add only the focused regression needed for an understood bug;
- rerun physically when the integrated behavior changes.

Offline checks cannot replace physical play. Do not hardcode a stage or spell
before a general cause has been tested. Keep menu and dialogue control separate
from movement. Do not commit the game, source clone, traces, logs, or caches;
release input and stop all trial processes after a run.
