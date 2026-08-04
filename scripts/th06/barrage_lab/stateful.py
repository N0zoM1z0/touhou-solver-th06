"""Small source-stepped, stateful barrage replay and fuzzing primitives.

The existing barrage lab checks isolated solver queries.  This module keeps
the player, held input, command pickup, proposal state, and fired bullets
alive across frames so an earlier decision can cause a later failure.  It is
deliberately narrow: unsupported world state is reported instead of silently
approximated.
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass, replace
import math
import struct
from collections import Counter
from typing import Callable

from ..model import (
    BUTTON_FOCUS,
    BUTTON_LEFT,
    BUTTON_RIGHT,
    BUTTON_SHOOT,
    BUTTON_UP,
    BUTTON_DOWN,
    ACTIONS,
    CONTROL_ACTIONS,
    Action,
    Bullet,
    BulletPattern,
    EnemyBody,
    EnemySpawner,
    ItemState,
    PLAYER_ALIVE,
    PLAYER_DEAD,
    PLAYER_INVULNERABLE,
    PLAYER_SPAWNING,
    PlayerAttackState,
    PlayerShot,
    SafeAction,
    Snapshot,
    action_from_input,
)
from ..ranking import ProposalRanker
from ..safety import transition_actions
from ..safety import certify_actions
from ..safety import DELIVERY_DELAYS
from ..viability import (
    delivery_segment_viability_scores,
    replanning_scores as source_replanning_scores,
)
from ..guidance import terminal_reachability_counts
from ..hazards.geometry import signed_clearance
from ..hazards.births import spawn_pattern
from ..hazards.ecl import consume_effect_spawn_rng
from ..hazards.world import forecast_world_births
from ..hazards.rng import RngState
from .oracle import (
    _step_player,
    _within_margin,
    certify_linear_source,
)
from .planner import source_terminal_counts


SOURCE_DYNAMIC_FLAGS = 0xDF1
SOURCE_EXACT_DYNAMIC_FLAGS = 0x0F1
TERMINAL_METRICS = (
    "count",
    "count-vector",
    "local-count-vector",
    "replanning-count",
    "authority-filtered-count",
    "delivery-filtered-count",
    "constant-reserve-count",
    "count-clearance",
    "count-clearance-confirmed",
    "count-focus-clearance",
    "count-focus-clearance-confirmed",
    "clearance-count",
    "causal-world-count",
    "causal-split-count",
)
# BulletManager::OnUpdate advances these three spawn states before calling the
# installed bullet ANM script.  The standard archive completes the scripts on
# timer 9/15/31 respectively; every physical transition in the retained
# corpus observes those same boundaries.
_SPAWN_DIVISOR = {2: 2.0, 3: 2.5, 4: 3.0}
_SPAWN_FINAL_TIMER = {2: 9, 3: 15, 4: 31}

# Authoritative ``g_CharacterPowerBulletDataReimuARank9``.  This is immutable
# source data, not a route rule: lower power ranks fail closed until their
# tables are compiled as well.  Fields are wait, phase, spawn offset, size,
# direction in degrees, speed, damage, orb index, type, and ANM script.
_REIMU_A_RANK9_SHOTS = (
    (5, 0, -8.0, 0.0, 12.0, 12.0, -97.0, 12.0, 23, 0, 0, 0x440),
    (5, 0, -8.0, 0.0, 12.0, 12.0, -90.0, 12.0, 24, 0, 0, 0x440),
    (5, 0, 8.0, 0.0, 12.0, 12.0, -90.0, 12.0, 24, 0, 0, 0x440),
    (5, 0, 8.0, 0.0, 12.0, 12.0, -83.0, 12.0, 23, 0, 0, 0x440),
    (16, 0, 0.0, 0.0, 12.0, 12.0, -110.0, 10.0, 10, 1, 1, 0x441),
    (16, 0, 0.0, 0.0, 12.0, 12.0, -70.0, 10.0, 10, 2, 1, 0x441),
    (16, 4, 0.0, 0.0, 12.0, 12.0, -130.0, 10.0, 8, 1, 1, 0x441),
    (16, 4, 0.0, 0.0, 12.0, 12.0, -50.0, 10.0, 8, 2, 1, 0x441),
    (16, 8, 0.0, 0.0, 12.0, 12.0, -150.0, 10.0, 7, 1, 1, 0x441),
    (16, 8, 0.0, 0.0, 12.0, 12.0, -30.0, 10.0, 7, 2, 1, 0x441),
    (16, 12, 0.0, 0.0, 12.0, 12.0, -170.0, 10.0, 10, 1, 1, 0x441),
    (16, 12, 0.0, 0.0, 12.0, 12.0, -9.9999979, 10.0, 10, 2, 1, 0x441),
)
_RANDOM_ITEMS = (
    0, 0, 1, 0, 1, 0, 0, 1, 1, 1, 0, 0, 0, 1, 1, 0,
    1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 0, 1, 1, 1, 0, 2,
)


def _consume_effect_callback_rng(rng: RngState, effect_ids) -> None:
    """Run the source RNG part of one priority-10 effect callback pass."""
    for effect_id in effect_ids:
        if 3 <= effect_id <= 11:
            rng.f32_zero_to_one()
            rng.f32_zero_to_one()
        elif effect_id in (17, 18):
            rng.f32_zero_to_one()


class UnsupportedStatefulModel(ValueError):
    """The compact forward model lacks authority for this source state."""


def _f32(value: float) -> float:
    return ctypes.c_float(value).value


def _copy_bullet(bullet: Bullet, **changes) -> Bullet:
    """Copy the flat hot-path record without ``dataclasses.replace`` reflection."""
    clone = object.__new__(Bullet)
    clone.__dict__.update(bullet.__dict__)
    clone.__dict__.update(changes)
    return clone


def _copy_player_shot(shot: PlayerShot, **changes) -> PlayerShot:
    """Copy one flat player-shot slot without reflective field discovery."""
    clone = object.__new__(PlayerShot)
    clone.__dict__.update(shot.__dict__)
    clone.__dict__.update(changes)
    return clone


def action_mask(action: Action) -> int:
    mask = BUTTON_SHOOT | (BUTTON_FOCUS if action.focused else 0)
    if action.dx < 0:
        mask |= BUTTON_LEFT
    elif action.dx > 0:
        mask |= BUTTON_RIGHT
    if action.dy < 0:
        mask |= BUTTON_UP
    elif action.dy > 0:
        mask |= BUTTON_DOWN
    return mask


def step_fired_bullet(
    bullet: Bullet,
    player_position: tuple[float, float] | None = None,
) -> Bullet:
    """Run one source ``BULLET_STATE_FIRED`` update at multiplier one."""
    if bullet.state != 1:
        raise UnsupportedStatefulModel(
            f"bullet slot {bullet.slot} is in unsupported state {bullet.state}"
        )
    unsupported_flags = (
        bullet.ex_flags
        & SOURCE_DYNAMIC_FLAGS
        & ~SOURCE_EXACT_DYNAMIC_FLAGS
    )
    if unsupported_flags:
        raise UnsupportedStatefulModel(
            f"bullet slot {bullet.slot} has unsupported EX flags "
            f"0x{unsupported_flags:03x}"
        )

    x, y = _f32(bullet.x), _f32(bullet.y)
    vx, vy = _f32(bullet.vx), _f32(bullet.vy)
    angle = _f32(bullet.angle)
    speed = _f32(bullet.speed)
    flags = bullet.ex_flags
    timer = bullet.timer
    timer_float = _f32(bullet.timer_float)
    direction_num_times = bullet.direction_num_times

    if flags & 0x01:
        if timer <= 16:
            deceleration = _f32(5.0 - _f32(timer_float * 5.0 / 16.0))
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
            speed = _f32(bullet.turn_speed)
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
    elif flags & 0x80:
        if timer >= bullet.direction_interval * (direction_num_times + 1):
            if player_position is None:
                raise UnsupportedStatefulModel(
                    f"homing bullet slot {bullet.slot} needs player state"
                )
            direction_num_times += 1
            if direction_num_times >= bullet.direction_max_times:
                flags &= ~0x80
            relative_x = _f32(player_position[0] - x)
            relative_y = _f32(player_position[1] - y)
            aimed = (
                _f32(math.pi / 2.0)
                if relative_x == 0.0 and relative_y == 0.0
                else _f32(math.atan2(relative_y, relative_x))
            )
            angle = _f32(aimed + bullet.direction_rotation)
            speed = _f32(bullet.turn_speed)
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

    return _copy_bullet(
        bullet,
        x=_f32(x + vx),
        y=_f32(y + vy),
        vx=vx,
        vy=vy,
        ex_flags=flags,
        angle=angle,
        speed=speed,
        timer=timer + 1,
        timer_float=_f32(timer_float + 1.0),
        direction_num_times=direction_num_times,
    )


def step_bullet(
    bullet: Bullet,
    player_position: tuple[float, float] | None = None,
) -> Bullet:
    """Advance one source bullet state, including spawn-animation fallthrough."""
    if bullet.state == 1:
        return step_fired_bullet(bullet, player_position)
    if bullet.state not in _SPAWN_DIVISOR:
        raise UnsupportedStatefulModel(
            f"bullet slot {bullet.slot} is in unsupported state {bullet.state}"
        )
    divisor = _SPAWN_DIVISOR[bullet.state]
    spawning = _copy_bullet(
        bullet,
        x=_f32(_f32(bullet.x) + _f32(_f32(bullet.vx) / divisor)),
        y=_f32(_f32(bullet.y) + _f32(_f32(bullet.vy) / divisor)),
    )
    if bullet.timer < _SPAWN_FINAL_TIMER[bullet.state]:
        return _copy_bullet(
            spawning,
            timer=bullet.timer + 1,
            timer_float=_f32(bullet.timer_float + 1.0),
        )
    # ExecuteScript completed: source resets the timer, changes state, and
    # deliberately falls through into BULLET_STATE_FIRED in this same update.
    return step_fired_bullet(
        _copy_bullet(
            spawning,
            state=1,
            timer=0,
            timer_float=0.0,
        ),
        player_position,
    )


def step_reimu_a_player_shot(
    shot: PlayerShot,
    attack: PlayerAttackState,
) -> PlayerShot | None:
    """Advance one captured Reimu-A shot through ``UpdatePlayerBullets``.

    Collision is intentionally not guessed here: EnemyManager applies it
    later in the same update.  Position parity therefore remains testable on
    a shot that changes from FIRED to COLLIDED in the adjacent snapshot.
    """
    if shot.bullet_type not in (0, 1):
        raise UnsupportedStatefulModel(
            f"player shot slot {shot.slot} has unsupported type "
            f"{shot.bullet_type}"
        )
    if shot.state not in (1, 2):
        raise UnsupportedStatefulModel(
            f"player shot slot {shot.slot} has unsupported state {shot.state}"
        )
    # player00.anm scripts 64/65 and 96/97 are source asset IDs plus the
    # authoritative 0x400 player offset. Fired scripts exit at 10000; their
    # collision scripts exit at 30.
    expected_scripts = (0x440, 0x441) if shot.state == 1 else (0x460, 0x461)
    if shot.anm_script not in expected_scripts:
        raise UnsupportedStatefulModel(
            f"player shot slot {shot.slot} has unsupported ANM script "
            f"0x{shot.anm_script:x}"
        )

    vx = _f32(shot.vx)
    vy = _f32(shot.vy)
    homing_speed = _f32(shot.homing_speed)
    if shot.bullet_type == 1 and shot.state == 1:
        if (
            attack.last_enemy_hit_x > -100.0
            and shot.timer < 40
            and shot.timer != shot.timer_previous
        ):
            target_x = _f32(attack.last_enemy_hit_x - shot.x)
            target_y = _f32(attack.last_enemy_hit_y - shot.y)
            denominator = _f32(homing_speed / 4.0)
            if denominator == 0.0:
                raise UnsupportedStatefulModel(
                    f"player shot slot {shot.slot} has zero homing divisor"
                )
            scale = _f32(math.hypot(target_x, target_y) / denominator)
            if scale < 1.0:
                scale = 1.0
            target_x = _f32(_f32(target_x / scale) + vx)
            target_y = _f32(_f32(target_y / scale) + vy)
            length = math.hypot(target_x, target_y)
            if length == 0.0:
                raise UnsupportedStatefulModel(
                    f"player shot slot {shot.slot} has zero homing vector"
                )
            homing_speed = _f32(min(length, 10.0))
            if homing_speed < 1.0:
                homing_speed = 1.0
            vx = _f32(target_x * homing_speed / length)
            vy = _f32(target_y * homing_speed / length)
        elif homing_speed < 10.0:
            homing_speed = _f32(homing_speed + _f32(0.33333333))
            length = math.hypot(vx, vy)
            if length == 0.0:
                raise UnsupportedStatefulModel(
                    f"player shot slot {shot.slot} has zero velocity"
                )
            vx = _f32(vx * homing_speed / length)
            vy = _f32(vy * homing_speed / length)

    x = _f32(_f32(shot.x) + vx)
    y = _f32(_f32(shot.y) + vy)
    if (
        x < -shot.sprite_half_width
        or x > 384.0 + shot.sprite_half_width
        or y < -shot.sprite_half_height
        or y > 448.0 + shot.sprite_half_height
    ):
        return None
    anm_exit = 10000 if shot.state == 1 else 30
    if shot.anm_timer >= anm_exit:
        return None
    return _copy_player_shot(
        shot,
        x=x,
        y=y,
        vx=vx,
        vy=vy,
        homing_speed=homing_speed,
        timer_previous=shot.timer,
        timer=shot.timer + 1,
        timer_float=_f32(shot.timer_float + 1.0),
        anm_timer=shot.anm_timer + 1,
        anm_timer_float=_f32(shot.anm_timer_float + 1.0),
    )


def _step_reimu_a_orbs(
    attack: PlayerAttackState,
    player: tuple[float, float],
    focused: bool,
    current_power: int,
) -> tuple[int, int, int, float, tuple[tuple[float, float], ...]]:
    """Run the source orb-state portion of ``HandlePlayerInputs``."""
    state = attack.orb_state
    previous = attack.focus_timer_previous
    timer = attack.focus_timer
    subframe = _f32(attack.focus_timer_float - attack.focus_timer)
    horizontal = 0.0
    vertical = 0.0
    handled_focusing = False

    if current_power < 8:
        state = 0
    elif state == 0:
        state = 1

    # The source switch deliberately falls through on focus direction changes.
    if state == 0:
        previous, timer, subframe = -999, 0, 0.0
    elif state == 1:
        horizontal = 24.0
        previous, timer, subframe = -999, 0, 0.0
        if focused:
            state = 2
    if state == 2:
        handled_focusing = True
        previous = timer
        timer += 1
        progress = _f32(_f32(timer + subframe) / 8.0)
        vertical = _f32(_f32(1.0 - progress) * 32.0 - 32.0)
        progress_squared = _f32(progress * progress)
        horizontal = _f32(-16.0 * progress_squared + 24.0)
        if timer >= 8:
            state = 3
        if not focused:
            state = 4
            previous = -999
            timer = 8 - timer
            subframe = 0.0
    if state == 3 and not handled_focusing:
        horizontal = 8.0
        vertical = -32.0
        previous, timer, subframe = -999, 0, 0.0
        if not focused:
            state = 4
    if state == 4:
        previous = timer
        timer += 1
        progress = _f32(_f32(timer + subframe) / 8.0)
        vertical = _f32(_f32(32.0 * progress) - 32.0)
        progress_squared = _f32(progress * progress)
        horizontal = _f32(-16.0 * _f32(1.0 - progress_squared) + 24.0)
        if timer >= 8:
            state = 1
        if focused:
            state = 2
            previous = -999
            timer = 8 - timer
            subframe = 0.0
            # Re-enter the focusing calculation at the mirrored timer.
            previous = timer
            timer += 1
            progress = _f32(_f32(timer) / 8.0)
            vertical = _f32(_f32(1.0 - progress) * 32.0 - 32.0)
            horizontal = _f32(-16.0 * _f32(progress * progress) + 24.0)
            if timer >= 8:
                state = 3

    x, y = map(_f32, player)
    positions = (
        (_f32(x - horizontal), _f32(y + vertical)),
        (_f32(x + horizontal), _f32(y + vertical)),
    )
    return state, previous, timer, _f32(timer + subframe), positions


def step_reimu_a_player_attack(
    attack: PlayerAttackState,
    player: tuple[float, float],
    focused: bool,
    current_power: int,
    shoot_allowed: bool = True,
) -> PlayerAttackState:
    """Run one Reimu-A Player update through shot creation, before damage."""
    if attack.shot_type != 0:
        raise UnsupportedStatefulModel("player attack is not Reimu-A")
    if current_power < 128:
        raise UnsupportedStatefulModel(
            "Reimu-A power ranks below the authoritative rank-9 table are not compiled"
        )
    if attack.bomb_active:
        raise UnsupportedStatefulModel("bomb-active player attack is not modeled")

    orb_state, focus_previous, focus_timer, focus_float, orbs = (
        _step_reimu_a_orbs(attack, player, focused, current_power)
    )
    advanced_shots = []
    for shot in attack.shots:
        advanced = step_reimu_a_player_shot(shot, attack)
        if advanced is not None:
            advanced_shots.append(advanced)

    fire_previous = attack.fire_timer_previous
    fire_timer = attack.fire_timer
    fire_subframe = _f32(attack.fire_timer_float - attack.fire_timer)
    # Every solver action holds Shoot. StartFireBulletTimer runs in
    # HandlePlayerInputs before UpdateFireBulletsTimer.
    if fire_timer < 0 and shoot_allowed:
        fire_previous, fire_timer, fire_subframe = -999, 0, 0.0
    spawn_timer = (
        fire_timer
        if fire_timer >= 0 and fire_timer != fire_previous
        else None
    )

    used = {shot.slot for shot in advanced_shots}
    free_slots = iter(slot for slot in range(80) if slot not in used)
    if spawn_timer is not None:
        for (
            wait, phase, offset_x, offset_y, size_x, size_y, degrees,
            speed, damage, orb_index, bullet_type, anm_script,
        ) in _REIMU_A_RANK9_SHOTS:
            if spawn_timer % wait != phase:
                continue
            slot = next(free_slots, None)
            if slot is None:
                break
            origin = player if orb_index == 0 else orbs[orb_index - 1]
            angle = _f32(math.radians(degrees))
            vx = _f32(math.cos(angle) * speed)
            vy = _f32(math.sin(angle) * speed)
            advanced_shots.append(PlayerShot(
                slot=slot,
                x=_f32(origin[0] + offset_x),
                y=_f32(origin[1] + offset_y),
                half_width=_f32(size_x / 2.0),
                half_height=_f32(size_y / 2.0),
                vx=vx,
                vy=vy,
                homing_speed=_f32(speed),
                timer_previous=-999,
                timer=0,
                timer_float=0.0,
                damage=damage,
                state=1,
                bullet_type=bullet_type,
                anm_script=anm_script,
                # FireSingleBullet also executes the selected ANM script
                # immediately, leaving its current timer at one.
                anm_timer=1,
                anm_timer_float=1.0,
                sprite_half_width=7.0,
                sprite_half_height=7.0,
                spawn_position_index=orb_index,
            ))

    if fire_timer >= 0:
        fire_previous = fire_timer
        fire_timer += 1
        fire_subframe = 0.0
        if fire_timer >= 30:
            fire_previous, fire_timer, fire_subframe = -999, -1, 0.0
    return replace(
        attack,
        shots=tuple(sorted(advanced_shots, key=lambda shot: shot.slot)),
        last_enemy_hit_x=-999.0,
        last_enemy_hit_y=-999.0,
        orb_state=orb_state,
        is_focus=focused,
        focus_timer_previous=focus_previous,
        focus_timer=focus_timer,
        focus_timer_float=focus_float,
        fire_timer_previous=fire_previous,
        fire_timer=fire_timer,
        fire_timer_float=_f32(fire_timer + fire_subframe),
        orb_positions=orbs,
    )


def _enter_ecl_sub(emitter: EnemySpawner, sub_id: int) -> EnemySpawner:
    if not 0 <= sub_id < len(emitter.ecl_subroutines):
        raise UnsupportedStatefulModel(
            f"enemy slot {emitter.slot} callback sub {sub_id} is unavailable"
        )
    address = emitter.ecl_subroutines[sub_id]
    instruction = next(
        (
            item for item in emitter.ecl_program
            if item.address == address
        ),
        None,
    )
    if instruction is None:
        raise UnsupportedStatefulModel(
            f"enemy slot {emitter.slot} callback graph is not captured"
        )
    return replace(
        emitter,
        next_instruction=instruction,
        ecl_time=0,
        ecl_time_float=0.0,
    )


class _NominalCombatStep:
    """One priority-9 damage pass plus priority-10 RNG consequences."""

    def __init__(
        self,
        snapshot: Snapshot,
        attack: PlayerAttackState,
        player: tuple[float, float] | None = None,
    ):
        if snapshot.effect_active_upper_bound < 0:
            raise UnsupportedStatefulModel(
                "nominal combat needs the source effect-pool bound"
            )
        if snapshot.item_active_upper_bound < 0:
            raise UnsupportedStatefulModel(
                "nominal combat needs the source item-pool bound"
            )
        self.attack = attack
        self.player = player
        self.player_half_width = snapshot.half_width
        self.player_half_height = snapshot.half_height
        self.effect_upper = snapshot.effect_active_upper_bound
        self.item_upper = snapshot.item_active_upper_bound
        self.items = {item.slot: item for item in snapshot.item_states}
        if (
            len(self.items) != len(snapshot.item_states)
            or any(not 0 <= slot < 512 for slot in self.items)
            or self.item_upper != len(self.items)
        ):
            raise UnsupportedStatefulModel("source item slots are incomplete")
        self.item_next_index = snapshot.item_next_index
        if not 0 <= self.item_next_index < 512:
            raise UnsupportedStatefulModel("source item next index is invalid")
        self.random_spawn_index = snapshot.random_item_spawn_index
        self.random_table_index = snapshot.random_item_table_index
        self.allocated_effects: list[int] = []
        self.pending_effects = list(snapshot.pending_effect_rng_ids)
        self.post_effect_ids: list[int] = []
        if attack.bomb_active:
            raise UnsupportedStatefulModel(
                "nominal combat does not model active player bombs"
            )

    def observe_effect_spawns(self, effect_ids) -> None:
        effect_ids = tuple(effect_ids)
        if any(not 0 <= effect_id < 20 for effect_id in effect_ids):
            raise UnsupportedStatefulModel("invalid source effect id")
        if len(effect_ids) > 512 - self.effect_upper:
            raise UnsupportedStatefulModel(
                "effect-pool upper bound cannot prove particle allocation"
            )
        self.effect_upper += len(effect_ids)
        self.allocated_effects.extend(effect_ids)

    def observe_item_spawns(self, count: int) -> None:
        if count:
            raise UnsupportedStatefulModel(
                "ECL item birth needs its type and position, not only a count"
            )

    def spawn_item(
        self,
        position: tuple[float, float],
        item_type: int,
        state: int,
        rng: RngState,
    ) -> None:
        """Allocate one source ItemManager slot with SpawnItem semantics."""
        if item_type not in range(7) or state not in range(3):
            raise UnsupportedStatefulModel("invalid source item birth")
        slot = self.item_next_index
        for _ in range(512):
            self.item_next_index = (self.item_next_index + 1) % 512
            if slot in self.items:
                slot = self.item_next_index
                continue
            target_x = target_y = 0.0
            start_x, start_y = 0.0, -2.2
            if state == 2:
                target_x = _f32(rng.f32_zero_to_one() * 288.0 + 48.0)
                target_y = _f32(rng.f32_zero_to_one() * 192.0 - 64.0)
                start_x, start_y = position
            self.items[slot] = ItemState(
                slot=slot,
                x=_f32(position[0]),
                y=_f32(position[1]),
                start_x=_f32(start_x),
                start_y=_f32(start_y),
                target_x=target_x,
                target_y=target_y,
                timer_previous=-999,
                timer=0,
                timer_float=0.0,
                item_type=item_type,
                state=state,
            )
            self.item_upper += 1
            return

    def _spawn_effects(self, effect_ids, rng: RngState) -> None:
        effect_ids = tuple(effect_ids)
        consume_effect_spawn_rng(rng, effect_ids)
        self.observe_effect_spawns(effect_ids)

    def spawn_post_effects(self, effect_ids, rng: RngState) -> None:
        """Spawn effects after EffectManager's pass (BulletManager priority 11)."""
        effect_ids = tuple(effect_ids)
        consume_effect_spawn_rng(rng, effect_ids)
        self.observe_effect_spawns(effect_ids)
        self.post_effect_ids.extend(effect_ids)

    @staticmethod
    def _reset_callback_state(emitter: EnemySpawner) -> EnemySpawner:
        return replace(
            emitter,
            ecl_stack=(),
            bullet_rank_speed_low=-0.5,
            bullet_rank_speed_high=0.5,
            bullet_rank_amount1_low=0,
            bullet_rank_amount1_high=0,
            bullet_rank_amount2_low=0,
            bullet_rank_amount2_high=0,
        )

    def _kill_nonbosses(self, slots: dict[int, EnemySpawner]) -> None:
        for slot, target in tuple(slots.items()):
            if target.is_boss:
                continue
            target = replace(target, life=0)
            if not target.interactable and target.death_callback_sub >= 0:
                target = _enter_ecl_sub(target, target.death_callback_sub)
                target = replace(target, death_callback_sub=-1)
            slots[slot] = target

    def enemy_kill_all(self, slots: dict[int, EnemySpawner]) -> None:
        """Apply source opcode 96 before the manager reaches later slots."""
        self._kill_nonbosses(slots)

    def pre_emitter(
        self,
        emitter: EnemySpawner,
        slots: dict[int, EnemySpawner],
    ) -> EnemySpawner:
        """Apply source life/timer callbacks before this slot's RunEcl."""
        if (
            emitter.life_callback_threshold >= 0
            and emitter.life < emitter.life_callback_threshold
        ):
            emitter = replace(
                emitter,
                life=emitter.life_callback_threshold,
                life_callback_threshold=-1,
                timer_callback_sub=emitter.death_callback_sub,
            )
            emitter = _enter_ecl_sub(emitter, emitter.life_callback_sub)
            emitter = self._reset_callback_state(emitter)
            slots[emitter.slot] = emitter
            self._kill_nonbosses(slots)
            emitter = slots[emitter.slot]
        if (
            emitter.timer_callback_threshold >= 0
            and emitter.boss_timer >= emitter.timer_callback_threshold
        ):
            callback_sub = emitter.timer_callback_sub
            life = emitter.life
            life_threshold = emitter.life_callback_threshold
            if life_threshold > 0:
                life = life_threshold
                life_threshold = -1
            emitter = replace(
                emitter,
                life=life,
                life_callback_threshold=life_threshold,
                timer_callback_threshold=-1,
                timer_callback_sub=emitter.death_callback_sub,
                boss_timer=0,
                boss_timer_float=0.0,
            )
            emitter = _enter_ecl_sub(emitter, callback_sub)
            emitter = self._reset_callback_state(emitter)
            slots[emitter.slot] = emitter
            self._kill_nonbosses(slots)
            emitter = slots[emitter.slot]
        return emitter

    @staticmethod
    def _shot_hits(shot: PlayerShot, emitter: EnemySpawner) -> bool:
        enemy_half_width = emitter.hitbox_half_width * 1.5
        enemy_half_height = emitter.hitbox_half_height * 1.5
        return not (
            shot.y - shot.half_height > emitter.y + enemy_half_height
            or shot.x - shot.half_width > emitter.x + enemy_half_width
            or shot.y + shot.half_height < emitter.y - enemy_half_height
            or shot.x + shot.half_width < emitter.x - enemy_half_width
        )

    def _player_touches(self, emitter: EnemySpawner) -> bool:
        if self.player is None:
            return False
        player_x, player_y = self.player
        return not (
            player_y - self.player_half_height
            > emitter.y + emitter.hitbox_half_height
            or player_x - self.player_half_width
            > emitter.x + emitter.hitbox_half_width
            or player_y + self.player_half_height
            < emitter.y - emitter.hitbox_half_height
            or player_x + self.player_half_width
            < emitter.x - emitter.hitbox_half_width
        )

    def _apply_death(
        self,
        emitter: EnemySpawner,
        rng: RngState,
    ) -> EnemySpawner | None:
        mode = emitter.death_mode
        if mode not in (0, 1, 2, 3):
            raise UnsupportedStatefulModel(
                f"enemy slot {emitter.slot} has invalid death mode {mode}"
            )
        emitter = replace(
            emitter,
            life_callback_threshold=-1,
            timer_callback_threshold=-1,
        )
        removed = mode == 0
        if mode == 3:
            emitter = replace(
                emitter, life=1, damageable=False, death_mode=0
            )
            self._spawn_effects((emitter.death_anm1,) * 3, rng)
        else:
            if mode == 1:
                emitter = replace(emitter, interactable=False)
            if emitter.item_drop >= 0:
                self._spawn_effects((emitter.death_anm2 + 4,) * 3, rng)
                self.spawn_item(
                    (emitter.x, emitter.y), emitter.item_drop, 0, rng
                )
            elif emitter.item_drop == -1:
                if self.random_spawn_index % 3 == 0:
                    self._spawn_effects(
                        (emitter.death_anm2 + 4,) * 6, rng
                    )
                    self.spawn_item(
                        (emitter.x, emitter.y),
                        _RANDOM_ITEMS[self.random_table_index],
                        0,
                        rng,
                    )
                    self.random_table_index = (
                        self.random_table_index + 1
                    ) % len(_RANDOM_ITEMS)
                self.random_spawn_index += 1
            emitter = replace(emitter, life=0)

        self._spawn_effects((emitter.death_anm1,), rng)
        self._spawn_effects((emitter.death_anm2 + 4,) * 4, rng)
        if emitter.death_callback_sub >= 0:
            emitter = _enter_ecl_sub(emitter, emitter.death_callback_sub)
            emitter = replace(emitter, death_callback_sub=-1)
            emitter = self._reset_callback_state(emitter)
        return None if removed else emitter

    def post_emitter(
        self,
        emitter: EnemySpawner,
        rng: RngState,
    ) -> EnemySpawner | None:
        if not emitter.has_been_in_bounds or emitter.invisible:
            return emitter
        shots = list(self.attack.shots)
        damage = 0
        if (
            emitter.collidable
            and emitter.interactable
            and not emitter.is_boss
            and self._player_touches(emitter)
        ):
            emitter = replace(emitter, life=emitter.life - 10)
        if emitter.interactable:
            for index, shot in enumerate(shots):
                if shot.state != 1 or not self._shot_hits(shot, emitter):
                    continue
                damage += shot.damage
                self._spawn_effects((5,), rng)
                shots[index] = _copy_player_shot(
                    shot,
                    state=2,
                    vx=_f32(shot.vx / 8.0),
                    vy=_f32(shot.vy / 8.0),
                    anm_script=shot.anm_script + 0x20,
                    # SetAndExecuteScriptIdx initializes at zero and then
                    # immediately ExecuteScript ticks the ANM timer once.
                    anm_timer=1,
                    anm_timer_float=1.0,
                )
            damage = min(damage, 70)
            if self.attack.spell_active:
                damage = damage // 7 if damage > 7 else int(damage != 0)
            if emitter.damageable:
                emitter = replace(emitter, life=emitter.life - damage)
            if self.attack.last_enemy_hit_y < emitter.y:
                self.attack = replace(
                    self.attack,
                    last_enemy_hit_x=emitter.x,
                    last_enemy_hit_y=emitter.y,
                )
        self.attack = replace(self.attack, shots=tuple(shots))
        if emitter.life <= 0 and emitter.interactable:
            return self._apply_death(emitter, rng)
        return emitter

    def finish_frame(self, rng: RngState) -> None:
        # Effects retained from a post-priority-10 birth on the preceding
        # update and effects born during EnemyManager both run now.  Visual
        # callback results are hazard-neutral; their exact RNG draws are not.
        _consume_effect_callback_rng(
            rng, (*self.pending_effects, *self.allocated_effects)
        )
        self.pending_effects.clear()
        self.allocated_effects.clear()


def step_closed_world(
    snapshot: Snapshot,
    held: Action,
    births: tuple[
        tuple[BulletPattern, tuple[float, float]], ...
    ] = (),
) -> Snapshot:
    """Advance the first exact simulator rung by one source update.

    This rung accepts current bullets plus explicitly scheduled source-valid
    volleys and no live emitter/body/laser state.  A scheduled volley is born
    after Player::OnUpdate and before BulletManager::OnUpdate, matching source
    chain priorities 7, 9, and 11.  It is synthetic fuzz input, not a claim
    that a particular ECL route reaches the composed sequence.
    """
    if snapshot.frame_multiplier != 1.0:
        raise UnsupportedStatefulModel("only frame multiplier one is modeled")
    if snapshot.lasers or snapshot.enemies or snapshot.spawners:
        raise UnsupportedStatefulModel(
            "the first closed-world rung models fired bullets only"
        )
    if snapshot.despawning_bullets:
        raise UnsupportedStatefulModel("despawning bullets are not modeled")

    x, y = _step_player(snapshot, snapshot.x, snapshot.y, held)
    bullets = list(snapshot.bullets)
    used_slots = {bullet.slot for bullet in bullets if bullet.slot >= 0}
    if len(used_slots) != len(bullets):
        raise UnsupportedStatefulModel("bullet slots must be unique and known")
    rng = RngState(snapshot.rng_seed, snapshot.rng_generation)
    free_slots = (slot for slot in range(640) if slot not in used_slots)
    for pattern, origin in births:
        for bullet in spawn_pattern(pattern, origin, (x, y), rng):
            slot = next(free_slots, None)
            if slot is None:
                break
            bullets.append(replace(bullet, slot=slot))
    return replace(
        snapshot,
        frame=snapshot.frame + 1,
        timeline_time=snapshot.timeline_time + 1,
        timeline_time_float=snapshot.timeline_time_float + 1.0,
        x=x,
        y=y,
        input_mask=action_mask(held),
        bullets=tuple(step_bullet(bullet, (x, y)) for bullet in bullets),
        rng_seed=rng.seed,
        rng_generation=rng.generation_count,
    )


def _body_from_emitter(emitter) -> EnemyBody | None:
    """Recover the captured lethal body view of one continued emitter."""
    if not (
        emitter.has_been_in_bounds
        and emitter.interactable
        and emitter.collidable
        and not emitter.invisible
    ):
        return None
    return EnemyBody(
        emitter.x,
        emitter.y,
        emitter.hitbox_half_width,
        emitter.hitbox_half_height,
        emitter.velocity_x,
        emitter.velocity_y,
        emitter.angle,
        emitter.angular_velocity,
        emitter.speed,
        emitter.acceleration,
        emitter.movement_mode,
        emitter.movement_ease,
        emitter.invert_x,
        emitter.move_interp_x,
        emitter.move_interp_y,
        emitter.move_start_x,
        emitter.move_start_y,
        emitter.move_timer,
        emitter.move_timer_float,
        emitter.move_start_time,
    )


def _player_overlaps_bullet(
    bullet: Bullet,
    player: tuple[float, float],
    player_half_width: float,
    player_half_height: float,
    margin: float,
) -> bool:
    """Source inclusive AABB collision used by CheckGraze/CalcKillBox."""
    return not (
        player[0] - player_half_width
        > bullet.x + bullet.half_width + margin
        or player[0] + player_half_width
        < bullet.x - bullet.half_width - margin
        or player[1] - player_half_height
        > bullet.y + bullet.half_height + margin
        or player[1] + player_half_height
        < bullet.y - bullet.half_height - margin
    )


def _increase_subrank(
    rank: int,
    subrank: int,
    max_rank: int,
    amount: int,
) -> tuple[int, int]:
    """Authoritative GameManager::IncreaseSubrank transition."""
    subrank += amount
    while subrank >= 100:
        rank += 1
        subrank -= 100
    return min(rank, max_rank), subrank


def _decrease_subrank(
    rank: int,
    subrank: int,
    min_rank: int,
    amount: int,
) -> tuple[int, int]:
    """Authoritative GameManager::DecreaseSubrank transition."""
    subrank -= amount
    while subrank < 0:
        rank -= 1
        subrank += 100
    return max(rank, min_rank), subrank


def _step_items_after_effects(
    combat: _NominalCombatStep,
    player: tuple[float, float],
    player_state: int,
    snapshot: Snapshot,
) -> tuple[int, int, int]:
    """Advance priority-11 ItemManager before hostile bullets."""
    rank = snapshot.rank
    subrank = snapshot.subrank
    power = snapshot.current_power
    retained: dict[int, ItemState] = {}
    for slot in sorted(combat.items):
        item = combat.items[slot]
        x = _f32(item.x)
        y = _f32(item.y)
        start_x = _f32(item.start_x)
        start_y = _f32(item.start_y)
        state = item.state
        if state == 2 and item.timer < 60:
            phase = _f32(item.timer_float / 60.0)
            inverse = _f32(1.0 - phase)
            x = _f32(
                _f32(phase * item.target_x)
                + _f32(start_x * inverse)
            )
            y = _f32(
                _f32(phase * item.target_y)
                + _f32(start_y * inverse)
            )
        else:
            if state == 2 and item.timer == 60:
                start_x = start_y = 0.0
            elif state != 2:
                if state == 1 or (power >= 128 and player[1] < 128.0):
                    relative_x = _f32(player[0] - x)
                    relative_y = _f32(player[1] - y)
                    angle = (
                        _f32(math.pi / 2.0)
                        if relative_x == 0.0 and relative_y == 0.0
                        else _f32(math.atan2(relative_y, relative_x))
                    )
                    start_x = _f32(math.cos(angle) * 8.0)
                    start_y = _f32(math.sin(angle) * 8.0)
                    state = 1
                else:
                    start_x = 0.0
                    if start_y < -2.2:
                        start_y = _f32(-2.2)
            x = _f32(x + start_x)
            y = _f32(y + start_y)
            if y >= 464.0:
                rank, subrank = _decrease_subrank(
                    rank, subrank, snapshot.min_rank, 3
                )
                combat.item_upper -= 1
                continue
            if start_y < 3.0:
                # Source adds before the next frame's else-clamp, so a value
                # just below three overshoots for exactly one update.
                start_y = _f32(start_y + 0.03)
            else:
                start_y = 3.0

        acquired = (
            player_state in (PLAYER_ALIVE, PLAYER_INVULNERABLE)
            and abs(player[0] - x) <= 20.0
            and abs(player[1] - y) <= 20.0
        )
        if acquired:
            if item.item_type == 0:
                if power < 128:
                    power += 1
                    if power >= 128:
                        raise UnsupportedStatefulModel(
                            "item acquisition reaches full-power bullet conversion"
                        )
                rank, subrank = _increase_subrank(
                    rank, subrank, snapshot.max_rank, 1
                )
            elif item.item_type == 1:
                rank, subrank = _increase_subrank(
                    rank,
                    subrank,
                    snapshot.max_rank,
                    30 if y < 128.0 else 3,
                )
            elif item.item_type == 2:
                if power < 128:
                    old_power = power
                    power = min(128, power + 8)
                    if old_power < 128 <= power:
                        raise UnsupportedStatefulModel(
                            "item acquisition reaches full-power bullet conversion"
                        )
            elif item.item_type == 3:
                rank, subrank = _increase_subrank(
                    rank, subrank, snapshot.max_rank, 5
                )
            elif item.item_type == 4:
                if power < 128:
                    raise UnsupportedStatefulModel(
                        "full-power item needs bullet conversion"
                    )
            elif item.item_type == 5:
                rank, subrank = _increase_subrank(
                    rank, subrank, snapshot.max_rank, 200
                )
            combat.item_upper -= 1
            continue

        retained[slot] = replace(
            item,
            x=x,
            y=y,
            start_x=start_x,
            start_y=start_y,
            state=state,
            timer_previous=item.timer,
            timer=item.timer + 1,
            timer_float=_f32(item.timer_float + 1.0),
        )
    combat.items = retained
    return rank, subrank, power


def _step_hostile_bullets_after_effects(
    bullets: list[Bullet],
    player: tuple[float, float],
    snapshot: Snapshot,
    combat: _NominalCombatStep,
    rng: RngState,
    rank: int,
    subrank: int,
) -> tuple[
    tuple[Bullet, ...],
    tuple[Bullet, ...],
    int,
    int,
    int,
]:
    """Advance BulletManager through movement, graze, and lethal collision."""
    active: list[Bullet] = []
    despawning: list[Bullet] = []
    player_state = snapshot.player_state
    for bullet in bullets:
        advanced = step_bullet(bullet, player)
        if advanced.state != 1:
            active.append(advanced)
            continue

        grazed = advanced.is_grazed
        if (
            not grazed
            and player_state not in (PLAYER_DEAD, PLAYER_SPAWNING)
            and _player_overlaps_bullet(
                advanced,
                player,
                snapshot.half_width,
                snapshot.half_height,
                20.0,
            )
        ):
            # ScoreGraze occurs before the following kill-box check.  Effect
            # 8 executes its time-zero ANM immediately, but its random splash
            # callback cannot run until the next EffectManager update.
            combat.spawn_post_effects((8,), rng)
            rank, subrank = _increase_subrank(
                rank, subrank, snapshot.max_rank, 6
            )
            grazed = True
            advanced = _copy_bullet(advanced, is_grazed=True)

        if grazed and _player_overlaps_bullet(
            advanced,
            player,
            snapshot.half_width,
            snapshot.half_height,
            0.0,
        ):
            advanced = _copy_bullet(advanced, state=5)
            despawning.append(advanced)
            if player_state == PLAYER_ALIVE:
                # Player::Die is also later than EffectManager: ID 12 plus
                # sixteen ID-6 particles execute ANM now and callbacks later.
                player_state = PLAYER_DEAD
                combat.spawn_post_effects((12, *((6,) * 16)), rng)
            continue
        active.append(advanced)
    return tuple(active), tuple(despawning), player_state, rank, subrank


def step_nominal_battle_world(snapshot: Snapshot, held: Action) -> Snapshot:
    """Advance bullets, live ECL emitters, and simple stage timeline state.

    This is the source-shaped offline battle rung.  It deliberately rejects
    lasers, despawning bullets, and an active message/boss timeline wait.
    Captured Reimu-A rank-9 roots also advance player shots, damage, death,
    callbacks, pool capacity, and their same-frame RNG consequences. Other
    attack states retain the older exploratory nominal behavior. This remains
    proposal evidence rather than Hard authority.
    """
    if snapshot.frame_multiplier != 1.0:
        raise UnsupportedStatefulModel("only frame multiplier one is modeled")
    if snapshot.lasers:
        raise UnsupportedStatefulModel(
            "nominal battle replay does not yet step live lasers"
        )
    if snapshot.despawning_bullets:
        raise UnsupportedStatefulModel(
            "nominal battle replay does not yet step despawning bullets"
        )
    if any(
        instruction.time <= snapshot.timeline_time
        and instruction.opcode in (9, 12)
        for instruction in snapshot.timeline_instructions
    ):
        raise UnsupportedStatefulModel(
            "nominal battle replay needs resolved timeline wait state"
        )

    x, y = _step_player(snapshot, snapshot.x, snapshot.y, held)
    combat = None
    attack = snapshot.player_attack
    if attack is not None:
        attack = step_reimu_a_player_attack(
            attack,
            (x, y),
            held.focused,
            snapshot.current_power,
            not snapshot.message_active,
        )
        combat = _NominalCombatStep(snapshot, attack, (x, y))
    query = replace(
        snapshot,
        x=x,
        y=y,
        input_mask=action_mask(held),
    )
    forecast = forecast_world_births(
        query,
        ((x, y),),
        rng_mode="nominal",
        nominal_combat=combat,
    )
    if forecast.covered_frames < 1 or forecast.continuation is None:
        raise UnsupportedStatefulModel(
            forecast.reason or "nominal battle world has no continuation"
        )

    bullets = list(snapshot.bullets)
    used_slots = {bullet.slot for bullet in bullets if bullet.slot >= 0}
    if len(used_slots) != len(bullets):
        raise UnsupportedStatefulModel("bullet slots must be unique and known")
    free_slots = (slot for slot in range(640) if slot not in used_slots)
    for bullet in forecast.births[0]:
        slot = next(free_slots, None)
        if slot is None:
            break
        bullets.append(_copy_bullet(bullet, slot=slot))
    next_rng = RngState(
        forecast.continuation.rng_seed,
        forecast.continuation.rng_generation,
    )
    if combat is not None:
        rank, subrank, current_power = _step_items_after_effects(
            combat,
            (x, y),
            snapshot.player_state,
            snapshot,
        )
        (
            bullets,
            despawning_bullets,
            player_state,
            rank,
            subrank,
        ) = _step_hostile_bullets_after_effects(
            bullets,
            (x, y),
            snapshot,
            combat,
            next_rng,
            rank,
            subrank,
        )
    else:
        bullets = tuple(step_bullet(bullet, (x, y)) for bullet in bullets)
        despawning_bullets = ()
        player_state = snapshot.player_state
        rank = snapshot.rank
        subrank = snapshot.subrank
        current_power = snapshot.current_power

    emitters = forecast.continuation.emitters
    bodies = tuple(
        body for body in map(_body_from_emitter, emitters)
        if body is not None
    )
    # The compact timeline corpus excludes waits, so every record at the
    # current timer has executed before EnemyManager ticks the timer once.
    remaining_timeline = tuple(
        instruction for instruction in snapshot.timeline_instructions
        if instruction.time > snapshot.timeline_time
    )
    return replace(
        snapshot,
        frame=snapshot.frame + 1,
        timeline_time=snapshot.timeline_time + 1,
        timeline_time_float=snapshot.timeline_time_float + 1.0,
        timeline_instructions=remaining_timeline,
        timeline_complete=(
            snapshot.timeline_complete or not remaining_timeline
        ),
        x=x,
        y=y,
        input_mask=action_mask(held),
        bullets=tuple(bullets),
        despawning_bullets=despawning_bullets,
        spawners=emitters,
        enemies=bodies,
        rng_seed=next_rng.seed,
        rng_generation=next_rng.generation_count,
        player_state=player_state,
        rank=rank,
        subrank=subrank,
        current_power=current_power,
        player_attack=(combat.attack if combat is not None else attack),
        effect_active_upper_bound=(
            combat.effect_upper
            if combat is not None
            else snapshot.effect_active_upper_bound
        ),
        item_active_upper_bound=(
            combat.item_upper
            if combat is not None
            else snapshot.item_active_upper_bound
        ),
        random_item_spawn_index=(
            combat.random_spawn_index
            if combat is not None
            else snapshot.random_item_spawn_index
        ),
        random_item_table_index=(
            combat.random_table_index
            if combat is not None
            else snapshot.random_item_table_index
        ),
        pending_effect_rng_ids=(
            tuple(combat.post_effect_ids) if combat is not None else ()
        ),
        item_states=(
            tuple(combat.items[slot] for slot in sorted(combat.items))
            if combat is not None
            else snapshot.item_states
        ),
        item_next_index=(
            combat.item_next_index
            if combat is not None
            else snapshot.item_next_index
        ),
    )


def collides_now(snapshot: Snapshot) -> bool:
    """Check the source kill boxes at the already-updated current frame."""
    def touches(
        left: float,
        top: float,
        right: float,
        bottom: float,
    ) -> bool:
        return not (
            left > snapshot.x + snapshot.half_width
            or snapshot.x - snapshot.half_width > right
            or top > snapshot.y + snapshot.half_height
            or snapshot.y - snapshot.half_height > bottom
        )

    bullet_collision = any(
        touches(
            bullet.x - bullet.half_width,
            bullet.y - bullet.half_height,
            bullet.x + bullet.half_width,
            bullet.y + bullet.half_height,
        )
        for bullet in snapshot.bullets
        if bullet.state == 1
    )
    if bullet_collision:
        return True
    return any(
        touches(
            enemy.x - enemy.half_width,
            enemy.y - enemy.half_height,
            enemy.x + enemy.half_width,
            enemy.y + enemy.half_height,
        )
        for enemy in snapshot.enemies
    )


def current_bullet_clearance(snapshot: Snapshot) -> float:
    """Return source kill-box clearance at the current updated frame."""
    return min(
        (
            signed_clearance(
                snapshot.x,
                snapshot.y,
                snapshot.half_width,
                snapshot.half_height,
                (
                    bullet.x - bullet.half_width,
                    bullet.y - bullet.half_height,
                    bullet.x + bullet.half_width,
                    bullet.y + bullet.half_height,
                ),
            )
            for bullet in snapshot.bullets
            if bullet.state == 1
        ),
        default=999.0,
    )


def _delivery_action_branches(
    snapshot: Snapshot,
    candidate: Action,
    frames: int,
) -> tuple[tuple[Action, ...], ...]:
    """Enumerate the same bounded delivery/prefix branches as Hard safety."""
    current = action_from_input(snapshot.input_mask)
    prefixes = transition_actions(current, candidate)
    branches = []
    for delay in DELIVERY_DELAYS:
        transition_branches = (None,) + (prefixes if delay > 0 else ())
        for prefix in transition_branches:
            actions = []
            for frame in range(1, frames + 1):
                if prefix is not None:
                    action = (
                        current
                        if frame < delay
                        else prefix
                        if frame == delay
                        else candidate
                    )
                else:
                    action = current if frame <= delay else candidate
                actions.append(action)
            sequence = tuple(actions)
            if sequence not in branches:
                branches.append(sequence)
    return tuple(branches)


def causal_world_terminal_counts(
    snapshot: Snapshot,
    candidates: tuple[SafeAction, ...],
    segment_length: int,
    horizon: int,
    *,
    continuation_actions: tuple[Action, ...] = CONTROL_ACTIONS,
) -> dict[Action, int]:
    """Count deduplicated nominal battle states behind each Hard candidate.

    Unlike the shared static soft forecast, every branch advances the complete
    compact battle world. Candidate movement therefore changes aimed births,
    Reimu-A orbs and shots, enemy damage/death/callbacks, and their modeled RNG
    consequences. The caller still supplies the Hard-certified first actions;
    an unsupported nominal transition contributes no proposal evidence.

    Later proposal continuations use the ordinary fixed-segment rung, but count
    unique physical states rather than action spellings. This is an offline
    comparison metric, not safety authority.
    """
    if segment_length <= 0 or horizon < segment_length:
        raise ValueError("causal world horizon must cover one positive segment")
    if not continuation_actions:
        raise ValueError("causal world continuation actions cannot be empty")

    def advance(
        start: Snapshot,
        actions: tuple[Action, ...],
    ) -> Snapshot | None:
        state = start
        try:
            for action in actions:
                state = step_nominal_battle_world(state, action)
                if collides_now(state):
                    return None
        except UnsupportedStatefulModel:
            return None
        return state

    scores = {}
    for candidate in candidates:
        branch_counts = []
        for delivery in _delivery_action_branches(
            snapshot, candidate.action, segment_length
        ):
            first = advance(snapshot, delivery)
            frontier = set() if first is None else {first}
            for start_frame in range(segment_length, horizon, segment_length):
                width = min(segment_length, horizon - start_frame)
                next_frontier = set()
                for state in frontier:
                    for action in continuation_actions:
                        following = advance(state, (action,) * width)
                        if following is not None:
                            next_frontier.add(following)
                frontier = next_frontier
                if not frontier:
                    break
            branch_counts.append(len(frontier))
        scores[candidate.action] = min(branch_counts, default=0)
    return scores


def causal_split_terminal_counts(
    snapshot: Snapshot,
    candidates: tuple[SafeAction, ...],
    segment_length: int,
    horizon: int,
    continuation_score: Callable[[Snapshot, int], int],
) -> dict[Action, int]:
    """Advance candidate-conditioned combat once, then score the fresh world.

    This is the affordable rung between a shared static forecast and the full
    causal-world frontier above. Every physical delivery/prefix branch runs
    through the exact compact battle transition for the first segment. The
    supplied continuation planner then starts from that branch-specific world;
    the worst delivery branch remains the candidate's proposal score.
    """
    if segment_length <= 0 or horizon < segment_length:
        raise ValueError("causal split horizon must cover one positive segment")

    remaining = horizon - segment_length
    scores = {}
    for candidate in candidates:
        branch_scores = []
        for delivery in _delivery_action_branches(
            snapshot, candidate.action, segment_length
        ):
            state = snapshot
            try:
                for action in delivery:
                    state = step_nominal_battle_world(state, action)
                    if collides_now(state):
                        state = None
                        break
            except UnsupportedStatefulModel:
                state = None
            branch_scores.append(
                0
                if state is None
                else 1
                if remaining == 0
                else max(0, int(continuation_score(state, remaining)))
            )
        scores[candidate.action] = min(branch_scores, default=0)
    return scores


@dataclass(frozen=True)
class CausalBranchDiversity:
    supported_actions: int
    unique_enemy_combat_states: int
    unique_player_attack_states: int
    unique_rng_states: int
    unique_bullet_counts: int


def causal_branch_diversity(
    snapshot: Snapshot,
    frames: int,
    *,
    actions: tuple[Action, ...] = CONTROL_ACTIONS,
) -> CausalBranchDiversity:
    """Measure whether candidate paths actually fork the compact world."""
    if frames <= 0 or not actions:
        raise ValueError("causal branch probe dimensions must be positive")
    results = []
    for action in actions:
        state = snapshot
        try:
            for _ in range(frames):
                state = step_nominal_battle_world(state, action)
                if collides_now(state):
                    state = None
                    break
        except UnsupportedStatefulModel:
            state = None
        if state is not None:
            results.append(state)

    enemy_states = {
        tuple(
            (
                emitter.slot,
                emitter.life,
                emitter.interactable,
                emitter.damageable,
                emitter.death_callback_sub,
                (
                    emitter.next_instruction.address
                    if emitter.next_instruction is not None else None
                ),
            )
            for emitter in state.spawners
        )
        for state in results
    }
    return CausalBranchDiversity(
        len(results),
        len(enemy_states),
        len({state.player_attack for state in results}),
        len({(state.rng_seed, state.rng_generation) for state in results}),
        len({len(state.bullets) for state in results}),
    )


class ExactTerminalPolicy:
    """Independent exact terminal-volume policy for closed-loop comparison."""

    def __init__(
        self,
        horizon: int,
        metric: str = "count",
        continuation: str = "segment",
    ) -> None:
        if horizon < 4:
            raise ValueError("stateful terminal horizon must be at least four")
        if metric not in TERMINAL_METRICS:
            raise ValueError(f"unknown terminal metric {metric!r}")
        if continuation not in ("segment", "frame", "hybrid"):
            raise ValueError(f"unknown continuation {continuation!r}")
        if continuation != "segment" and metric != "count":
            raise ValueError(
                "frame and hybrid continuation currently support count only"
            )
        self.horizon = horizon
        self.metric = metric
        self.continuation = continuation
        self.ranker = ProposalRanker()
        self.metric_confirmation: Action | None = None

    def __call__(self, snapshot: Snapshot) -> Action | None:
        if self.metric in ("causal-world-count", "causal-split-count"):
            candidates = certify_actions(
                snapshot, 4, actions=CONTROL_ACTIONS
            )
            if not candidates:
                return None
            if self.metric == "causal-world-count":
                scores = causal_world_terminal_counts(
                    snapshot, candidates, 4, self.horizon
                )
            else:
                def continuation_score(state, remaining):
                    split = min(4, remaining)
                    continuation = certify_actions(
                        state, split, actions=CONTROL_ACTIONS
                    )
                    if not continuation:
                        return 0
                    if remaining <= 4:
                        return len({
                            (_f32(item.final_x), _f32(item.final_y))
                            for item in continuation
                        })
                    values = terminal_reachability_counts(
                        state, continuation, 4, remaining
                    )
                    return max(values.values(), default=0)

                scores = causal_split_terminal_counts(
                    snapshot,
                    candidates,
                    4,
                    self.horizon,
                    continuation_score,
                )
            best = max(scores.values(), default=0)
            preferred = frozenset(
                action for action, score in scores.items()
                if best > 0 and score == best
            )
            return self.ranker.choose(
                snapshot, candidates, preferred
            ).action

        hard = certify_linear_source(snapshot, 4)
        if not hard.actions:
            return None
        terminal_by_name = {
            name: (x, y) for name, x, y in hard.terminal_positions
        }
        candidates = tuple(
            SafeAction(
                next(action for action in CONTROL_ACTIONS if action.name == name),
                0.0,
                terminal_by_name[name][0],
                terminal_by_name[name][1],
            )
            for name in hard.actions
        )
        if self.horizon == 4:
            preferred = frozenset()
        elif self.metric in ("count-vector", "local-count-vector"):
            rungs = _terminal_rungs(self.horizon)
            counts = tuple(
                dict(source_terminal_counts(
                    snapshot,
                    hard.actions,
                    4,
                    rung,
                ).counts)
                for rung in rungs
            )
            scores = {
                candidate.action.name: tuple(
                    float(values[candidate.action.name])
                    for values in (
                        counts
                        if self.metric == "local-count-vector"
                        else reversed(counts)
                    )
                )
                for candidate in candidates
            }
            best = max(scores.values(), default=None)
            preferred = frozenset(
                candidate.action
                for candidate in candidates
                if best is not None
                and best[0] > 0
                and scores[candidate.action.name] == best
            )
        elif self.metric in (
            "replanning-count",
            "authority-filtered-count",
            "delivery-filtered-count",
        ):
            if self.metric == "delivery-filtered-count":
                def terminal_scores(working, rung):
                    by_name = dict(source_terminal_counts(
                        snapshot,
                        tuple(item.action.name for item in working),
                        4,
                        rung,
                    ).counts)
                    return {
                        candidate.action: by_name[candidate.action.name]
                        for candidate in working
                    }

                preferred = _progressive_delivery_preferred(
                    candidates,
                    self.horizon,
                    lambda working, rung: (
                        delivery_segment_viability_scores(
                            snapshot,
                            working,
                            4,
                            rung,
                        )
                    ),
                    terminal_scores,
                )
                if not preferred:
                    deep = dict(source_terminal_counts(
                        snapshot,
                        hard.actions,
                        4,
                        self.horizon,
                    ).counts)
                    deep_by_action = {
                        candidate.action: deep[candidate.action.name]
                        for candidate in candidates
                    }
                    reserve = certify_linear_source(
                        snapshot,
                        min(6, self.horizon),
                        actions=tuple(
                            candidate.action for candidate in candidates
                        ),
                    ).actions
                    preferred = _deep_preferred_within(
                        frozenset(
                            candidate.action for candidate in candidates
                            if candidate.action.name in reserve
                        ),
                        deep_by_action,
                    )
            else:
                replanning = source_replanning_scores(
                    snapshot,
                    candidates,
                    split=4,
                    horizon=min(8, self.horizon),
                    continuation_actions=CONTROL_ACTIONS,
                )
            if self.metric == "authority-filtered-count":
                deep = dict(source_terminal_counts(
                    snapshot,
                    hard.actions,
                    4,
                    self.horizon,
                ).counts)
                deep_by_action = {
                    candidate.action: deep[candidate.action.name]
                    for candidate in candidates
                }
                preferred = _authority_filtered_preferred(
                    replanning, deep_by_action
                )
            elif self.metric == "replanning-count":
                scores = {
                    candidate.action: (replanning[candidate.action],)
                    for candidate in candidates
                }
                best = max(scores.values(), default=None)
                preferred = frozenset(
                    action for action, score in scores.items()
                    if best is not None and score == best
                )
        elif self.metric == "constant-reserve-count":
            reserve = certify_linear_source(
                snapshot,
                min(6, self.horizon),
                actions=tuple(candidate.action for candidate in candidates),
            ).actions
            deep = dict(source_terminal_counts(
                snapshot,
                hard.actions,
                4,
                self.horizon,
            ).counts)
            preferred = _deep_preferred_within(
                frozenset(
                    candidate.action
                    for candidate in candidates
                    if candidate.action.name in reserve
                ),
                {
                    candidate.action: deep[candidate.action.name]
                    for candidate in candidates
                },
            )
        elif self.continuation == "frame":
            guidance_by_action = terminal_reachability_counts(
                snapshot,
                candidates,
                4,
                self.horizon,
            )
            preferred, self.metric_confirmation = _terminal_preferred(
                guidance_by_action,
                self.metric,
                self.metric_confirmation,
            )
        elif self.continuation == "hybrid":
            base_horizon = min(8, self.horizon)
            base_values = dict(source_terminal_counts(
                snapshot,
                hard.actions,
                4,
                base_horizon,
            ).counts)
            base_by_action = {
                candidate.action: base_values[candidate.action.name]
                for candidate in candidates
            }
            base_preferred, _confirmation = _terminal_preferred(
                base_by_action,
                "count",
                None,
            )
            membership = terminal_reachability_counts(
                snapshot,
                candidates,
                4,
                self.horizon,
            )
            winning = frozenset(
                action for action, score in membership.items()
                if score > 0
            )
            preferred = base_preferred & winning or winning
        else:
            guidance = dict(source_terminal_counts(
                snapshot,
                hard.actions,
                4,
                self.horizon,
                include_guidance=self.metric != "count",
            ).counts)
            guidance_by_action = {
                next(
                    action for action in CONTROL_ACTIONS
                    if action.name == name
                ): value
                for name, value in guidance.items()
            }
            preferred, self.metric_confirmation = _terminal_preferred(
                guidance_by_action,
                self.metric,
                self.metric_confirmation,
            )
        return self.ranker.choose(snapshot, candidates, preferred).action


class NativeTerminalPolicy:
    """The parity-checked native planner for high-throughput stateful sweeps."""

    def __init__(
        self,
        horizon: int,
        kernel=None,
        metric: str = "count",
        continuation: str = "segment",
    ) -> None:
        if horizon < 4:
            raise ValueError("stateful terminal horizon must be at least four")
        if metric not in TERMINAL_METRICS:
            raise ValueError(f"unknown terminal metric {metric!r}")
        if continuation not in ("segment", "frame", "hybrid"):
            raise ValueError(f"unknown continuation {continuation!r}")
        if continuation != "segment" and metric != "count":
            raise ValueError(
                "frame and hybrid continuation currently support count only"
            )
        if kernel is None:
            from ..kernels.safety import NativeSafetyKernel
            kernel = NativeSafetyKernel()
        self.horizon = horizon
        self.kernel = kernel
        self.metric = metric
        self.continuation = continuation
        self.ranker = ProposalRanker()
        self.metric_confirmation: Action | None = None

    def __call__(self, snapshot: Snapshot) -> Action | None:
        hard = self.kernel.certify_selected(
            snapshot,
            4,
            CONTROL_ACTIONS,
            collision_margin=0.35,
        )
        if not hard:
            return None
        if self.metric == "causal-world-count":
            scores = causal_world_terminal_counts(
                snapshot, hard, 4, self.horizon
            )
            best = max(scores.values(), default=0)
            preferred = frozenset(
                action for action, score in scores.items()
                if best > 0 and score == best
            )
        elif self.metric == "causal-split-count":
            def continuation_score(state, remaining):
                split = min(4, remaining)
                continuation = self.kernel.certify_selected(
                    state,
                    split,
                    CONTROL_ACTIONS,
                    collision_margin=0.35,
                )
                if not continuation:
                    return 0
                if remaining <= 4:
                    return len({
                        (_f32(item.final_x), _f32(item.final_y))
                        for item in continuation
                    })
                values = self.kernel.terminal_counts(
                    state,
                    continuation,
                    4,
                    remaining,
                    collision_margin=0.35,
                )
                return max(values.values(), default=0)

            scores = causal_split_terminal_counts(
                snapshot,
                hard,
                4,
                self.horizon,
                continuation_score,
            )
            best = max(scores.values(), default=0)
            preferred = frozenset(
                action for action, score in scores.items()
                if best > 0 and score == best
            )
        elif self.horizon == 4:
            preferred = frozenset()
        elif self.metric in ("count-vector", "local-count-vector"):
            rungs = _terminal_rungs(self.horizon)
            counts = tuple(
                self.kernel.terminal_counts(
                    snapshot,
                    hard,
                    4,
                    rung,
                    collision_margin=0.35,
                )
                for rung in rungs
            )
            scores = {
                candidate.action: tuple(
                    float(values[candidate.action])
                    for values in (
                        counts
                        if self.metric == "local-count-vector"
                        else reversed(counts)
                    )
                )
                for candidate in hard
            }
            best = max(scores.values(), default=None)
            preferred = frozenset(
                candidate.action
                for candidate in hard
                if best is not None
                and best[0] > 0
                and scores[candidate.action] == best
            )
        elif self.metric in (
            "replanning-count",
            "authority-filtered-count",
            "delivery-filtered-count",
        ):
            if self.metric == "delivery-filtered-count":
                def delivery_scores(working, rung):
                    robust = (
                        self.kernel.delivery_segment_viability_progressive(
                            snapshot,
                            working,
                            4,
                            rung,
                            rung,
                            collision_margin=0.35,
                            budget_ms=1000.0,
                        )
                    )
                    if (
                        robust is None
                        or robust[0] != rung
                        or not robust[2]
                    ):
                        raise RuntimeError(
                            "stateful repeated-pickup rung did not complete"
                        )
                    return robust[1]

                preferred = _progressive_delivery_preferred(
                    hard,
                    self.horizon,
                    delivery_scores,
                    lambda working, rung: self.kernel.terminal_counts(
                        snapshot,
                        working,
                        4,
                        rung,
                        collision_margin=0.35,
                    ),
                )
                if not preferred:
                    deep = self.kernel.terminal_counts(
                        snapshot,
                        hard,
                        4,
                        self.horizon,
                        collision_margin=0.35,
                    )
                    reserve = self.kernel.certify_selected(
                        snapshot,
                        min(6, self.horizon),
                        tuple(candidate.action for candidate in hard),
                        collision_margin=0.35,
                    )
                    preferred = _deep_preferred_within(
                        frozenset(
                            candidate.action for candidate in reserve
                        ),
                        deep,
                    )
            else:
                replanning = self.kernel.macro_tail_scores_budgeted(
                    snapshot,
                    hard,
                    4,
                    min(8, self.horizon),
                    collision_margin=0.35,
                    budget_ms=1000.0,
                )
            if self.metric != "delivery-filtered-count" and replanning is None:
                raise RuntimeError(
                    "stateful full-control replanning did not complete"
                )
            if self.metric == "authority-filtered-count":
                deep = self.kernel.terminal_counts(
                    snapshot,
                    hard,
                    4,
                    self.horizon,
                    collision_margin=0.35,
                )
                preferred = _authority_filtered_preferred(
                    replanning,
                    deep,
                )
            elif self.metric == "replanning-count":
                scores = {
                    candidate.action: (replanning[candidate.action],)
                    for candidate in hard
                }
                best = max(scores.values(), default=None)
                preferred = frozenset(
                    action for action, score in scores.items()
                    if best is not None and score == best
                )
        elif self.metric == "constant-reserve-count":
            reserve = self.kernel.certify_selected(
                snapshot,
                min(6, self.horizon),
                tuple(candidate.action for candidate in hard),
                collision_margin=0.35,
            )
            deep = self.kernel.terminal_counts(
                snapshot,
                hard,
                4,
                self.horizon,
                collision_margin=0.35,
            )
            preferred = _deep_preferred_within(
                frozenset(candidate.action for candidate in reserve),
                deep,
            )
        elif self.continuation == "frame":
            result = self.kernel.flexible_terminal_counts_progressive(
                snapshot,
                hard,
                4,
                self.horizon,
                self.horizon,
                collision_margin=0.35,
                budget_ms=1000.0,
            )
            if result is None or result[0] != self.horizon or not result[2]:
                raise RuntimeError("stateful frame continuation did not complete")
            preferred, self.metric_confirmation = _terminal_preferred(
                result[1],
                self.metric,
                self.metric_confirmation,
            )
        elif self.continuation == "hybrid":
            base_horizon = min(8, self.horizon)
            base_values = self.kernel.terminal_counts(
                snapshot,
                hard,
                4,
                base_horizon,
                collision_margin=0.35,
            )
            base_preferred, _confirmation = _terminal_preferred(
                base_values,
                "count",
                None,
            )
            result = self.kernel.boolean_reachability_progressive(
                snapshot,
                hard,
                4,
                base_horizon,
                self.horizon,
                collision_margin=0.35,
                budget_ms=1000.0,
            )
            if result is None or result[0] != self.horizon or not result[2]:
                raise RuntimeError(
                    "stateful hybrid continuation did not complete: "
                    f"requested={self.horizon} result={result}"
                )
            winning = frozenset(
                action for action, score in result[1].items()
                if score > 0
            )
            preferred = base_preferred & winning or winning
        else:
            guidance = (
                self.kernel.terminal_counts(
                    snapshot,
                    hard,
                    4,
                    self.horizon,
                    collision_margin=0.35,
                )
                if self.metric == "count"
                else self.kernel.terminal_guidance(
                    snapshot,
                    hard,
                    4,
                    self.horizon,
                    collision_margin=0.35,
                )
            )
            preferred, self.metric_confirmation = _terminal_preferred(
                guidance,
                self.metric,
                self.metric_confirmation,
            )
        return self.ranker.choose(snapshot, hard, preferred).action


def _terminal_metric(value, metric: str) -> tuple[float, ...]:
    count = value if isinstance(value, int) else value.terminal_count
    if metric == "count":
        return (float(count),)
    clearance = value.free_clearance
    if metric in (
        "count-clearance",
        "count-clearance-confirmed",
        "count-focus-clearance",
        "count-focus-clearance-confirmed",
    ):
        return (float(count), clearance)
    if metric == "clearance-count":
        return (float(count > 0), clearance, float(count))
    raise ValueError(f"unknown terminal metric {metric!r}")


def _authority_filtered_preferred(
    replanning: dict[Action, int],
    deep: dict[Action, int],
) -> frozenset[Action]:
    """Keep next-command authority; rank it only with positive deep evidence."""
    viable = frozenset(
        action for action, score in replanning.items() if score > 0
    )
    return _deep_preferred_within(viable, deep)


def _progressive_delivery_preferred(
    candidates: tuple[SafeAction, ...],
    horizon: int,
    viability_at_horizon,
    terminal_at_horizon,
) -> frozenset[Action]:
    """Mirror production's indivisible repeated-pickup/terminal ladder."""
    working = candidates
    preferred: frozenset[Action] = frozenset()
    for rung in _terminal_rungs(horizon):
        replanning = viability_at_horizon(working, rung)
        viable = frozenset(
            action for action, score in replanning.items() if score > 0
        )
        if not viable:
            break
        working = tuple(
            candidate for candidate in working
            if candidate.action in viable
        )
        preferred = _authority_filtered_preferred(
            replanning,
            terminal_at_horizon(working, rung),
        )
    return preferred


def _deep_preferred_within(
    allowed: frozenset[Action],
    deep: dict[Action, int],
) -> frozenset[Action]:
    """Use positive deep evidence inside a complete local reserve."""
    if not allowed:
        return frozenset()
    best_deep = max((deep[action] for action in allowed), default=0)
    if best_deep <= 0:
        return allowed
    return frozenset(
        action for action in allowed if deep[action] == best_deep
    )


def _terminal_action_metric(
    value,
    metric: str,
    action: Action,
) -> tuple[float, ...]:
    if metric in (
        "count-focus-clearance",
        "count-focus-clearance-confirmed",
    ):
        count = value.terminal_count
        return (float(count), float(action.focused), value.free_clearance)
    return _terminal_metric(value, metric)


def _terminal_preferred(
    guidance: dict[Action, object],
    metric: str,
    previous_confirmation: Action | None,
) -> tuple[frozenset[Action], Action | None]:
    scores = {
        action: _terminal_action_metric(value, metric, action)
        for action, value in guidance.items()
    }
    best = max(scores.values(), default=None)
    if best is None or best[0] <= 0:
        return frozenset(), None
    winners = frozenset(
        action for action, score in scores.items() if score == best
    )
    if not metric.endswith("-confirmed"):
        return winners, None

    unique = next(iter(winners)) if len(winners) == 1 else None
    if unique is not None and unique == previous_confirmation:
        return winners, unique
    best_count = max(
        (
            value if isinstance(value, int) else value.terminal_count
            for value in guidance.values()
        ),
        default=0,
    )
    count_winners = frozenset(
        action
        for action, value in guidance.items()
        if (
            value if isinstance(value, int) else value.terminal_count
        ) == best_count
    )
    return count_winners, unique


def _terminal_rungs(horizon: int) -> tuple[int, ...]:
    """Return the ordinary four-frame ladder ending at ``horizon``."""
    return tuple((*range(8, horizon, 4), horizon))


@dataclass(frozen=True)
class ClosedLoopResult:
    outcome: str
    start_frame: int
    final_frame: int
    survived_frames: int
    decisions: int
    commands: int
    final_x: float
    final_y: float
    actions: tuple[str, ...]
    born_bullets: int
    decision_trace: tuple[tuple[int, str], ...]
    minimum_clearance: float


def _delivery_choice(
    seed: int,
    command_index: int,
    current: Action,
    target: Action,
) -> tuple[int, Action | None]:
    mixed = (
        seed * 0x9E3779B1 + command_index * 0x85EBCA77
    ) & 0xFFFFFFFF
    delay = mixed & 3
    prefixes = transition_actions(current, target) if delay > 0 else ()
    prefix = prefixes[(mixed >> 8) % len(prefixes)] if prefixes else None
    return delay, prefix


def run_closed_loop(
    snapshot: Snapshot,
    policy: Callable[[Snapshot], Action | None],
    *,
    frames: int,
    delivery_seed: int,
    birth_schedule=(),
    battle_world: bool = False,
    state_sink: Callable[[Snapshot], None] | None = None,
) -> ClosedLoopResult:
    """Run solver decisions through bounded pickup and source bullet updates."""
    if frames <= 0:
        raise ValueError("closed-loop frame count must be positive")
    state = snapshot
    held = action_from_input(state.input_mask)
    pending: Action | None = None
    pending_delay = 0
    pending_prefix: Action | None = None
    decisions = 0
    commands = 0
    action_trace: list[str] = []
    decision_trace: list[tuple[int, str]] = []
    born_bullets = 0
    minimum_clearance = current_bullet_clearance(state)
    births_by_update = {
        update: tuple(
            (event.pattern, event.origin)
            for event in birth_schedule
            if event.update == update
        )
        for update in {event.update for event in birth_schedule}
    }
    if battle_world and birth_schedule:
        raise ValueError(
            "battle-world replay uses captured ECL/timeline births, not a "
            "synthetic birth schedule"
        )

    for update in range(frames):
        minimum_clearance = min(
            minimum_clearance, current_bullet_clearance(state)
        )
        if collides_now(state):
            outcome = "hit"
            break
        if pending is None:
            target = policy(state)
            decisions += 1
            if target is None:
                outcome = "authority-stop"
                break
            decision_trace.append((state.frame, target.name))
            if target != held:
                pending = target
                pending_delay, pending_prefix = _delivery_choice(
                    delivery_seed, commands, held, target
                )
                commands += 1
        else:
            # Match Solver.decide(required_action): an in-flight command is
            # rechecked for the next physical update, not replanned through a
            # fresh four-frame delivery window. Focused commands share the
            # source's focused action batch exactly as production does.
            leased_actions = ACTIONS if pending.focused else (pending,)
            lease_safe = (
                tuple(
                    item.action.name for item in certify_actions(
                        state, 1, actions=leased_actions
                    )
                )
                if battle_world
                else certify_linear_source(
                    state, 1, actions=leased_actions
                ).actions
            )
            if pending.name not in lease_safe:
                outcome = "lease-authority-stop"
                break

        step_action = held
        if pending is not None:
            if pending_delay == 0:
                step_action = pending
                held = pending
                pending = None
                pending_prefix = None
            else:
                if pending_delay == 1 and pending_prefix is not None:
                    step_action = pending_prefix
                pending_delay -= 1
        action_trace.append(step_action.name)
        before_slots = {bullet.slot for bullet in state.bullets}
        state = (
            step_nominal_battle_world(state, step_action)
            if battle_world
            else step_closed_world(
                state,
                step_action,
                births_by_update.get(update, ()),
            )
        )
        if state_sink is not None:
            state_sink(state)
        minimum_clearance = min(
            minimum_clearance, current_bullet_clearance(state)
        )
        born_bullets += sum(
            bullet.slot not in before_slots for bullet in state.bullets
        )
    else:
        outcome = "survived"

    return ClosedLoopResult(
        outcome,
        snapshot.frame,
        state.frame,
        state.frame - snapshot.frame,
        decisions,
        commands,
        state.x,
        state.y,
        tuple(action_trace),
        born_bullets,
        tuple(decision_trace),
        minimum_clearance,
    )


@dataclass(frozen=True)
class PhysicalParity:
    adjacent_pairs: int
    exact_player_steps: int
    fired_bullet_steps: int
    exact_fired_bullet_steps: int
    spawning_bullet_steps: int
    exact_spawning_bullet_steps: int
    maximum_player_error: float
    maximum_bullet_error: float
    unsupported_bullet_steps: int
    births: int
    removals: int
    player_shot_steps: int = 0
    exact_player_shot_steps: int = 0
    unsupported_player_shot_steps: int = 0
    maximum_player_shot_error: float = 0.0
    player_shot_births: int = 0
    player_shot_removals: int = 0
    enemy_slot_births: int = 0
    enemy_slot_removals: int = 0
    enemy_life_changes: int = 0
    player_attack_steps: int = 0
    exact_player_attack_steps: int = 0
    exact_player_shot_births: int = 0
    exact_player_orb_steps: int = 0
    exact_player_fire_timer_steps: int = 0
    first_player_attack_mismatch: str = ""
    combat_world_steps: int = 0
    exact_combat_enemy_steps: int = 0
    exact_combat_player_shot_steps: int = 0
    exact_combat_rng_steps: int = 0
    combat_enemy_transition_steps: int = 0
    exact_combat_enemy_transition_steps: int = 0
    unsupported_combat_world_steps: int = 0
    first_combat_world_mismatch: str = ""
    first_combat_enemy_mismatch: str = ""
    first_combat_player_shot_mismatch: str = ""
    first_combat_rng_mismatch: str = ""
    hostile_graze_transitions: int = 0
    combat_graze_steps: int = 0
    exact_combat_graze_steps: int = 0
    exact_combat_rank_steps: int = 0
    exact_combat_pending_effect_steps: int = 0
    item_slot_births: int = 0
    item_slot_removals: int = 0
    combat_item_steps: int = 0
    exact_combat_item_steps: int = 0
    exact_combat_power_steps: int = 0


def physical_step_parity(history: tuple[Snapshot, ...]) -> PhysicalParity:
    """Validate one-step source transitions against consecutive online states."""
    adjacent_pairs = 0
    exact_player_steps = 0
    fired_bullet_steps = 0
    exact_fired_bullet_steps = 0
    spawning_bullet_steps = 0
    exact_spawning_bullet_steps = 0
    unsupported_bullet_steps = 0
    births = 0
    removals = 0
    maximum_player_error = 0.0
    maximum_bullet_error = 0.0
    player_shot_steps = 0
    exact_player_shot_steps = 0
    unsupported_player_shot_steps = 0
    maximum_player_shot_error = 0.0
    player_shot_births = 0
    player_shot_removals = 0
    enemy_slot_births = 0
    enemy_slot_removals = 0
    enemy_life_changes = 0
    player_attack_steps = 0
    exact_player_attack_steps = 0
    exact_player_shot_births = 0
    exact_player_orb_steps = 0
    exact_player_fire_timer_steps = 0
    first_player_attack_mismatch = ""
    combat_world_steps = 0
    exact_combat_enemy_steps = 0
    exact_combat_player_shot_steps = 0
    exact_combat_rng_steps = 0
    combat_enemy_transition_steps = 0
    exact_combat_enemy_transition_steps = 0
    unsupported_combat_world_steps = 0
    first_combat_world_mismatch = ""
    first_combat_enemy_mismatch = ""
    first_combat_player_shot_mismatch = ""
    first_combat_rng_mismatch = ""
    hostile_graze_transitions = 0
    combat_graze_steps = 0
    exact_combat_graze_steps = 0
    exact_combat_rank_steps = 0
    exact_combat_pending_effect_steps = 0
    item_slot_births = 0
    item_slot_removals = 0
    combat_item_steps = 0
    exact_combat_item_steps = 0
    exact_combat_power_steps = 0

    for left, right in zip(history, history[1:]):
        if right.frame != left.frame + 1:
            continue
        adjacent_pairs += 1
        observed = action_from_input(right.input_mask)
        expected_x, expected_y = _step_player(left, left.x, left.y, observed)
        player_error = math.hypot(expected_x - right.x, expected_y - right.y)
        maximum_player_error = max(maximum_player_error, player_error)
        exact_player_steps += player_error <= 1e-4

        if left.player_attack is not None and right.player_attack is not None:
            before_shots = {
                shot.slot: shot for shot in left.player_attack.shots
            }
            after_shots = {
                shot.slot: shot for shot in right.player_attack.shots
            }
            player_shot_births += len(after_shots.keys() - before_shots.keys())
            player_shot_removals += len(before_shots.keys() - after_shots.keys())
            for slot in before_shots.keys() & after_shots.keys():
                try:
                    expected_shot = step_reimu_a_player_shot(
                        before_shots[slot], left.player_attack
                    )
                except UnsupportedStatefulModel:
                    unsupported_player_shot_steps += 1
                    continue
                if expected_shot is None:
                    continue
                player_shot_steps += 1
                observed_shot = after_shots[slot]
                shot_error = math.hypot(
                    expected_shot.x - observed_shot.x,
                    expected_shot.y - observed_shot.y,
                )
                maximum_player_shot_error = max(
                    maximum_player_shot_error, shot_error
                )
                exact_player_shot_steps += shot_error <= 1e-4
            predicted_attack = None
            if left.player_state in (0, 3):
                try:
                    predicted_attack = step_reimu_a_player_attack(
                        left.player_attack,
                        (right.x, right.y),
                        observed.focused,
                        left.current_power,
                        bool(right.input_mask & BUTTON_SHOOT)
                        and not left.message_active,
                    )
                except UnsupportedStatefulModel:
                    pass
            if predicted_attack is not None:
                player_attack_steps += 1
                orb_exact = (
                    predicted_attack.orb_state == right.player_attack.orb_state
                    and predicted_attack.is_focus == right.player_attack.is_focus
                    and predicted_attack.focus_timer_previous
                    == right.player_attack.focus_timer_previous
                    and predicted_attack.focus_timer
                    == right.player_attack.focus_timer
                    and all(
                        math.hypot(px - ox, py - oy) <= 1e-4
                        for (px, py), (ox, oy) in zip(
                            predicted_attack.orb_positions,
                            right.player_attack.orb_positions,
                        )
                    )
                )
                fire_exact = (
                    predicted_attack.fire_timer_previous
                    == right.player_attack.fire_timer_previous
                    and predicted_attack.fire_timer
                    == right.player_attack.fire_timer
                )
                exact_player_orb_steps += orb_exact
                exact_player_fire_timer_steps += fire_exact
                attack_state_exact = orb_exact and fire_exact
                exact_player_attack_steps += attack_state_exact
                if not attack_state_exact and not first_player_attack_mismatch:
                    first_player_attack_mismatch = (
                        f"f{left.frame}->{right.frame} "
                        f"state={left.player_state} msg={int(left.message_active)} "
                        f"orb={predicted_attack.orb_state}/"
                        f"{right.player_attack.orb_state} "
                        f"focus_timer={predicted_attack.focus_timer_previous},"
                        f"{predicted_attack.focus_timer}/"
                        f"{right.player_attack.focus_timer_previous},"
                        f"{right.player_attack.focus_timer} "
                        f"fire={predicted_attack.fire_timer_previous},"
                        f"{predicted_attack.fire_timer}/"
                        f"{right.player_attack.fire_timer_previous},"
                        f"{right.player_attack.fire_timer}"
                    )
                predicted_shots = {
                    shot.slot: shot for shot in predicted_attack.shots
                }
                for slot in after_shots.keys() - before_shots.keys():
                    predicted = predicted_shots.get(slot)
                    actual = after_shots[slot]
                    if (
                        predicted is not None
                        and math.hypot(
                            predicted.x - actual.x,
                            predicted.y - actual.y,
                        ) <= 1e-4
                        and predicted.damage == actual.damage
                        and predicted.bullet_type == actual.bullet_type
                        and predicted.anm_script == actual.anm_script
                    ):
                        exact_player_shot_births += 1

        left_emitters = {item.slot: item for item in left.spawners}
        right_emitters = {item.slot: item for item in right.spawners}
        enemy_slot_births += len(right_emitters.keys() - left_emitters.keys())
        enemy_slot_removals += len(left_emitters.keys() - right_emitters.keys())
        enemy_life_changes += sum(
            left_emitters[slot].life != right_emitters[slot].life
            for slot in left_emitters.keys() & right_emitters.keys()
        )

        if (
            left.player_attack is not None
            and right.player_attack is not None
            and left.player_state == PLAYER_ALIVE
            and right.player_state == PLAYER_ALIVE
            and bool(right.input_mask & BUTTON_SHOOT)
        ):
            try:
                predicted_world = step_nominal_battle_world(left, observed)
            except (UnsupportedStatefulModel, ValueError):
                unsupported_combat_world_steps += 1
            else:
                combat_world_steps += 1
                predicted_emitters = {
                    item.slot: item for item in predicted_world.spawners
                }
                actual_emitters = {
                    item.slot: item for item in right.spawners
                }
                enemy_transition = (
                    actual_emitters.keys() != left_emitters.keys()
                    or any(
                        left_emitters[slot].life
                        != actual_emitters[slot].life
                        for slot in left_emitters.keys()
                        & actual_emitters.keys()
                    )
                )
                combat_enemy_transition_steps += enemy_transition

                enemy_exact = (
                    predicted_emitters.keys() == actual_emitters.keys()
                )
                enemy_mismatch_detail = ""
                if not enemy_exact:
                    enemy_mismatch_detail = (
                        f"slots={sorted(predicted_emitters)}/"
                        f"{sorted(actual_emitters)}"
                    )
                if enemy_exact:
                    for slot in predicted_emitters:
                        predicted = predicted_emitters[slot]
                        actual = actual_emitters[slot]
                        predicted_address = (
                            predicted.next_instruction.address
                            if predicted.next_instruction is not None
                            else None
                        )
                        actual_address = (
                            actual.next_instruction.address
                            if actual.next_instruction is not None
                            else None
                        )
                        if not (
                            math.hypot(
                                predicted.x - actual.x,
                                predicted.y - actual.y,
                            ) <= 1e-4
                            and predicted.life == actual.life
                            and predicted.interactable == actual.interactable
                            and predicted.collidable == actual.collidable
                            and predicted.invisible == actual.invisible
                            and predicted.damageable == actual.damageable
                            and predicted.death_mode == actual.death_mode
                            and predicted.has_been_in_bounds
                            == actual.has_been_in_bounds
                            and predicted.ecl_time == actual.ecl_time
                            and predicted_address == actual_address
                            and predicted.death_callback_sub
                            == actual.death_callback_sub
                            and predicted.life_callback_threshold
                            == actual.life_callback_threshold
                            and predicted.life_callback_sub
                            == actual.life_callback_sub
                            and predicted.timer_callback_threshold
                            == actual.timer_callback_threshold
                            and predicted.timer_callback_sub
                            == actual.timer_callback_sub
                            and predicted.item_drop == actual.item_drop
                        ):
                            enemy_exact = False
                            enemy_mismatch_detail = (
                                f"slot={slot} "
                                f"life={predicted.life}/{actual.life} "
                                f"pos={predicted.x:.6g},{predicted.y:.6g}/"
                                f"{actual.x:.6g},{actual.y:.6g} "
                                f"flags="
                                f"{int(predicted.interactable)}"
                                f"{int(predicted.collidable)}"
                                f"{int(predicted.invisible)}"
                                f"{int(predicted.damageable)}"
                                f"{predicted.death_mode}/"
                                f"{int(actual.interactable)}"
                                f"{int(actual.collidable)}"
                                f"{int(actual.invisible)}"
                                f"{int(actual.damageable)}"
                                f"{actual.death_mode} "
                                f"ecl={predicted.ecl_time},"
                                f"{predicted_address}/"
                                f"{actual.ecl_time},{actual_address} "
                                f"bounds="
                                f"{int(predicted.has_been_in_bounds)}/"
                                f"{int(actual.has_been_in_bounds)} "
                                f"death_cb={predicted.death_callback_sub}/"
                                f"{actual.death_callback_sub} "
                                f"life_cb="
                                f"{predicted.life_callback_threshold},"
                                f"{predicted.life_callback_sub}/"
                                f"{actual.life_callback_threshold},"
                                f"{actual.life_callback_sub} "
                                f"timer_cb="
                                f"{predicted.timer_callback_threshold},"
                                f"{predicted.timer_callback_sub}/"
                                f"{actual.timer_callback_threshold},"
                                f"{actual.timer_callback_sub} "
                                f"item={predicted.item_drop}/"
                                f"{actual.item_drop}"
                            )
                            break
                if not enemy_exact and not first_combat_enemy_mismatch:
                    first_combat_enemy_mismatch = (
                        f"f{left.frame}->{right.frame} "
                        f"{enemy_mismatch_detail}"
                    )
                exact_combat_enemy_steps += enemy_exact
                exact_combat_enemy_transition_steps += (
                    enemy_transition and enemy_exact
                )

                predicted_attack = predicted_world.player_attack
                shot_exact = predicted_attack is not None
                shot_mismatch_detail = "missing predicted attack"
                if shot_exact:
                    predicted_shots = {
                        shot.slot: shot for shot in predicted_attack.shots
                    }
                    actual_shots = {
                        shot.slot: shot for shot in right.player_attack.shots
                    }
                    shot_exact = predicted_shots.keys() == actual_shots.keys()
                    if not shot_exact:
                        shot_mismatch_detail = (
                            f"slots={sorted(predicted_shots)}/"
                            f"{sorted(actual_shots)}"
                        )
                    if shot_exact:
                        for slot in predicted_shots:
                            predicted = predicted_shots[slot]
                            actual = actual_shots[slot]
                            if not (
                                math.hypot(
                                    predicted.x - actual.x,
                                    predicted.y - actual.y,
                                ) <= 1e-4
                                and math.hypot(
                                    predicted.vx - actual.vx,
                                    predicted.vy - actual.vy,
                                ) <= 1e-4
                                and predicted.state == actual.state
                                and predicted.damage == actual.damage
                                and predicted.bullet_type == actual.bullet_type
                                and predicted.anm_script == actual.anm_script
                                and predicted.timer == actual.timer
                                and predicted.anm_timer == actual.anm_timer
                            ):
                                shot_exact = False
                                shot_mismatch_detail = (
                                    f"slot={slot} "
                                    f"state={predicted.state}/{actual.state} "
                                    f"pos={predicted.x:.6g},{predicted.y:.6g}/"
                                    f"{actual.x:.6g},{actual.y:.6g} "
                                    f"vel={predicted.vx:.6g},{predicted.vy:.6g}/"
                                    f"{actual.vx:.6g},{actual.vy:.6g} "
                                    f"damage={predicted.damage}/{actual.damage} "
                                    f"anm=0x{predicted.anm_script:x},"
                                    f"{predicted.anm_timer}/"
                                    f"0x{actual.anm_script:x},"
                                    f"{actual.anm_timer} "
                                    f"timer={predicted.timer}/{actual.timer}"
                                )
                                break
                if not shot_exact and not first_combat_player_shot_mismatch:
                    first_combat_player_shot_mismatch = (
                        f"f{left.frame}->{right.frame} "
                        f"{shot_mismatch_detail}"
                    )
                exact_combat_player_shot_steps += shot_exact

                predicted_bullets = {
                    bullet.slot: bullet for bullet in predicted_world.bullets
                }
                actual_bullets = {
                    bullet.slot: bullet for bullet in right.bullets
                }
                prior_bullets = {
                    bullet.slot: bullet for bullet in left.bullets
                }
                hostile_graze_transitions += sum(
                    not prior_bullets[slot].is_grazed
                    and actual_bullets[slot].is_grazed
                    for slot in prior_bullets.keys() & actual_bullets.keys()
                )
                retained_bullet_slots = (
                    prior_bullets.keys() & actual_bullets.keys()
                )
                graze_exact = (
                    retained_bullet_slots <= predicted_bullets.keys()
                    and all(
                        predicted_bullets[slot].is_grazed
                        == actual_bullets[slot].is_grazed
                        for slot in retained_bullet_slots
                    )
                )
                combat_graze_steps += 1
                exact_combat_graze_steps += graze_exact
                rank_exact = (
                    predicted_world.rank == right.rank
                    and predicted_world.subrank == right.subrank
                )
                exact_combat_rank_steps += rank_exact
                pending_effect_exact = Counter(
                    predicted_world.pending_effect_rng_ids
                ) == Counter(right.pending_effect_rng_ids)
                exact_combat_pending_effect_steps += pending_effect_exact

                predicted_items = {
                    item.slot: item for item in predicted_world.item_states
                }
                actual_items = {
                    item.slot: item for item in right.item_states
                }
                item_exact = predicted_items.keys() == actual_items.keys()
                if item_exact:
                    item_exact = all(
                        math.hypot(
                            predicted_items[slot].x - actual.x,
                            predicted_items[slot].y - actual.y,
                        ) <= 1e-4
                        and math.hypot(
                            predicted_items[slot].start_x - actual.start_x,
                            predicted_items[slot].start_y - actual.start_y,
                        ) <= 1e-4
                        and math.hypot(
                            predicted_items[slot].target_x - actual.target_x,
                            predicted_items[slot].target_y - actual.target_y,
                        ) <= 1e-4
                        and predicted_items[slot].timer == actual.timer
                        and predicted_items[slot].item_type == actual.item_type
                        and predicted_items[slot].state == actual.state
                        for slot, actual in actual_items.items()
                    )
                combat_item_steps += 1
                exact_combat_item_steps += item_exact
                power_exact = (
                    predicted_world.current_power == right.current_power
                )
                exact_combat_power_steps += power_exact

                rng_exact = (
                    predicted_world.rng_seed == right.rng_seed
                    and predicted_world.rng_generation
                    == right.rng_generation
                    and predicted_world.random_item_spawn_index
                    == right.random_item_spawn_index
                    and predicted_world.random_item_table_index
                    == right.random_item_table_index
                )
                exact_combat_rng_steps += rng_exact
                if not rng_exact and not first_combat_rng_mismatch:
                    first_combat_rng_mismatch = (
                        f"f{left.frame}->{right.frame} "
                        f"seed=0x{predicted_world.rng_seed:04x}/"
                        f"0x{right.rng_seed:04x} "
                        f"generation={predicted_world.rng_generation}/"
                        f"{right.rng_generation} "
                        f"from={left.rng_generation}"
                    )
                if (
                    not (
                        enemy_exact
                        and shot_exact
                        and graze_exact
                        and rank_exact
                        and pending_effect_exact
                        and item_exact
                        and power_exact
                        and rng_exact
                    )
                    and not first_combat_world_mismatch
                ):
                    first_combat_world_mismatch = (
                        f"f{left.frame}->{right.frame} "
                        f"enemy={int(enemy_exact)} "
                        f"shot={int(shot_exact)} "
                        f"graze={int(graze_exact)} "
                        f"rank={int(rank_exact)} "
                        f"pending_effect={int(pending_effect_exact)} "
                        f"item={int(item_exact)} "
                        f"power={int(power_exact)} "
                        f"rng={int(rng_exact)} "
                        f"slots={sorted(predicted_emitters)}/"
                        f"{sorted(actual_emitters)} "
                        f"rng_generation="
                        f"{predicted_world.rng_generation}/"
                        f"{right.rng_generation}"
                    )

        left_by_slot = {bullet.slot: bullet for bullet in left.bullets}
        right_by_slot = {bullet.slot: bullet for bullet in right.bullets}
        births += len(right_by_slot.keys() - left_by_slot.keys())
        removals += len(left_by_slot.keys() - right_by_slot.keys())
        for slot in left_by_slot.keys() & right_by_slot.keys():
            before = left_by_slot[slot]
            after = right_by_slot[slot]
            try:
                expected = step_bullet(before, (right.x, right.y))
            except UnsupportedStatefulModel:
                unsupported_bullet_steps += 1
                continue
            error = math.hypot(expected.x - after.x, expected.y - after.y)
            maximum_bullet_error = max(maximum_bullet_error, error)
            if before.state == 1:
                fired_bullet_steps += 1
                exact_fired_bullet_steps += error <= 1e-4
            else:
                spawning_bullet_steps += 1
                exact_spawning_bullet_steps += error <= 1e-4

        left_items = {item.slot for item in left.item_states}
        right_items = {item.slot for item in right.item_states}
        item_slot_births += len(right_items - left_items)
        item_slot_removals += len(left_items - right_items)

    return PhysicalParity(
        adjacent_pairs,
        exact_player_steps,
        fired_bullet_steps,
        exact_fired_bullet_steps,
        spawning_bullet_steps,
        exact_spawning_bullet_steps,
        maximum_player_error,
        maximum_bullet_error,
        unsupported_bullet_steps,
        births,
        removals,
        player_shot_steps,
        exact_player_shot_steps,
        unsupported_player_shot_steps,
        maximum_player_shot_error,
        player_shot_births,
        player_shot_removals,
        enemy_slot_births,
        enemy_slot_removals,
        enemy_life_changes,
        player_attack_steps,
        exact_player_attack_steps,
        exact_player_shot_births,
        exact_player_orb_steps,
        exact_player_fire_timer_steps,
        first_player_attack_mismatch,
        combat_world_steps,
        exact_combat_enemy_steps,
        exact_combat_player_shot_steps,
        exact_combat_rng_steps,
        combat_enemy_transition_steps,
        exact_combat_enemy_transition_steps,
        unsupported_combat_world_steps,
        first_combat_world_mismatch,
        first_combat_enemy_mismatch,
        first_combat_player_shot_mismatch,
        first_combat_rng_mismatch,
        hostile_graze_transitions,
        combat_graze_steps,
        exact_combat_graze_steps,
        exact_combat_rank_steps,
        exact_combat_pending_effect_steps,
        item_slot_births,
        item_slot_removals,
        combat_item_steps,
        exact_combat_item_steps,
        exact_combat_power_steps,
    )


@dataclass(frozen=True)
class StatefulSweepSummary:
    cases: int
    viable_cases: int
    frames: int
    horizons: tuple[int, ...]
    outcomes: tuple[tuple[int, tuple[tuple[str, int], ...]], ...]
    mean_survival: tuple[tuple[int, float], ...]
    mean_commands: tuple[tuple[int, float], ...]
    mean_decisions: tuple[tuple[int, float], ...]
    mean_minimum_clearance: tuple[tuple[int, float], ...]
    deeper_wins: tuple[tuple[int, int, int], ...]
    birth_events_per_case: int
    case_metrics: tuple[
        tuple[int, tuple[tuple[int, str, int, int, float], ...]], ...
    ]
    first_actions: tuple[
        tuple[int, tuple[tuple[int, str], ...]], ...
    ]


@dataclass(frozen=True)
class NominalBattleDerivationSummary:
    requested_cases: int
    generated_cases: int
    maximum_warmup_frames: int
    outcomes: tuple[tuple[str, int], ...]
    total_warmup_updates: int
    total_born_bullets: int
    source_root_frames: tuple[int, ...]
    unique_enemy_combat_states: int
    unique_player_attack_states: int
    unique_rng_states: int


class _HardWorldExplorationPolicy:
    """Deterministically sample complete Hard-4 reachable-state groups."""

    def __init__(self, seed: int, certifier) -> None:
        self.seed = seed
        self.certifier = certifier
        self.selection_index = 0
        self.selected: Action | None = None
        self.hold_decisions = 0

    def __call__(self, snapshot: Snapshot) -> Action | None:
        hard = self.certifier(snapshot)
        if not hard:
            return None
        by_action = {candidate.action: candidate for candidate in hard}
        if self.selected in by_action and self.hold_decisions > 0:
            self.hold_decisions -= 1
            return self.selected

        # Boundary clamping can make different controls reach the same state.
        # Sample endpoint groups first so those aliases do not receive extra
        # corpus weight merely because they have more action spellings.
        groups: dict[tuple[float, float], list[Action]] = {}
        for candidate in hard:
            groups.setdefault(
                (_f32(candidate.final_x), _f32(candidate.final_y)), []
            ).append(candidate.action)
        ordered = tuple(groups[key] for key in sorted(groups))
        mixed = (
            self.seed * 0x9E3779B1
            + self.selection_index * 0x85EBCA77
        ) & 0xFFFFFFFF
        group = ordered[mixed % len(ordered)]
        self.selected = group[(mixed >> 16) % len(group)]
        self.selection_index += 1
        self.hold_decisions = 3
        return self.selected


def derive_nominal_battle_worlds(
    roots: tuple[Snapshot, ...],
    *,
    cases: int,
    maximum_warmup_frames: int,
    certifier=None,
) -> tuple[tuple[Snapshot, ...], NominalBattleDerivationSummary]:
    """Grow full battle states through safe, pickup-aware nominal play.

    Each output retains the captured bullet pool, enemy VM/timeline state,
    shared RNG and slot occupancy. The varied player history changes source
    aim, Reimu-A shots, enemy damage/death/callbacks, and bullet age before the
    measured policy begins. These worlds remain proposal-only nominal states:
    active global ANM consumers outside the compact combat/ECL model are still
    an explicit RNG boundary.
    """
    if not roots or cases <= 0 or maximum_warmup_frames <= 0:
        raise ValueError("nominal battle derivation dimensions must be positive")
    if certifier is None:
        certifier = lambda snapshot: certify_actions(
            snapshot, 4, actions=CONTROL_ACTIONS
        )

    worlds = []
    outcomes = Counter()
    total_updates = 0
    total_births = 0
    source_frames = set()
    for seed in range(cases):
        root = roots[(seed * 1_315_423_911) % len(roots)]
        source_frames.add(root.frame)
        warmup_frames = 1 + (
            (seed * 2_654_435_761 + 2_246_822_519)
            % maximum_warmup_frames
        )
        history: list[Snapshot] = []
        result = run_closed_loop(
            root,
            _HardWorldExplorationPolicy(seed ^ root.frame, certifier),
            frames=warmup_frames,
            delivery_seed=seed ^ 0xB1771E,
            battle_world=True,
            state_sink=history.append,
        )
        outcomes[result.outcome] += 1
        total_updates += result.survived_frames
        total_births += result.born_bullets
        if result.outcome == "survived":
            worlds.append(history[-1])

    enemy_states = {
        tuple(
            (
                emitter.slot,
                emitter.life,
                emitter.interactable,
                emitter.damageable,
                emitter.death_callback_sub,
            )
            for emitter in world.spawners
        )
        for world in worlds
    }
    return tuple(worlds), NominalBattleDerivationSummary(
        cases,
        len(worlds),
        maximum_warmup_frames,
        tuple(sorted(outcomes.items())),
        total_updates,
        total_births,
        tuple(sorted(source_frames)),
        len(enemy_states),
        len({world.player_attack for world in worlds}),
        len({(world.rng_seed, world.rng_generation) for world in worlds}),
    )


@dataclass(frozen=True)
class HorizonAdvantage:
    seed: int
    shallow_horizon: int
    deep_horizon: int
    shallow: ClosedLoopResult
    deep: ClosedLoopResult
    snapshot: Snapshot
    birth_schedule: tuple = ()


@dataclass(frozen=True)
class PolicyAdvantage:
    seed: int
    horizon: int
    baseline_name: str
    candidate_name: str
    baseline: ClosedLoopResult
    candidate: ClosedLoopResult
    snapshot: Snapshot
    birth_schedule: tuple = ()


def closed_bullet_world(snapshot: Snapshot) -> Snapshot:
    """Project a physical snapshot onto the stateful bullet-only rung.

    This is an offline ablation, not a Hard-certified replacement for the
    omitted enemy, laser, timeline, or callback world.
    """
    return replace(
        snapshot,
        laser_count=0,
        lasers=(),
        enemies=(),
        despawning_bullets=(),
        spawners=(),
        timeline_instructions=(),
        timeline_complete=True,
        timeline_emitter_subs=(),
        timeline_boss_subs=(),
        ecl_subroutines=(),
        timeline_ecl_program=(),
        timeline_message_delays=(),
        timeline_current_message_waits=0,
    )


def sweep_initial_snapshot(
    catalogue,
    seed: int,
    *,
    runtime_templates=(),
    physical_initial_worlds=(),
    physical_battle_worlds=(),
    barrage_family: str = "mixed",
) -> Snapshot:
    """Choose the exact initial state used by a reproducible sweep seed."""
    from .generator import generate_barrage_case

    supplied_worlds = sum(bool(values) for values in (
        runtime_templates,
        physical_initial_worlds,
        physical_battle_worlds,
    ))
    if supplied_worlds > 1:
        raise ValueError(
            "generated templates, bullet ablations, and physical battle "
            "worlds are exclusive"
        )
    index = seed * 1_315_423_911
    if physical_initial_worlds:
        return closed_bullet_world(
            physical_initial_worlds[index % len(physical_initial_worlds)]
        )
    if physical_battle_worlds:
        return physical_battle_worlds[index % len(physical_battle_worlds)]
    return generate_barrage_case(
        catalogue,
        seed,
        runtime_template=(
            runtime_templates[index % len(runtime_templates)]
            if runtime_templates else None
        ),
        barrage_family=barrage_family,
    ).snapshot


def _deeper_better(
    shallow: ClosedLoopResult,
    deep: ClosedLoopResult,
) -> bool:
    return (
        deep.survived_frames > shallow.survived_frames
        or deep.outcome == "survived" and shallow.outcome != "survived"
    )


def shrink_horizon_advantage(
    advantage: HorizonAdvantage,
    *,
    frames: int,
    delivery_seed: int,
    policy_factory=ExactTerminalPolicy,
) -> HorizonAdvantage:
    """Delta-debug bullets while preserving a closed-loop deep-policy win."""
    bullets = list(advantage.snapshot.bullets)

    events = list(advantage.birth_schedule)

    def evaluate(values: list[Bullet], schedule=events):
        state = replace(advantage.snapshot, bullets=tuple(values))
        if not certify_linear_source(state, 4).actions:
            return None
        shallow = run_closed_loop(
            state,
            policy_factory(advantage.shallow_horizon),
            frames=frames,
            delivery_seed=delivery_seed,
            birth_schedule=schedule,
        )
        deep = run_closed_loop(
            state,
            policy_factory(advantage.deep_horizon),
            frames=frames,
            delivery_seed=delivery_seed,
            birth_schedule=schedule,
        )
        return shallow, deep

    granularity = 2
    while len(bullets) >= 2:
        chunk = max(1, (len(bullets) + granularity - 1) // granularity)
        reduced = False
        for start in range(0, len(bullets), chunk):
            candidate = bullets[:start] + bullets[start + chunk:]
            if not candidate:
                continue
            result = evaluate(candidate)
            if result is not None and _deeper_better(*result):
                bullets = candidate
                granularity = max(2, granularity - 1)
                reduced = True
                break
        if reduced:
            continue
        if granularity >= len(bullets):
            break
        granularity = min(len(bullets), granularity * 2)

    granularity = 2
    while events:
        chunk = max(1, (len(events) + granularity - 1) // granularity)
        reduced = False
        for start in range(0, len(events), chunk):
            candidate = events[:start] + events[start + chunk:]
            result = evaluate(bullets, candidate)
            if result is not None and _deeper_better(*result):
                events = candidate
                granularity = max(2, granularity - 1)
                reduced = True
                break
        if reduced:
            continue
        if granularity >= len(events):
            break
        granularity = min(len(events), granularity * 2)

    state = replace(advantage.snapshot, bullets=tuple(bullets))
    shallow, deep = evaluate(bullets, events)
    return replace(
        advantage,
        shallow=shallow,
        deep=deep,
        snapshot=state,
        birth_schedule=tuple(events),
    )


def shrink_policy_advantage(
    advantage: PolicyAdvantage,
    *,
    frames: int,
    delivery_seed: int,
    baseline_factory,
    candidate_factory,
) -> PolicyAdvantage:
    """Delta-debug initial bullets and births preserving a policy win."""
    bullets = list(advantage.snapshot.bullets)
    events = list(advantage.birth_schedule)

    def evaluate(values: list[Bullet], schedule):
        state = replace(advantage.snapshot, bullets=tuple(values))
        if not certify_linear_source(state, 4).actions:
            return None
        baseline = run_closed_loop(
            state,
            baseline_factory(advantage.horizon),
            frames=frames,
            delivery_seed=delivery_seed,
            birth_schedule=schedule,
        )
        candidate = run_closed_loop(
            state,
            candidate_factory(advantage.horizon),
            frames=frames,
            delivery_seed=delivery_seed,
            birth_schedule=schedule,
        )
        return baseline, candidate

    def reduce(values, other, values_are_bullets):
        current = list(values)
        granularity = 2
        while current:
            chunk = max(1, (len(current) + granularity - 1) // granularity)
            reduced = False
            for start in range(0, len(current), chunk):
                candidate_values = current[:start] + current[start + chunk:]
                result = (
                    evaluate(candidate_values, other)
                    if values_are_bullets
                    else evaluate(other, candidate_values)
                )
                if result is not None and _deeper_better(*result):
                    current = candidate_values
                    granularity = max(2, granularity - 1)
                    reduced = True
                    break
            if reduced:
                continue
            if granularity >= len(current):
                break
            granularity = min(len(current), granularity * 2)
        return current

    bullets = reduce(bullets, events, True)
    events = reduce(events, bullets, False)
    state = replace(advantage.snapshot, bullets=tuple(bullets))
    baseline, candidate = evaluate(bullets, events)
    return replace(
        advantage,
        baseline=baseline,
        candidate=candidate,
        snapshot=state,
        birth_schedule=tuple(events),
    )


def run_stateful_sweep(
    catalogue,
    *,
    seeds: int,
    frames: int,
    horizons: tuple[int, ...],
    runtime_templates=(),
    physical_initial_worlds=(),
    physical_battle_worlds=(),
    policy_factory=ExactTerminalPolicy,
    birth_events_per_case: int = 0,
    barrage_family: str = "mixed",
) -> tuple[StatefulSweepSummary, HorizonAdvantage | None]:
    """Fuzz complete decision/pickup/world sequences, not isolated queries."""
    from .generator import generate_barrage_births

    if seeds <= 0 or frames <= 0 or not horizons or birth_events_per_case < 0:
        raise ValueError("stateful sweep dimensions must be positive")
    if tuple(sorted(set(horizons))) != horizons or horizons[0] < 4:
        raise ValueError("stateful horizons must be unique, sorted, and >= 4")
    supplied_worlds = sum(bool(values) for values in (
        runtime_templates,
        physical_initial_worlds,
        physical_battle_worlds,
    ))
    if supplied_worlds > 1:
        raise ValueError(
            "generated templates, bullet ablations, and physical battle "
            "worlds are exclusive"
        )
    if physical_battle_worlds and birth_events_per_case:
        raise ValueError(
            "physical battle worlds already obtain births from ECL/timeline"
        )

    outcomes = {horizon: Counter() for horizon in horizons}
    survival = {horizon: 0 for horizon in horizons}
    commands = {horizon: 0 for horizon in horizons}
    decisions = {horizon: 0 for horizon in horizons}
    minimum_clearances = {horizon: 0.0 for horizon in horizons}
    case_metrics = {horizon: [] for horizon in horizons}
    first_actions = {horizon: [] for horizon in horizons}
    wins = Counter()
    viable_cases = 0
    first_advantage = None

    for seed in range(seeds):
        snapshot = sweep_initial_snapshot(
            catalogue,
            seed,
            runtime_templates=runtime_templates,
            physical_initial_worlds=physical_initial_worlds,
            physical_battle_worlds=physical_battle_worlds,
            barrage_family=barrage_family,
        )
        # A generated seed that is already touching a kill box is not a
        # decision problem.  The four-frame certifier starts at the next
        # update, so it cannot be used as a substitute for this current-frame
        # source collision gate.
        initially_safe = (
            certify_actions(snapshot, 4, actions=CONTROL_ACTIONS)
            if physical_battle_worlds
            else certify_linear_source(snapshot, 4).actions
        )
        if collides_now(snapshot) or not initially_safe:
            continue
        birth_schedule = (
            ()
            if physical_battle_worlds
            else generate_barrage_births(
                catalogue,
                seed,
                snapshot,
                frames=frames,
                events=birth_events_per_case,
                barrage_family=barrage_family,
            )
        )
        viable_cases += 1
        results = {}
        for horizon in horizons:
            result = run_closed_loop(
                snapshot,
                policy_factory(horizon),
                frames=frames,
                delivery_seed=seed,
                birth_schedule=birth_schedule,
                battle_world=bool(physical_battle_worlds),
            )
            results[horizon] = result
            outcomes[horizon][result.outcome] += 1
            survival[horizon] += result.survived_frames
            commands[horizon] += result.commands
            decisions[horizon] += result.decisions
            minimum_clearances[horizon] += result.minimum_clearance
            case_metrics[horizon].append((
                seed,
                result.outcome,
                result.survived_frames,
                result.commands,
                result.minimum_clearance,
            ))
            first_actions[horizon].append((
                seed,
                result.decision_trace[0][1]
                if result.decision_trace else "",
            ))
        for shallow_horizon, deep_horizon in zip(horizons, horizons[1:]):
            shallow = results[shallow_horizon]
            deep = results[deep_horizon]
            if _deeper_better(shallow, deep):
                wins[shallow_horizon, deep_horizon] += 1
                if first_advantage is None:
                    first_advantage = HorizonAdvantage(
                        seed,
                        shallow_horizon,
                        deep_horizon,
                        shallow,
                        deep,
                        snapshot,
                        birth_schedule,
                    )

    return StatefulSweepSummary(
        seeds,
        viable_cases,
        frames,
        horizons,
        tuple(
            (horizon, tuple(sorted(outcomes[horizon].items())))
            for horizon in horizons
        ),
        tuple(
            (
                horizon,
                survival[horizon] / viable_cases if viable_cases else 0.0,
            )
            for horizon in horizons
        ),
        tuple(
            (
                horizon,
                commands[horizon] / viable_cases if viable_cases else 0.0,
            )
            for horizon in horizons
        ),
        tuple(
            (
                horizon,
                decisions[horizon] / viable_cases if viable_cases else 0.0,
            )
            for horizon in horizons
        ),
        tuple(
            (
                horizon,
                minimum_clearances[horizon] / viable_cases
                if viable_cases else 0.0,
            )
            for horizon in horizons
        ),
        tuple(
            (shallow, deep, count)
            for (shallow, deep), count in sorted(wins.items())
        ),
        birth_events_per_case,
        tuple(
            (horizon, tuple(case_metrics[horizon]))
            for horizon in horizons
        ),
        tuple(
            (horizon, tuple(first_actions[horizon]))
            for horizon in horizons
        ),
    ), first_advantage
