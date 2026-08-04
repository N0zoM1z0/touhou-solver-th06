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
