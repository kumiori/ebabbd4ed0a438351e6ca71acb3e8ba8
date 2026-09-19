"""Neutral coarse-grained persistence protocol and in-memory reference store."""

from __future__ import annotations

from copy import deepcopy
from typing import Protocol

from .runtime import Trajectory


class TrajectoryStore(Protocol):
    def load(self, participation_id: str) -> Trajectory | None: ...
    def checkpoint(self, trajectory: Trajectory) -> Trajectory: ...
    def integrate(self, trajectory: Trajectory, *, idempotency_key: str) -> Trajectory: ...


class InMemoryTrajectoryStore:
    def __init__(self) -> None:
        self._trajectories: dict[str, Trajectory] = {}
        self._integrations: dict[str, Trajectory] = {}
        self.load_calls = 0
        self.checkpoint_calls = 0
        self.integration_calls = 0

    def load(self, participation_id: str) -> Trajectory | None:
        self.load_calls += 1
        value = self._trajectories.get(participation_id)
        return deepcopy(value) if value else None

    def checkpoint(self, trajectory: Trajectory) -> Trajectory:
        self.checkpoint_calls += 1
        self._trajectories[trajectory.participation.id] = deepcopy(trajectory)
        return deepcopy(trajectory)

    def integrate(self, trajectory: Trajectory, *, idempotency_key: str) -> Trajectory:
        self.integration_calls += 1
        if idempotency_key in self._integrations:
            return deepcopy(self._integrations[idempotency_key])
        stored = deepcopy(trajectory)
        self._integrations[idempotency_key] = stored
        self._trajectories[trajectory.participation.id] = stored
        return deepcopy(stored)
