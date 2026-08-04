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
