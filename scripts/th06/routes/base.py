"""Minimal contract between route strategy and the common Hard runtime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..model import Action, Snapshot


@dataclass(frozen=True)
class RouteKey:
    difficulty: int
    character: int
    shot_type: int
    stage: int

    @property
    def name(self) -> str:
        return (
            f"d{self.difficulty}:c{self.character}:"
            f"s{self.shot_type}:stage{self.stage}"
        )


@dataclass(frozen=True)
class RouteIntent:
    """One short soft request evaluated only inside a fresh Hard set.

    ``policy-volume`` asks the common runtime primitive to compare bounded
    source-shaped local continuations at the route-selected horizon.
    ``count-clearance`` ranks those continuations first by deduplicated
    terminal volume and then by their best terminal hazard clearance.
    ``constant-frontier`` keeps the subset that survives one unchanged-action
    segment at that horizon. ``constant-clearance`` ranks that reserve by the
    minimum hazard clearance along the same unchanged-action segment.
    ``constant-frontier-count`` retains the whole reserve as an eligibility
    filter, then ranks only inside it by terminal reachable-state count. A
    later phase may instead provide already compiled ``preferred_actions`` or
    use ``target-only``. No field can add an action to Hard.
    """

    phase_id: str
    policy_state: str
    algorithm: str
    horizon: int
    target: tuple[float, float] | None
    commitment_frames: int
    preferred_actions: tuple[Action, ...] = ()
    provenance: str = ""

    def __post_init__(self) -> None:
        if self.algorithm not in (
            "policy-volume",
            "count-clearance",
            "constant-frontier",
            "constant-clearance",
            "constant-frontier-count",
            "target-only",
            "uncovered",
        ):
            raise ValueError(f"unsupported route algorithm {self.algorithm!r}")
        if self.horizon < 4:
            raise ValueError("route horizon cannot be shorter than Hard-4")
        if self.commitment_frames <= 0:
            raise ValueError("route commitment must be positive")


class RoutePack(Protocol):
    key: RouteKey
    route_id: str

    def intent(self, snapshot: Snapshot) -> RouteIntent | None:
        """Return the current source-phase proposal, or expose no coverage."""
