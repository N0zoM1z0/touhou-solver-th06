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

The first replay initially could not make that claim: the offline combat
world supported only Reimu-A's full-Power rank-9 shot table, while this entry
has Power 2. The smallest source fix compiled authoritative rank 1 (Power
0--7): one straight main shot every five fire-timer ticks, speed 12 and damage
48. Intermediate ranks remain fail-closed until physically reached.

After that addition, the captured f386--f641 window matched all 255 adjacent
player-attack, enemy-combat, player-shot, RNG, graze, rank, item, and Power
transitions. All 49 newborn rank-1 shots and 1,800 retained shot steps matched;
23 enemy birth/removal transitions were exact and unsupported combat steps
fell from 255 to zero. This validates the low-Power causal root used by the
t640 offline sweep; it is not evidence for uncompiled power ranks.

## t640 aimed-stream candidate

From the exact f641 root, a 192-frame delivery sweep found h4/h6/h8 identical
through the first part of the phase: all 16 seeds survived. The complete
578-frame sweep to t1219 separated them. h4 stopped on all eight seeds after
329.75 mean frames; targeted h6, h7, and h8 survived all eight. h8 had 5.16
mean minimum clearance versus h7's 4.45 and h6's 2.55, while h7 saved less
than one mean command. The selected continuation rung is therefore h8.

On that complete root, target-free h8 also survived 8/8 while reducing mean
commands from 224.13 to 53.38 and increasing mean minimum clearance from 5.16
to 7.97. A second corpus derived 30 complete worlds by 8,151 varied Hard-safe
warmup updates and 1,062 source births. It covered 13 enemy-combat, 30
player-attack, and 13 RNG states. Both policies survived all 32 delivery
cases for 96 frames; target-free used 11.84 mean commands versus 24.19. Its
worst minimum clearance was also higher, although the targeted policy's mean
clearance was inflated by several quiet roots.

The next physical falsifier therefore covers only t640--t1219 with target-free
policy-volume h8. A private state boundary at t1080 names the compressed
sub2 tail whose t1080/t1100/t1110 parents fire at t1150/t1170/t1180. The
algorithm is unchanged across that boundary. Random-coordinate insertion at
t1220 remains explicit `phase-unavailable`.

The ordinary-RNG default fail-close run physically promoted this phase. It
completed every t640 sub2 aimed fan and the compressed tail without HIT,
Bomb, or Hard-authority loss, then stopped exactly at the deliberate
f1220/t1220 random-insertion boundary. The boundary retained all 18 Hard-safe
actions at `(174.444,242.929)`, Power 2, with 80 live bullets.

There was one stale retry at f1034 and no publication failure. Across 511
fresh phase decisions, h8 solve time was 4.943 ms median, 10.251 ms p90, and
22.474 ms maximum. The compressed tail was the more expensive state at 6.480
ms median and 15.102 ms p90. Its occasional over-frame calls remained
publishable in this run, but should be kept in later timing comparisons.

Adjacent replay of the final 241 physical transitions matched every player,
combat, player-shot, RNG, graze/rank, item/Power, and enemy transition. It
also matched all 9,691 fired-bullet and 774 spawning-bullet steps, including
72 births, with no unsupported transition or positional error. This promotes
target-free h8 only for t640--t1219.

## t1220 random-body candidate

The physical entry still carries 80 bullets from the aimed stream, but the
newly inserted sub0/sub1 routines have no Hard bullet instruction. On an
exact 379-frame sweep to t1599, bottom-target h4, h6, and h8 were identical
for every one of eight delivery seeds: all survived, used 134 mean commands,
and had 14.85 mean minimum clearance. Deeper continuation therefore adds no
phase information.

Target-free h4 also survived 8/8, but reduced mean minimum clearance to 4.73,
including one 0.62 case, and changed the first action from `down` to `left`.
The target is useful here: it returns the high t1220 entry toward the lower
route while the inherited bullets expire. The smallest falsifier is thus
`target-only` h4 from t1220 through t1599, with a private tail state after the
last random parent at t1400. The t1600 sub0 body/resource formation remains
explicitly uncovered.

The ordinary-RNG default fail-close run physically promoted this phase. It
completed both the random-insertion state and its quiet tail without HIT,
Bomb, or Hard-authority loss, then stopped exactly at f1600/t1600 with
`phase-unavailable` for the next source formation. The boundary retained all
18 Hard-safe actions and a five-frame certified held input at
`(197.331,379.355)`, with Power 3 and one expiring bullet.

All 325 phase decisions were fresh: there were no stale publications or
timeouts. Solve time was 3.382 ms median/4.838 ms p90/6.166 ms maximum during
`random-insertion`, and 1.481/3.248/4.444 ms in the tail. Adjacent replay of
the final 255 physical transitions matched every player, player-shot, enemy,
RNG, graze/rank, item, and Power transition. It also matched all 3,289
retained hostile-bullet steps and 1,765 player-shot steps, with no unsupported
transition. The next offline root is therefore the exact f1600 entry; it must
evaluate only the t1600--t2007 sub0 body/resource formation before the t2008
midboss transition.

## t1600 mirrored-body candidate

The installed t1600 section contains 28 sub0 parents in two mirrored
formations through t1808. Every parent has life 300 and item 3; sub0's only
bullet instruction is not enabled on Hard. The phase still uses the complete
battle world because player damage, enemy retirement, item collection, and
Power determine the midboss entry.

On the exact f1600 Power-3 root, bottom-target policy-volume h4, h6, and h8
were identical across all eight delivery seeds for the complete 407 frames to
t2007. Every case survived, used 162.88 mean commands, and retained 151.47
mean minimum clearance; all horizons chose `left` first. Deeper continuation
therefore adds no phase information. Target-free h4 also survived 8/8 with
nearly identical clearance and fewer commands, but chose `up` on every seed.
The historical Stage 1 physical clear's ranker explicitly preferred
`(192,380)`, so its useful route-position lesson agrees with the current
resource/midboss objective without restoring its global bullet-count scene
classifier.

The smallest physical falsifier is thus bottom-target `target-only` h4. Its
private `mirrored-formations` state ends after the last t1808 parent and a
`tail` state carries only to t2007. The t2008 sub8 midboss remains uncovered;
once its ECL sets the boss state, stable boss source identity must take
precedence over the timeline label.
