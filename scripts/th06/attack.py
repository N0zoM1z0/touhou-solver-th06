"""Proposal-only emitter suppression inside fresh survival ties."""

from __future__ import annotations

from dataclasses import dataclass
import math

from .hazards.timeline import decode_enemy_spawn
from .model import Action, SafeAction, Snapshot


MOVEMENT_LEFT = 8.0
MOVEMENT_RIGHT = 376.0
SOURCE_DAMAGE_CAP_PER_UPDATE = 70


@dataclass(frozen=True)
class SuppressionTarget:
    x: float
    deadline: int
    life: int
    source: str
    kill_latency: int


def _movement_frames(snapshot: Snapshot, target_x: float) -> int:
    if snapshot.normal_speed <= 0.0:
        return 1 << 30
    return math.ceil(abs(target_x - snapshot.x) / snapshot.normal_speed)


def _kill_updates(life: int) -> int:
    return max(1, math.ceil(life / SOURCE_DAMAGE_CAP_PER_UPDATE))


def suppression_target(snapshot: Snapshot) -> SuppressionTarget | None:
    """Choose the earliest source-backed, damage-feasible emitter opportunity.

    The calculation is deliberately optimistic about landing the source
    damage cap.  It is a soft global proposal only: it cannot add an action to
    Hard or overrule a stronger completed continuation.  The planning window
    is the time needed to traverse the source movement rectangle once, so it
    scales with the current source-defined player speed rather than a scene.
    """
    opportunities: list[
        tuple[tuple[int, int, int, int, int], SuppressionTarget]
    ] = []

    for emitter in snapshot.spawners:
        emits = (
            emitter.interval > 0
            or any(67 <= instruction.opcode <= 86 for instruction in emitter.ecl_program)
        )
        if (
            not emits
            or not emitter.interactable
            or not emitter.damageable
            or emitter.is_boss
            or emitter.life <= 0
        ):
            continue
        target_x = min(max(emitter.x, MOVEMENT_LEFT), MOVEMENT_RIGHT)
        align = _movement_frames(snapshot, target_x)
        latency = align + _kill_updates(emitter.life)
        target = SuppressionTarget(
            target_x,
            snapshot.frame,
            emitter.life,
            f"live:{emitter.slot}",
            latency,
        )
        opportunities.append((
            (_kill_updates(emitter.life), latency, 0, align, emitter.slot),
            target,
        ))

    if not any(emitter.is_boss for emitter in snapshot.spawners):
        planned = []
        emitter_subs = frozenset(snapshot.timeline_emitter_subs)
        boss_subs = frozenset(snapshot.timeline_boss_subs)
        for instruction in snapshot.timeline_instructions:
            spawn = decode_enemy_spawn(instruction)
            if (
                spawn is None
                or spawn.time < snapshot.timeline_time
                or spawn.sub_id not in emitter_subs
                or spawn.sub_id in boss_subs
                or spawn.life is None
                or spawn.life <= 0
                or spawn.random_x
            ):
                continue
            planned.append(spawn)

        if planned:
            earliest = min(spawn.time for spawn in planned)
            traverse = math.ceil(
                (MOVEMENT_RIGHT - MOVEMENT_LEFT)
                / max(snapshot.normal_speed, 1e-6)
            )
            for spawn in planned:
                if spawn.time > earliest + traverse:
                    continue
                lead = spawn.time - snapshot.timeline_time
                target_x = min(max(spawn.x, MOVEMENT_LEFT), MOVEMENT_RIGHT)
                align = _movement_frames(snapshot, target_x)
                latency = max(0, align - lead) + _kill_updates(spawn.life)
                target = SuppressionTarget(
                    target_x,
                    snapshot.frame + lead,
                    spawn.life,
                    f"timeline:0x{spawn.instruction_address:08x}",
                    latency,
                )
                opportunities.append((
                    (
                        _kill_updates(spawn.life),
                        latency,
                        lead,
                        align,
                        spawn.instruction_address,
                    ),
                    target,
                ))

    return min(opportunities, key=lambda item: item[0])[1] if opportunities else None


def preferred_suppression_actions(
    candidates: tuple[SafeAction, ...],
    allowed: frozenset[Action],
    target: SuppressionTarget,
) -> frozenset[Action]:
    """Approach one emitter only inside the strongest fresh survival tie."""
    eligible = tuple(
        candidate for candidate in candidates if candidate.action in allowed
    )
    if not eligible:
        return frozenset()
    best = min(abs(candidate.final_x - target.x) for candidate in eligible)
    return frozenset(
        candidate.action
        for candidate in eligible
        if abs(candidate.final_x - target.x) == best
    )
