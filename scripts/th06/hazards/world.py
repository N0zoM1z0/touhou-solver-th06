"""One compact world forecast for source-defined bullet births."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Literal

from ..model import Bullet, EnemySpawner, Snapshot
from .births import UnsupportedBirthModel
from .bullets import hazard_boxes, radial_hazard_box
from .ecl import forecast_ecl_births
from .rng import RngState


class ForecastDeadlineExceeded(RuntimeError):
    """The caller's budget expired before a complete forecast existed."""


def _check_deadline(deadline: float | None) -> None:
    if deadline is not None and time.perf_counter() >= deadline:
        raise ForecastDeadlineExceeded


@dataclass(frozen=True)
class WorldBirthForecast:
    births: tuple[tuple[Bullet, ...], ...]
    hazards: tuple[tuple[tuple[float, float, float, float], ...], ...]
    covered_frames: int
    reason: str = ""
    body_hazards: tuple[tuple[tuple[float, float, float, float], ...], ...] = ()
    continuation: "WorldForecastContinuation | None" = None


@dataclass(frozen=True)
class WorldForecastContinuation:
    emitters: tuple[EnemySpawner, ...]
    rng_seed: int
    rng_generation: int
    framewise: bool


def _project_hazards(
    births: list[list[Bullet]],
    radial: bool,
    deadline: float | None = None,
) -> tuple[tuple[tuple[float, float, float, float], ...], ...]:
    frames: list[list[tuple[float, float, float, float]]] = [
        [] for _ in births
    ]
    for birth_frame, bullets in enumerate(births):
        _check_deadline(deadline)
        remaining = len(frames) - birth_frame
        for bullet in bullets:
            _check_deadline(deadline)
            hazards = (
                (
                    radial_hazard_box(bullet, age)
                    for age in range(1, remaining + 1)
                )
                if radial
                else hazard_boxes(bullet, remaining)
            )
            for frame_index, hazard in enumerate(hazards, birth_frame):
                frames[frame_index].append(hazard)
    return tuple(tuple(frame) for frame in frames)


def _forecast_nominal_from_state(
    snapshot: Snapshot,
    player_positions: tuple[tuple[float, float], ...],
    emitters: tuple[EnemySpawner, ...],
    rng: RngState,
    *,
    framewise: bool,
    deadline: float | None = None,
) -> WorldBirthForecast:
    births: list[list[Bullet]] = [[] for _ in player_positions]
    bodies: list[list[tuple[float, float, float, float]]] = [
        [] for _ in player_positions
    ]
    if not framewise:
        if not emitters:
            return WorldBirthForecast(
                tuple(tuple(frame) for frame in births),
                _project_hazards(births, False, deadline),
                len(player_positions),
                body_hazards=tuple(tuple(frame) for frame in bodies),
                continuation=WorldForecastContinuation(
                    (), rng.seed, rng.generation_count, False
                ),
            )
        if len(emitters) != 1:
            raise ValueError("batched nominal continuation needs one emitter")
        emitter = emitters[0]
        _check_deadline(deadline)
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
                radial_births=False,
                # The original single-emitter path intentionally assumes no
                # unknown future player damage. Preserve that exact contract
                # when an already-started forecast is extended.
                model_player_damage=False,
            )
        except UnsupportedBirthModel as error:
            return WorldBirthForecast(
                tuple(tuple(frame) for frame in births),
                _project_hazards(births, False, deadline),
                0,
                f"emitter {emitter.slot}: {error}",
            )
        _check_deadline(deadline)
        for frame_index, frame_births in enumerate(forecast.births):
            births[frame_index].extend(frame_births)
        for frame_index, frame_bodies in enumerate(forecast.body_hazards):
            bodies[frame_index].extend(frame_bodies)
        next_emitters = (
            (forecast.next_spawner,)
            if forecast.next_spawner is not None
            else ()
        )
        continuation = (
            WorldForecastContinuation(
                next_emitters,
                rng.seed,
                rng.generation_count,
                False,
            )
            if (
                forecast.covered_frames == len(player_positions)
                and (
                    forecast.next_spawner is not None
                    or forecast.finished
                )
            )
            else None
        )
        return WorldBirthForecast(
            tuple(tuple(frame) for frame in births),
            _project_hazards(births, False, deadline),
            forecast.covered_frames,
            forecast.reason,
            tuple(tuple(frame) for frame in bodies),
            continuation,
        )

    for frame_index, player in enumerate(player_positions):
        next_emitters: list[EnemySpawner] = []
        stop_reason = ""
        for emitter in emitters:
            _check_deadline(deadline)
            try:
                forecast = forecast_ecl_births(
                    emitter,
                    (player,),
                    snapshot.difficulty,
                    snapshot.rank,
                    snapshot.bullet_sizes,
                    snapshot.frame_multiplier,
                    rng,
                    allow_player_variables=True,
                    radial_births=False,
                )
            except UnsupportedBirthModel as error:
                return WorldBirthForecast(
                    tuple(tuple(frame) for frame in births),
                    _project_hazards(births, False, deadline),
                    frame_index,
                    f"emitter {emitter.slot}: {error}",
                )
            if forecast.covered_frames < 1:
                return WorldBirthForecast(
                    tuple(tuple(frame) for frame in births),
                    _project_hazards(births, False, deadline),
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
        _check_deadline(deadline)
        if stop_reason:
            return WorldBirthForecast(
                tuple(tuple(frame) for frame in births),
                _project_hazards(births, False, deadline),
                frame_index + 1,
                stop_reason,
            )
        emitters = tuple(next_emitters)

    return WorldBirthForecast(
        tuple(tuple(frame) for frame in births),
        _project_hazards(births, False, deadline),
        len(player_positions),
        body_hazards=tuple(tuple(frame) for frame in bodies),
        continuation=WorldForecastContinuation(
            emitters,
            rng.seed,
            rng.generation_count,
            True,
        ),
    )


def extend_nominal_world_births(
    snapshot: Snapshot,
    prefix: WorldBirthForecast,
    player_positions: tuple[tuple[float, float], ...],
    *,
    deadline: float | None = None,
) -> WorldBirthForecast:
    """Extend one complete nominal prefix from its exact ECL/RNG state."""
    if prefix.continuation is None:
        raise ValueError("nominal world prefix has no exact continuation")
    if prefix.covered_frames != len(prefix.births):
        raise ValueError("cannot extend a partially covered nominal prefix")
    continuation = prefix.continuation
    tail = _forecast_nominal_from_state(
        snapshot,
        player_positions,
        continuation.emitters,
        RngState(
            continuation.rng_seed,
            continuation.rng_generation,
        ),
        framewise=continuation.framewise,
        deadline=deadline,
    )
    births = prefix.births + tail.births
    bodies = prefix.body_hazards + tail.body_hazards
    prefix_horizon = len(prefix.births)
    total_horizon = len(births)
    hazards = [list(frame) for frame in prefix.hazards]
    hazards.extend([] for _ in tail.births)
    # Preserve every already-published prefix box. Only project older births
    # into the appended frames, then append the tail's newly born bullets in
    # the same source birth-frame order as one full forecast.
    for birth_frame, frame_births in enumerate(prefix.births):
        _check_deadline(deadline)
        remaining = total_horizon - birth_frame
        for bullet in frame_births:
            projected = hazard_boxes(bullet, remaining)
            for frame_index in range(prefix_horizon, total_horizon):
                hazards[frame_index].append(
                    projected[frame_index - birth_frame]
                )
    for frame_index, frame_hazards in enumerate(
        tail.hazards,
        prefix_horizon,
    ):
        hazards[frame_index].extend(frame_hazards)
    return WorldBirthForecast(
        births,
        tuple(tuple(frame) for frame in hazards),
        prefix.covered_frames + tail.covered_frames,
        tail.reason,
        bodies,
        tail.continuation,
    )


def forecast_world_births(
    snapshot: Snapshot,
    player_positions: tuple[tuple[float, float], ...],
    rng_mode: Literal["fail-closed", "nominal"] = "fail-closed",
    *,
    deadline: float | None = None,
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
            _check_deadline(deadline)
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
        _check_deadline(deadline)
        return WorldBirthForecast(
            tuple(tuple(frame) for frame in births),
            _project_hazards(births, True, deadline),
            covered_frames,
            reason,
            tuple(tuple(frame) for frame in bodies),
        )
    return _forecast_nominal_from_state(
        snapshot,
        player_positions,
        emitters,
        RngState(snapshot.rng_seed, snapshot.rng_generation),
        framewise=len(emitters) != 1,
        deadline=deadline,
    )
