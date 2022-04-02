"""Tests a basic unicycle store."""
from __future__ import annotations

import pytest
from anyio import TASK_STATUS_IGNORED, create_task_group, move_on_after
from anyio.abc import TaskStatus
from typing import NamedTuple, Union
from unicycle import Store, SubscriptionStrategy, combined_store, reducer

pytestmark = pytest.mark.anyio


class Decrement(NamedTuple):
    """Action to decrement the counter."""


class Increment(NamedTuple):
    """Action to increment the counter."""


Actions = Union[Decrement, Increment]


class CounterStore(Store[int, Actions]):
    """Store that keeps a counter state."""

    state = 0

    @reducer(Increment)
    def increment(self, action: Increment) -> int:
        """Increment the counter."""
        return self.state + 1

    @reducer(Decrement)
    def decrement(self, action: Decrement) -> int:
        """Decrement the counter."""
        return self.state - 1


class MirrorStore(Store[int, Actions]):
    """Store that increments and decrements a counter in reverse."""

    state = 0

    @reducer(Increment)
    def increment(self, action: Increment) -> int:
        """Handle an Increment action by decrementing."""
        return self.state - 1

    @reducer(Decrement)
    def decrement(self, action: Decrement) -> int:
        """Handle a Decrement action by incrementing."""
        return self.state + 1


class CombinedState(NamedTuple):
    """Combined state of a CounterStore and a MirrorStore."""

    counter: int
    mirror: int


@combined_store(CombinedState, counter=CounterStore, mirror=MirrorStore)
class CombinedStore(Store[CombinedState, Actions]):
    """A combined CounterStore and MirrorStore."""


def test_initial_state() -> None:
    subject = CounterStore()
    assert subject.state == 0


def test_set_initial_state() -> None:
    subject = CounterStore(initial_state=42)
    assert subject.state == 42


def test_set_state_not_allowed() -> None:
    subject = CounterStore()

    with pytest.raises(TypeError, match="Cannot overwrite state attribute."):
        subject.state = 42


def test_missing_initial_state_not_allowed() -> None:
    class NoInitialStateStore(Store[int, Actions]):
        state: int

    NoInitialStateStore(initial_state=42)

    with pytest.raises(TypeError, match="Initial state"):
        NoInitialStateStore()


def test_dispatch() -> None:
    subject = CounterStore()

    result = subject.dispatch(Increment())
    assert result == 1
    assert subject.state == 1

    result = subject.dispatch(Decrement())
    assert result == 0
    assert subject.state == 0


def test_direct_reducer_method_raises() -> None:
    subject = CounterStore()

    with pytest.raises(TypeError, match="use Store.dispatch"):
        subject.increment(Increment())

    with pytest.raises(TypeError, match="use Store.dispatch"):
        subject.decrement(Decrement())


def test_reducer_decorator_misuse_raises() -> None:
    @reducer(Increment)
    def _not_a_store_method(foo: int, action: Increment) -> int:
        ...

    with pytest.raises(TypeError, match="methods of a Store"):
        _not_a_store_method(42, Increment())


async def test_subscribe_every() -> None:
    subject = CounterStore()
    results = []

    async def _subscribe(*, task_status: TaskStatus = TASK_STATUS_IGNORED) -> None:
        nonlocal results

        with subject.subscribe(strategy=SubscriptionStrategy.EVERY) as events:
            task_status.started()
            async for event in events:
                results.append(event)

    with move_on_after(0.01):
        async with create_task_group() as tg:
            await tg.start(_subscribe)
            subject.dispatch(Increment())
            subject.dispatch(Increment())
            subject.dispatch(Increment())

    assert results == [
        (1, Increment()),
        (2, Increment()),
        (3, Increment()),
    ]


async def test_multiple_subscribers_every() -> None:
    subject = CounterStore()
    results_1 = []
    results_2 = []

    async def _subscribe_1(*, task_status: TaskStatus = TASK_STATUS_IGNORED) -> None:
        nonlocal results_1

        with subject.subscribe(strategy=SubscriptionStrategy.EVERY) as events:
            task_status.started()
            async for event in events:
                results_1.append(event)

    async def _subscribe_2(*, task_status: TaskStatus = TASK_STATUS_IGNORED) -> None:
        nonlocal results_2

        with subject.subscribe(strategy=SubscriptionStrategy.EVERY) as events:
            task_status.started()
            async for event in events:
                results_2.append(event)

    with move_on_after(0.01):
        async with create_task_group() as tg:
            await tg.start(_subscribe_1)
            subject.dispatch(Decrement())
            await tg.start(_subscribe_2)
            subject.dispatch(Decrement())
            subject.dispatch(Decrement())

    assert results_1 == [
        (-1, Decrement()),
        (-2, Decrement()),
        (-3, Decrement()),
    ]

    assert results_2 == [
        (-2, Decrement()),
        (-3, Decrement()),
    ]


async def test_subscribe_latest() -> None:
    subject = CounterStore()
    results = []

    async def _subscribe(*, task_status: TaskStatus = TASK_STATUS_IGNORED) -> None:
        nonlocal results

        with subject.subscribe() as events:
            task_status.started()
            async for event in events:
                results.append(event)

    with move_on_after(0.01):
        async with create_task_group() as tg:
            await tg.start(_subscribe)
            subject.dispatch(Increment())
            subject.dispatch(Increment())
            subject.dispatch(Increment())

    assert results == [
        (3, Increment()),
    ]


async def test_subscribe_ends() -> None:
    subject = CounterStore()
    results = []

    async def _subscribe(*, task_status: TaskStatus = TASK_STATUS_IGNORED) -> None:
        nonlocal results

        with subject.subscribe() as events:
            task_status.started()

        # cannot use notification stream oustide the context manager
        async for event in events:
            results.append(event)

    with move_on_after(0.01):
        async with create_task_group() as tg:
            await tg.start(_subscribe)
            subject.dispatch(Increment())

    assert results == []


async def test_multiple_subscribers_latest() -> None:
    subject = CounterStore()
    results_1 = []
    results_2 = []

    async def _subscribe_1(*, task_status: TaskStatus = TASK_STATUS_IGNORED) -> None:
        nonlocal results_1

        with subject.subscribe() as events:
            task_status.started()
            async for event in events:
                results_1.append(event)

    async def _subscribe_2(*, task_status: TaskStatus = TASK_STATUS_IGNORED) -> None:
        nonlocal results_2

        with subject.subscribe() as events:
            task_status.started()
            async for event in events:
                results_2.append(event)

    with move_on_after(0.01):
        async with create_task_group() as tg:
            await tg.start(_subscribe_1)
            subject.dispatch(Decrement())
            await tg.start(_subscribe_2)
            subject.dispatch(Decrement())
            subject.dispatch(Decrement())

    assert results_1 == [
        (-1, Decrement()),
        (-3, Decrement()),
    ]

    assert results_2 == [
        (-3, Decrement()),
    ]


def test_combined_store() -> None:
    subject = CombinedStore()

    result = subject.state
    assert result == CombinedState(counter=0, mirror=0)

    result = subject.dispatch(Increment())
    assert result == CombinedState(counter=1, mirror=-1)

    result = subject.dispatch(Decrement())
    assert result == CombinedState(counter=0, mirror=0)


def test_combined_store_initial_state() -> None:
    subject = CombinedStore(CombinedState(counter=42, mirror=24))

    result = subject.state
    assert result == CombinedState(counter=42, mirror=24)

    result = subject.dispatch(Increment())
    assert result == CombinedState(counter=43, mirror=23)


def test_combined_store_bad_initial_state() -> None:
    class _WrongState(NamedTuple):
        counter: int
        foo: int

    with pytest.raises(TypeError):
        CombinedStore(_WrongState(counter=42, foo=24))  # type: ignore[arg-type]


async def test_combined_store_subscribe() -> None:
    subject = CombinedStore()
    results = []

    async def _subscribe(*, task_status: TaskStatus = TASK_STATUS_IGNORED) -> None:
        nonlocal results

        with subject.subscribe() as events:
            task_status.started()
            async for event in events:
                results.append(event)

    with move_on_after(0.01):
        async with create_task_group() as tg:
            await tg.start(_subscribe)
            subject.dispatch(Increment())

    assert results == [
        (CombinedState(counter=1, mirror=-1), Increment()),
    ]


def test_multiple_reducers() -> None:
    class DoubleCounter(Store[int, Actions]):
        state = 0

        @reducer(Increment)
        def increment(self, action: Increment) -> int:
            return self.state + 1

        @reducer(Increment)
        def increment_again(self, action: Increment) -> int:
            return self.state + 1

    subject = DoubleCounter()
    result = subject.dispatch(Increment())

    assert result == 2


def test_multiaction_reducer() -> None:
    class ActionCounter(Store[int, Actions]):
        state = 0

        @reducer((Increment, Decrement))
        def increment(self, action: Union[Increment, Decrement]) -> int:
            return self.state + 1

    subject = ActionCounter()
    result = subject.dispatch(Increment())
    result = subject.dispatch(Decrement())

    assert result == 2
