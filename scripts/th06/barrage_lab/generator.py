"""Deterministic dense cases composed from real TH06 ECL volleys."""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
import random
import struct

from ..hazards.births import spawn_pattern
from ..hazards.rng import RngState
from ..model import BUTTON_FOCUS, CONTROL_ACTIONS, Bullet, BulletPattern, Snapshot
from .assets import EclBulletOpcode


# BulletManager::AddedCallback derives these full kill-box sizes from the ten
# source bullet types. Native sensing divides the D3DX dimensions by two.
SOURCE_BULLET_HALF_SIZES = (
    2.0, 3.0, 2.0, 3.0, 2.5, 2.0, 8.0, 5.5, 4.5, 16.0,
)
SOURCE_DYNAMIC_FLAGS = 0xDF1
SOURCE_BULLET_CAP = 640


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


def _advance_fired_linear(bullet: Bullet, age: int, slot: int) -> Bullet:
    x, y = _f32(bullet.x), _f32(bullet.y)
    vx, vy = _f32(bullet.vx), _f32(bullet.vy)
    for _ in range(age):
        x = _f32(x + vx)
        y = _f32(y + vy)
    return replace(
        bullet,
        x=x,
        y=y,
        vx=vx,
        vy=vy,
        state=1,
        timer=age,
        timer_float=float(age),
        slot=slot,
    )


def _resolved_pattern(opcode: EclBulletOpcode, rank: int) -> BulletPattern:
    # EnemyManager's source defaults are [-0.5, +0.5]. This is one explicit,
    # source-valid rank context; ECL-mutated rank contexts are a later rung.
    rank_speed = _f32(_f32(float(rank)) / 32.0 - 0.5)
    speed1 = opcode.speed1
    if speed1 != 0.0:
        speed1 = max(0.3, _f32(speed1 + rank_speed))
    speed2 = max(0.3, _f32(opcode.speed2 + _f32(rank_speed / 2.0)))
    half_size = SOURCE_BULLET_HALF_SIZES[opcode.sprite]
    return BulletPattern(
        sprite=opcode.sprite,
        angle1=opcode.angle1,
        angle2=opcode.angle2,
        speed1=speed1,
        speed2=speed2,
        ex_floats=(0.0, 0.0, 0.0, 0.0),
        ex_ints=(0, 0, 0, 0),
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


def eligible_opcodes(
    catalogue: tuple[EclBulletOpcode, ...], difficulty: int = 2
) -> tuple[EclBulletOpcode, ...]:
    return tuple(
        opcode for opcode in catalogue
        if opcode.has_literal_arguments
        and opcode.executes_on(difficulty)
        and not opcode.flags & SOURCE_DYNAMIC_FLAGS
    )


def generate_barrage_case(
    catalogue: tuple[EclBulletOpcode, ...],
    seed: int,
    *,
    difficulty: int = 2,
    target_bullets: int | None = None,
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
    density_steps = (64, 128, 256, 384, 512, 640)
    target = target_bullets or density_steps[seed % len(density_steps)]
    target = max(1, min(SOURCE_BULLET_CAP, target))
    bullets: list[Bullet] = []
    sources = []
    attempts = 0
    while len(bullets) < target and attempts < 160:
        attempts += 1
        opcode = chooser.choice(opcodes)
        pattern = _resolved_pattern(opcode, rank)
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
        # Once fired, these selected flags are source-exact linear motion.
        age = chooser.randrange(0, 25)
        accepted = 0
        for bullet in volley:
            advanced = _advance_fired_linear(bullet, age, len(bullets))
            if -80.0 <= advanced.x <= 464.0 and -80.0 <= advanced.y <= 512.0:
                bullets.append(advanced)
                accepted += 1
                if len(bullets) >= target:
                    break
        if accepted:
            sources.append((opcode.source, opcode.subroutine, opcode.offset))
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
