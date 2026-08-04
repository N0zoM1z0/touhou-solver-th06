# Stage 1 Hard/Reimu-A phase route

## Source manifest

The installed `ecldata1.ecl` has 231 ordinary timeline instructions. Its
pre-boss spawn sections begin at source times 128, 1600, 2008, 2408, 4498,
and 5279. This route will not author all of them speculatively; each source
phase is exposed only after the preceding physical boundary is understood.

The first section contains three materially different source states:

- t128--t576 spawns sub0/sub1 parents. On Hard, their only bullet setup is
  masked to Lunatic, so the Hard problem is enemy-body safety, damage/kill,
  falling Power/item collection, and positioning for the next phase.
- t640 begins sub2/sub3. Sub2 moves for 60 local ticks and fires a Hard 9x2
  aimed fan at local ECL t70. Sub3 has no Hard bullet instruction. This phase
  must receive its own state-conditioned policy because player position at
  the firing transition changes the source fan.
- t1220 begins random-coordinate sub0/sub1 insertion. The shared Hard model
  already encloses the authoritative random x range; that is hazard authority,
  not a route policy for this later state.

These claims come from the installed stage asset plus authoritative
`EclManager::RunEcl` difficulty dispatch and bullet setup. The engine executes
an instruction only when its difficulty bit is set, and aimed fan opcode 67
reads the live player position when the firing instruction executes.

## First falsifier

The first authored checkpoint covers only quiet setup and the t128 sub0/sub1
body/resource stream. It uses the common Hard-4 authority and a phase-local
bottom-center target; no deep search is justified before bullets exist. At
t640 the pack returns explicit `phase-unavailable` naming the next aimed
source phase. This is intentional coverage, not a failure fallback.

The historical Stage 1 clear remains a hypothesis library. Its h8/h12/h16
bullet-count classifier is not restored: it mixed several source phases in a
single global effort rule. The current first run asks a smaller question:
does the isolated body/resource policy reach t640 alive, with fresh authority,
no Bomb, and a usable position/Power state? The resulting physical entry will
seed stateful offline work for the t640 aimed stream.

## Physical promotion of the first phase

The ordinary-RNG default fail-close run at checkpoint `fd84165` reached the
deliberate boundary exactly. It completed setup and the entire t128 sub0/sub1
body/resource stream, then stopped alive at f641/t641 with
`phase-unavailable` for `timeline:t640:subs2-3-aimed-stream`. There was no HIT,
Bomb, or earlier Hard-authority loss. The boundary retained all 18 Hard-safe
actions and a certified five-frame held action.

The physical entry is `(192,384)` with Power 2, no current bullets, twelve
ordinary enemies and the newly spawned t640 sub2 emitter. The route made only
three input transitions. Across 528 non-lease route decisions, solve time was
1.884 ms median, 4.307 ms p90, and 7.051 ms maximum. This promotes the first
phase only; it does not validate the t640 aimed stream.

The next experiment starts from this captured entry and advances the complete
candidate-conditioned battle world through t640--t1219. It must compare small
phase-local policies across source-valid RNG/action warmups, including the
sub2 local-t70 aimed shots and player damage/kill state. The t1220
random-coordinate insertion remains the next explicit uncovered boundary.
