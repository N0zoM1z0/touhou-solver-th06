# TH06 Optimization Notes

Optimize only a measured route-phase bottleneck. Safety semantics and source
ordering must remain identical.

## Retained measured techniques

- Reuse one prepared hazard window inside a phase decision when multiple
  exact queries share the same snapshot.
- Keep decoded ECL/enemy state scalar inside frame/entity loops; this reduced
  a retained Stage 3 local decision from roughly 25.6 ms to 9.5 ms.
- Advance temporal hazards once and use spatial pruning only before the same
  exact collision predicate.
- Minimize physical counterexamples before retaining them.
- Deduplicate physically aliased reachable states, especially at movement
  clamps.

## New optimization order

1. Move static timeline/ECL decoding offline.
2. Precompute phase policy structure and source event schedules.
3. Keep online conditioning proportional to the actual branch state.
4. If a phase helper is measured too slow, move that small exact helper to
   native code and parity-test it.
5. Reject an optimization that wins by stale projections, omitted source
   events, partial results, or changed collision semantics.

Do not resurrect a global adaptive horizon ladder merely as an optimization.
The owning route phase selects the work it needs; the runtime enforces its
deadline and falls back only to a freshly Hard-certified held action or an
explicit authority stop.
