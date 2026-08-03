"""Small source-stepped, stateful barrage replay and fuzzing primitives.

The existing barrage lab checks isolated solver queries.  This module keeps
the player, held input, command pickup, proposal state, and fired bullets
alive across frames so an earlier decision can cause a later failure.  It is
deliberately narrow: unsupported world state is reported instead of silently
approximated.
"""

from __future__ import annotations

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
    SafeAction,
    Snapshot,
    action_from_input,
)
from ..ranking import ProposalRanker
from ..safety import transition_actions
from ..viability import replanning_scores as source_replanning_scores
from ..guidance import terminal_reachability_counts
from ..hazards.geometry import signed_clearance
from ..hazards.births import spawn_pattern
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
    "constant-reserve-count",
    "count-clearance",
    "count-clearance-confirmed",
    "count-focus-clearance",
    "count-focus-clearance-confirmed",
    "clearance-count",
)
# BulletManager::OnUpdate advances these three spawn states before calling the
# installed bullet ANM script.  The standard archive completes the scripts on
# timer 9/15/31 respectively; every physical transition in the retained
# corpus observes those same boundaries.
_SPAWN_DIVISOR = {2: 2.0, 3: 2.5, 4: 3.0}
_SPAWN_FINAL_TIMER = {2: 9, 3: 15, 4: 31}


class UnsupportedStatefulModel(ValueError):
    """The compact forward model lacks authority for this source state."""


def _f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


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

    return replace(
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
    spawning = replace(
        bullet,
        x=_f32(_f32(bullet.x) + _f32(_f32(bullet.vx) / divisor)),
        y=_f32(_f32(bullet.y) + _f32(_f32(bullet.vy) / divisor)),
    )
    if bullet.timer < _SPAWN_FINAL_TIMER[bullet.state]:
        return replace(
            spawning,
            timer=bullet.timer + 1,
            timer_float=_f32(bullet.timer_float + 1.0),
        )
    # ExecuteScript completed: source resets the timer, changes state, and
    # deliberately falls through into BULLET_STATE_FIRED in this same update.
    return step_fired_bullet(
        replace(
            spawning,
            state=1,
            timer=0,
            timer_float=0.0,
        ),
        player_position,
    )


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


def collides_now(snapshot: Snapshot) -> bool:
    """Check the source kill boxes at the already-updated current frame."""
    return any(
        _within_margin(
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
            0.0,
        )
        for bullet in snapshot.bullets
        if bullet.state == 1
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
        ):
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
                preferred = _authority_filtered_preferred(
                    replanning,
                    {
                        candidate.action: deep[candidate.action.name]
                        for candidate in candidates
                    },
                )
            else:
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
        if self.horizon == 4:
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
        ):
            replanning = self.kernel.macro_tail_scores_budgeted(
                snapshot,
                hard,
                4,
                min(8, self.horizon),
                collision_margin=0.35,
                budget_ms=1000.0,
            )
            if replanning is None:
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
            else:
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
            if pending.name not in certify_linear_source(
                state, 1, actions=leased_actions
            ).actions:
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
        state = step_closed_world(
            state,
            step_action,
            births_by_update.get(update, ()),
        )
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

    for left, right in zip(history, history[1:]):
        if right.frame != left.frame + 1:
            continue
        adjacent_pairs += 1
        observed = action_from_input(right.input_mask)
        expected_x, expected_y = _step_player(left, left.x, left.y, observed)
        player_error = math.hypot(expected_x - right.x, expected_y - right.y)
        maximum_player_error = max(maximum_player_error, player_error)
        exact_player_steps += player_error <= 1e-4

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
    policy_factory=ExactTerminalPolicy,
    birth_events_per_case: int = 0,
) -> tuple[StatefulSweepSummary, HorizonAdvantage | None]:
    """Fuzz complete decision/pickup/world sequences, not isolated queries."""
    from .generator import generate_barrage_births, generate_barrage_case

    if seeds <= 0 or frames <= 0 or not horizons or birth_events_per_case < 0:
        raise ValueError("stateful sweep dimensions must be positive")
    if tuple(sorted(set(horizons))) != horizons or horizons[0] < 4:
        raise ValueError("stateful horizons must be unique, sorted, and >= 4")

    outcomes = {horizon: Counter() for horizon in horizons}
    survival = {horizon: 0 for horizon in horizons}
    commands = {horizon: 0 for horizon in horizons}
    decisions = {horizon: 0 for horizon in horizons}
    minimum_clearances = {horizon: 0.0 for horizon in horizons}
    case_metrics = {horizon: [] for horizon in horizons}
    wins = Counter()
    viable_cases = 0
    first_advantage = None

    for seed in range(seeds):
        case = generate_barrage_case(
            catalogue,
            seed,
            runtime_template=(
                runtime_templates[
                    (seed * 1_315_423_911) % len(runtime_templates)
                ]
                if runtime_templates else None
            ),
        )
        # A generated seed that is already touching a kill box is not a
        # decision problem.  The four-frame certifier starts at the next
        # update, so it cannot be used as a substitute for this current-frame
        # source collision gate.
        if (
            collides_now(case.snapshot)
            or not certify_linear_source(case.snapshot, 4).actions
        ):
            continue
        birth_schedule = generate_barrage_births(
            catalogue,
            seed,
            case.snapshot,
            frames=frames,
            events=birth_events_per_case,
        )
        viable_cases += 1
        results = {}
        for horizon in horizons:
            result = run_closed_loop(
                case.snapshot,
                policy_factory(horizon),
                frames=frames,
                delivery_seed=seed,
                birth_schedule=birth_schedule,
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
                        case.snapshot,
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
    ), first_advantage
