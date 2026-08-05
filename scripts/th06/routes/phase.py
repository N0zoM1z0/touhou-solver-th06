"""Stable source-phase identities derived from captured ECL state."""

from __future__ import annotations

from ..model import EnemySpawner


def ecl_subroutine_index(spawner: EnemySpawner) -> int | None:
    """Map a relocated instruction pointer back to its source sub index."""
    instruction = spawner.next_instruction
    if instruction is None or not spawner.ecl_subroutines:
        return None
    containing = tuple(
        (address, index)
        for index, address in enumerate(spawner.ecl_subroutines)
        if address <= instruction.address
    )
    if not containing:
        return None
    return max(containing)[1]


def ecl_source_instruction_id(
    spawner: EnemySpawner,
) -> tuple[int, int] | None:
    """Return ``(subroutine, relative byte offset)`` across ASLR relocation."""
    subroutine = ecl_subroutine_index(spawner)
    instruction = spawner.next_instruction
    if subroutine is None or instruction is None:
        return None
    return (
        subroutine,
        instruction.address - spawner.ecl_subroutines[subroutine],
    )


def boss_phase_id(spawner: EnemySpawner, spell_active: bool) -> str:
    """Describe the active boss source context without an absolute address."""
    sub = ecl_subroutine_index(spawner)
    sub_name = "unknown" if sub is None else str(sub)
    return ":".join((
        "boss",
        str(spawner.boss_id),
        f"sub{sub_name}",
        f"life_cb{spawner.life_callback_sub}",
        f"timer_cb{spawner.timer_callback_sub}",
        "spell" if spell_active else "nonspell",
    ))
