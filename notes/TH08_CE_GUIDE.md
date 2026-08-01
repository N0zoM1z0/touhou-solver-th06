# TH08 Lessons Kept For TH06

This is a compact warning list, not a TH08 design specification.  Apply an
item only when TH06 source or physical evidence reaches the corresponding
failure.  Do not import the TH08 architecture that originally exposed it.

## Evidence

- A different-RNG hit count is observational, not a causal A/B result.
- The first hit of a fresh run is the primary causal witness.  Later hits are
  diagnostics after state, resources, and RNG may already have diverged.
- Offline safety, implementation parity, and a replay/root witness do not
  establish live delivery or a physical clear.
- Timeout or missing coverage means unresolved.  It is never a winning or
  losing certificate.
- Fix the earliest source/runtime mismatch.  Do not compensate downstream
  with a waypoint, score, or stage-specific exception.

## Input And Time

- Native active input, actuator-held desired input, and a pending command are
  distinct observable/control states.
- Selecting the already-held complete mask is no-write only when that held
  path is itself certified.  Missing or empty authority is not no-write.
- Computation is a physical held-input interval.  A proof may expire while a
  synchronous solve is running.
- Snapshot-to-issue age and post-issue pickup delay are separate uncertainty.
- Input publication and player movement may have different frame phases;
  establish the TH06 phase from source and runtime rather than inheriting the
  TH08 one-frame result.
- A command transaction must describe the complete mask.  Avoid intermediate
  key states that the game could sample between separate writes.

## Hazards And Geometry

- Positive clearance against current bullets does not cover a future bullet,
  transform, laser, or hostile body.
- Future aimed emissions are action-conditioned because the candidate player
  path may change their angle or timing.
- Signed continuous clearance is authoritative.  A safe lattice center does
  not certify the surrounding cell without consuming its sampling radius.
- Coarse global erosion can become sound but uselessly empty.  Refine only the
  pressure region instead of restoring center-only or fallback widening.
- One conservative scalar such as boundary reserve is not equivalent to a
  viable set; clamping and common uncontrollable prefixes can alias actions.
- Unknown source semantics fail closed and must not become free space.

## Planning And Delivery

- Hard authority, adaptive compute allocation, and proposal/ranking remain
  separate.  A proposal may order exact work but cannot enlarge its result.
- Spend exact work on held input and the most promising repair directions
  before broad compass enumeration.
- Near pressure, concentrate compute on few viable candidates.  Use long
  horizons or fine resolution only where their result can arrive in time.
- A published result must match the exact root, hazard/content version,
  interval, and issue-time state that consumes it.
- Fresh issue-time evidence may narrow an old proof; a short local check may
  not widen a named exact authority.
- Do not add asynchronous publication, leases, a global kernel, or native
  acceleration until a measured TH06 failure requires that mechanism.

## Soft Objectives

- Survival and no-Bomb are hard.  Position, damage, collection, Power, and
  score are objectives only inside the certified viable set.
- Focus/unfocus is eventually an action factor, not a permanent assumption,
  but expand it only after the focused survival baseline is understood.
- Early kill is useful only when a causal native result shows that a safe
  action prevents later hostile births.
- Stage or phase identity may be context for proposals; it is not a substitute
  for observable pattern features or a general safety law.
