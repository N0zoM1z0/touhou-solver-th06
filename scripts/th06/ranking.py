"""Soft proposal ranking over an already Hard-certified action set."""

from __future__ import annotations

from .model import Action, SafeAction, Snapshot, action_from_input


# GameManager::AddedCallback defines this center-position movement rectangle;
# Player::HandlePlayerInputs clamps the player center to it after movement.
_MOVEMENT_LEFT = 8.0
_MOVEMENT_RIGHT = 376.0
_MOVEMENT_TOP = 16.0
_MOVEMENT_BOTTOM = 432.0


def _preferred_free_space(candidate: SafeAction) -> float:
    """Source-defined movement-area clearance for an otherwise exact tie."""
    return min(
        candidate.final_x - _MOVEMENT_LEFT,
        _MOVEMENT_RIGHT - candidate.final_x,
        candidate.final_y - _MOVEMENT_TOP,
        _MOVEMENT_BOTTOM - candidate.final_y,
    )


class ProposalRanker:
    """Keep one short plan stable without acquiring action authority."""

    def __init__(self) -> None:
        self.committed_action: Action | None = None
        self.commit_until_frame: int | None = None
        self.last_frame: int | None = None

    def observe(self, _survived: bool) -> None:
        """Learning is deliberately disabled until contextual proposals exist."""

    def reset_plan(self) -> None:
        """Discard proposal commitment after a physical discontinuity."""
        self.committed_action = None
        self.commit_until_frame = None
        self.last_frame = None

    def choose(
        self,
        snapshot: Snapshot,
        candidates: tuple[SafeAction, ...],
        preferred_actions: frozenset[Action] = frozenset(),
        commitment_frames: int = 4,
    ) -> SafeAction:
        if not candidates:
            raise ValueError("proposal ranking needs a Hard-certified action")
        current = action_from_input(snapshot.input_mask)
        actions = frozenset(candidate.action for candidate in candidates)
        preferred_clearances = frozenset(
            candidate.clearance
            for candidate in candidates
            if candidate.action in preferred_actions
        )
        preferred_clearance_tied = len(preferred_clearances) == 1

        discontinuity = (
            self.last_frame is not None and snapshot.frame <= self.last_frame
        )
        commitment_expired = (
            self.commit_until_frame is not None
            and snapshot.frame >= self.commit_until_frame
        )
        commitment_invalid = (
            self.committed_action is not None
            and (
                self.committed_action not in actions
                or self.committed_action not in preferred_actions
            )
        )
        renewable_action = (
            self.committed_action
            if (
                commitment_expired
                and not discontinuity
                and not commitment_invalid
            )
            else None
        )
        if discontinuity or commitment_expired or commitment_invalid:
            self.committed_action = None
            self.commit_until_frame = None

        if not preferred_actions:
            # With no fresh continuation proposal, Hard clearance only proves
            # short-horizon eligibility; it does not justify issuing a new
            # route direction.  Retain the observed input while it remains in
            # the fresh Hard set, and fall back to clearance only when that
            # input itself is no longer eligible.
            current_candidate = next(
                (
                    candidate for candidate in candidates
                    if candidate.action == current
                ),
                None,
            )
            if current_candidate is not None:
                self.committed_action = None
                self.commit_until_frame = None
                self.last_frame = snapshot.frame
                return current_candidate

        def score(candidate: SafeAction) -> tuple[
            bool, bool, float, bool, bool, bool, float, bool, str,
        ]:
            preferred = candidate.action in preferred_actions
            return (
                preferred,
                # Equal strongest continuation evidence does not justify the
                # larger displacement of an unfocused segment.  Focused
                # motion preserves correction reserve if the next soft rung
                # misses its compute deadline; Hard has already certified
                # the required Focus transition and retains sole authority.
                preferred and candidate.action.focused,
                (
                    _preferred_free_space(candidate)
                    if preferred and preferred_clearance_tied
                    else 0.0
                ),
                candidate.action == self.committed_action,
                # Expiry bounds a stale commitment; it need not manufacture
                # a route switch when the same action is still present in the
                # strongest fresh continuation set. Renew it ahead of noisy
                # Hard-window clearance, while target/free-space evidence and
                # any changed preferred set retain higher authority.
                candidate.action == renewable_action,
                # Avoid an extra Focus edge unless stronger continuation
                # evidence selected the other mode. This is publication
                # continuity, not a fixed preference for focused movement.
                candidate.action.focused == current.focused,
                candidate.clearance,
                candidate.action == current,
                candidate.action.name,
            )

        chosen = max(candidates, key=score)
        if (
            preferred_actions
            and len(preferred_actions) < len(actions)
            and chosen.action in preferred_actions
        ):
            self.committed_action = chosen.action
            self.commit_until_frame = (
                snapshot.frame + max(1, commitment_frames)
            )
        elif not preferred_actions:
            self.committed_action = None
            self.commit_until_frame = None
        self.last_frame = snapshot.frame
        return chosen
