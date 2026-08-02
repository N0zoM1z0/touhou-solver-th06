"""Compare one physical frame transition with periodic birth predictions."""

from __future__ import annotations

from dataclasses import dataclass
import math

from .hazards.ecl import forecast_ecl_births
from .hazards.rng import RngState
from .model import Bullet, Snapshot


@dataclass(frozen=True)
class BirthParity:
    supported: bool
    predicted: int
    observed: int
    matched: int
    max_position_error: float
    max_angle_error: float
    max_speed_error: float
    reason: str = ""


def _same_tick_position(bullet: Bullet) -> tuple[float, float]:
    factor = 0.5 if bullet.state == 2 else 0.4 if bullet.state == 3 else 1.0 / 3.0 if bullet.state == 4 else 1.0
    return bullet.x + bullet.vx * factor, bullet.y + bullet.vy * factor


def _newborns(previous: Snapshot, current: Snapshot) -> tuple[Bullet, ...]:
    previous_slots = {
        bullet.slot
        for bullet in previous.bullets + previous.despawning_bullets
        if bullet.slot >= 0
    }
    return tuple(
        bullet for bullet in current.bullets
        if (
            bullet.slot not in previous_slots
            or bullet.state in (2, 3, 4) and bullet.timer <= 1
        )
    )


def compare_births(previous: Snapshot, current: Snapshot) -> BirthParity:
    """Measure exact count/geometry parity for one adjacent game frame."""
    if previous.stage != current.stage or current.frame - previous.frame != 1:
        return BirthParity(False, 0, 0, 0, 0.0, 0.0, 0.0, "non-adjacent frames")
    predicted: list[Bullet] = []
    rng = RngState(previous.rng_seed, previous.rng_generation)
    for spawner in sorted(previous.spawners, key=lambda item: item.slot):
        forecast = forecast_ecl_births(
            spawner,
            ((current.x, current.y),),
            previous.difficulty,
            previous.rank,
            previous.bullet_sizes,
            previous.frame_multiplier,
            rng,
        )
        if forecast.covered_frames < 1:
            return BirthParity(
                False, len(predicted), 0, 0, 0.0, 0.0, 0.0, forecast.reason
            )
        predicted.extend(forecast.births[0])
    free_slots = max(
        0,
        640 - len(previous.bullets) - len(previous.despawning_bullets),
    )
    predicted = predicted[:free_slots]
    observed = list(_newborns(previous, current))
    unmatched = set(range(len(observed)))
    position_errors: list[float] = []
    angle_errors: list[float] = []
    speed_errors: list[float] = []
    for expected in predicted:
        expected_x, expected_y = _same_tick_position(expected)
        if not unmatched:
            break
        best = min(
            unmatched,
            key=lambda index: (
                math.hypot(
                    observed[index].x - expected_x,
                    observed[index].y - expected_y,
                )
                + abs(math.remainder(
                    observed[index].angle - expected.angle,
                    math.tau,
                ))
                + abs(observed[index].speed - expected.speed)
            ),
        )
        actual = observed[best]
        unmatched.remove(best)
        position_errors.append(math.hypot(
            actual.x - expected_x,
            actual.y - expected_y,
        ))
        angle_errors.append(abs(math.remainder(
            actual.angle - expected.angle,
            math.tau,
        )))
        speed_errors.append(abs(actual.speed - expected.speed))
    matched = min(len(predicted), len(observed))
    return BirthParity(
        True,
        len(predicted),
        len(observed),
        matched,
        max(position_errors, default=0.0),
        max(angle_errors, default=0.0),
        max(speed_errors, default=0.0),
    )


# Compatibility name for the first periodic-only corpus experiments.
compare_periodic_births = compare_births
