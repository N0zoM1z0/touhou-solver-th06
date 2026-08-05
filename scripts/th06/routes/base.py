"""Minimal contract between route strategy and the common Hard runtime.

The common solver owns sensing and Hard authority.  A route receives that
already-certified set and may only rank actions inside it.  ``RouteIntent`` is
retained as the compact authoring format used by the existing phase tables;
``RouteProposal`` is the executable boundary used by the online runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..model import Action, SafeAction, Snapshot


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

    This is retained as a compact phase-table/offline-authoring format.  The
    route-side adapter in ``routes.policy`` turns legacy intent algorithms
    into executable proposals; the common runtime does not interpret an
    algorithm name. ``policy-volume`` compares bounded source-shaped local
    continuations at the route-selected horizon.
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
            "compiled-policy",
            "target-only",
            "uncovered",
        ):
            raise ValueError(f"unsupported route algorithm {self.algorithm!r}")
        if self.horizon < 4:
            raise ValueError("route horizon cannot be shorter than Hard-4")
        if self.commitment_frames <= 0:
            raise ValueError("route commitment must be positive")


class ProposalServices(Protocol):
    """Read-only shared evaluators available to a soft route policy.

    These helpers use the common source model and collision constants, but
    their results are never authority: the common solver intersects every
    returned tier with the original fresh Hard set before selecting an action.
    """

    def remaining_budget_ms(self) -> float:
        """Return the proposal budget remaining before publication guard."""

    def certify_selected(
        self,
        snapshot: Snapshot,
        horizon: int,
        actions: tuple[Action, ...],
    ) -> tuple[SafeAction, ...]:
        """Evaluate a soft constant-action continuation."""

    def certify_selected_budgeted(
        self,
        snapshot: Snapshot,
        horizon: int,
        actions: tuple[Action, ...],
    ) -> tuple[SafeAction, ...] | None:
        """Evaluate one complete continuation inside the publication budget."""

    def replanning_scores(
        self,
        snapshot: Snapshot,
        candidates: tuple[SafeAction, ...],
        split: int,
        horizon: int,
    ) -> dict[Action, int] | None:
        """Evaluate a complete two-command repair inside the deadline."""

    def nominal_policy_counts(
        self,
        snapshot: Snapshot,
        hard: tuple[SafeAction, ...],
        horizon: int,
    ) -> dict[Action, int] | None:
        """Return bounded local-continuation counts, or ``None`` on timeout."""

    def terminal_guidance(
        self,
        snapshot: Snapshot,
        hard: tuple[SafeAction, ...],
        horizon: int,
    ) -> dict[Action, object] | None:
        """Return bounded terminal count/clearance data, or timeout."""


@dataclass(frozen=True)
class ProposalRequest:
    """One fresh snapshot and its immutable common Hard authority."""

    snapshot: Snapshot
    hard: tuple[SafeAction, ...]
    services: ProposalServices


@dataclass(frozen=True)
class RouteProposal:
    """An inspectable soft ranking that cannot add an action to Hard.

    ``action_tiers`` are ordered strongest-first.  Actions inside one tier are
    tied.  The common runtime uses the first tier that still intersects the
    same fresh Hard set; this preserves a compiled policy's fallback order
    without granting it collision authority.
    """

    phase_id: str
    policy_state: str
    action_tiers: tuple[tuple[Action, ...], ...]
    commitment_frames: int
    effort_horizon: int
    proposal_source: str
    provenance: str = ""
    available: bool = True

    def __post_init__(self) -> None:
        if self.commitment_frames <= 0:
            raise ValueError("route commitment must be positive")
        if self.effort_horizon < 4:
            raise ValueError("route effort horizon cannot be shorter than Hard-4")
        flattened = tuple(action for tier in self.action_tiers for action in tier)
        if len(flattened) != len(frozenset(flattened)):
            raise ValueError("an action may appear in only one proposal tier")
        if any(not tier for tier in self.action_tiers):
            raise ValueError("proposal tiers cannot be empty")

    def first_hard_tier(
        self,
        hard_actions: frozenset[Action],
    ) -> tuple[Action, ...]:
        """Intersect ordered tiers with the publication snapshot's Hard set."""
        for tier in self.action_tiers:
            eligible = tuple(action for action in tier if action in hard_actions)
            if eligible:
                return eligible
        return ()


class RoutePack(Protocol):
    key: RouteKey
    route_id: str

    def intent(self, snapshot: Snapshot) -> RouteIntent | None:
        """Describe the selected source phase for audit/offline tooling."""

    def propose(self, request: ProposalRequest) -> RouteProposal | None:
        """Rank only actions from ``request.hard`` for the selected phase."""
