import struct
import unittest
from dataclasses import asdict, replace

from th06.barrage_lab.corpus import decode_snapshot
from th06.barrage_lab.stateful import (
    _NominalCombatStep,
    _step_items_after_effects,
    _step_lasers_after_bullets,
    physical_step_parity,
    step_nominal_battle_world,
    step_reimu_a_player_attack,
    step_reimu_a_player_shot,
)
from th06.hazards.ecl import source_enemy_template
from th06.hazards.rng import RngState
from th06.model import (
    Bullet,
    CONTROL_ACTIONS,
    EclInstruction,
    ItemState,
    Laser,
    PlayerAttackState,
    PlayerShot,
    Snapshot,
)
from th06.native import (
    ANM_VM_SCRIPT_OFFSET,
    ANM_VM_SPRITE_OFFSET,
    ANM_VM_TIMER_OFFSET,
    PLAYER_BOMB_ACTIVE_OFFSET,
    PLAYER_BULLETS_OFFSET,
    PLAYER_BULLET_DAMAGE_OFFSET,
    PLAYER_BULLET_HOMING_SPEED_OFFSET,
    PLAYER_BULLET_POSITION_OFFSET,
    PLAYER_BULLET_SIZE_OFFSET,
    PLAYER_BULLET_STATE_OFFSET,
    PLAYER_BULLET_STRIDE,
    PLAYER_BULLET_TIMER_OFFSET,
    PLAYER_BULLET_VELOCITY_OFFSET,
    PLAYER_FIRE_TIMER_OFFSET,
    PLAYER_FOCUS_OFFSET,
    PLAYER_FOCUS_TIMER_OFFSET,
    PLAYER_LAST_ENEMY_HIT_OFFSET,
    PLAYER_ORBS_POSITION_OFFSET,
    PLAYER_ORB_STATE_OFFSET,
    PLAYER_POSITION_OFFSET,
    ENEMY_DEATH_ANM_OFFSET,
    ENEMY_RANDOM_ITEM_SPAWN_INDEX_OFFSET,
    ENEMY_RANDOM_ITEM_TABLE_INDEX_OFFSET,
    EFFECT_ACTIVE_COUNT_OFFSET,
    ITEM_ACTIVE_COUNT_OFFSET,
    _decode_player_attack,
)


def _snapshot(attack: PlayerAttackState) -> Snapshot:
    return Snapshot(
        frame=10,
        stage=5,
        player_state=0,
        x=192.0,
        y=400.0,
        half_width=1.25,
        half_height=1.25,
        normal_speed=4.0,
        focus_speed=2.0,
        normal_diagonal_speed=2.828427,
        focus_diagonal_speed=1.414214,
        frame_multiplier=1.0,
        input_mask=0x05,
        bullets=(),
        laser_count=0,
        in_menu=False,
        time_stopped=False,
        replay_or_demo=False,
        player_attack=attack,
        effect_active_upper_bound=0,
        item_active_upper_bound=0,
    )


def _attack_with_shot(damage: int, *, spell: bool = False) -> PlayerAttackState:
    return PlayerAttackState(
        shots=(PlayerShot(
            slot=0,
            x=100.0,
            y=100.0,
            half_width=6.0,
            half_height=6.0,
            vx=0.0,
            vy=-12.0,
            homing_speed=12.0,
            timer_previous=0,
            timer=1,
            timer_float=1.0,
            damage=damage,
            state=1,
            bullet_type=0,
            anm_script=0x440,
            anm_timer=1,
            anm_timer_float=1.0,
            sprite_half_width=7.0,
            sprite_half_height=7.0,
        ),),
        last_enemy_hit_x=-999.0,
        last_enemy_hit_y=-999.0,
        orb_state=1,
        is_focus=False,
        focus_timer_previous=-999,
        focus_timer=0,
        focus_timer_float=0.0,
        fire_timer_previous=0,
        fire_timer=1,
        fire_timer_float=1.0,
        orb_positions=((76.0, 400.0), (124.0, 400.0)),
        shot_type=0,
        bomb_active=False,
        spell_active=spell,
    )


def _combat_emitter(**changes):
    first = EclInstruction(0x1000, 999, 0, 12, 0, "00" * 12)
    callback = EclInstruction(0x2000, 999, 0, 12, 0, "00" * 12)
    emitter = source_enemy_template(
        (first, callback), (first.address, callback.address),
        0, 100.0, 100.0, 100,
    )
    assert emitter is not None
    values = dict(
        slot=0,
        next_instruction=first,
        interactable=True,
        damageable=True,
        has_been_in_bounds=True,
        hitbox_half_width=4.0,
        hitbox_half_height=4.0,
        sprite_half_width=8.0,
        sprite_half_height=8.0,
        item_drop=-2,
    )
    values.update(changes)
    return replace(emitter, **values)


class PlayerAttackTests(unittest.TestCase):
    def test_periodic_timeline_subrank_precedes_battle_update(self):
        attack = replace(_attack_with_shot(1), shots=())
        root = replace(
            _snapshot(attack),
            frame=1920,
            timeline_time=1920,
            timeline_time_float=1920.0,
            timeline_time_previous=1919,
            timeline_complete=True,
            lives_remaining=2,
            rank=16,
            subrank=85,
            max_rank=32,
        )
        stay = next(action for action in CONTROL_ACTIONS if action.name == "stay")

        following = step_nominal_battle_world(root, stay)

        # RunEclTimeline computes 2400 - 2 * 240 = 1920 and applies +100
        # before the rest of the source battle update. The remainder stays.
        self.assertEqual((following.rank, following.subrank), (17, 85))
        self.assertEqual(following.timeline_time_previous, 1920)

        stalled = step_nominal_battle_world(
            replace(root, timeline_time_previous=1920), stay
        )
        self.assertEqual((stalled.rank, stalled.subrank), (16, 85))

    def test_combat_pool_and_enemy_death_layout_matches_source(self):
        self.assertEqual(ENEMY_DEATH_ANM_OFFSET, 0xE3C)
        self.assertEqual(ENEMY_RANDOM_ITEM_SPAWN_INDEX_OFFSET, 0xEE5B8)
        self.assertEqual(ENEMY_RANDOM_ITEM_TABLE_INDEX_OFFSET, 0xEE5BA)
        self.assertEqual(EFFECT_ACTIVE_COUNT_OFFSET, 4)
        self.assertEqual(ITEM_ACTIVE_COUNT_OFFSET, 0x28948)

    def test_authoritative_player_layout_decodes_one_occupied_shot(self):
        player = bytearray(
            PLAYER_BOMB_ACTIVE_OFFSET + 4 - PLAYER_POSITION_OFFSET
        )
        relative = lambda offset: offset - PLAYER_POSITION_OFFSET
        slot = 7
        base = relative(PLAYER_BULLETS_OFFSET) + slot * PLAYER_BULLET_STRIDE
        sprite = 0x123400
        struct.pack_into("<I", player, base + ANM_VM_SPRITE_OFFSET, sprite)
        struct.pack_into("<ifi", player, base + ANM_VM_TIMER_OFFSET, 3, 0.0, 4)
        struct.pack_into("<h", player, base + ANM_VM_SCRIPT_OFFSET, 0x441)
        struct.pack_into("<ff", player, base + PLAYER_BULLET_POSITION_OFFSET, 100.0, 200.0)
        struct.pack_into("<ff", player, base + PLAYER_BULLET_SIZE_OFFSET, 12.0, 12.0)
        struct.pack_into("<ff", player, base + PLAYER_BULLET_VELOCITY_OFFSET, 0.0, -10.0)
        struct.pack_into("<f", player, base + PLAYER_BULLET_HOMING_SPEED_OFFSET, 10.0)
        struct.pack_into("<ifi", player, base + PLAYER_BULLET_TIMER_OFFSET, 11, 0.0, 12)
        struct.pack_into("<hhhhh", player, base + PLAYER_BULLET_DAMAGE_OFFSET, 10, 1, 1, 0, 2)
        struct.pack_into("<ff", player, relative(PLAYER_LAST_ENEMY_HIT_OFFSET), 120.0, 80.0)
        struct.pack_into("<ff", player, relative(PLAYER_ORBS_POSITION_OFFSET), 180.0, 360.0)
        struct.pack_into("<ff", player, relative(PLAYER_ORBS_POSITION_OFFSET) + 12, 204.0, 360.0)
        player[relative(PLAYER_ORB_STATE_OFFSET)] = 3
        player[relative(PLAYER_FOCUS_OFFSET)] = 1
        struct.pack_into("<ifi", player, relative(PLAYER_FOCUS_TIMER_OFFSET), -999, 0.0, 0)
        struct.pack_into("<ifi", player, relative(PLAYER_FIRE_TIMER_OFFSET), 11, 0.0, 12)

        attack = _decode_player_attack(
            bytes(player),
            {sprite: (16.0, 20.0)},
            shot_type=0,
            spell_active=False,
        )

        self.assertEqual(len(attack.shots), 1)
        shot = attack.shots[0]
        self.assertEqual((shot.slot, shot.state, shot.bullet_type), (7, 1, 1))
        self.assertEqual((shot.half_width, shot.sprite_half_height), (6.0, 10.0))
        self.assertEqual((attack.last_enemy_hit_x, attack.fire_timer), (120.0, 12))

    def test_reimu_a_homing_uses_previous_frame_last_hit(self):
        player = bytearray(
            PLAYER_BOMB_ACTIVE_OFFSET + 4 - PLAYER_POSITION_OFFSET
        )
        relative = lambda offset: offset - PLAYER_POSITION_OFFSET
        base = relative(PLAYER_BULLETS_OFFSET)
        sprite = 0x123400
        struct.pack_into("<I", player, base + ANM_VM_SPRITE_OFFSET, sprite)
        struct.pack_into("<ifi", player, base + ANM_VM_TIMER_OFFSET, 4, 0.0, 5)
        struct.pack_into("<h", player, base + ANM_VM_SCRIPT_OFFSET, 0x441)
        struct.pack_into("<ff", player, base + PLAYER_BULLET_POSITION_OFFSET, 100.0, 200.0)
        struct.pack_into("<ff", player, base + PLAYER_BULLET_SIZE_OFFSET, 12.0, 12.0)
        struct.pack_into("<ff", player, base + PLAYER_BULLET_VELOCITY_OFFSET, 0.0, -10.0)
        struct.pack_into("<f", player, base + PLAYER_BULLET_HOMING_SPEED_OFFSET, 10.0)
        struct.pack_into("<ifi", player, base + PLAYER_BULLET_TIMER_OFFSET, 11, 0.0, 12)
        struct.pack_into("<hhhhh", player, base + PLAYER_BULLET_DAMAGE_OFFSET, 10, 1, 1, 0, 1)
        struct.pack_into("<ff", player, relative(PLAYER_LAST_ENEMY_HIT_OFFSET), 140.0, 100.0)
        struct.pack_into("<ff", player, relative(PLAYER_ORBS_POSITION_OFFSET), 180.0, 360.0)
        struct.pack_into("<ff", player, relative(PLAYER_ORBS_POSITION_OFFSET) + 12, 204.0, 360.0)
        struct.pack_into("<ifi", player, relative(PLAYER_FOCUS_TIMER_OFFSET), -999, 0.0, 0)
        struct.pack_into("<ifi", player, relative(PLAYER_FIRE_TIMER_OFFSET), 11, 0.0, 12)
        attack = _decode_player_attack(
            bytes(player), {sprite: (16.0, 16.0)},
            shot_type=0, spell_active=False,
        )

        advanced = step_reimu_a_player_shot(attack.shots[0], attack)

        self.assertIsNotNone(advanced)
        self.assertGreater(advanced.x, attack.shots[0].x)
        self.assertLess(advanced.y, attack.shots[0].y)
        self.assertEqual((advanced.timer_previous, advanced.timer), (12, 13))

    def test_attack_state_round_trips_through_corpus_decoder(self):
        player = bytearray(
            PLAYER_BOMB_ACTIVE_OFFSET + 4 - PLAYER_POSITION_OFFSET
        )
        relative = lambda offset: offset - PLAYER_POSITION_OFFSET
        struct.pack_into("<ff", player, relative(PLAYER_LAST_ENEMY_HIT_OFFSET), -999.0, -999.0)
        struct.pack_into("<ff", player, relative(PLAYER_ORBS_POSITION_OFFSET), 180.0, 360.0)
        struct.pack_into("<ff", player, relative(PLAYER_ORBS_POSITION_OFFSET) + 12, 204.0, 360.0)
        struct.pack_into("<ifi", player, relative(PLAYER_FOCUS_TIMER_OFFSET), -999, 0.0, 0)
        struct.pack_into("<ifi", player, relative(PLAYER_FIRE_TIMER_OFFSET), -999, 0.0, -1)
        attack = _decode_player_attack(
            bytes(player), {}, shot_type=0, spell_active=False
        )

        decoded = decode_snapshot(asdict(_snapshot(attack)))

        self.assertEqual(decoded.player_attack, attack)

    def test_rank9_fire_phase_spawns_source_main_and_orb_shots(self):
        player = bytearray(
            PLAYER_BOMB_ACTIVE_OFFSET + 4 - PLAYER_POSITION_OFFSET
        )
        relative = lambda offset: offset - PLAYER_POSITION_OFFSET
        struct.pack_into("<ff", player, relative(PLAYER_LAST_ENEMY_HIT_OFFSET), -999.0, -999.0)
        struct.pack_into("<ff", player, relative(PLAYER_ORBS_POSITION_OFFSET), 168.0, 400.0)
        struct.pack_into("<ff", player, relative(PLAYER_ORBS_POSITION_OFFSET) + 12, 216.0, 400.0)
        player[relative(PLAYER_ORB_STATE_OFFSET)] = 1
        struct.pack_into("<ifi", player, relative(PLAYER_FOCUS_TIMER_OFFSET), -999, 0.0, 0)
        struct.pack_into("<ifi", player, relative(PLAYER_FIRE_TIMER_OFFSET), -999, 0.0, -1)
        attack = _decode_player_attack(
            bytes(player), {}, shot_type=0, spell_active=False
        )

        following = step_reimu_a_player_attack(
            attack, (192.0, 400.0), False, 128
        )

        self.assertEqual(len(following.shots), 6)
        self.assertEqual(
            tuple(shot.damage for shot in following.shots),
            (23, 24, 24, 23, 10, 10),
        )
        self.assertEqual(
            tuple(shot.bullet_type for shot in following.shots),
            (0, 0, 0, 0, 1, 1),
        )
        self.assertEqual((following.fire_timer_previous, following.fire_timer), (0, 1))
        self.assertEqual(following.orb_positions, ((168.0, 400.0), (216.0, 400.0)))

    def test_rank1_fire_phase_spawns_single_source_main_shot(self):
        player = bytearray(
            PLAYER_BOMB_ACTIVE_OFFSET + 4 - PLAYER_POSITION_OFFSET
        )
        relative = lambda offset: offset - PLAYER_POSITION_OFFSET
        struct.pack_into(
            "<ff", player, relative(PLAYER_LAST_ENEMY_HIT_OFFSET),
            -999.0, -999.0,
        )
        struct.pack_into(
            "<ifi", player, relative(PLAYER_FOCUS_TIMER_OFFSET),
            -999, 0.0, 0,
        )
        struct.pack_into(
            "<ifi", player, relative(PLAYER_FIRE_TIMER_OFFSET),
            -999, 0.0, -1,
        )
        attack = _decode_player_attack(
            bytes(player), {}, shot_type=0, spell_active=False
        )

        following = step_reimu_a_player_attack(
            attack, (192.0, 400.0), True, 2
        )

        self.assertEqual(len(following.shots), 1)
        shot = following.shots[0]
        self.assertEqual((shot.x, shot.y), (192.0, 400.0))
        self.assertAlmostEqual(shot.vx, 0.0, places=5)
        self.assertEqual((shot.vy, shot.damage), (-12.0, 48))
        self.assertEqual((shot.bullet_type, shot.anm_script), (0, 0x440))
        self.assertEqual(following.orb_state, 0)

    def test_rank2_fire_phase_spawns_main_and_two_source_orb_shots(self):
        player = bytearray(
            PLAYER_BOMB_ACTIVE_OFFSET + 4 - PLAYER_POSITION_OFFSET
        )
        relative = lambda offset: offset - PLAYER_POSITION_OFFSET
        struct.pack_into(
            "<ff", player, relative(PLAYER_LAST_ENEMY_HIT_OFFSET),
            -999.0, -999.0,
        )
        struct.pack_into(
            "<ifi", player, relative(PLAYER_FOCUS_TIMER_OFFSET),
            -999, 0.0, 0,
        )
        struct.pack_into(
            "<ifi", player, relative(PLAYER_FIRE_TIMER_OFFSET),
            -999, 0.0, -1,
        )
        attack = _decode_player_attack(
            bytes(player), {}, shot_type=0, spell_active=False
        )

        following = step_reimu_a_player_attack(
            attack, (192.0, 400.0), False, 8
        )

        self.assertEqual(len(following.shots), 3)
        self.assertEqual(
            tuple(shot.damage for shot in following.shots),
            (48, 14, 14),
        )
        self.assertEqual(
            tuple(shot.bullet_type for shot in following.shots),
            (0, 1, 1),
        )
        self.assertEqual(following.orb_state, 1)
        self.assertEqual(
            following.orb_positions,
            ((168.0, 400.0), (216.0, 400.0)),
        )

    def test_uncompiled_intermediate_reimu_a_rank_fails_closed(self):
        attack = _attack_with_shot(1)

        with self.assertRaisesRegex(
            ValueError, "power ranks 3 through 8 are not compiled"
        ):
            step_reimu_a_player_attack(
                attack, (192.0, 400.0), False, 16
            )

    def test_focusing_reaches_focused_without_same_frame_timer_reset(self):
        player = bytearray(
            PLAYER_BOMB_ACTIVE_OFFSET + 4 - PLAYER_POSITION_OFFSET
        )
        relative = lambda offset: offset - PLAYER_POSITION_OFFSET
        struct.pack_into("<ff", player, relative(PLAYER_LAST_ENEMY_HIT_OFFSET), -999.0, -999.0)
        player[relative(PLAYER_ORB_STATE_OFFSET)] = 2
        player[relative(PLAYER_FOCUS_OFFSET)] = 1
        struct.pack_into("<ifi", player, relative(PLAYER_FOCUS_TIMER_OFFSET), 6, 0.0, 7)
        struct.pack_into("<ifi", player, relative(PLAYER_FIRE_TIMER_OFFSET), 8, 0.0, 9)
        attack = _decode_player_attack(
            bytes(player), {}, shot_type=0, spell_active=False
        )

        following = step_reimu_a_player_attack(
            attack, (192.0, 400.0), True, 128
        )

        self.assertEqual(following.orb_state, 3)
        self.assertEqual(
            (following.focus_timer_previous, following.focus_timer), (7, 8)
        )

    def test_damage_caps_at_70_and_hit_effect_advances_priority10_rng(self):
        attack = _attack_with_shot(100)
        combat = _NominalCombatStep(_snapshot(attack), attack)

        rng = RngState(0x1234, 9)
        following = combat.post_emitter(_combat_emitter(), rng)
        combat.finish_frame(rng)

        self.assertIsNotNone(following)
        self.assertEqual(following.life, 30)
        self.assertEqual(combat.attack.shots[0].state, 2)
        self.assertEqual(combat.attack.shots[0].anm_script, 0x460)
        self.assertEqual(combat.attack.shots[0].anm_timer, 1)
        self.assertEqual(combat.effect_upper, 1)
        # Shipped effect ANM randomizes its sprite once, then callback 5 calls
        # two f32 values: one plus four source u16 generations.
        self.assertEqual(rng.generation_count, 14)

    def test_spell_damage_reduction_happens_after_source_cap(self):
        attack = _attack_with_shot(100, spell=True)
        combat = _NominalCombatStep(_snapshot(attack), attack)

        following = combat.post_emitter(
            _combat_emitter(), RngState(0x1234, 0)
        )

        self.assertEqual(following.life, 90)

    def test_mode1_death_keeps_slot_and_installs_callback_context(self):
        attack = _attack_with_shot(70)
        combat = _NominalCombatStep(_snapshot(attack), attack)

        following = combat.post_emitter(_combat_emitter(
            life=60,
            death_mode=1,
            death_callback_sub=1,
        ), RngState(0x1234, 0))

        self.assertIsNotNone(following)
        self.assertFalse(following.interactable)
        self.assertEqual(following.life, 0)
        self.assertEqual(following.death_callback_sub, -1)
        self.assertEqual(following.next_instruction.address, 0x2000)

    def test_life_callback_kills_nonbosses_before_later_slot_update(self):
        attack = _attack_with_shot(1)
        combat = _NominalCombatStep(_snapshot(attack), attack)
        boss = _combat_emitter(
            is_boss=True,
            life=40,
            life_callback_threshold=50,
            life_callback_sub=1,
        )
        minion = replace(_combat_emitter(), slot=1, life=20)
        slots = {0: boss, 1: minion}

        following = combat.pre_emitter(boss, slots)

        self.assertEqual(following.life, 50)
        self.assertEqual(following.next_instruction.address, 0x2000)
        self.assertEqual(slots[1].life, 0)

    def test_contact_damage_precedes_player_shot_damage(self):
        attack = _attack_with_shot(1)
        combat = _NominalCombatStep(
            _snapshot(attack), attack, player=(100.0, 100.0)
        )

        following = combat.post_emitter(
            _combat_emitter(life=12), RngState(0x1234, 0)
        )

        self.assertIsNotNone(following)
        self.assertEqual(following.life, 1)

    def test_enemy_kill_all_installs_noninteractive_death_callback(self):
        attack = _attack_with_shot(1)
        combat = _NominalCombatStep(_snapshot(attack), attack)
        target = replace(
            _combat_emitter(),
            interactable=False,
            death_callback_sub=1,
        )
        slots = {0: target}

        combat.enemy_kill_all(slots)

        self.assertEqual(slots[0].life, 0)
        self.assertEqual(slots[0].death_callback_sub, -1)
        self.assertEqual(slots[0].next_instruction.address, 0x2000)

    def test_explicit_item_drop_reserves_item_and_death_effect_slots(self):
        attack = _attack_with_shot(70)
        combat = _NominalCombatStep(_snapshot(attack), attack)

        following = combat.post_emitter(_combat_emitter(
            life=60,
            item_drop=1,
            death_anm1=12,
            death_anm2=3,
        ), RngState(0x1234, 0))

        self.assertIsNone(following)
        self.assertEqual(combat.item_upper, 1)
        self.assertEqual(combat.items[0].item_type, 1)
        # One shot impact, three item particles, then five common particles.
        self.assertEqual(combat.effect_upper, 9)

    def test_item_exit_and_collection_apply_source_subrank_transitions(self):
        attack = _attack_with_shot(1)
        miss = ItemState(
            slot=0,
            x=20.0,
            y=463.0,
            start_x=0.0,
            start_y=1.0,
            target_x=0.0,
            target_y=0.0,
            timer_previous=9,
            timer=10,
            timer_float=10.0,
            item_type=0,
            state=0,
        )
        miss_root = replace(
            _snapshot(attack),
            rank=19,
            subrank=1,
            min_rank=10,
            max_rank=32,
            item_states=(miss,),
            item_active_upper_bound=1,
        )
        miss_combat = _NominalCombatStep(miss_root, attack)

        miss_rank = _step_items_after_effects(
            miss_combat,
            (miss_root.x, miss_root.y),
            miss_root.player_state,
            miss_root,
        )

        self.assertEqual(miss_rank, (18, 98, 0))
        self.assertEqual(miss_combat.items, {})

        point = replace(
            miss,
            x=192.0,
            y=400.0,
            start_y=-2.2,
            item_type=1,
        )
        collect_root = replace(
            miss_root,
            subrank=1,
            item_states=(point,),
        )
        collect_combat = _NominalCombatStep(collect_root, attack)

        collect_rank = _step_items_after_effects(
            collect_combat,
            (collect_root.x, collect_root.y),
            collect_root.player_state,
            collect_root,
        )

        self.assertEqual(collect_rank, (19, 4, 0))
        self.assertEqual(collect_combat.items, {})

    def test_reaching_full_power_converts_bullets_into_live_point_items(self):
        attack = _attack_with_shot(1)
        power_item = ItemState(
            slot=0,
            x=192.0,
            y=402.2,
            start_x=0.0,
            start_y=-2.2,
            target_x=0.0,
            target_y=0.0,
            timer_previous=9,
            timer=10,
            timer_float=10.0,
            item_type=0,
            state=0,
        )
        root = replace(
            _snapshot(attack),
            current_power=127,
            item_states=(power_item,),
            item_active_upper_bound=1,
            item_next_index=1,
        )
        combat = _NominalCombatStep(root, attack)
        bullets = [Bullet(
            x=100.0,
            y=100.0,
            vx=1.0,
            vy=0.0,
            half_width=2.0,
            half_height=2.0,
            state=1,
            slot=7,
        )]

        following = _step_items_after_effects(
            combat,
            (root.x, root.y),
            root.player_state,
            root,
            bullets=bullets,
            rng=RngState(0x1234, 0),
        )

        self.assertEqual(following, (0, 1, 128))
        self.assertEqual(bullets, [])
        self.assertEqual(tuple(combat.items), (1,))
        point = combat.items[1]
        self.assertEqual((point.item_type, point.state, point.timer), (6, 1, 1))
        self.assertEqual(combat.item_upper, 1)

    def test_laser_phase_fallthrough_and_repeated_graze_rng(self):
        attack = _attack_with_shot(1)
        root = replace(_snapshot(attack), max_rank=32)
        far = Laser(
            x=1000.0,
            y=1000.0,
            angle=0.0,
            start_offset=0.0,
            end_offset=50.0,
            start_length=100.0,
            width=16.0,
            speed=2.0,
            start_time=10,
            hitbox_start_time=100,
            duration=2,
            despawn_duration=3,
            hitbox_end_delay=1,
            timer=9,
            timer_float=9.0,
            flags=0,
            state=0,
            slot=0,
        )
        combat = _NominalCombatStep(root, attack)
        rng = RngState(0x1234, 0)

        first = _step_lasers_after_bullets(
            (far,), (root.x, root.y), root, combat, rng, 0, 0, 0
        )[0][0]
        second = _step_lasers_after_bullets(
            (first,), (root.x, root.y), root, combat, rng, 0, 0, 0
        )[0][0]
        third = _step_lasers_after_bullets(
            (second,), (root.x, root.y), root, combat, rng, 0, 0, 0
        )[0][0]
        fourth = _step_lasers_after_bullets(
            (third,), (root.x, root.y), root, combat, rng, 0, 0, 0
        )[0][0]

        self.assertEqual((first.state, first.timer, first.end_offset), (0, 10, 52.0))
        self.assertEqual((second.state, second.timer, second.end_offset), (1, 1, 54.0))
        self.assertEqual((third.state, third.timer), (1, 2))
        self.assertEqual((fourth.state, fourth.timer), (2, 1))

        graze = replace(
            far,
            x=100.0,
            y=350.0,
            end_offset=200.0,
            speed=0.0,
            start_time=0,
            hitbox_start_time=0,
            duration=60,
            timer=0,
            timer_float=0.0,
            state=1,
        )
        graze_combat = _NominalCombatStep(root, attack)
        graze_rng = RngState(0x1234, 0)

        _, state, rank, subrank = _step_lasers_after_bullets(
            (graze,),
            (root.x, root.y),
            root,
            graze_combat,
            graze_rng,
            0,
            0,
            0,
        )

        self.assertEqual((state, rank, subrank), (0, 0, 6))
        self.assertEqual(graze_combat.post_effect_ids, [8])
        self.assertEqual(graze_rng.generation_count, 1)

    def test_reaching_full_power_converts_live_laser_points_in_pool_order(self):
        attack = _attack_with_shot(1)
        power_item = ItemState(
            slot=0,
            x=192.0,
            y=402.2,
            start_x=0.0,
            start_y=-2.2,
            target_x=0.0,
            target_y=0.0,
            timer_previous=9,
            timer=10,
            timer_float=10.0,
            item_type=0,
            state=0,
        )
        laser = Laser(
            x=100.0,
            y=100.0,
            angle=0.0,
            start_offset=0.0,
            end_offset=65.0,
            start_length=100.0,
            width=16.0,
            speed=0.0,
            start_time=0,
            hitbox_start_time=0,
            duration=60,
            despawn_duration=10,
            hitbox_end_delay=5,
            timer=7,
            timer_float=7.0,
            flags=0,
            state=1,
            slot=4,
        )
        root = replace(
            _snapshot(attack),
            current_power=127,
            item_states=(power_item,),
            item_active_upper_bound=1,
            item_next_index=1,
            lasers=(laser,),
            laser_count=1,
        )
        combat = _NominalCombatStep(root, attack)
        lasers = [laser]

        following = _step_items_after_effects(
            combat,
            (root.x, root.y),
            root.player_state,
            root,
            lasers=lasers,
            rng=RngState(0x1234, 0),
        )

        self.assertEqual(following, (0, 1, 128))
        self.assertEqual(tuple(combat.items), (1, 2, 3))
        self.assertTrue(all(
            (item.item_type, item.state, item.timer) == (6, 1, 1)
            for item in combat.items.values()
        ))
        self.assertEqual(
            (lasers[0].state, lasers[0].timer, lasers[0].hitbox_end_delay),
            (2, 0, 0),
        )

    def test_spell_end_despawns_bullets_and_awards_laser_points_in_one_pass(self):
        spell_end_raw = struct.pack(
            "<ihhBBBB", 0, 94, 12, 0, 4, 0, 0
        )
        spell_end = EclInstruction(
            0x1000, 0, 94, 12, 4, spell_end_raw.hex()
        )
        wait_raw = struct.pack(
            "<ihhBBBB", 999, 0, 12, 0, 4, 0, 0
        )
        wait = EclInstruction(
            0x100C, 999, 0, 12, 4, wait_raw.hex()
        )
        source = source_enemy_template(
            (spell_end, wait), (spell_end.address,), 0, 50.0, 50.0, 10
        )
        self.assertIsNotNone(source)
        bullet = Bullet(
            x=100.0,
            y=100.0,
            vx=2.0,
            vy=4.0,
            half_width=3.0,
            half_height=3.0,
            state=1,
            timer=7,
            timer_float=7.0,
            slot=3,
        )
        laser = Laser(
            x=50.0,
            y=50.0,
            angle=0.0,
            start_offset=0.0,
            end_offset=65.0,
            start_length=100.0,
            width=16.0,
            speed=0.0,
            start_time=0,
            hitbox_start_time=0,
            duration=60,
            despawn_duration=10,
            hitbox_end_delay=5,
            timer=7,
            timer_float=7.0,
            flags=0,
            state=1,
            slot=4,
        )
        attack = replace(_attack_with_shot(1, spell=True), shots=())
        root = replace(
            _snapshot(attack),
            bullets=(bullet,),
            lasers=(laser,),
            laser_count=1,
            spawners=(replace(source, slot=0),),
            item_next_index=0,
        )
        stay = next(action for action in CONTROL_ACTIONS if action.name == "stay")

        following = step_nominal_battle_world(root, stay)

        self.assertEqual(following.bullets, ())
        self.assertEqual(len(following.despawning_bullets), 1)
        despawning = following.despawning_bullets[0]
        self.assertEqual(
            (despawning.slot, despawning.state, despawning.x, despawning.y),
            (3, 5, 101.0, 102.0),
        )
        self.assertEqual((despawning.timer, despawning.timer_float), (8, 8.0))
        self.assertEqual(len(following.lasers), 1)
        self.assertEqual(
            (
                following.lasers[0].state,
                following.lasers[0].timer,
                following.lasers[0].hitbox_end_delay,
            ),
            (2, 1, 0),
        )
        # One bullet item, one explicit laser-origin item, and the source
        # offset walk at 0/32/64. The zero offset duplicates the origin.
        self.assertEqual(
            [item.slot for item in following.item_states],
            [0, 1, 2, 3, 4],
        )
        self.assertTrue(all(
            (item.item_type, item.state, item.timer) == (6, 1, 1)
            for item in following.item_states
        ))
        self.assertEqual(following.item_next_index, 5)
        self.assertFalse(following.player_attack.spell_active)
        self.assertEqual(following.rng_generation, root.rng_generation)

    def test_ecl_laser_birth_joins_same_frame_bullet_manager_pass(self):
        raw = struct.pack(
            "<ihhBBBBhhffffffiiiiii",
            0, 85, 0x40, 0, 4, 0, 0,
            0, 6, 0.5, 2.0, 0.0, 20.0, 100.0, 16.0,
            10, 60, 8, 2, 3, 0,
        )
        create = EclInstruction(0x1000, 0, 85, 0x40, 4, raw.hex())
        wait_raw = struct.pack("<ihhBBBB", 50, 0, 0x0C, 0, 4, 0, 0)
        wait = EclInstruction(0x1040, 50, 0, 0x0C, 4, wait_raw.hex())
        source = source_enemy_template(
            (create, wait),
            (0x1000,),
            0,
            50.0,
            50.0,
            10,
        )
        self.assertIsNotNone(source)
        root = replace(
            _snapshot(_attack_with_shot(1)),
            current_power=128,
            spawners=(replace(source, slot=0),),
        )
        stay = next(action for action in CONTROL_ACTIONS if action.name == "stay")

        following = step_nominal_battle_world(root, stay)

        self.assertEqual(following.laser_count, 1)
        laser = following.lasers[0]
        self.assertEqual((laser.slot, laser.state, laser.timer), (0, 0, 1))
        self.assertEqual((laser.x, laser.y), (50.0, 50.0))
        self.assertEqual(laser.end_offset, 22.0)
        self.assertEqual(following.spawners[0].laser_slots[0], 0)

    def test_physical_parity_certifies_ecl_laser_rotation_and_manager_step(self):
        rotate = EclInstruction(
            0x1000,
            0,
            88,
            20,
            0xFF,
            "000000005800140000ffff0003000000c673073c",
        )
        wait = EclInstruction(
            0x1014,
            999,
            0,
            12,
            0xFF,
            "e703000000000c0000ffff00",
        )
        source = source_enemy_template(
            (rotate, wait), (rotate.address,), 0, 50.0, 50.0, 10
        )
        self.assertIsNotNone(source)
        laser = Laser(
            x=50.0,
            y=50.0,
            angle=0.5,
            start_offset=0.0,
            end_offset=100.0,
            start_length=100.0,
            width=16.0,
            speed=0.0,
            start_time=0,
            hitbox_start_time=30,
            duration=120,
            despawn_duration=16,
            hitbox_end_delay=14,
            timer=10,
            timer_float=10.0,
            flags=0,
            state=1,
            slot=3,
        )
        root = replace(
            _snapshot(replace(_attack_with_shot(1), shots=())),
            spawners=(replace(
                source,
                slot=0,
                laser_slots=(-1, -1, -1, 3) + (-1,) * 28,
            ),),
            lasers=(laser,),
            laser_count=1,
            timeline_complete=True,
        )
        stay = next(
            action for action in CONTROL_ACTIONS if action.name == "stay"
        )
        following = step_nominal_battle_world(root, stay)
        parity = physical_step_parity((root, following))

        self.assertNotEqual(following.lasers[0].angle, laser.angle)
        self.assertEqual(parity.externally_mutated_laser_steps, 1)
        self.assertEqual(parity.laser_steps, 1)
        self.assertEqual(parity.exact_laser_steps, 1)
        self.assertEqual(parity.maximum_laser_error, 0.0)
        self.assertEqual(parity.first_laser_mismatch, "")


if __name__ == "__main__":
    unittest.main()
