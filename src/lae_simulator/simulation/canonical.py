"""Shared event-fold contract for every canonical simulation family.

Event families may keep their versioned payload types, but live execution,
replay, and stored-state validation all use this one ordered fold.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from enum import StrEnum
from typing import Protocol, TypeVar

StateT = TypeVar("StateT")
EventT = TypeVar("EventT")

Reducer = Callable[[StateT, EventT, int], StateT]


class CanonicalState(Protocol):
    @property
    def run_id(self) -> str: ...
    @property
    def logical_time(self) -> int: ...
    @property
    def actor_id(self) -> str: ...
    @property
    def workspace_version(self) -> str: ...


class CanonicalEventContract(Protocol):
    @property
    def id(self) -> str: ...
    @property
    def run_id(self) -> str: ...
    @property
    def order(self) -> int: ...
    @property
    def logical_time(self) -> int: ...
    @property
    def kind(self) -> StrEnum: ...
    @property
    def actor_id(self) -> str | None: ...
    @property
    def target_id(self) -> str | None: ...
    @property
    def input_version(self) -> str | None: ...
    @property
    def output_version(self) -> str | None: ...
    @property
    def caused_by(self) -> tuple[str, ...]: ...


def start_execution(definition: object) -> object:
    """Create a live execution for a validated canonical definition."""
    from lae_simulator.simulation.engine import _Execution
    from lae_simulator.simulation.local_engine import LocalSession
    from lae_simulator.simulation.local_model import ScenarioExecution, stable_run_id
    from lae_simulator.simulation.local_reducer import initial_local_state
    from lae_simulator.world.model import WorldDefinition

    if isinstance(definition, WorldDefinition):
        return _Execution(definition)
    if isinstance(definition, ScenarioExecution):
        if not definition.verified:
            raise ValueError("G3 execution requires a verified G1/G2 scenario")
        session = LocalSession(definition, initial_local_state(definition, stable_run_id(definition)), [])
        session.initialize_timing()
        return session
    raise TypeError("unsupported canonical definition")


def transition(definition: object, state: CanonicalState, event: CanonicalEventContract,
               expected_order: int) -> CanonicalState:
    """One transition boundary for live execution and historical replay."""
    from lae_simulator.simulation.local_model import (
        LocalEvent,
        LocalState,
        ScenarioExecution,
    )
    from lae_simulator.simulation.local_reducer import reduce_local_event
    from lae_simulator.simulation.model import CanonicalEvent, SimulationState
    from lae_simulator.simulation.reducer import reduce_event
    from lae_simulator.world.model import WorldDefinition

    if isinstance(definition, WorldDefinition) and isinstance(state, SimulationState) and isinstance(event, CanonicalEvent):
        return reduce_event(definition, state, event, expected_order=expected_order)
    if isinstance(definition, ScenarioExecution) and isinstance(state, LocalState) and isinstance(event, LocalEvent):
        return reduce_local_event(definition, state, event, expected_order=expected_order)
    raise TypeError("definition, state, and event must belong to the same canonical family")


def project_verified(definition: object, initial: CanonicalState,
                     events: tuple[CanonicalEventContract, ...],
                     final: CanonicalState) -> tuple[object, ...]:
    """Apply the family publication ceiling after canonical replay validation."""
    from lae_simulator.simulation.local_model import (
        LocalEvent,
        LocalState,
        ScenarioExecution,
    )
    from lae_simulator.simulation.local_projector import project_local_log
    from lae_simulator.simulation.model import CanonicalEvent, SimulationState
    from lae_simulator.simulation.projector import project_public_log
    from lae_simulator.world.model import WorldDefinition

    if (isinstance(definition, WorldDefinition) and isinstance(initial, SimulationState)
            and isinstance(final, SimulationState) and all(isinstance(e, CanonicalEvent) for e in events)):
        return project_public_log(definition, initial, tuple(e for e in events if isinstance(e, CanonicalEvent)), final)
    if (isinstance(definition, ScenarioExecution) and isinstance(initial, LocalState)
            and isinstance(final, LocalState) and all(isinstance(e, LocalEvent) for e in events)):
        return project_local_log(definition, initial, tuple(e for e in events if isinstance(e, LocalEvent)), final)
    raise TypeError("definition, history, and state must belong to the same canonical family")


def replay_history(definition: object, initial: CanonicalState,
                   events: tuple[CanonicalEventContract, ...]) -> CanonicalState:
    """Reconstruct either family through the common transition contract."""
    from lae_simulator.simulation.local_model import (
        LocalEvent,
        LocalState,
        ScenarioExecution,
    )
    from lae_simulator.simulation.local_reducer import replay_local
    from lae_simulator.simulation.model import CanonicalEvent, SimulationState
    from lae_simulator.simulation.reducer import replay
    from lae_simulator.world.model import WorldDefinition

    if (isinstance(definition, WorldDefinition) and isinstance(initial, SimulationState)
            and all(isinstance(e, CanonicalEvent) for e in events)):
        return replay(definition, initial, tuple(e for e in events if isinstance(e, CanonicalEvent)))
    if (isinstance(definition, ScenarioExecution) and isinstance(initial, LocalState)
            and all(isinstance(e, LocalEvent) for e in events)):
        return replay_local(definition, initial, tuple(e for e in events if isinstance(e, LocalEvent)))
    raise TypeError("definition, history, and state must belong to the same canonical family")


def apply_canonical_event[StateT, EventT](
    state: StateT, event: EventT, expected_order: int, reducer: Reducer[StateT, EventT]
) -> StateT:
    """Apply one event through the event-family validator/reducer."""
    return reducer(state, event, expected_order)


def replay_canonical_events[StateT, EventT](
    initial: StateT, events: Iterable[EventT], reducer: Reducer[StateT, EventT]
) -> StateT:
    """Reconstruct state using exactly the same ordered reducer used live."""
    state = initial
    for expected_order, event in enumerate(events, start=1):
        state = apply_canonical_event(state, event, expected_order, reducer)
    return state
