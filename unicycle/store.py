"""Unicycle stores."""
from __future__ import annotations
import collections
import contextlib
import enum
import functools
import inspect
from anyio import Event
from typing import (
    Any,
    AsyncIterator,
    Callable,
    Deque,
    Dict,
    Generic,
    Generator,
    List,
    Tuple,
    Type,
    TypeVar,
    cast,
)

ActionT = TypeVar("ActionT")
StateT = TypeVar("StateT")
ReducerMethodT = Callable[[Any, ActionT], Any]

_ACTION_TYPE_ATTR = "__action_type__"


class SubscriptionStrategy(str, enum.Enum):
    """Message strategy to use for a subscription.

    Props:
        LATEST: Receive the latest state. Guarantees that the store's state
            will match the state in the notification, but may miss transitions.
        EVERY: Receive every state change. Guarantees that you will be notified
            of every state transition, but the store's state have transitioned
            again by the time the notification is handled.
    """

    LATEST = "latest"
    EVERY = "every"


class Subscription(AsyncIterator[Tuple[StateT, ActionT]]):
    """An asynchronous iterator of state change events."""

    def __init__(self, strategy: SubscriptionStrategy) -> None:
        self._strategy = strategy
        self._notification_event = Event()
        self._queue: Deque[Tuple[StateT, ActionT]] = collections.deque(
            maxlen=1 if strategy == SubscriptionStrategy.LATEST else None
        )

    def _notify(self, next_state: StateT, next_action: ActionT) -> None:
        notification = (next_state, next_action)
        self._queue.append(notification)
        self._notification_event.set()

    async def __anext__(self) -> Tuple[StateT, ActionT]:
        while len(self._queue) == 0:
            await self._notification_event.wait()
            self._notification_event = Event()

        notification = self._queue.popleft()
        return notification

    def __aiter__(self) -> AsyncIterator[Tuple[StateT, ActionT]]:
        return self


class Store(Generic[StateT, ActionT]):
    """A state store.

    Args:
        initial_state: Initial state to use in the store.
    """

    state: StateT

    def __init__(self, initial_state: StateT = ...) -> None:  # type: ignore[assignment]
        self._initialize_state(initial_state)
        self._subscriptions: Dict[Subscription[StateT, ActionT], bool] = {}
        self._reducers: List[Tuple[Type[ActionT], Callable[..., StateT]]] = [
            (getattr(member, _ACTION_TYPE_ATTR), member)
            for _, member in inspect.getmembers(self)
            if callable(member) and hasattr(member, _ACTION_TYPE_ATTR)
        ]

    def dispatch(self, action: ActionT) -> StateT:
        """Dispatch an action into the store."""
        self._compute_state(action)
        state = self.state

        for sub in self._subscriptions.keys():
            sub._notify(state, action)

        return state

    @contextlib.contextmanager
    def subscribe(
        self,
        strategy: SubscriptionStrategy = SubscriptionStrategy.LATEST,
    ) -> Generator[Subscription[StateT, ActionT], None, None]:
        """Create a subscription to receive notifications of state changes.

        Args:
            strategy: whether to receive the latest state change (default)
                or every state change.

        Returns:
            A context manager wrapping a subscription.
        """
        sub: Subscription[StateT, ActionT] = Subscription(strategy=strategy)
        self._subscriptions[sub] = True
        yield sub
        del self._subscriptions[sub]

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "state":
            raise TypeError("Cannot overwrite state attribute.")
        super().__setattr__(name, value)

    def _set_state(self, value: StateT) -> None:
        super().__setattr__("state", value)

    def _initialize_state(
        self,
        initial_state: StateT = ...,  # type: ignore[assignment]
    ) -> None:
        if initial_state != Ellipsis:
            self._set_state(initial_state)
        elif not hasattr(self, "state"):
            raise TypeError("Initial state must be provided")

    def _compute_state(self, action: ActionT) -> None:
        state = self.state

        for action_type, reducer in self._reducers:
            if isinstance(action, action_type):
                state = reducer(action, __dispatch__=True)
                self._set_state(state)


def reducer(
    action_type: Any,
) -> Callable[[ReducerMethodT[ActionT]], ReducerMethodT[ActionT]]:
    """Mark a Store method as a reducer for a given action type."""

    def _decorator(func: ReducerMethodT[ActionT]) -> ReducerMethodT[ActionT]:
        @functools.wraps(func)
        def _wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            is_store = isinstance(self, Store)
            ok_to_call = kwargs.pop("__dispatch__", False)

            if not is_store:
                raise TypeError("@reducer must be applied to methods of a Store")

            if not ok_to_call:
                raise TypeError("Do not call reducers directly; use Store.dispatch")

            return func(self, *args, **kwargs)

        setattr(_wrapper, _ACTION_TYPE_ATTR, action_type)
        return cast(ReducerMethodT[ActionT], _wrapper)

    return _decorator


def combined_store(
    combine_states: Callable[..., StateT],
    **kwargs: Type[Store[Any, ActionT]],
) -> Callable[[Type[Store[StateT, ActionT]]], Type[Store[StateT, ActionT]]]:
    '''Turn a store into a combined store.

    Args:
        combine_states: A class or factory function that will return
            the computed state when passed the substates by name.
        **kwargs: Sub-store types, by substate name.

    Example:
        ```python
        class Increment(NamedTuple):
            """Action to increment the counter."""

        class CounterStore(Store[int, Actions]):
            state = 0

            @reducer(Increment)
            def increment(self, action: Increment) -> int:
                return self.state + 1


        class MirrorStore(Store[int, Actions]):
            state = 0

            @reducer(Increment)
            def decrement(self, action: Increment) -> int:
                return self.state - 1


        class CombinedState(NamedTuple):
            counter: int
            mirror: int


        @combined_store(CombinedState, counter=CounterStore, mirror=MirrorStore)
        class CombinedStore(Store[CombinedState, Actions]):
            """A combined CounterStore and MirrorStore."""
        ```
    '''

    def _initialize_state(
        self: Store[StateT, ActionT],
        initial_state: StateT = ...,  # type: ignore[assignment]
    ) -> None:
        substores: Dict[str, Store[Any, ActionT]] = {}
        substates: Dict[str, Any] = {}

        for name, substore_cls in kwargs.items():
            if initial_state != Ellipsis:
                try:
                    initial_substate = getattr(initial_state, name)
                except AttributeError as e:
                    raise TypeError(str(e)) from e
            else:
                initial_substate = Ellipsis

            substore = substore_cls(initial_state=initial_substate)
            substores[name] = substore
            substates[name] = substore.state

        self._substores = substores
        self._set_state(combine_states(**substates))

    def _compute_state(self: Store[StateT, ActionT], action: ActionT) -> None:
        substates = {
            name: substore.dispatch(action)
            for name, substore in self._substores.items()  # type: ignore[attr-defined]
        }
        self._set_state(combine_states(**substates))

    def _decorator(cls: Type[Store[StateT, ActionT]]) -> Type[Store[StateT, ActionT]]:
        setattr(cls, _initialize_state.__name__, _initialize_state)
        setattr(cls, _compute_state.__name__, _compute_state)
        return cls

    return _decorator
