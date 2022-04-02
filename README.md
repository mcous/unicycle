# Unicycle

A friendly, unidirectional state store for Python. Inspired by [Redux][].

Unicycle allows you to:

- Keep the state of a component or application in one or more immutable objects
- Trigger state changes with action objects
- Subscribe to state transitions

[redux]: https://redux.js.org/

## Install

```shell
pip install unicycle
```

## Simple usage

Let's build a Pokédex with Unicycle!

### Step 1 - Define your state

Start by defining the application's state. Our Pokédex is going to keep track of which Pokémon we've seen, and which ones we've caught.

The state can be anything! It can be as simple as a single boolean, but usually you'll need more complexity than that. The only rule is that **state is immutable**. You are not allowed to modify state directly nor mutate. For this reason, we recommend you use a `NamedTuple` or a frozen `dataclass` as your state type.

You _can_ define your state using mutable objects as long as you never actually mutate them. Using immutable type hints like `Mapping` and `Sequence` can help, if you want to go this route.

```python
from typing import NamedTuple, Set

class PokedexState(NamedTuple):
    """Pokedex state.

    Properties:
        seen: Names of all seen Pokemon.
        caught: Names of all caught Pokemon.
    """
    seen: frozenset[str] = frozenset()
    caught: frozenset[str] = frozenset()
```

### Step 2 - Define your actions

Next, we define our **actions**. An action is an event that may
cause the state to change. The state of our Pokédex will change whenever
we see or catch a new Pokémon.

An action object can be anything! Like state, though, actions are **read-only**. If you need to attach payloads to action, we recommend you use a `NamedTuple` or a frozen `dataclass` as your action type.

If you use type-hints, you must also create a `Union` of actions the store may receive.

```python
from typing import NamedTuple, Union

class PokemonSeen(NamedTuple):
    """A Pokemon named `name` has been spotted."""
    name: str

class PokemonCaught(NamedTuple):
    """A Pokemon named `name` has been caught."""
    name: str

PokedexAction = Union[PokemonSeen, PokemonCaught]
```

### Step 3 - Define how your state changes

With our state shape and actions defined, we need to define:

- Our initial state.
- How the state changes in response to those actions.

For this, we'll create a subclass of `Store`. We can set the initial state of the store using the `state` attribute, and we can write reducers to [fold][] the action into the previous state to calculate a new state.

Use the `@reducer` decorator to mark a given method as handling a certain action type. We have two state changes to worry about:

- If we see a Pokémon, we need to ensure it is in the seen list
- If we catch a Pokémon, we need to ensure it is in both the seen and caught

```python
from unicycle import Store, reducer

class PokedexStore(Store[PokedexState, PokedexAction]):
    state: PokedexState = PokedexState()

    @reducer(PokemonSeen)
    def pokemon_seen(self, action: PokemonSeen) -> PokedexState:
        prev_state = self.state
        return PokedexState(
            seen=prev_state.seen.union([action.name]),
            caught=prev_state.caught,
        )

    @reducer(PokemonCaught)
    def pokemon_caught(self,  action: PokemonCaught) -> PokedexState:
        prev_state = self.state
        return PokedexState(
            seen=prev_state.seen.union([action.name]),
            caught=prev_state.caught.union([action.name]),
        )
```

[reduce]: https://en.wikipedia.org/wiki/Fold_(higher-order_function)

### Step 4 - Add it to your app

Let's wire this state up to a simple HTTP API that:

- Can add a Pokémon to the seen list
- Can add a Pokémon to the caught list
- Pushes out WebSocket notifications whenever our Pokédex state changes!

To trigger state changes, use `Store.dispatch` to send actions into the store. From there, you can retrieve the state from `Store.state`. Additionally, you can use `Store.subscribe` to receive to state changes notifications asynchronously.

```python
from quart import Quart, request, websocket

app = Quart("Pokedex")
store = PokedexStore()

@app.route("/seen", methods=["PUT"])
async def put_seen() -> None:
    name = request.data.decode()
    state = store.dispatch(PokemonSeen(name=name)))
    return state.seen

@app.route("/caught", methods=["PUT"])
async def put_caught() -> None:
    name = request.data.decode()
    state = store.dispatch(PokemonCaught(name=name)))
    return state.caught

@app.route("/", methods=["GET"])
async def get_pokedex() -> Dict[str, OrderedSet[str]]:
    state = store.state
    return {
        "seen": state.seen,
        "caught": state.caught,
    }

@app.websocket('/notifications')
async def notifications() -> None:
    with store.subscribe() as notifications:
        async for state, action in notifications:
            await websocket.send(
                {
                    "seen": state.seen,
                    "caught": state.caught,
                }
            )

app.run()
```

## Complicated usage

### Combined stores

For more complicated states, you can combine several stores into one. This is a powerful feature that allows you to separate your state into different domains while still receiving all the same actions.

A combined store is just another `Store`, so you nest combined stores in other combined stores to create whatever state tree you may need.

For our Pokédex, we could split our single store into two: a `SeenStore` for tracking seen Pokémon and a `CaughtStore` for tracking caught Pokémon.

Using our same actions...

```python
from typing import NamedTuple, Union
from unicycle import Store, combine_stores, reducer

class PokemonSeen(NamedTuple):
    """A Pokemon named `name` has been spotted."""
    name: str


class PokemonCaught(NamedTuple):
    """A Pokemon named `name` has been caught."""
    name: str

PokedexAction = Union[PokemonSeen, PokemonCaught]
```

We can create a `SeenState` and `SeenStore`...

```python
class SeenState(NamedTuple):
    """Seen Pokemon state.

    Properties:
        names: Names of all seen Pokemon names.
    """
    names: frozenset[str] = frozenset()


class SeenStore(Store[SeenState, PokedexAction]):
    state: SeenState = SeenState()

    @reducer((PokemonSeen, PokemonCaught))
    def pokemon_seen(self, action: Union[PokemonSeen, PokemonCaught]) -> SeenState:
        names = self.state.names
        return SeenState(names=names.union([action.name]))
```

As well as a `CaughtState` and `CaughtStore`...

```python
class CaughtState(NamedTuple):
    """Caught Pokemon state.

    Properties:
        names: Names of all caught Pokemon.
    """
    names: frozenset[str] = frozenset()


class CaughtStore(Store[CaughtState, PokedexAction]):
    state: CaughtState = CaughtState()

    @reducer(PokemonCaught)
    def pokemon_caught(self, action: PokemonCaught) -> CaughtState:
        names = self.state.names
        return CaughtState(names=names.union([action.name]))
```

To create our combined store, we must create a combined state object, built up of the sub-states, as well as a combined store, using `@combined_store`.

```python
class PokedexState(NamedTuple):
    seen: SeenState
    caught: CaughtState

@combined_store(PokedexState, seen=SeenStore, caught=CaughtStore)
class PokedexStore(Store(PokedexState, PokedexAction)):
    pass
```

From here, we can `dispatch` actions into the combined `PokedexStore`, and the actions will be sent into the `SeenStore` and `CaughtStore` substores, giving us a new combined state!

```python
>>> pokedex_store = PokedexStore()
>>> pokedex_store.state
PokedexState(seen=SeenState(names=frozenset()), caught=CaughtState(names=frozenset()))
>>>
>>> pokedex_store.dispatch(PokemonSeen("Squirtle"))
PokedexState(seen=SeenState(names=frozenset({'Squirtle'})), caught=CaughtState(names=frozenset()))
>>>
>>> pokedex_store.dispatch(PokemonSeen("Charmander"))
PokedexState(seen=SeenState(names=frozenset({'Charmander', 'Squirtle'})), caught=CaughtState(names=frozenset({'Charmander'})))
```

### Computed states and caching

When using a state store like Unicycle, it's usually a good idea to store the most fundamental state possible, and compute derived data on the fly.

There's more than one way to compute derived state from your store. One easy option is to use functions:

```python
def get_all_known_pokemon(state: PokedexState) -> FrozenSet[str]:
    return state.seen.names | state.caught.names
```

If you're using a `NamedTuple` or `dataclass` for your states, another option is to add methods to your state objects to create these "selectors".

```python
class SeenState(NamedTuple):
    names: frozenset[str] = frozenset()

    @property
    def bulbasaur_is_seen(self) -> bool:
        return "Bulbasaur" in self.names
```

Since the state objects are immutable, if you have expensive computed state, you can use tools like `functools.cache` to cache these computed states. **Caching like this can cause unintended performance issues and memory leaks** (depending on the arguments a method may receive), so be careful, and only add caching after you've confirmed it'll actually improve performance.

```python
class SeenState(NamedTuple):
    names: frozenset[str] = frozenset()

    @property
    @functools.cache
    def shasum(self) -> str:
        # expensive calculation
        ...
```

Need to compute state from several substates? No problem! Add methods to a common ancestor of substate.

```python
class PokedexState(NamedTuple):
    seen: SeenState
    caught: CaughtState

    def pokemon_is_known(self, name: str) -> bool:
        return name in self.seen.names or name in self.caught.names
```
