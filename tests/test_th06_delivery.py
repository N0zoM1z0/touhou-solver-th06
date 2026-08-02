import os
import unittest

from th06.input_lease import (
    changed_action_delivery_supported,
    required_changed_action_delivery_delay,
)
from th06.kernels.safety import NativeSafetyKernel
from th06.model import ACTION_BY_VECTOR, BUTTON_FOCUS, Bullet, Snapshot
from th06.safety import certify_actions
from th06.solver import HARD_SAFETY_HORIZON, Solver


LEFT = ACTION_BY_VECTOR[(-1, 0)]
STAY = ACTION_BY_VECTOR[(0, 0)]


def delivery_snapshot(*bullets: Bullet) -> Snapshot:
    return Snapshot(
        frame=1,
        stage=1,
        player_state=0,
        x=192.0,
        y=380.0,
        half_width=1.25,
        half_height=1.25,
        normal_speed=4.0,
        focus_speed=2.0,
        normal_diagonal_speed=2.8284270763397217,
        focus_diagonal_speed=1.4142135381698608,
        input_mask=BUTTON_FOCUS,
        bullets=tuple(bullets),
        lasers=(),
        enemies=(),
        despawning_bullets=(),
        replay_or_demo=False,
        in_menu=False,
        time_stopped=False,
        frame_multiplier=1.0,
        bullet_read_retries=0,
        laser_count=0,
    )


class DeliveryAuthorityTests(unittest.TestCase):
    def test_publication_bound_is_derived_from_measured_age(self):
        self.assertEqual(
            tuple(required_changed_action_delivery_delay(age) for age in range(3)),
            (3, 4, 5),
        )
        self.assertTrue(changed_action_delivery_supported(0, STAY, LEFT, 3))
        self.assertFalse(changed_action_delivery_supported(1, STAY, LEFT, 3))
        self.assertTrue(changed_action_delivery_supported(1, STAY, LEFT, 4))
        self.assertTrue(changed_action_delivery_supported(2, STAY, STAY, 3))

    def test_selected_extension_rejects_a_delay_four_collision(self):
        state = delivery_snapshot(
            Bullet(177.5, 372.5, 4.0, 1.0, 2.0, 2.0, 1)
        )
        self.assertTrue(certify_actions(
            state,
            HARD_SAFETY_HORIZON,
            delivery_delays=(0, 1, 2, 3),
            actions=(LEFT,),
        ))
        self.assertFalse(Solver().selected_delivery_safe(state, LEFT, 4))

    @unittest.skipUnless(os.name == "nt", "native delivery kernel requires Windows")
    def test_native_selected_extension_matches_reference(self):
        state = delivery_snapshot(
            Bullet(177.5, 372.5, 4.0, 1.0, 2.0, 2.0, 1)
        )
        kernel = NativeSafetyKernel()
        hard = kernel.certify_selected(
            state,
            HARD_SAFETY_HORIZON,
            (LEFT,),
            collision_margin=0.35,
        )
        extended = kernel.certify_selected_extended_delivery(
            state,
            HARD_SAFETY_HORIZON,
            (LEFT,),
            collision_margin=0.35,
        )

        self.assertTrue(hard)
        self.assertFalse(extended)


if __name__ == "__main__":
    unittest.main()
