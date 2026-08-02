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
- **Keep decoded state scalar inside frame-by-entity loops.** The Stage 3
  f2511 latency CE exposed reflective copies and proxy objects in ECL/enemy
  projection.  Removing those allocations cut the saved f2500 cold decision
  median from about 25.6 ms to 9.5 ms without changing safety or planning.
- **Advance temporal hazards once and spatially prune exact collision tests.**
  Bulk bullet projection removes horizon-squared trajectory work; the native
  proposal grid still runs the original exact margin test inside each cell and
  stops a min-score branch once it reaches zero.  Saved f1338--f1356 full
  decisions measured roughly 9.6--11.5 ms median, and the next physical run
  crossed both the former f1361 authority stop and f5478 hit.

## Candidates to measure

- Decode runtime pools into native structure-of-arrays only if end-to-end
  sensing time is significant; snapshot decode is outside `solve_ms`.
- Add broad-phase geometry, feasibility pruning, or state deduplication only
  after a profile shows repeated native collision work is dominant.
- Flatten or cache immutable ECL decode at its boundary; do not add planner
  layers merely to host the cache.
