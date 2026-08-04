"""Exact route lookup; route strategy never falls across route keys."""

from __future__ import annotations

from dataclasses import dataclass

from ..model import Snapshot
from .base import RouteKey, RoutePack
from .stage4_hard_reimu_a import HardReimuAStage4


def snapshot_route_key(snapshot: Snapshot) -> RouteKey | None:
    if snapshot.player_attack is None:
        return None
    return RouteKey(
        difficulty=snapshot.difficulty,
        character=snapshot.character,
        shot_type=snapshot.player_attack.shot_type,
        stage=snapshot.stage,
    )


@dataclass(frozen=True)
class RouteRegistry:
    packs: tuple[RoutePack, ...]

    def __post_init__(self) -> None:
        keys = tuple(pack.key for pack in self.packs)
        if len(keys) != len(frozenset(keys)):
            raise ValueError("duplicate route key")

    def resolve(self, snapshot: Snapshot) -> RoutePack | None:
        key = snapshot_route_key(snapshot)
        if key is None:
            return None
        return next((pack for pack in self.packs if pack.key == key), None)


def default_routes() -> RouteRegistry:
    return RouteRegistry((HardReimuAStage4(),))
