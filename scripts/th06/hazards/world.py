"""One compact world forecast for source-defined bullet births."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..model import Bullet, EnemySpawner, Snapshot
from .bullets import hazard_box, radial_hazard_box
from .ecl import forecast_ecl_births
from .rng import RngState


@dataclass(frozen=True)
class WorldBirthForecast:
    births: tuple[tuple[Bullet, ...], ...]
    hazards: tuple[tuple[tuple[float, float, float, float], ...], ...]
    covered_frames: int
    reason: str = ""


def _project_hazards(
    births: list[list[Bullet]],
    radial: bool,
) -> tuple[tuple[tuple[float, float, float, float], ...], ...]:
    frames: list[list[tuple[float, float, float, float]]] = [
        [] for _ in births
    ]
    for birth_frame, bullets in enumerate(births):
        for frame_index in range(birth_frame, len(frames)):
            age = frame_index - birth_frame + 1
            frames[frame_index].extend(
                (radial_hazard_box if radial else hazard_box)(bullet, age)
                for bullet in bullets
            )
    return tuple(tuple(frame) for frame in frames)


def forecast_world_births(
    snapshot: Snapshot,
    player_positions: tuple[tuple[float, float], ...],
    rng_mode: Literal["fail-closed", "nominal"] = "fail-closed",
) -> WorldBirthForecast:
    """Advance emitters frame-first and slot-second, matching EnemyManager.

    ``nominal`` reproduces the observed RNG stream for validation and proposal
    ranking. Hard authority uses ``fail-closed``: reaching a future random
    consumer ends coverage instead of assuming that no other subsystem has
    advanced the global RNG.
    """
    if rng_mode not in ("fail-closed", "nominal"):
        raise ValueError(f"unknown RNG mode {rng_mode}")
    births: list[list[Bullet]] = [[] for _ in player_positions]
    emitters = tuple(sorted(snapshot.spawners, key=lambda item: item.slot))
    rng = (
        RngState(snapshot.rng_seed, snapshot.rng_generation)
        if rng_mode == "nominal"
        else None
    )
    radial = rng_mode == "fail-closed"

    for frame_index, player in enumerate(player_positions):
        next_emitters: list[EnemySpawner] = []
        stop_reason = ""
        for emitter in emitters:
            forecast = forecast_ecl_births(
                emitter,
                (player,),
                snapshot.difficulty,
                snapshot.rank,
                snapshot.bullet_sizes,
                snapshot.frame_multiplier,
                rng,
                allow_player_variables=rng_mode == "nominal",
                radial_births=radial,
            )
            if forecast.covered_frames < 1:
                return WorldBirthForecast(
                    tuple(tuple(frame) for frame in births),
                    _project_hazards(births, radial),
                    frame_index,
                    f"emitter {emitter.slot}: {forecast.reason}",
                )
            births[frame_index].extend(forecast.births[0])
            if forecast.next_spawner is None:
                stop_reason = stop_reason or (
                    f"emitter {emitter.slot}: {forecast.reason}"
                )
            else:
                next_emitters.append(forecast.next_spawner)
        if stop_reason:
            return WorldBirthForecast(
                tuple(tuple(frame) for frame in births),
                _project_hazards(births, radial),
                frame_index + 1,
                stop_reason,
            )
        emitters = tuple(next_emitters)

    return WorldBirthForecast(
        tuple(tuple(frame) for frame in births),
        _project_hazards(births, radial),
        len(player_positions),
    )
