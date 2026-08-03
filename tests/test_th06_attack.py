import struct
import unittest

from th06.attack import (
    MOVEMENT_LEFT,
    preferred_suppression_actions,
    suppression_target,
)
from th06.hazards.timeline import decode_enemy_spawn
from th06.model import (
    ACTIONS,
    CONTROL_ACTIONS,
    SafeAction,
    Snapshot,
    StageTimelineInstruction,
)


def timeline_spawn(
    *,
    address: int,
    time: int,
    sub_id: int,
    opcode: int,
    x: float,
    y: float,
    life: int,
) -> StageTimelineInstruction:
    raw = struct.pack(
        "<hhhhfffHHi",
        time,
        sub_id,
        opcode,
        28,
        x,
        y,
        0.0,
        life,
        1,
        2000,
    )
    return StageTimelineInstruction(
        address, time, sub_id, opcode, len(raw), raw.hex()
    )


def snapshot(**changes) -> Snapshot:
    values = dict(
        frame=1379,
        stage=5,
        player_state=0,
        x=331.0,
        y=430.0,
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
        timeline_time=1379,
        timeline_emitter_subs=(0, 1),
    )
    values.update(changes)
    return Snapshot(**values)


class TimelineAttackTests(unittest.TestCase):
    def test_source_timeline_spawn_keeps_explicit_life_and_mirror(self):
        instruction = timeline_spawn(
            address=0x1000,
            time=1462,
            sub_id=1,
            opcode=2,
            x=352.0,
            y=160.0,
            life=200,
        )
        spawn = decode_enemy_spawn(instruction)
        self.assertIsNotNone(spawn)
        self.assertEqual(spawn.life, 200)
        self.assertTrue(spawn.invert_x)
        self.assertFalse(spawn.random_x)

    def test_random_timeline_coordinate_is_not_made_nominal(self):
        instruction = timeline_spawn(
            address=0x1000,
            time=1462,
            sub_id=1,
            opcode=4,
            x=-999.0,
            y=160.0,
            life=200,
        )
        spawn = decode_enemy_spawn(instruction)
        self.assertTrue(spawn.random_x)
        self.assertFalse(spawn.random_y)

    def test_low_life_emitter_is_prepositioned_before_nearer_high_life_one(self):
        state = snapshot(timeline_instructions=(
            timeline_spawn(
                address=0x1000,
                time=1442,
                sub_id=0,
                opcode=0,
                x=256.0,
                y=-48.0,
                life=900,
            ),
            timeline_spawn(
                address=0x2000,
                time=1462,
                sub_id=1,
                opcode=0,
                x=-32.0,
                y=160.0,
                life=200,
            ),
        ))
        target = suppression_target(state)
        self.assertIsNotNone(target)
        self.assertEqual(target.x, MOVEMENT_LEFT)
        self.assertEqual(target.deadline, 1462)
        self.assertEqual(target.life, 200)
        self.assertEqual(target.kill_latency, 3)

    def test_source_boss_subroutine_is_not_an_attack_target(self):
        instruction = timeline_spawn(
            address=0x2000,
            time=1462,
            sub_id=1,
            opcode=0,
            x=-32.0,
            y=160.0,
            life=200,
        )
        state = snapshot(
            timeline_instructions=(instruction,),
            timeline_emitter_subs=(1,),
            timeline_boss_subs=(1,),
        )
        self.assertIsNone(suppression_target(state))

    def test_future_spawn_waits_until_one_full_reposition_can_matter(self):
        instruction = timeline_spawn(
            address=0x2000,
            time=690,
            sub_id=1,
            opcode=0,
            x=-32.0,
            y=160.0,
            life=200,
        )
        state = snapshot(
            frame=442,
            timeline_time=442,
            x=180.0,
            timeline_instructions=(instruction,),
            timeline_emitter_subs=(1,),
        )
        self.assertIsNone(suppression_target(state))

    def test_attack_refines_only_the_supplied_survival_tie(self):
        candidates = (
            SafeAction(ACTIONS[0], 10.0, 331.0, 430.0),
            SafeAction(ACTIONS[3], 10.0, 329.0, 430.0),
            SafeAction(ACTIONS[4], 10.0, 333.0, 430.0),
        )
        target = suppression_target(snapshot(timeline_instructions=(
            timeline_spawn(
                address=0x2000,
                time=1462,
                sub_id=1,
                opcode=0,
                x=-32.0,
                y=160.0,
                life=200,
            ),
        )))
        allowed = frozenset((ACTIONS[0], ACTIONS[3]))
        self.assertEqual(
            preferred_suppression_actions(candidates, allowed, target),
            frozenset((ACTIONS[3],)),
        )

    def test_attack_cannot_discard_focused_correction_reserve(self):
        focused = next(
            action for action in CONTROL_ACTIONS
            if action.name == "down_right"
        )
        fast = next(
            action for action in CONTROL_ACTIONS
            if action.name == "down_fast"
        )
        candidates = (
            SafeAction(focused, 2.075, 335.0, 366.0),
            SafeAction(fast, 0.405, 334.0, 368.0),
        )
        target = suppression_target(snapshot(timeline_instructions=(
            timeline_spawn(
                address=0x2000,
                time=1379,
                sub_id=1,
                opcode=0,
                x=192.0,
                y=160.0,
                life=200,
            ),
        )))

        self.assertEqual(
            preferred_suppression_actions(
                candidates,
                frozenset((focused, fast)),
                target,
            ),
            frozenset((focused,)),
        )


if __name__ == "__main__":
    unittest.main()
