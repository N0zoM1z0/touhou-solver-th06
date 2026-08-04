"""Source-defined enemy births in the loaded ECL stage timeline."""

from __future__ import annotations

from dataclasses import dataclass
import math
import struct

from ..model import StageTimelineInstruction


WORLD_TRANSITION_OPCODES = frozenset((*range(8), 10))


@dataclass(frozen=True)
class TimelineEnemySpawn:
    """The route-neutral source semantics of one timeline spawn opcode."""

    instruction_address: int
    time: int
    sub_id: int
    x: float
    y: float
    life: int | None
    invert_x: bool
    random_x: bool
    random_y: bool


def first_world_transition(
    instructions: tuple[StageTimelineInstruction, ...],
    current_time: int,
    horizon: int,
) -> tuple[int, StageTimelineInstruction] | None:
    """Return the first uninserted hazard-world transition in the window.

    EnemyManager runs the timeline before its enemy slots.  A record whose
    source time equals the captured post-update timeline timer therefore runs
    on forecast frame zero.  Spawn opcodes 0..7 can add a body and execute
    newborn time-zero ECL; opcode 10 changes a boss ECL interrupt before that
    boss is updated.  Dialogue/power/wait records do not directly add or
    redirect a hazard in the same update.
    """
    if horizon <= 0:
        return None
    for instruction in instructions:
        if instruction.time < 0:
            return None
        lead = max(0, instruction.time - current_time)
        if lead >= horizon:
            return None
        if instruction.opcode in WORLD_TRANSITION_OPCODES:
            return lead, instruction
    return None


def decode_enemy_spawn(
    instruction: StageTimelineInstruction,
) -> TimelineEnemySpawn | None:
    """Decode EnemyManager::RunEclTimeline opcodes 0..7.

    Opcodes 0/2/4/6 carry an explicit life override.  The odd opcodes use
    the ECL-initialized life, which is not present in the timeline record and
    therefore remains unknown here.  Random-coordinate sentinels are retained
    instead of being replaced with a nominal position.
    """
    if not 0 <= instruction.opcode <= 7:
        return None
    raw = bytes.fromhex(instruction.raw_hex)
    if len(raw) < 20:
        return None
    x, y, _z = struct.unpack_from("<fff", raw, 8)
    if not math.isfinite(x) or not math.isfinite(y):
        return None
    explicit = instruction.opcode % 2 == 0
    life = struct.unpack_from("<h", raw, 20)[0] if explicit and len(raw) >= 22 else None
    random_position = instruction.opcode >= 4
    return TimelineEnemySpawn(
        instruction.address,
        instruction.time,
        instruction.arg0,
        x,
        y,
        life,
        bool(instruction.opcode & 0x02),
        random_position and x <= -990.0,
        random_position and y <= -990.0,
    )
