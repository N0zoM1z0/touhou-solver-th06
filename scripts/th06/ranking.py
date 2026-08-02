"""Soft proposal ranking over an already Hard-certified action set."""

from __future__ import annotations

from .model import Action, SafeAction, Snapshot, action_from_input


class ProposalRanker:
    """Keep one short plan stable without acquiring action authority."""

    def __init__(self) -> None:
        self.committed_action: Action | None = None
        self.commit_until_frame: int | None = None
        self.last_frame: int | None = None

    def observe(self, _survived: bool) -> None:
        """Learning is deliberately disabled until contextual proposals exist."""

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
        if discontinuity or commitment_expired or commitment_invalid:
            self.committed_action = None
            self.commit_until_frame = None

        def score(candidate: SafeAction) -> tuple[
            bool, bool, bool, float, bool, str,
        ]:
            return (
                candidate.action in preferred_actions,
                candidate.action == self.committed_action,
                candidate.action.focused,
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
