# Optimization strategy

Only promote an optimization here after measurements, focused tests, and a
physical counterexample or run show that it helps.  Safety authority must not
change merely to save time.

## Confirmed

- **Prepare the largest selected hazard window once.** Derive Hard-4 and the
  adaptive future set from the same flattened arrays.  On physical Stage 3
  f1341, a cold Hard-4+h8 pair measured 7--9 ms median instead of rebuilding
  the window; the next run crossed the former f1344 and f2069 stops.
- **Minimize physical counterexamples before keeping them.** The f1341 future
  frontier reduced from 356 bullets to 2 while preserving the exact h4/h8
  sets.  Smaller corpus cases make both regressions and model errors clearer.

## Candidates to measure

- Decode runtime pools into native structure-of-arrays only if end-to-end
  sensing time is significant; snapshot decode is outside `solve_ms`.
- Add broad-phase geometry, feasibility pruning, or state deduplication only
  after a profile shows repeated native collision work is dominant.
- Flatten or cache immutable ECL decode at its boundary; do not add planner
  layers merely to host the cache.
