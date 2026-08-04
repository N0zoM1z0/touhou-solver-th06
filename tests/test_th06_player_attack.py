import struct
import unittest
from dataclasses import asdict, replace

from th06.barrage_lab.corpus import decode_snapshot
from th06.barrage_lab.stateful import (
    step_reimu_a_player_attack,
    step_reimu_a_player_shot,
)
from th06.model import PlayerAttackState, Snapshot
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
    )


class PlayerAttackTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
