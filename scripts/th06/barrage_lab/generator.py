"""Deterministic dense cases composed from real TH06 ECL volleys."""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
import random
import struct
from typing import Mapping

from ..hazards.births import spawn_pattern
from ..hazards.rng import RngState
from ..model import (
    BUTTON_FOCUS,
    CONTROL_ACTIONS,
    Bullet,
    BulletPattern,
    Snapshot,
    action_from_input,
)
from .assets import EclBulletOpcode


# BulletManager::AddedCallback derives these full kill-box sizes from the ten
# source bullet types. Native sensing divides the D3DX dimensions by two.
SOURCE_BULLET_HALF_SIZES = (
    2.0, 3.0, 2.0, 3.0, 2.5, 2.0, 8.0, 5.5, 4.5, 16.0,
)
SOURCE_DYNAMIC_FLAGS = 0xDF1
SOURCE_EXACT_DYNAMIC_FLAGS = 0x071
SOURCE_BULLET_CAP = 640
SOURCE_PLAYER_LEFT = 8.0
SOURCE_PLAYER_RIGHT = 376.0
SOURCE_PLAYER_TOP = 16.0
SOURCE_PLAYER_BOTTOM = 432.0


def stress_player_position(
    seed: int, placement: str
) -> tuple[float, float] | None:
    """Choose deterministic source-valid movement-boundary stress points."""
    edges = (
        (SOURCE_PLAYER_LEFT, 224.0),
        (SOURCE_PLAYER_RIGHT, 224.0),
        (192.0, SOURCE_PLAYER_TOP),
        (192.0, SOURCE_PLAYER_BOTTOM),
    )
    corners = (
        (SOURCE_PLAYER_LEFT, SOURCE_PLAYER_TOP),
        (SOURCE_PLAYER_RIGHT, SOURCE_PLAYER_TOP),
        (SOURCE_PLAYER_LEFT, SOURCE_PLAYER_BOTTOM),
        (SOURCE_PLAYER_RIGHT, SOURCE_PLAYER_BOTTOM),
    )
    if placement == "interior":
        return None
    if placement == "edge":
        return edges[seed % len(edges)]
    if placement == "corner":
        return corners[seed % len(corners)]
    if placement == "mixed":
        family = seed % 3
        if family == 0:
            return None
        values = edges if family == 1 else corners
        return values[(seed // 3) % len(values)]
    raise ValueError(f"unknown player placement {placement!r}")


def _f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def _input_mask(action) -> int:
    mask = BUTTON_FOCUS if action.focused else 0
    if action.dx < 0:
        mask |= 0x40
    elif action.dx > 0:
        mask |= 0x80
    if action.dy < 0:
        mask |= 0x10
    elif action.dy > 0:
        mask |= 0x20
    return mask


def _advance_fired(bullet: Bullet, age: int, slot: int) -> Bullet:
    x, y = _f32(bullet.x), _f32(bullet.y)
    vx, vy = _f32(bullet.vx), _f32(bullet.vy)
    angle = _f32(bullet.angle)
    speed = _f32(bullet.speed)
    turn_speed = _f32(bullet.turn_speed)
    flags = bullet.ex_flags
    timer = bullet.timer
    timer_float = _f32(bullet.timer_float)
    direction_num_times = bullet.direction_num_times
    for _ in range(age):
        if flags & 0x01:
            if timer <= 16:
                deceleration = _f32(
                    5.0 - _f32(timer_float * 5.0 / 16.0)
                )
                current_speed = _f32(deceleration + speed)
                vx = _f32(math.cos(angle) * current_speed)
                vy = _f32(math.sin(angle) * current_speed)
            else:
                flags ^= 0x01
        elif flags & 0x10:
            if timer >= bullet.acceleration_duration:
                flags &= ~0x10
            else:
                vx = _f32(vx + bullet.acceleration_x)
                vy = _f32(vy + bullet.acceleration_y)
                angle = _f32(math.atan2(vy, vx))
        elif flags & 0x20:
            if timer >= bullet.acceleration_duration:
                flags &= ~0x20
            else:
                angle = _f32(math.remainder(
                    _f32(angle + bullet.curve_angular_velocity), math.tau
                ))
                speed = _f32(speed + bullet.curve_speed_acceleration)
                vx = _f32(math.cos(angle) * speed)
                vy = _f32(math.sin(angle) * speed)
        if flags & 0x40:
            if timer >= bullet.direction_interval * (direction_num_times + 1):
                direction_num_times += 1
                if direction_num_times >= bullet.direction_max_times:
                    flags &= ~0x40
                angle = _f32(angle + bullet.direction_rotation)
                speed = turn_speed
                current_speed = speed
            else:
                phase = _f32(
                    timer_float - bullet.direction_interval * direction_num_times
                )
                current_speed = _f32(
                    speed - _f32(phase * speed / bullet.direction_interval)
                )
            vx = _f32(math.cos(angle) * current_speed)
            vy = _f32(math.sin(angle) * current_speed)
        x = _f32(x + vx)
        y = _f32(y + vy)
        timer += 1
        timer_float = _f32(timer_float + 1.0)
    return replace(
        bullet,
        x=x,
        y=y,
        vx=vx,
        vy=vy,
        state=1,
        ex_flags=flags,
        angle=angle,
        speed=speed,
        direction_num_times=direction_num_times,
        timer=age,
        timer_float=float(age),
        slot=slot,
    )


def _resolved_pattern(
    opcode: EclBulletOpcode, rank: int, difficulty: int
) -> BulletPattern:
    # EnemyManager's source defaults are [-0.5, +0.5]. This is one explicit,
    # source-valid rank context; ECL-mutated rank contexts are a later rung.
    rank_speed = _f32(_f32(float(rank)) / 32.0 - 0.5)
    speed1 = opcode.speed1
    if speed1 != 0.0:
        speed1 = max(0.3, _f32(speed1 + rank_speed))
    speed2 = max(0.3, _f32(opcode.speed2 + _f32(rank_speed / 2.0)))
    half_size = SOURCE_BULLET_HALF_SIZES[opcode.sprite]
    effects = opcode.effects_for(difficulty)
    return BulletPattern(
        sprite=opcode.sprite,
        angle1=opcode.angle1,
        angle2=opcode.angle2,
        speed1=speed1,
        speed2=speed2,
        ex_floats=(
            effects.floats if effects is not None else (0.0, 0.0, 0.0, 0.0)
        ),
        ex_ints=(
            effects.ints if effects is not None else (0, 0, 0, 0)
        ),
        count1=opcode.count1,
        count2=opcode.count2,
        aim_mode=opcode.aim_mode,
        flags=opcode.flags,
        half_width=half_size,
        half_height=half_size,
    )


@dataclass(frozen=True)
class BarrageCase:
    seed: int
    target_bullets: int
    snapshot: Snapshot
    sources: tuple[tuple[str, int, int], ...]


@dataclass(frozen=True)
class RuntimeBarrageTemplate:
    """Small online state distribution used to condition source volleys."""

    player_x: float
    player_y: float
    input_mask: int
    rank: int
    target_bullets: int


def runtime_barrage_template(
    raw: Mapping[str, object], density_scale: float = 1.0,
) -> RuntimeBarrageTemplate:
    """Extract non-hazard runtime context without importing a trace codec."""
    if density_scale <= 0.0:
        raise ValueError("corpus density scale must be positive")
    x = float(raw["x"])
    y = float(raw["y"])
    if not (
        SOURCE_PLAYER_LEFT <= x <= SOURCE_PLAYER_RIGHT
        and SOURCE_PLAYER_TOP <= y <= SOURCE_PLAYER_BOTTOM
    ):
        raise ValueError("corpus player position is outside source bounds")
    raw_bullets = raw.get("bullets", ())
    if not isinstance(raw_bullets, (list, tuple)):
        raise ValueError("corpus bullets must be a sequence")
    target = max(
        1,
        min(SOURCE_BULLET_CAP, math.ceil(len(raw_bullets) * density_scale)),
    )
    return RuntimeBarrageTemplate(
        x,
        y,
        int(raw.get("input_mask", BUTTON_FOCUS)),
        int(raw.get("rank", 16)),
        target,
    )


def eligible_opcodes(
    catalogue: tuple[EclBulletOpcode, ...], difficulty: int = 2
) -> tuple[EclBulletOpcode, ...]:
    result = []
    for opcode in catalogue:
        if (
            not opcode.has_literal_arguments
            or not opcode.executes_on(difficulty)
            or opcode.flags & (
                SOURCE_DYNAMIC_FLAGS & ~SOURCE_EXACT_DYNAMIC_FLAGS
            )
        ):
            continue
        if (
            opcode.flags & (0x10 | 0x20 | 0x40)
            and opcode.effects_for(difficulty) is None
        ):
            continue
        result.append(opcode)
    return tuple(result)


def generate_barrage_case(
    catalogue: tuple[EclBulletOpcode, ...],
    seed: int,
    *,
    difficulty: int = 2,
    target_bullets: int | None = None,
    player_position: tuple[float, float] | None = None,
    runtime_template: RuntimeBarrageTemplate | None = None,
) -> BarrageCase:
    """Compose time-shifted real volleys under the source's 640-slot cap."""
    opcodes = eligible_opcodes(catalogue, difficulty)
    if not opcodes:
        raise ValueError("catalogue has no exact source volley for difficulty")
    chooser = random.Random(seed)
    th06_rng = RngState(seed & 0xFFFF, 0)
    rank = chooser.randrange(16, 33)
    player_x = _f32(chooser.uniform(40.0, 344.0))
    player_y = _f32(chooser.uniform(120.0, 416.0))
    current = chooser.choice(CONTROL_ACTIONS)
    if runtime_template is not None:
        if player_position is not None:
            raise ValueError(
                "runtime template and explicit player position are exclusive"
            )
        player_x = _f32(runtime_template.player_x)
        player_y = _f32(runtime_template.player_y)
        current = action_from_input(runtime_template.input_mask)
        rank = runtime_template.rank
    if player_position is not None:
        requested_x, requested_y = player_position
        if not (
            SOURCE_PLAYER_LEFT <= requested_x <= SOURCE_PLAYER_RIGHT
            and SOURCE_PLAYER_TOP <= requested_y <= SOURCE_PLAYER_BOTTOM
        ):
            raise ValueError("player position is outside source movement bounds")
        player_x = _f32(requested_x)
        player_y = _f32(requested_y)
    density_steps = (64, 128, 256, 384, 512, 640)
    target = (
        target_bullets
        or (
            runtime_template.target_bullets
            if runtime_template is not None
            else density_steps[seed % len(density_steps)]
        )
    )
    target = max(1, min(SOURCE_BULLET_CAP, target))
    bullets: list[Bullet] = []
    sources = []
    attempts = 0
    while len(bullets) < target and attempts < 160:
        attempts += 1
        opcode = chooser.choice(opcodes)
        pattern = _resolved_pattern(opcode, rank, difficulty)
        bearing = chooser.uniform(-math.pi, math.pi)
        radius = chooser.uniform(48.0, 210.0)
        origin = (
            _f32(min(400.0, max(-16.0, player_x + math.cos(bearing) * radius))),
            _f32(min(320.0, max(-24.0, player_y + math.sin(bearing) * radius))),
        )
        aim = (
            _f32(player_x + chooser.uniform(-32.0, 32.0)),
            _f32(player_y + chooser.uniform(-32.0, 32.0)),
        )
        volley = spawn_pattern(pattern, origin, aim, th06_rng)
        # Different real volleys may have been emitted on different updates.
        # Once fired, these selected flags have source-exact motion in the
        # current oracle rung (linear plus the deterministic 0x01 slowdown).
        age = chooser.randrange(0, 25)
        accepted = 0
        for bullet in volley:
            advanced = _advance_fired(bullet, age, len(bullets))
            if -80.0 <= advanced.x <= 464.0 and -80.0 <= advanced.y <= 512.0:
                bullets.append(advanced)
                sources.append((
                    opcode.source, opcode.subroutine, opcode.offset
                ))
                accepted += 1
                if len(bullets) >= target:
                    break
    if not bullets:
        raise RuntimeError("source barrage generator produced no in-range bullet")
    snapshot = Snapshot(
        frame=0,
        stage=0,
        player_state=0,
        x=player_x,
        y=player_y,
        half_width=1.25,
        half_height=1.25,
        normal_speed=4.0,
        focus_speed=2.0,
        normal_diagonal_speed=2.8284270763397217,
        focus_diagonal_speed=1.4142135381698608,
        frame_multiplier=1.0,
        input_mask=_input_mask(current),
        bullets=tuple(bullets),
        laser_count=0,
        in_menu=False,
        time_stopped=False,
        replay_or_demo=False,
        difficulty=difficulty,
        rank=rank,
        bullet_sizes=tuple((size, size) for size in SOURCE_BULLET_HALF_SIZES),
        rng_seed=th06_rng.seed,
        rng_generation=th06_rng.generation_count,
    )
    return BarrageCase(seed, target, snapshot, tuple(sources))
