"""One compact world forecast for source-defined bullet births."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..model import Bullet, EnemySpawner, Snapshot
from .births import UnsupportedBirthModel
from .bullets import hazard_box, radial_hazard_box
from .ecl import forecast_ecl_births
from .rng import RngState


@dataclass(frozen=True)
class WorldBirthForecast:
    births: tuple[tuple[Bullet, ...], ...]
    hazards: tuple[tuple[tuple[float, float, float, float], ...], ...]
    covered_frames: int
    reason: str = ""
    body_hazards: tuple[tuple[tuple[float, float, float, float], ...], ...] = ()


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
    bodies: list[list[tuple[float, float, float, float]]] = [
        [] for _ in player_positions
    ]
    emitters = tuple(sorted(snapshot.spawners, key=lambda item: item.slot))
    if rng_mode == "fail-closed":
        enemy_kill_all_is_noop = not any(
            not emitter.is_boss and emitter.death_callback_sub >= 0
            for emitter in emitters
        )
        covered_frames = len(player_positions)
        reason = ""
        for emitter in emitters:
            try:
                forecast = forecast_ecl_births(
                    emitter,
                    player_positions,
                    snapshot.difficulty,
                    snapshot.rank,
                    snapshot.bullet_sizes,
                    snapshot.frame_multiplier,
                    allow_player_variables=False,
                    radial_births=True,
                    abstract_rng=True,
                    enemy_kill_all_is_noop=enemy_kill_all_is_noop,
                )
            except UnsupportedBirthModel as error:
                forecast = None
                emitter_coverage = 0
                emitter_reason = str(error)
            else:
                emitter_coverage = forecast.covered_frames
                emitter_reason = forecast.reason
                for frame_index, frame_births in enumerate(forecast.births):
                    births[frame_index].extend(frame_births)
                for frame_index, frame_bodies in enumerate(forecast.body_hazards):
                    bodies[frame_index].extend(frame_bodies)
            if emitter_coverage < covered_frames:
                covered_frames = emitter_coverage
                reason = f"emitter {emitter.slot}: {emitter_reason}"
        return WorldBirthForecast(
            tuple(tuple(frame) for frame in births),
            _project_hazards(births, True),
            covered_frames,
            reason,
            tuple(tuple(frame) for frame in bodies),
        )
    rng = (
        RngState(snapshot.rng_seed, snapshot.rng_generation)
        if rng_mode == "nominal"
        else None
    )
    radial = False

    # With one emitter, frame-first/slot-second order is identical to one
    # multi-frame ECL execution. Keep its compiled control state in the ECL
    # interpreter instead of rebuilding and copying it once per frame. The
    # runtime RNG object and player-position sequence remain exact inputs.
    batch_emitter = emitters[0] if len(emitters) == 1 else None
    if batch_emitter is not None:
        emitter = batch_emitter
        try:
            forecast = forecast_ecl_births(
                emitter,
                player_positions,
                snapshot.difficulty,
                snapshot.rank,
                snapshot.bullet_sizes,
                snapshot.frame_multiplier,
                rng,
                allow_player_variables=True,
                radial_births=radial,
                # Nominal proposal forecasting already assumes no unknown
                # future player damage: the old per-frame path restored the
                # captured life before each next frame. Make that source
                # boundary explicit so one emitter can retain its compiled
                # ECL state across the whole horizon. Timer callbacks, exact
                # RNG, and per-frame player positions remain live inputs.
                model_player_damage=False,
            )
        except UnsupportedBirthModel as error:
            return WorldBirthForecast(
                tuple(tuple(frame) for frame in births),
                _project_hazards(births, radial),
                0,
                f"emitter {emitter.slot}: {error}",
            )
        for frame_index, frame_births in enumerate(forecast.births):
            births[frame_index].extend(frame_births)
        for frame_index, frame_bodies in enumerate(forecast.body_hazards):
            bodies[frame_index].extend(frame_bodies)
        return WorldBirthForecast(
            tuple(tuple(frame) for frame in births),
            _project_hazards(births, radial),
            forecast.covered_frames,
            forecast.reason,
            tuple(tuple(frame) for frame in bodies),
        )

    for frame_index, player in enumerate(player_positions):
        next_emitters: list[EnemySpawner] = []
        stop_reason = ""
        for emitter in emitters:
            try:
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
            except UnsupportedBirthModel as error:
                return WorldBirthForecast(
                    tuple(tuple(frame) for frame in births),
                    _project_hazards(births, radial),
                    frame_index,
                    f"emitter {emitter.slot}: {error}",
                )
            if forecast.covered_frames < 1:
                return WorldBirthForecast(
                    tuple(tuple(frame) for frame in births),
                    _project_hazards(births, radial),
                    frame_index,
                    f"emitter {emitter.slot}: {forecast.reason}",
                )
            births[frame_index].extend(forecast.births[0])
            if forecast.body_hazards:
                bodies[frame_index].extend(forecast.body_hazards[0])
            if forecast.next_spawner is None and not forecast.finished:
                stop_reason = stop_reason or (
                    f"emitter {emitter.slot}: {forecast.reason}"
                )
            elif forecast.next_spawner is not None:
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
        body_hazards=tuple(tuple(frame) for frame in bodies),
    )
