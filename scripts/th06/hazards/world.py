"""One compact world forecast for source-defined bullet births."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

from ..model import Bullet, EnemySpawner, Snapshot
from .births import UnsupportedBirthModel
from .bullets import hazard_boxes, radial_hazard_box
from .ecl import forecast_ecl_births, source_enemy_template
from .rng import RngState
from .timeline import decode_enemy_spawn, first_world_transition


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


class _NominalRngConsumed(Exception):
    pass


class _NoRngState(RngState):
    """Abort a speculative batch at its first shared-RNG dependency."""

    def u16(self) -> int:
        raise _NominalRngConsumed


def _limit_for_uninserted_timeline(
    snapshot: Snapshot,
    forecast: WorldBirthForecast,
) -> WorldBirthForecast:
    transition = first_world_transition(
        snapshot.timeline_instructions,
        snapshot.timeline_time,
        len(forecast.births),
    )
    if transition is None:
        return forecast
    lead, instruction = transition
    if forecast.covered_frames <= lead:
        return forecast
    return WorldBirthForecast(
        forecast.births,
        forecast.hazards,
        lead,
        "uninserted stage timeline world transition "
        f"opcode {instruction.opcode} at 0x{instruction.address:08x}",
        forecast.body_hazards,
        None,
    )


def _project_hazards(
    births: list[list[Bullet]],
    radial: bool,
) -> tuple[tuple[tuple[float, float, float, float], ...], ...]:
    frames: list[list[tuple[float, float, float, float]]] = [
        [] for _ in births
    ]
    for birth_frame, bullets in enumerate(births):
        remaining = len(frames) - birth_frame
        for bullet in bullets:
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


def _forecast_hard_timeline_births(
    snapshot: Snapshot,
    player_positions: tuple[tuple[float, float], ...],
) -> WorldBirthForecast:
    """Insert deterministic timeline children into the bounded Hard world."""
    births: list[list[Bullet]] = [[] for _ in player_positions]
    bodies: list[list[tuple[float, float, float, float]]] = [
        [] for _ in player_positions
    ]
    horizon = len(player_positions)
    for instruction in snapshot.timeline_instructions:
        if instruction.time < 0:
            break
        lead = max(0, instruction.time - snapshot.timeline_time)
        if lead >= horizon:
            break
        if instruction.opcode == 10:
            return WorldBirthForecast(
                tuple(map(tuple, births)),
                _project_hazards(births, True),
                lead,
                "uninserted stage timeline boss interrupt opcode 10 "
                f"at 0x{instruction.address:08x}",
                tuple(map(tuple, bodies)),
            )
        spawn = decode_enemy_spawn(instruction)
        if spawn is None:
            if 0 <= instruction.opcode <= 7:
                return WorldBirthForecast(
                    tuple(map(tuple, births)),
                    _project_hazards(births, True),
                    lead,
                    "invalid stage timeline enemy spawn record "
                    f"at 0x{instruction.address:08x}",
                    tuple(map(tuple, bodies)),
                )
            continue
        if spawn.random_x or spawn.random_y:
            return WorldBirthForecast(
                tuple(map(tuple, births)),
                _project_hazards(births, True),
                lead,
                "random stage timeline enemy position needs a world envelope "
                f"at 0x{instruction.address:08x}",
                tuple(map(tuple, bodies)),
            )
        child = source_enemy_template(
            snapshot.timeline_ecl_program,
            snapshot.ecl_subroutines,
            spawn.sub_id,
            spawn.x,
            spawn.y,
            spawn.life if spawn.life is not None else -1,
        )
        if child is None:
            return WorldBirthForecast(
                tuple(map(tuple, births)),
                _project_hazards(births, True),
                lead,
                "timeline enemy ECL graph is unavailable "
                f"for sub {spawn.sub_id}",
                tuple(map(tuple, bodies)),
            )

        # SpawnEnemy executes time-zero ECL inline. The manager then starts its
        # slot loop at zero, so every timeline child receives one ordinary
        # update in the same source frame. The template's initial movement is
        # zero, making the first forecast step equivalent to the inline call.
        inline = forecast_ecl_births(
            child,
            (player_positions[lead],),
            snapshot.difficulty,
            snapshot.rank,
            snapshot.bullet_sizes,
            snapshot.frame_multiplier,
            allow_player_variables=False,
            radial_births=True,
            abstract_rng=True,
            # Other timeline children in this forecast can install callbacks;
            # do not prove ENEMYKILLALL neutral from only the live root.
            enemy_kill_all_is_noop=False,
            model_player_damage=False,
        )
        if inline.covered_frames < 1:
            return WorldBirthForecast(
                tuple(map(tuple, births)),
                _project_hazards(births, True),
                lead,
                f"timeline emitter {spawn.sub_id}: {inline.reason}",
                tuple(map(tuple, bodies)),
            )
        births[lead].extend(inline.births[0])
        if inline.next_spawner is None:
            if inline.finished:
                continue
            return WorldBirthForecast(
                tuple(map(tuple, births)),
                _project_hazards(births, True),
                lead + 1,
                f"timeline emitter {spawn.sub_id}: {inline.reason}",
                tuple(map(tuple, bodies)),
            )

        child = replace(
            inline.next_spawner,
            invert_x=spawn.invert_x,
            life=(
                spawn.life
                if spawn.life is not None
                else inline.next_spawner.life
            ),
        )
        ordinary = forecast_ecl_births(
            child,
            player_positions[lead:],
            snapshot.difficulty,
            snapshot.rank,
            snapshot.bullet_sizes,
            snapshot.frame_multiplier,
            allow_player_variables=False,
            radial_births=True,
            abstract_rng=True,
            enemy_kill_all_is_noop=False,
        )
        for offset, frame_births in enumerate(ordinary.births, lead):
            births[offset].extend(frame_births)
        for offset, frame_bodies in enumerate(ordinary.body_hazards, lead):
            bodies[offset].extend(frame_bodies)
        if ordinary.covered_frames < horizon - lead:
            return WorldBirthForecast(
                tuple(map(tuple, births)),
                _project_hazards(births, True),
                lead + ordinary.covered_frames,
                f"timeline emitter {spawn.sub_id}: {ordinary.reason}",
                tuple(map(tuple, bodies)),
            )
        if ordinary.next_spawner is None and not ordinary.finished:
            return WorldBirthForecast(
                tuple(map(tuple, births)),
                _project_hazards(births, True),
                horizon,
                f"timeline emitter {spawn.sub_id}: persistent state branches",
                tuple(map(tuple, bodies)),
            )
    return WorldBirthForecast(
        tuple(map(tuple, births)),
        _project_hazards(births, True),
        horizon,
        body_hazards=tuple(map(tuple, bodies)),
    )


def _forecast_nominal_without_shared_rng(
    snapshot: Snapshot,
    player_positions: tuple[tuple[float, float], ...],
    emitters: tuple[EnemySpawner, ...],
    rng: RngState,
) -> WorldBirthForecast | None:
    """Batch independent emitters only after proving that none reads RNG.

    EnemyManager normally advances ECL frame-first and slot-second because all
    emitters share one RNG.  A no-RNG interval is commutative: each captured
    emitter can advance across the whole interval once.  Unsupported global
    behavior, incomplete coverage, or the first RNG read discards this fast
    path and leaves the ordinary framewise model authoritative.
    """
    births: list[list[Bullet]] = [[] for _ in player_positions]
    bodies: list[list[tuple[float, float, float, float]]] = [
        [] for _ in player_positions
    ]
    next_emitters = []
    for emitter in emitters:
        try:
            forecast = forecast_ecl_births(
                emitter,
                player_positions,
                snapshot.difficulty,
                snapshot.rank,
                snapshot.bullet_sizes,
                snapshot.frame_multiplier,
                _NoRngState(rng.seed, rng.generation_count),
                allow_player_variables=True,
                radial_births=False,
            )
        except (_NominalRngConsumed, UnsupportedBirthModel):
            return None
        if (
            forecast.covered_frames != len(player_positions)
            or (
                forecast.next_spawner is None
                and not forecast.finished
            )
        ):
            return None
        for frame_index, frame_births in enumerate(forecast.births):
            births[frame_index].extend(frame_births)
        for frame_index, frame_bodies in enumerate(forecast.body_hazards):
            bodies[frame_index].extend(frame_bodies)
        if forecast.next_spawner is not None:
            next_emitters.append(forecast.next_spawner)
    return WorldBirthForecast(
        tuple(tuple(frame) for frame in births),
        _project_hazards(births, False),
        len(player_positions),
        body_hazards=tuple(tuple(frame) for frame in bodies),
        continuation=WorldForecastContinuation(
            tuple(next_emitters),
            rng.seed,
            rng.generation_count,
            True,
        ),
    )


def _forecast_nominal_from_state(
    snapshot: Snapshot,
    player_positions: tuple[tuple[float, float], ...],
    emitters: tuple[EnemySpawner, ...],
    rng: RngState,
    *,
    framewise: bool,
) -> WorldBirthForecast:
    births: list[list[Bullet]] = [[] for _ in player_positions]
    bodies: list[list[tuple[float, float, float, float]]] = [
        [] for _ in player_positions
    ]
    if not framewise:
        if not emitters:
            return WorldBirthForecast(
                tuple(tuple(frame) for frame in births),
                _project_hazards(births, False),
                len(player_positions),
                body_hazards=tuple(tuple(frame) for frame in bodies),
                continuation=WorldForecastContinuation(
                    (), rng.seed, rng.generation_count, False
                ),
            )
        if len(emitters) != 1:
            raise ValueError("batched nominal continuation needs one emitter")
        emitter = emitters[0]
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
                _project_hazards(births, False),
                0,
                f"emitter {emitter.slot}: {error}",
            )
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
            _project_hazards(births, False),
            forecast.covered_frames,
            forecast.reason,
            tuple(tuple(frame) for frame in bodies),
            continuation,
        )

    batched = _forecast_nominal_without_shared_rng(
        snapshot, player_positions, emitters, rng
    )
    if batched is not None:
        return batched

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
                    allow_player_variables=True,
                    radial_births=False,
                )
            except UnsupportedBirthModel as error:
                return WorldBirthForecast(
                    tuple(tuple(frame) for frame in births),
                    _project_hazards(births, False),
                    frame_index,
                    f"emitter {emitter.slot}: {error}",
                )
            if forecast.covered_frames < 1:
                return WorldBirthForecast(
                    tuple(tuple(frame) for frame in births),
                    _project_hazards(births, False),
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
                _project_hazards(births, False),
                frame_index + 1,
                stop_reason,
            )
        emitters = tuple(next_emitters)

    return WorldBirthForecast(
        tuple(tuple(frame) for frame in births),
        _project_hazards(births, False),
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
        timeline = _forecast_hard_timeline_births(
            snapshot,
            player_positions,
        )
        for frame_index, frame_births in enumerate(timeline.births):
            births[frame_index].extend(frame_births)
        for frame_index, frame_bodies in enumerate(timeline.body_hazards):
            bodies[frame_index].extend(frame_bodies)
        if timeline.covered_frames < covered_frames:
            covered_frames = timeline.covered_frames
            reason = timeline.reason
        return WorldBirthForecast(
            tuple(tuple(frame) for frame in births),
            _project_hazards(births, True),
            covered_frames,
            reason,
            tuple(tuple(frame) for frame in bodies),
        )
    return _limit_for_uninserted_timeline(
        snapshot,
        _forecast_nominal_from_state(
            snapshot,
            player_positions,
            emitters,
            RngState(snapshot.rng_seed, snapshot.rng_generation),
            framewise=len(emitters) != 1,
        ),
    )
