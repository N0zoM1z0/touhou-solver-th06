import unittest
from unittest import mock

from th06.model import ACTIONS, SafeAction, Snapshot
from th06.solver import HARD_SAFETY_HORIZON, Solver


def snapshot() -> Snapshot:
    return Snapshot(
        frame=100,
        stage=1,
        player_state=0,
        x=192.0,
        y=380.0,
        half_width=1.25,
        half_height=1.25,
        normal_speed=4.0,
        focus_speed=2.0,
        normal_diagonal_speed=2.828427,
        focus_diagonal_speed=1.414214,
        frame_multiplier=1.0,
        input_mask=0x04,
        bullets=(),
        laser_count=0,
        in_menu=False,
        time_stopped=False,
        replay_or_demo=False,
    )


class MultisegmentPolicyTests(unittest.TestCase):
    def test_policy_volume_ranks_only_hard_certified_actions(self):
        state = snapshot()
        stay, up, down = ACTIONS[:3]
        certified = tuple(
            SafeAction(action, 10.0, state.x, state.y)
            for action in (stay, up, down)
        )
        class Kernel:
            def __init__(self):
                self.calls = mock.Mock(return_value={
                    stay: 4,
                    up: 9,
                    down: 3,
                    ACTIONS[4]: 99,
                })

            def nominal_policy_counts(self, *args, **kwargs):
                return self.calls(*args, **kwargs)

        kernel = Kernel()
        solver = Solver()
        solver.kernel = kernel

        durable = solver._multisegment_durable(
            state,
            certified,
            HARD_SAFETY_HORIZON * 3,
        )

        self.assertEqual(durable, frozenset((up,)))
        kernel.calls.assert_called_once_with(
            state,
            certified,
            HARD_SAFETY_HORIZON,
            HARD_SAFETY_HORIZON * 3,
            collision_margin=0.35,
        )

    def test_policy_volume_never_becomes_action_authority(self):
        state = snapshot()
        certified = (
            SafeAction(ACTIONS[0], 10.0, state.x, state.y),
            SafeAction(ACTIONS[1], 10.0, state.x, state.y),
        )
        solver = Solver()
        class Kernel:
            def nominal_policy_counts(self, *_args, **_kwargs):
                return {ACTIONS[0]: 0, ACTIONS[1]: 0}

        solver.kernel = Kernel()

        self.assertEqual(
            solver._multisegment_durable(
                state,
                certified,
                HARD_SAFETY_HORIZON * 3,
            ),
            frozenset(),
        )


if __name__ == "__main__":
    unittest.main()
