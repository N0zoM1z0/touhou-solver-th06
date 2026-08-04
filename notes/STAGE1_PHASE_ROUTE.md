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

The ordinary-RNG default fail-close run physically promoted the phase. It
completed both states without HIT, Bomb, timeout, or Hard-authority loss and
stopped exactly at f2008/t2008 with `phase-unavailable`. The source sub8 slot
had not executed yet at this boundary, so the stop correctly retained the
timeline entry identity rather than inventing a boss identity. The player was
at `(192.887,382.225)` with Power 6, no bullets, and all 18 Hard-safe actions.
All 350 phase decisions were fresh. `mirrored-formations` measured 3.072 ms
median/5.185 ms p90/14.305 ms maximum; the tail measured
0.618/2.998/4.665 ms.

Adjacent replay initially matched 254/255 rank transitions despite exact
player, enemy, shot, RNG, item, and Power state. The differing f1920--f1921
transition exposed a missing authoritative rule rather than a route failure:
`RunEclTimeline` adds 100 subrank whenever its ticked timer is divisible by
`2400 - livesRemaining * 240`. With two lives the interval is 1920. The
battle world now carries the live remaining-life count and timer-previous
value and applies that transition before timeline/ECL work. The same retained
window now matches all 255 combat/rank transitions, 2,091 player-shot steps,
and all 24 enemy transition frames with no unsupported state. The next phase
must author only the t2008 insertion bridge and then identify sub8 from its
source ECL state.

## t2008 midboss insertion candidate

The physical f2008 snapshot is still immediately before the timeline spawn:
it has no boss slot, although the decoded source manifest already marks sub8
as a boss-producing routine. Installed sub8 performs `BOSSSET`, death callback
sub6, Hard/Lunatic life threshold 500 to sub9, and timer threshold 1440 to
sub7 at local t0. It moves from `(192,-32)` toward the playfield, enables
damage and collision at local t60, and emits its first Hard attack at local
t160: a player-aimed 16-by-5 circle with speeds 2.0 through 1.2. Later aimed
circles occur at local t414/t444 and t738/t768 around source-defined movement
segments.

Those are separate boss policy states and are not authored by inference. The
next falsifier covers only source t2008 with bottom-target h4 and a one-frame
commitment. Common Hard already projects the source boss body across that
transition. At the following snapshot the route must either expose stable
`boss:0:sub8:life_cb9:timer_cb7:nonspell` identity or fail visibly as
`timeline:t2009:sub8-midboss-missing`; it must not continue on an anonymous
timeline policy.

The ordinary-RNG default fail-close run validated the handoff. At f2008 the
already published `down` command still had a fresh one-frame Hard certificate,
so the input-lease path crossed the insertion rather than evaluating the route
proposal. At f2009 the source slot appeared with life 6000 and the exact stable
identity `boss:0:sub8:life_cb9:timer_cb7:nonspell`; the route then stopped with
all 18 Hard-safe actions, no HIT, Bomb, or prior authority loss. The captured
entry is `(192.343,382.569)`, Power 5, no bullets. The transition therefore
promotes timeline-to-boss identity publication, while the target-only bridge
remains only offline-certified for runs whose input lease expires at f2008.

Adjacent battle replay found the newborn life, position, ECL time, callbacks,
and RNG exact, but initially set `has_been_in_bounds` one call too early and
also advanced the boss timer twice. `SpawnEnemy` calls time-zero `RunEcl`
inline before the manager slot loop; that call advances ECL but performs no
movement, bounds test, callbacks, body/damage pass, or boss-timer tick. The
future world now models that source call separately from the ordinary
same-frame slot update. A focused source regression checks an offscreen
time-zero boss move: ECL time becomes 2, boss timer 1, and the bounds flag
remains false. The retained f2008--f2009 transition and all 255 adjacent enemy
steps now match exactly with no unsupported combat state.

The first exact f2009 entry sweep then failed closed at physical-equivalent
f2092 rather than fabricating a boss result. Six retained items remain live at
the entry; Power items are collected at f2015, f2058, and f2092, raising Power
5 to 8. That crosses from Reimu-A source shot rank 1 into the previously
uncompiled rank 2 table. Authoritative rank 2 contains the existing straight
48-damage main shot every five fire ticks plus two 14-damage homing orb shots
at fire phase zero every 30 ticks, launched at -120 and -60 degrees. Only this
rank is now compiled; ranks 3--8 remain fail closed. The next physical entry
run must parity-check rank-2 shot births and motion before the boss-entry
policy is promoted.

With rank 2 present, the exact f2009 sweep reached local t160 on every one of
eight delivery seeds. Bottom-target policy-volume h4, h6, and h8 were exactly
identical for the 158-frame entry: all survived with 63.5 mean commands and
no deeper-horizon win. Target-free h4 also survived, but used only two mean
commands because it kept the initial `up` proposal instead of returning to the
bottom route. That is undesirable immediately before a player-aimed circle,
even though this bullet-free prefix cannot distinguish it by clearance.

The authored sub8 policy therefore covers only `ecl_time < 160` with
bottom-target h4 and source state `entry-movement`. At ecl time 160 it returns
`phase-unavailable` under the same stable boss identity, before executing the
first Hard circle. The next ordinary-RNG run must reach that boundary alive
and provide physical parity for the Power-8 rank-2 shots created on the way.

That ordinary-RNG default fail-close run physically promoted the entry state.
It reached f2167 with sub8 at exact local ECL t160, then stopped alive as
`phase-unavailable` before publishing an action into the first unauthored
circle. There was no HIT, Bomb, timeout, stale publication, or earlier Hard
authority loss. The boundary retained all 18 Hard-safe actions and a
five-frame held certificate at `(194.603,379.740)`, Power 9, with no hostile
bullets and one boss slot.

The 155 fresh `entry-movement` decisions measured 0.945 ms median, 1.098 ms
p90, and 1.246 ms maximum. The retained physical window included five Power
transitions from 4 through 9 and therefore exercised the newly compiled rank-2
straight and homing shots. Adjacent replay matched all 254 player-attack,
enemy-combat, RNG, graze/rank, pending-effect, item, and Power transitions,
all 1,886 player-shot steps, all 56 shot births, and all five enemy transition
frames, with no unsupported combat world step. The next offline root is the
exact local-t160 boundary; it must model the player-conditioned 16-by-5 circle
and stop again before the later local-t414 attack state unless physical/source
evidence justifies a smaller boundary.

## sub8 first-circle candidate

The exact local-t160 root can execute the Hard opcode-69 transition without
unsupported state. A complete 254-update sweep stops on local t414 before the
next attack instruction. Target-free h4, h6, and h8 all survived all eight
delivery seeds. h8 used 50.75 mean commands with 8.32 mean minimum clearance;
h6 used 55.00 with 7.08. h4 happened to preserve the incoming `right` lease
with no new command and 31.80 clearance, but that result aliased every delivery
seed to the same streaming path.

A higher-pressure corpus therefore derived 32 complete battle worlds by 1,072
varied Hard-safe updates from the physical root. It exercised 2,560 source
births, seven enemy-combat states, 32 player-attack states, and seven RNG
states while staying before local t414. On 96-frame delivery tests, h4 retained
31/32 worlds and lost one to lease authority. Target-free h6 and h8 both
retained 32/32; h8 had 9.23 mean minimum clearance versus h6's 7.37, at 9.78
versus 9.53 mean commands. The targeted variants generated substantially more
commands, and targeted h6 had already lost three exact-root delivery seeds.

The smallest physical falsifier is therefore target-free policy-volume h8 for
`160 <= ecl_time < 414`, named `first-circle-movement`. This is a state-local
algorithm selection, not a stage/frame condition in common Hard: aim, player
attack, enemy damage, movement, RNG, and bullet births remain candidate-
conditioned source transitions. At local t414 the same stable boss phase
returns `phase-unavailable` before the second aimed circle.

The ordinary-RNG default fail-close run physically promoted this state. It
completed the first circle and source movement without HIT, Bomb, stale
publication, timeout, or earlier Hard-authority loss, then stopped exactly at
f2421/local t414 before the next opcode-69 instruction. The boundary retained
all 18 Hard-safe actions and a five-frame held certificate at
`(197.029,259.456)`, Power 9, with 64 live bullets; the boss remained in sub8
with life 4140.

All 214 fresh h8 decisions published. Solve time was 3.789 ms median, 4.437 ms
p90, and 12.525 ms maximum. Adjacent replay of the complete 255-transition
window matched all player, player-attack, enemy-combat, RNG, graze/rank, item,
and Power transitions. It matched 17,075 fired-bullet steps, 3,980 spawning
steps, 180 births, 116 removals, 2,623 player-shot steps, six graze transitions,
and all 43 boss life-change frames with no unsupported world state or position
error. The next root is therefore exact local t414; the t414/t444 aimed
attacks must be evaluated as their own source state before any later t738/t768
state is exposed.

## sub8 paired-circle candidate

Installed sub8 executes another Hard aimed circle at local t414 and a second
one at t444, then begins a source movement segment at t526. The next attack
pair does not begin until t738/t768. The exact local-t414 root therefore uses
t738 as its next attack boundary, while stable ECL identity still takes
priority if the life callback enters sub9 earlier.

On the complete 324-update exact-root sweep, target-free h4, h6, and h8 all
survived all eight delivery seeds and chose `down` first. h4 again aliased the
incoming lease and retained only 1.78 mean minimum clearance. h6 and h8 used
47.38 and 60.00 mean commands with 4.27 and 4.81 clearance respectively.

The higher-pressure corpus retained 29 complete battle worlds after 1,000
varied Hard-safe warmup updates; three derivations stopped on authority. It
exercised 3,920 source births, five enemy-combat states, 29 player-attack
states, and ten RNG states. Across 31 viable 128-frame delivery cases, h4
survived 27, while h6 and h8 survived all 31. h8 raised mean minimum clearance
from h6's 5.44 to 7.77 at 21.42 versus 20.58 mean commands. The authored
`paired-circles-movement` state therefore uses target-free policy-volume h8
for `414 <= ecl_time < 738`; local t738 remains explicit `phase-unavailable`.

The ordinary-RNG default fail-close run physically promoted this state. It
completed both aimed circles and the t526 movement without HIT, Bomb, stale
publication, timeout, or earlier authority loss, then stopped exactly at
f2745/local t738 before the next attack. The boundary retained all 18
Hard-safe actions and a five-frame held certificate at `(188.551,225.213)`,
Power 9, with 41 live bullets. The life callback had not fired; sub8 remained
stable at life 2364.

All 272 h8 decisions were fresh, measuring 3.918 ms median, 5.643 ms p90, and
8.061 ms maximum. Adjacent replay matched all 255 player/combat/RNG/rank/item/
Power transitions, 19,062 fired-bullet steps, 1,800 spawning steps, 120
births, 222 removals, 2,135 player-shot steps, 16 graze transitions, and all
42 boss life-change frames with no unsupported state or position error. The
next exact root begins before the local-t738/t768 attacks; life-callback
reachability is now a near-term causal boundary rather than a hypothetical
later concern.

## sub8 late-circle loop candidate

Installed sub8 fires the final pair of the control cycle at local t738/t768.
At t840 it performs a source jump back to local t192, so ECL time rewinds and
the already authored h8 movement/circle states repeat over the complete live
bullet world. The next distinct stable phase is therefore the life callback
into sub9, not an invented timeline boundary at t840.

On the exact 299-update pre-callback window, target-free h4/h6/h8 survived all
eight delivery seeds. h4 again aliased its lease and fell to 0.59 mean minimum
clearance. h8 improved h6 from 3.68 to 6.90 clearance while also reducing mean
commands from 88.25 to 87.13. A direct bounded callback probe then ran h8 until
the stable subroutine changed: all eight branches survived, crossed the t840
rewind at physical-equivalent f2848/local t193, and entered sub9 after 299--362
updates. Candidate-conditioned damage changed the callback frame, while every
branch entered at exact life 500; minimum clearance ranged from 5.03 to 8.71.

The high-pressure corpus retained 31 complete worlds after 1,070 Hard-safe
warmup updates and 4,000 source births, spanning five enemy-combat, 31 player-
attack, and eight RNG states. Across 32 viable 128-frame cases h4 survived 29,
while h6/h8 survived all 32. h8 raised mean minimum clearance from 4.62 to
6.85 for only 0.13 additional mean commands. The route now authors only
`738 <= ecl_time <= 840` as target-free h8 `late-circles-loop`; the t840
update naturally returns to `first-circle-movement`, and sub9 remains explicit
`phase-unavailable`.

The ordinary-RNG default fail-close run physically promoted the complete
control loop. It crossed t840, repeated the h8 source states over accumulated
bullets, and stopped alive exactly when stable identity changed at f3044 to
`boss:0:sub9:life_cb9:timer_cb6:spell`. This is the earliest callback frame
predicted by the eight offline delivery branches. There was no HIT, Bomb,
stale publication, timeout, or earlier authority loss.

The sub9 boundary retained all 18 Hard-safe actions at `(192.260,208.083)`,
Power 9. Spell start had source-cancelled the old bullets; the boss was at
exact life 500, its life threshold was cleared to -1, its timer callback was
sub6 at 1320, and ECL/boss timers were both 2. All 237 post-t738 h8 decisions
were fresh at 3.976 ms median, 5.699 ms p90, and 7.655 ms maximum.

Adjacent replay matched all 254 player/combat/RNG/rank/item/Power transitions,
21,519 fired-bullet steps, 3,020 spawning steps, 100 births, 197 removals,
2,342 player-shot steps, 11 graze transitions, and all 45 boss life-change
frames. The next phase is now the exact sub9 spell entry, not an estimated
future callback.

## sub9 spell-entry candidate

Installed sub9 starts the spell at local t0, cancels the old bullets, disables
damage, installs timer callback sub6 at 1320, and moves the boss for 120 ticks.
At local t120 it re-enables damage, configures the Hard 42-way pattern and
delayed interval, and creates two source lasers. The bullet/laser transition
is therefore excluded from the entry policy rather than approximated.

From the exact f3044/local-t2 root, bottom-target h4/h6/h8 all survived all
eight complete 118-update delivery seeds. h4 required no new command, while
h6/h8 each used eleven mean commands; all remained hazard-free before t120.
Target-free h4 was exactly identical, but the bottom target preserves the
intended low spell entry without changing Hard eligibility. Only stable sub9
with spell publication and `ecl_time < 120` is now authored as target-only h4
`spell-entry`. A missing spell flag or local t120 remains fail-visible.

The ordinary-RNG default fail-close run physically promoted this entry. Its
candidate-conditioned damage delayed the sub8 life callback until f3313,
demonstrating that the policy is keyed by stable sub9/ECL state rather than an
expected game frame. It then completed the full protected movement and
stopped exactly at f3433/local t120, before executing the first pattern or
laser instruction. There was no HIT, Bomb, stale publication, timeout, or
earlier authority loss. The boundary retained all 18 Hard-safe actions at
`(191.799,382.049)`, Power 9, with no hostile bullets or lasers; the boss
remained damage-disabled at life 500 with timer callback sub6/1320.

All 112 `spell-entry` decisions were fresh at 0.958 ms median, 1.433 ms p90,
and 2.345 ms maximum. Adjacent replay initially matched every player, enemy,
shot, hostile-bullet, RNG, rank, pending-effect, and Power transition but
exposed one source-semantic omission at the f3313 callback. Opcode 93 calls
`TurnAllBulletsIntoPoints`: it traversed 89 live bullet slots in order,
allocated point-item slots 19 through 107, then `ItemManager::OnUpdate`
immediately collected the two newborns overlapping the player. The nominal
battle world now performs that exact cancellation/allocation/update sequence,
sets the spell-damage state in the same update, and leaves Hard forecasting's
conservative bullet retention unchanged. A same-frame bullet birth whose
ordering relative to opcode 93 is not represented still fails closed.

The corrected retained window matches all 252/252 adjacent combat, item,
Power, and RNG transitions, including 87 live item births and 85 later item
removals; all 9,900 fired-bullet, 1,704 spawning-bullet, and 2,446 player-shot
steps are exact. The physical transition is minimized as independent corpus
case `stage1-f3313-spell-start-point-conversion`. The next exact root is
f3433/local t120. The next experiment must expose the Hard 42-way delayed
pattern and both source lasers only over the smallest adjacent source window,
then validate their birth, slot allocation, timers, and motion against
physical frames before authoring any larger spell state.

## sub9 laser/pattern-start candidate

The exact f3433/local-t120 root resolves the Hard-only opcode-69 instruction
as a 42-by-1 player-aimed circle at speed 2.5, then enables a delayed interval
whose rank-adjusted period is 38. The physical RNG state selects initial timer
36, so no bullet is born on t120 itself; the first 42 slots are allocated on
the third update. The same t120 instruction group allocates fixed-angle laser
slots 0 and 1 at angles approximately 0.393 and 2.749, each with start time
30, hitbox start time 30, duration 120, despawn duration 16, width 32, and
source hitbox end delay 14.

Exact one-frame stepping preserves the seven ECL/RNG draws and produces both
laser slots at timer 1. A complete 30-update constant diagnostic reaches
local t150 with 42 fired bullets at timer 13 and both lasers still in state 0
at timer 30. The t150/t151 sound, loop initialization, and opposed opcode-88
laser rotations have not executed and remain a distinct source boundary.

On eight delivery seeds from the exact physical root, bottom-target
policy-volume h4/h6/h8 all survived 30/30 updates and were identical: 11.875
mean commands, 12.125 decisions, and no deeper-horizon win. The route
therefore authors only `120 <= ecl_time < 150` as target-only h4 state
`laser-pattern-start`. This is the smallest physical falsifier for bullet
birth, laser allocation, delayed RNG, and the first 30 laser timer updates;
it does not claim that the later rotating laser geometry is solved.

The ordinary-RNG default fail-close run physically promoted this state. It
stopped exactly at f3500/local t150 with `phase-unavailable`, before the
t150/t151 rotation-loop instructions. There was no HIT, Bomb, stale
publication, timeout, or earlier authority loss. The boundary retained all 18
Hard-safe actions at `(194.846,379.581)`, Power 9, with 42 bullets and exactly
two lasers. Both lasers occupy source slots 0/1, remain in state 0 at timer
30, preserve angles 0.393/2.749 and end offset 500, and retain hitbox end delay
14. The delayed interval is 38 with timer 28; the boss is damageable at life
460 and local boss timer 150.

All 27 fresh policy queries measured 1.181 ms median, 2.428 ms p90, and
3.070 ms maximum. Adjacent replay matched all 252 player/combat/RNG/rank/item/
Power transitions, 9,388 fired-bullet steps, 2,334 spawning steps, 138 births,
166 removals, and 2,652 player-shot steps. It also matched both source laser
births and all 58 retained laser transitions with zero geometry/timer error.
The next exact root is local t150; opcode 88's opposed angle mutations and the
state-0-to-state-1 laser transition must be audited and physically validated
before extending the spell policy.

## sub9 rotating-laser candidate

At local t150 the source sets integer register 4 to 120. Local t151 applies
opcode 88 to laser slots 0/1 with opposed angular deltas of approximately
`+0.008267/-0.008267`, decrements the register, and jumps the ECL clock back
to t150 while the value remains positive. The published clock therefore stays
at t151 for 120 physical updates; the register is the source loop state, and
no game-frame identity is needed. The first t150 update also advances both
lasers from source state 0/timer 30 to state 1/timer 1. When the register
reaches zero, ECL advances to t152, both lasers enter state 2, and they retire
through their 16-update despawn before the clock reaches the next instruction
at t211.

The complete exact-root 180-update sweep to local t211 sharply rejects h4:
only 3/8 targeted h4 delivery seeds survived, while targeted h6/h8 survived
8/8. Removing the bottom target kept h6/h8 at 8/8 but reduced mean commands
from about 70 to 9.25/9.38 and raised mean minimum clearance to 7.71/9.95.

The higher-pressure corpus derived 27 complete worlds through 2,082 varied
Hard-safe warmup updates and 2,562 source births, spanning 20 enemy-combat,
27 player-attack, and 19 RNG states. Across 32 measured 96-update delivery
cases, target-free h6 and h8 each survived 30. Each won one differing seed
and both lost one; h6 retained slightly more aggregate frames and used 6.16
mean commands versus 7.25, while h8 clearance was 11.45 versus 9.82. There is
no causal survival evidence for paying h8's extra online cost, so the smallest
physical falsifier is target-free policy-volume h6.

The route records the repeating `150 <= ecl_time < 152` source state as
`rotating-laser-loop` and the `152 <= ecl_time < 211` post-loop state as
`laser-retirement-tail`. Both use the same measured h6 primitive, while the
state names keep the rotation and retirement transitions independently
observable in the physical trace. Local t211 remains fail-visible before the
next boss movement instruction.

The ordinary-RNG default fail-close run physically promoted both states. Its
earlier candidate-conditioned sub8 callback shifted the absolute boundary to
f3490, but source dispatch still completed the register-controlled t151 loop,
entered `laser-retirement-tail` at t152, and stopped exactly at local t211
before the next opcode-50 movement instruction. There was no HIT, Bomb, stale
publication, timeout, or earlier authority loss. The boundary retained all 18
Hard-safe actions at `(223.657,381.480)`, Power 8, with 112 bullets, no lasers,
boss life 256, and interval 38/timer 7.

The rotating state published 118 fresh h6 decisions at 4.074 ms median,
4.944 ms p90, and 6.236 ms maximum. The retirement tail published 58 fresh
decisions at 3.029/4.884/14.496 ms; neither state produced a stale retry or
timeout. Adjacent replay matched all 254 combat/RNG/rank/item/Power
transitions, 12,650 fired-bullet steps, 3,444 spawning steps, 252 births, 140
removals, and 3,448 player-shot steps.

The first parity report marked 236 retained-laser pairs as externally mutated
by ECL and intentionally skipped them in its manager-only check. Promotion was
held until the harness used the complete same-frame combat prediction to
validate the preceding ECL mutation and later BulletManager update together.
The corrected report matches all 326/326 retained laser transitions, including
all 236 opposed angle mutations, plus both source-defined laser removals, with
zero geometry/timer error. The next exact root is local t211.

## sub9 random-movement candidate

Installed sub9 executes three instructions at local t211: random movement in
the active source bounds, speed 2.0, then a 120-tick decelerating movement.
The delayed aimed-circle interval continues throughout. At local t331 a source
jump rewinds the spell to t120, recreating the pattern/laser cycle; that jump
is excluded from this candidate so a new physical boundary can validate it
independently. The boss has life 256 on the exact root, but the first complete
movement cycle remains sub9 under every tested candidate branch; spell-end
semantics are therefore not needed to claim this bounded state.

Target-free h6/h8 both survived all eight complete 120-update exact-root
delivery seeds. h6 used fewer commands and retained 2.43--7.00 minimum
clearance across the seeds; h8 spent more commands for 4.56--8.54 clearance.
A higher-pressure corpus derived 32 complete worlds through 1,072 Hard-safe
warmup updates and 756 births, spanning 17 enemy-combat, 32 player-attack, and
17 RNG states. Across 32 measured 56-update cases, h6/h8 both survived 32/32
with no deeper win. h6 used 4.63 mean commands versus 5.88; h8 raised mean
clearance from 7.42 to 8.69 without changing survival.

The smallest falsifier is therefore target-free policy-volume h6 for
`211 <= ecl_time < 331`, state `random-movement`. Local t331 remains explicit
`phase-unavailable` before the rewind into the already authored t120 cycle.

The first ordinary-RNG promotion attempt exposed a sensor counterexample
before it could test this state. At f3063 a sub8 life callback crossed while a
single large native pool copy was in progress: its early EnemyManager bytes
showed installed sub9 at local t0 before opcode 93, while its later bullet/item
bytes already reflected the completed spell-start update. The source executes
`HandleLifeCallback` and then `RunEcl` in the same EnemyManager pass, so this
was a torn same-game-frame root rather than a new nonspell phase. A leading
BulletManager timer witness now must match the timer copied at the pool tail;
otherwise the whole snapshot is retried. No route condition was added for the
transient state.

The rerun physically promoted `random-movement`. It crossed the callback as a
complete `sub9/.../spell` snapshot, traversed the already promoted spell
states, and stopped alive exactly at f3822/local t331 before opcode 2 rewinds
the source clock. There was no HIT, Bomb, stale authority stop, timeout, or
earlier fail-close. The boundary retained all 18 Hard-safe actions at
`(236.052,379.228)`, Power 7, with 70 bullets, no laser, and boss life 308 at
`(304.316,53.748)`. The preceding frame was exact local t330.

All 119 fresh movement decisions measured 3.078 ms median, 4.747 ms p90, and
6.154 ms maximum. The retained 255 adjacent pairs match every player,
combat-enemy, player-shot, RNG, graze, rank, pending-effect, item, and Power
transition. They also match all 19,453 fired-bullet steps, 4,242 spawning
steps, 252 births, 263 removals, 2,132 player-shot steps, all 182 retained
laser transitions (152 with ECL mutation), and both source laser removals with
zero error. The next exact root is local t331; only its rewind/update into the
already authored local-t120 state should be exposed next.

## sub9 cycle-rewind candidate

At exact local t331, opcode 2 jumps the ECL context to local t120. The source
interpreter continues within the same update, so the Hard-only 42-way pattern
configuration, delayed interval, and two fixed-angle laser allocations are
recreated before the next published snapshot. This is one source-clock state,
not a new movement policy; the following `<150` state is already the promoted
`laser-pattern-start` implementation.

An exact f3822 battle-world sweep compared target-free h4/h6 across eight
four-update delivery branches. Both survived 8/8, selected the same first
action, issued no additional command over the short window, and retained
27.43 minimum clearance. There is no measured benefit to carrying the h6
movement cost across this one-update transition. Only `ecl_time == 331` is
therefore authored as target-free h4 `cycle-rewind` with a one-frame
commitment. Any observed clock above 331 remains explicit `phase-unavailable`.

Physical promotion must include the adjacent t331-to-t120 rewind in retained
history and match opcode-2 dispatch, interval/RNG state, new laser slots and
timers, bullets, combat, and player state before this transition is considered
closed. Later spell-end entry remains independently uncovered.

The ordinary-RNG run physically promoted `cycle-rewind` and later stopped on
the independently uncovered sub6 death callback. The retained second rewind
is exact f4148/local t331 to f4149/local t121. It carries boss life 100 and
position `(238.549,144.000)` unchanged, advances boss timer 780 to 781, keeps
RNG generation 3996 unchanged, and changes the live world from 90 bullets/no
laser to 89 bullets plus source laser slots 0/1 at state 0/timer 1. The
existing interval remains 38 and advances timer 33 to 34; the rewind does not
invent a second initial-delay RNG draw.

Adjacent replay matches all 254 retained player/combat/RNG/rank/item/Power
pairs, 20,717 fired-bullet steps, 4,116 spawning steps, 294 births, 267
removals, and 2,822 player-shot steps. Both rewind laser births, all 182
retained laser transitions (116 with ECL mutation), and both later source
laser removals are exact with zero error. There was no HIT, Bomb, stale
authority stop, or timeout before the final sub6 fail-close. `cycle-rewind` is
therefore physically promoted; the exact new phase root is f4237/sub6 local
t0, installed by a post-RunEcl death callback with spell publication still
active.

## unresolved sub8 attack-tempo counterexample

A separate ordinary-RNG run never reached sub9: sub8 reached boss timer 1440
at f3448 with life 1248, then correctly entered timer-callback sub7 and
fail-closed. The retained window starts at f3192/local t537 with life 2496;
damage falls to zero at f3372/local t717 when the boss begins moving right
while the player stays near center. The terminal sub7 state is an effect, not
the cause: the route had already lost the life-callback race much earlier.

A first offline ablation kept the same h8 continuation evidence and used live
boss x only as a tie-break from source t526/t708/t738. It did not robustly
repair the race: across four delivery seeds the last sub8 life remained
1056--1488. Constant-action projections from the f3372 root likewise show why
simple chasing is insufficient: focused right survives 64 updates but only
deals 48 damage, while faster/right-diagonal approaches enter unsupported or
colliding branches. Source movement plus player-shot travel time requires a
phase-local future-damage objective or an earlier lead/preposition policy, not
a coordinate special case.

The next falsifier must capture a modern exact local-t160 root, before the
first damaging circle state, and run the full sub8 life/timer race offline.
Compare survival-equivalent policies using candidate-conditioned future boss
position and player-shot damage/kill timing. Hard eligibility and h8 survival
evidence must remain unchanged; only the soft route ranking may change.

The explicit diagnostic stop captured that root at f2167/local t160: player
`(191.473,383.983)`, Power 10, no hostile bullet/laser, ten live Reimu-A
shots, boss life 5916 at `(320,128)`, life callback 500/sub9, and timer
159/1440/sub7. The diagnostic branch was removed immediately and never became
route coverage.

The installed source movement records already expose the required lead target
without a scene table. While movement mode 2 is active, the destination is
`move_start_x + move_interp_x`; otherwise it is the live boss x. The sub8
sequence therefore yields its authored horizontal waypoints directly from the
captured ECL state. Player y is retained, so this proposal changes only
horizontal attack alignment inside actions already tied for strongest h8
continuation evidence.

From the exact t160 world, a 600-update probe showed why live-x chasing is the
wrong model: baseline boss life was 2478--2766, live-x was 2764--2860, while
source-destination alignment reached 2140--2236. The complete 1300-update
race was then run across eight delivery seeds. Baseline reached life-callback
sub9 on 7/8 and reproduced the physical timeout on seed 7, entering sub7 at
timer 1440 with life 526. Its successful callbacks took 862--1110 updates.
Source-destination alignment survived all eight and reached sub9 on 8/8 in
845--959 updates, with minimum clearance 1.247--5.155.

The route now applies this destination only as a tie-break inside the existing
h8 `first-circle-movement`, `paired-circles-movement`, and
`late-circles-loop` policies. Hard-4 eligibility, h8 continuation scores,
commitments, source physics, and every spell policy are unchanged. The next
ordinary-RNG physical run must show a sub9 life callback rather than sub7
timeout, with no HIT or publication regression, before this attack-tempo
repair is promoted.

The ordinary-RNG default fail-close run physically promoted the destination
tie-break. The first damaging state began at f2167 and the final sub8 policy
decision was f3011; a certified in-flight command remained safe at f3012, and
the next fresh root was complete sub9 spell state at f3013. Thus the life
callback won after about 845 physical updates, matching the fast edge of the
offline 845--959 window and leaving roughly 435 updates of timer margin. It
later stopped only at the expected uncovered f3499/sub6 death callback. There
was no HIT, Bomb, stale authority stop, timeout, or earlier fail-close.

The 687 fresh sub8 h8 decisions measured 3.523 ms median, 5.060 ms p90, and
7.916 ms maximum. The retained spell window matches all 255 adjacent player,
combat-enemy, player-shot, RNG, graze, rank, pending-effect, item, and Power
transitions; all 21,637 fired-bullet steps, 3,780 spawning steps, 3,244
player-shot steps, both laser births, all 180 laser transitions, and both
laser removals are exact. The f3499 boundary is alive at
`(178.402,374.108)`, Power 8, with 88 bullets and two lasers; sub6 is local t0
with boss life 0/interactable false and opcode 47 still pending. The attack-
tempo repair is now physically promoted.

## sub6 SpellEnd conversion candidate

The f3499 state is a complete source boundary, not a torn callback snapshot.
The preceding EnemyManager pass installed death-callback sub6 after RunEcl,
so local t0/opcode 47 remains pending while the globally published spell is
still active. On the following update sub6 executes opcode 47, opcode 94
`SPELLCARDEND`, sound/interval/drop/flag instructions, and leaves the next
instruction at local t40.

Authoritative `DespawnBullets(12800, 1)` differs materially from spell-start
`RemoveAllBullets(true)`. It iterates all 640 bullet slots and skips only
unused slots, awards a Point item for every occupied slot, and changes the
bullet to state 5 without clearing it or resetting its timer. For each live
laser below state 2 it allocates a separate item at the laser origin, then one
item at every 32-pixel offset starting at `startOffset`; with zero start offset
the origin is therefore allocated twice. It resets the laser to state 2/timer
0 and clears `hitboxEndDelay`. The same priority-11 BulletManager update first
runs ItemManager, then moves each state-5 bullet by half velocity and advances
the laser retirement state.

The exact offline f3499 transition predicts f3500/sub6 t1 with 88 state-5
bullets, both lasers at state 2/timer 1, and 127 live items in slots 113--239.
The item types are 122 Point, one Big Power, and four Small Power; the last
five are the source `DROPITEMS 5` and account for RNG generation 3764 to 3784.
All items receive their same-frame ItemManager update. No active hostile
bullet remains in the exact nominal world, while the common Hard world keeps
the old hazards conservatively during certification.

The route candidate opens only exact sub6/t0/spell-active, uses the ordinary
target-only Hard-4 proposal for one frame, and then exposes sub6/t1 as
uncovered. A focused source regression covers the conversion/allocation/half-
velocity ordering. The next default physical run must validate the entire
adjacent transition before this state is promoted. Later state-5 lifetime is
not modeled because the captured bullet record lacks the donut ANM VM.

## random-body residual-wave counterexample

The first physical attempt to reach the SpellEnd boundary instead stopped
alive at f1330 during source `t1220/random-insertion`. It had no HIT or Bomb.
The current random sub0/sub1 parents do not emit the threatening bullets; the
hazards are the still-live tail of the preceding aimed stream while the route
uses a bottom-center target-only proposal for the resource-body phase.

The terminal is not the cause. At f1325 and f1327 the physical world retained
17 Hard-safe actions. Around f1290--1328 the target tie-break repeatedly
selected alternating down/up diagonals near y=380. A stale `up_right` was
carried at f1329, and f1330 then had no ordinary Hard-4 set although seven
actions were repairable with the shorter delivery prefix. Adjacent replay is
exact for all 246 complete combat/RNG/item/Power transitions, 13,999 fired
bullet steps, 558 spawning steps, and 1,060 player-shot steps. This is a route
policy failure on a source-exact world, not missing hazard semantics.

Exact f1270 stateful replay for 80 updates gives the important ablation:

- h4 with the bottom target survives 6/8 delivery seeds;
- h4 target-free survives 0/8 and stops after 39--78 updates;
- h6 target-free survives 8/8, uses 15--19 commands, and keeps 5.013--9.264
  minimum clearance;
- h8 target-free also survives 8/8 but adds no survival evidence.

Thus neither “remove the target” nor “increase depth while retaining the
target” is the causal change. The smallest supported policy is target-free h6:
its continuation volume prevents an unconstrained upward flight, while the
absence of the waypoint prevents the later bottom oscillation.

A second workload derived 16 complete battle states from four physical roots
through 160 safe warmup updates. It covers 11 distinct enemy/RNG states and 16
player-attack states. Both policies survive the shorter 64-update screen, but
h6 uses 236 aggregate commands versus 259 and removes the old late-root
clearance collapse to 1.313. Only source t1220--1400 `random-insertion` is
changed; the t1401 tail remains target-only h4, and Hard-4 authority is
unchanged. The next ordinary-RNG default run is the physical falsifier.

The next ordinary-RNG run physically promoted the target-free h6 state. It
crossed the old f1330 boundary and completed all of source t1220--1400 without
HIT, Bomb, stale-decision retry, timeout, or authority loss. Its 133 fresh
policy decisions measured 7.265/13.998/17.508 ms median/p90/maximum. Every
fresh root retained at least 15 Hard actions and seven strongest h6 actions.
The unchanged t1401 tail then completed normally. The physical result matches
the offline prediction and does not require changing common Hard-4.

## physical SpellEnd promotion

The same run reached f3979/sub6 local t0 and executed the authored SpellEnd
transition. This RNG world had 105 active bullets rather than the earlier
candidate root's 88; both source lasers had already retired, and the item pool
was empty with next index 118. The following complete f3980 root is sub6 local
t1/op59 with the global spell inactive.

Exact nominal-versus-physical comparison matches all 105 state-5 slot IDs,
positions, velocities, and timers after their half-speed update. It also
matches all 110 live items in slots 118--227: 105 Point items plus the
DROPITEMS Big Power and four Small Power items, including every same-frame
position/velocity/type/timer. RNG seed/generation is exactly 2992/3956 from
32265/3936, Power remains 9, active bullets and lasers are empty, and ECL is
local t1/op59. The compact corpus retains two observed bullets and the five
physical random drops under stable synthetic ECL addresses.

The retained 253-pair report is exact for all combat enemy, player-shot, RNG,
rank, item and Power transitions; 19,515 fired-bullet steps; 4,242 spawning
steps; 2,523 player-shot steps; 322 laser transitions; and both removals. The
active SpellEnd source transition is therefore physically promoted. The
source/unit laser-origin and 32-pixel conversion branch remains unvalidated by
physical SpellEnd evidence because no laser was live at f3979.

## physical sub6 Power-tail promotion

The next ordinary-RNG default fail-close run entered sub6 at f3686/t0 with
Power 8 and 64 active bullets. The exact SpellEnd transition produced f3687/t1
with the 64 bullets nonlethal in state 5, 64 Point items, one Big Power, and
four Small Power items. The phase-local target continued to use ordinary
Hard-4 and selected its target only from the live item pool: Big Power first,
then the nearest Small Power.

The run remained alive with all 18 Hard actions throughout this tail. It
collected the Big Power at f3822, raising Power 8 to 16, then one Small Power
at f3823, reaching Power 17. The following physical attack update created the
authoritative Rank-3 paired 30-damage main shots; their slots, positions,
velocities, timers, and later steps match the newly compiled Rank-3 table.
Thus this static offline table has adjacent physical parity at the resource
transition that first needs it.

The installed sub6 ECL contains a t40 opcode-59 movement over 120 ticks toward
`(192,-64)` and a nominal opcode-1 termination at t160. Physical execution
does not reach the latter: after local t140, `EnemyManager::OnUpdate` moves
the already-in-bounds boss outside the source bounds before `RunEcl`, so the
source out-of-bounds rule despawns it at f3827. A 16-seed exact replay from
f3687 predicts Power 17 on 12 seeds and Power 16 on four at local t140; after
the removal update all 16 have Power 17. The physical Power 17 result matches
that robust phase prediction rather than the earlier 159-frame diagnostic
from a different root.

Across the retained 255 adjacent pairs, player motion is exact; all 8,169
fired-bullet and 1,890 spawning-bullet steps are exact; all 2,502 player-shot
steps and 67 births are exact; and all 244 supported item, Power, RNG, graze,
rank, and pending-effect transitions are exact. Eleven combat worlds are
explicitly unsupported because unrelated post-midboss enemy-slot births are
not reproduced, beginning at f3698; they are not silently counted as parity.
The run stopped safely after boss removal at f3827 with three ordinary
post-midboss emitters already live. This exposes the next missing route as the
post-midboss timeline at physical t3827, not the old synthetic
`timeline:t2009:sub8-midboss-missing` label.

## post-midboss aimed-stream candidate

The installed timeline continues throughout the midboss. Its next combat
section is not keyed to the boss callback: source t2408--4298 inserts 64
alternating sub2/sub3 parents every 30 ticks. The physical f3827 root appears
after the boss exits, with three such parents already live and the next source
insertion at t3848. Sub2 emits the difficulty-selected immediate Hard aimed
fans at local t70; sub3 emits its Hard aimed fan at the same local clock. The
last t4298 child therefore still contributes a residual attack after the last
timeline insertion. The next distinct source formation starts at t4498.

An exact native full-section screen starts at f3827 and runs 671 updates to
t4498, retaining timeline births, candidate-conditioned aim, Reimu-A Rank-3
shots, enemy damage/retirement, RNG, items, Power, and delivery delay. H4, h6,
and h8 all survive 8/8. H4 has 2.254 mean minimum clearance and reaches 0.839;
h6 has 3.587 mean and reaches 1.608; h8 has 5.709 mean and never falls below
3.463. Mean command counts are 141.75, 114.125, and 123.5 respectively.

A second screen derives seven complete worlds from 12 Hard-safe exploration
attempts through 1,520 total warmup updates and 558 source births. These worlds
contain seven distinct enemy-combat, player-attack, and RNG states. H6 and h8
both survive 12/12 96-update delivery cases; h8 has 11.038 mean clearance
versus 9.258, while h6 uses 11.33 mean commands versus 15.58. Neither dominates
every individual world. The full-section worst-case margin selects target-free
h8 as the smallest physical candidate with the stronger measured tail reserve;
this is a phase-local falsifier, not a universal horizon claim. Coverage ends
before t4498 so the following resource formation remains explicit.

The next ordinary-RNG physical run did not exercise this candidate. Its
midboss survived until after timeline t4498, so boss-owned policy remained
active throughout the entire t2408--4298 insertion section. It safely stopped
at f4637 only after sub6 removed the boss, with the timeline already inside the
next resource section. The h8 post-midboss policy therefore remains an offline
candidate for earlier-boss-removal worlds; it is not physically promoted by
that run.

A later ordinary-RNG default fail-close run exercised the previously shadowed
world. The boss retired before f4005, after which target-free h8 published 391
fresh decisions through f4497/t4497. Power rose from 9 to 11 while this policy
was active. The run crossed the residual aimed stream alive and entered the
distinct t4498 resource phase without HIT, Bomb, authority loss, or timeout.
The h8 post-midboss policy is therefore physically promoted for the no-boss
world in which it is selected; the later-boss interleaving continues to use
the independently promoted boss route.

## post-midboss random-item resource candidate

Physical f4637 is alive at timeline t4637 with no enemy or hostile bullet,
Power 6, and the SpellEnd Big Power plus four Small Power items still live.
The installed t4498--4978 section contains 62 sub0 parents. Each explicit
timeline record supplies life 3 and item drop -1, so killed parents consume the
source random-item table. Sub0's only bullet instruction has difficulty mask
`0x08` and does not execute on Hard. The next source control event is the t5278
dialogue start; movement coverage must end before it.

Exact battle replay from f4637 through 641 updates compares the old bottom
waypoint with a live Power-item target. Across eight paired delivery seeds,
the bottom target survives but uses 241--246 commands and reaches only Power
18--20. The Power target survives with 66--116 commands and reaches Power
25--29. A 32-seed extension keeps every branch alive through t5278, uses
66--120 commands, ends at Power 25--29, and never crosses into uncompiled
Reimu-A Rank 4. The policy is dynamic over source item type and position, not
slot or captured coordinates: Big/Full Power first, then nearest Small Power,
then the bottom waypoint when no Power item is live. Common Hard-4 is unchanged.

The ordinary-RNG default fail-close run physically promoted this phase. It
published 705 fresh decisions from f4498 through f5277 and increased Power
from 11 to 26 before stopping alive on the deliberately uncovered t5278
dialogue boundary. There was no HIT, Bomb, earlier authority loss, or timeout.
The retained final 255 adjacent physical pairs exactly match player, combat
enemy, player-shot, RNG, item, and Power transitions; they include five item
births and six removals. Inputs were released and the exact trial PID stopped.

This validates the item-aware soft proposal only within unchanged Hard-4
eligibility. It does not authorize movement through dialogue. The next
falsifiable boundary is the source-defined t5278 dialogue and t5279 main-boss
insertion, with dialogue control kept separate from movement.

## pre-boss dialogue candidate

The authoritative update order is EnemyManager at priority 9 and Gui at
priority 12. At t5278 the timeline starts message 0; t5279 MSGWAIT then holds
the timeline until the message VM executes its time-84 ECLRESUME. The installed
message program proves six earliest wait updates with fastest source-legal
input. When the wait releases, RunEclTimeline inserts sub10 in that same update
before the new enemy slot runs its time-zero ECL.

The candidate therefore covers only the no-boss t5278/t5279 snapshots with a
bottom-center target-only Hard-4 proposal. Existing independent Ctrl/Z dialogue
control advances the message; the route does not emit or reinterpret those
keys. The exact physical t5278 root has 18 Hard-safe actions under this policy,
including the six-update message delay and future sub10 world. A no-boss t5280
snapshot and every newborn sub10 state remain fail-visible. The next physical
run must stop at the first stable sub10 root.

That run did not reach this phase. It failed closed earlier at f5060 in the
resource formation, with no HIT or Bomb, after the item target had held down
toward a live enemy body. The first consequential mismatch is already visible
at f5054: down is Hard-4 and uniquely closest to the bottom fallback, but has
h8 policy volume 8 while the best fresh set has volume 9. At f5056/f5058 down
has no constant h8 continuation; the eventual f5059 reversal was stale and
f5060 had no delivery-robust Hard-4 action. One physical enemy body preserves
this relation after the other 19 bodies and all bullets are removed.

The resource candidate now computes policy-volume h8 first and applies the
dynamic Power target only inside its strongest fresh set. Common Hard-4 is
unchanged. From physical f5020, old h4 targeting has four lease-authority stops
across 16 delivery seeds; h8/h12/h16 all survive 16/16. Additional h8 replay
from f5048, f5052, and f5054 survives 32/32 seeds for 64 updates per root.
Across all 255 retained resource snapshots, the production budgeted h8 rung
completes 255/255 with no policy timeout. This remains an offline candidate
until a default fail-close run reaches t5278 and the first sub10 root.

The next ordinary-RNG default fail-close run physically promoted both the h8
resource repair and the dialogue bridge. Resource h8 published 584 fresh
decisions from f4499 through f5277 and raised Power from 18 to 32. Twenty-three
stale decisions retained only already certified input and all recovered fresh
Hard; there was no HIT, Bomb, authority loss, or timeout. Mean resource solve
time was 9.262 ms, p90 17.671 ms, and maximum 48.698 ms. These timings justify
keeping h8 rather than the survival-equivalent deeper offline rungs.

At f5278 the dialogue route started from fresh Hard. Message 0 became active
at f5279, Ctrl skip remained asserted through f5285, and the timeline remained
at t5279 for the predicted wait interval. F5286 published boss slot 0 as sub10
local t2 and the route stopped before issuing an unaudited boss action. The
message is still active at this root and the next timeline t5280 MSGWAIT has 48
proved remaining updates. Adjacent replay matches all 255 player transitions;
the 15 supported combat transitions are exact for enemy, player attack, RNG,
item, and Power state. Inputs were released and the exact PID stopped.

Power 32 is a newly reached Reimu-A shot rank, so the earlier Power-16--31
offline attack table is no longer sufficient. The next phase audit must join
the sub10 entry ECL, the still-active message/timeline wait, and the Power-32
player attack state before opening any boss movement policy.

## main-boss sub10 dialogue-gated entry candidate

The immutable Stage 1 ECL identifies the f5286 boss as sub10. Its time-zero
instructions disable damage and collision, mark the slot as boss 0, set the
entry position to `(320,-32)`, install interrupt 0 -> sub11, and begin a
60-tick decelerating move to `(192,96)`. At local t60 it changes animation and
installs the source move bounds. There is no bullet or laser creation opcode
anywhere in sub10. Its t1060 rewind is irrelevant to the ordinary online path
but remains part of the audited source graph.

The stage timeline is still stopped on the t5280 MSGWAIT. The captured message
VM proves a lower bound of 48 remaining priority-9 waits; it is an earliest
transition bound, not an exact decrementing countdown. After the wait releases,
t5281 writes interrupt 0 before the boss slot updates. Sub11 enables collision
and damage at time zero, installs life 7000 plus life/timer callbacks, and
reaches its first call site at local t100. It therefore stays a distinct
fail-visible phase.

Reimu-A Rank 4 (Power 32--47) is now compiled directly from authoritative
`g_CharacterPowerBulletDataReimuARank4`: three five-frame main shots at
-96/-90/-84 degrees with damage 24/30/24, plus the two existing 30-frame orb
shots with damage 14. On the retained f5031--f5286 physical history, all 255
player-attack transitions, 145 shot births, and 3,227 shot steps match. The
nominal combat world is exact on 248/255 adjacent pairs, including 17 enemy
slot transitions and all item/RNG/Power state. The seven unsupported pairs are
exactly f5279--f5286 while the active message holds the timeline; they remain
explicitly unsupported rather than receiving an invented countdown state.

Route-neutral fail-closed forecasting from f5286 covers the first 120 frames
with zero hostile births and exposes the sub11 boss body after the proved
message delay. It stops at lead 137 because player damage can then reach an
active, not-yet-authored life callback. The next physical candidate therefore
uses only target-only Hard-4 toward bottom center during sub10. The exact root
retains all 18 Hard actions and selects `down_left`; sub11 remains uncovered,
so the run must stop on its first stable snapshot.

The ordinary-RNG default fail-close run physically promotes this candidate.
It reached sub10 at f5286 with Power 30, then published 61 fresh entry decisions
through f5349. Every decision retained all 18 Hard actions; solve time was
0.884 ms mean, 0.900 ms median, and 1.500 ms maximum. There was no HIT, Bomb,
stale decision, timeout, or authority loss in this phase.

The physical message did not release at the 48-frame lower bound. Its computed
bound remained at 38 during a source WAIT interval, so sub10 reached local t60
at f5344 and exactly completed the decelerating move at `(192,96)`. It executed
the t60 animation/bounds instructions on f5345 and remained non-damageable,
non-collidable, and bullet-free. Message 0 ended at f5348, the timeline reached
t5281 at f5349, and the next update applied interrupt 0. F5350 is the first
stable sub11 root: `(192,96)`, local t1, life 7000, damageable/collidable, and
Hard difficulty callbacks 22/22. The route issued no sub11 action and stopped
with all 18 Hard actions still available.

All 63 adjacent physical sub10 emitter transitions match the source ECL model,
including the t60 movement completion and instruction advance. The retained
255-pair window also has exact player attack on 255/255 pairs and exact full
combat state on all 185 supported pairs; 53 message-wait pairs remain
explicitly unsupported by the stateful timeline VM. Across the complete CSV,
there is no dead player state and neither native nor desired input ever carries
Bomb bit `0x02`. The sole authority stop is the intended f5350 sub11 boundary.

## main-boss first nonspell candidate

The installed Stage 1 ECL and authoritative `EclManager::RunEcl` semantics give
the following bounded source contract:

- sub11 time zero enables damage and collision, sets life 7000, and installs
  Hard life/timer callbacks 22/22;
- sub11 local t100 performs an unconditional CALL to sub12;
- sub12 time zero selects a source random-in-bounds direction, speed 3, and a
  60-tick movement duration;
- sub12 emits opcode-67 aimed fans at local t12, t20, t28, t36, t44, t52, and
  t60. Hard mask `0x04` gives first counts 1, 1, 1, 1, 2, 3, and 4, each with
  ten secondary lanes, for 130 bullets at base speeds 5 and 1. The 1, 2, 2,
  3, 3, 4, 5 / 200-bullet sequence belongs to Lunatic mask `0x08`; the first
  audit incorrectly conflated these masks;
- sub12 local t180 draws a three-way integer. Values zero/one CALL sub13/sub14;
  value two skips both conditions and falls through to CALL sub15. None of
  these callees RET, so a taken conditional CALL does not later reach sub15.

The route stops before that t180 branch. Callback 22 is also a distinct spell
transition, so candidate damage and boss life remain part of every offline
world rather than being replaced by a fixed phase duration.

The captured timeline is parked on opcode 12 waiting for boss removal. For
this bounded offline comparison only, the root is shaped with an empty,
complete timeline because source guarantees the wait cannot advance while the
boss slot is occupied. This does not change online timeline semantics and is
invalid after boss retirement or a callback that changes that invariant.

On eight exact f5350 delivery seeds through the t180 boundary, target-free
h6/h8/h12 policy-volume survived 6/8, 7/8, and 8/8 respectively. H12 cost
roughly twice h8 and is not an online candidate. At h8, the measured local
metrics were:

- policy-volume: 7/8;
- constant-frontier: 6/8;
- replanning-count: 8/8 but 26.321 seconds for the eight offline runs;
- constant-reserve-count: 8/8 with weaker clearance;
- count-clearance: 8/8, 20.16--28.03 minimum clearance, and 6.938 seconds.

`count-clearance` first maximizes deduplicated terminal-state count, then uses
the best terminal hazard clearance only inside that strongest count. It is a
soft phase primitive: the common fresh Hard-4 set remains the only action
authority. Its native projection contains currently live hazards plus nominal
timeline/ECL births in the eight-frame window. Future aimed births inside one
query still use the current player location; candidate-conditioned aim comes
from the stateful battle loop re-running source ECL after each candidate and
delivery transition.

The promotion screen broadens the exact-root result in two ways. First, eight
source RNG states, both Power 30 and the authoritative Power-32 Rank-4 boundary,
and four delivery schedules produced 64/64 complete 278-update survivals; the
worst minimum clearance was 2.660. Second, Hard-safe source stepping derived
32/32 worlds through 2,476 warmup updates and 420 births. Those roots contain
23 unique enemy-combat states, 32 player-attack states, and 32 RNG states; all
128 subsequent 64-update delivery worlds survived, with worst clearance
18.189.

The actual Windows production dispatch was measured on 280 consecutive states.
It completed all 278 authored decisions with no timeout at 2.105 ms median,
2.562 ms p90, 3.578 ms p99, and 3.679 ms maximum. The last two states are the
intentional post-t180 `phase-unavailable` boundary. Linux and Windows/native
baseline suites both pass 296 tests; Linux skips the 25 Windows-only checks.

The physical candidate therefore authors only sub11 `ecl_time <= 100` as
`first-nonspell-entry` and sub12 `ecl_time < 180` as
`first-nonspell-aimed-fans`, both target-free h8 count-clearance. A default
fail-close run must stop at the first stable t180 branch identity. Promotion
also requires exact adjacent parity for sub11's CALL, sub12 movement and all
fan births, Reimu-A shots, boss damage/life, bullets, and RNG.

The ordinary-RNG/default fail-close run physically promotes this candidate. It
crossed the sub11 t100 CALL and all seven Hard sub12 groups, then stopped at
f5629 on `boss:0:sub14:life_cb22:timer_cb22:nonspell` local t1. The final state
is `(108.811,331.571)`, Power 34, boss life 4634, 61 live bullets, and all 18
Hard-safe actions. There is no player-dead state, native/desired Bomb bit,
policy timeout, or earlier authority stop anywhere in the full CSV; exact PID
60964 was stopped and all inputs were released.

From f5349 through f5627, all 246 fresh route decisions used count-clearance,
retained all 18 Hard actions, and recorded zero stale retry. Another 33 updates
were already-issued one-frame input leases. Fresh solve time was 3.196 ms
median, 4.375 ms p90, 5.655 ms p99, and 12.424 ms maximum, with no timeout.
The physical peak was 130 hostile bullets and the retained minimum current-
bullet clearance was 27.882.

Raw physical parity covers 254/254 player and Reimu-A attack transitions, 159
exact player-shot births, 5,691 player-shot steps, 130 exact hostile births,
13,135 mature-bullet steps, and 1,950 spawning-bullet steps. It reports the
full combat rung unsupported solely because timeline opcode 12 is waiting for
boss removal. Applying the already documented, source-proved phase-local
shaping gives 254/254 exact combat enemy, player-shot, RNG, graze, rank, pending
effect, item, and Power transitions; all 49 boss-life changes match and no
combat state is unsupported. This shaping remains invalid after boss removal.

At f5628 sub12 is still local t180 while a previously issued action completes
its one-frame Hard lease. The f5628->f5629 update then consumes the modeled RNG
and publishes sub14 local t1; the route issues no sub14 strategy action. Audit
sub14's movement/first attack and the following sub15 call structure next.
Sub13 remains an independent RNG sibling and must be audited separately rather
than inheriting sub14 policy.

## main-boss sub14 candidate

The exact f5629 root enters sub14 local t1 with boss life 4634 and 61 residual
sub12 bullets. Installed source gives this bounded contract:

- time zero selects a random-in-bounds direction, speed 3, for 60 ticks;
- Hard mask `0x04` emits opcode 67 at t80: aimed fan, sprite 2/color 2,
  `count1=5`, `count2=16`, speeds 5/1, angle step pi/48, flags 8;
- Hard mask `0x04` emits opcode 69 at t110: aimed circle, sprite 1/color 6,
  `count1=24`, `count2=2`, speed 2.5, flags 4;
- t200 draws a three-way integer. Values zero/one CALL sub13/sub12; value two
  skips both conditions and falls through to CALL sub15. The callees do not
  RET, so these are three exclusive persistent source states.

Sub13 is a different seven-circle stream and sub15 is a variable-angle loop;
neither is covered by this state. Candidate damage may also reach life callback
sub22 before t200, so the stateful world retains boss life and treats that
callback as another stable boundary.

The first exact comparison rejects copying the preceding phase's policy.
Count-clearance h8 has one lease-authority stop across eight delivery seeds.
Policy-volume h8 also loses one. Constant-reserve-count h8 passes the exact
eight but loses 3/62 on a wider warmup-derived screen; h10 moves those failures
but still loses 2/62. Deeper terminal metrics repair different roots without a
consistent smallest winner.

Target-free constant-frontier h10 is the smallest candidate that survives the
whole screen: 8/8 exact roots plus 62/62 delivery branches from 31 derived
worlds reach t200 or a stable called subroutine. The derived corpus was produced
by 2,263 Hard-safe warmup updates with 1,456 source births and contains 29
unique enemy-combat states, 31 player-attack states, and 22 RNG states. Its
worst clearance is 0.354, so the result selects a physical falsifier rather
than proving a robust route.

This primitive does not count aliased paths. It keeps only first actions whose
unchanged control remains safe through a ten-frame, delivery-aware source
projection; ranking still occurs inside the fresh common Hard set. On 199
consecutive candidate states, complete Hard-4 plus constant-h10 queries cost
1.337 ms median, 1.644 ms p90, 2.073 ms p99, and 2.383 ms maximum.

Only sub14 `ecl_time < 200` is candidate-authored as
`first-nonspell-hard-fan-circle`. A default fail-close run must stop on the
first stable t200 branch or life callback and must retain exact adjacent parity
for movement, both aimed births, player shots, boss damage/life, and RNG.
