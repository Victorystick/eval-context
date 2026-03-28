import inspect
from typing import Any, Callable, Dict, TypeVar, Protocol, runtime_checkable, Self

T = TypeVar("T", covariant=True)


@runtime_checkable
class Typeish(Protocol[T]):
    """Something that can be used as a type, either a class or a NewType."""

    # flake8: noqa: FSL001
    def __call__(self, *args, **kwargs) -> T: ...


class EvalFactories:
    def __init__(self):
        self.factories: Dict[Typeish, Typeish[Any]] = dict()

    def get(self, name: Typeish[T]) -> Typeish[T]:
        try:
            return self.factories[name]
        except KeyError:
            raise ValueError(f"Missing factory for {name}")

    def register(self, fn: Callable[..., T]) -> Callable[..., T]:
        """Registers a factory function for the return type of the function."""
        type = fn.__annotations__.get("return", None)
        if type is None:
            raise ValueError(f"{fn} must have a return type annotation")

        if factory := self.factories.get(type, None):
            raise ValueError(
                f"Factory for type {type} is already registered: {factory}"
            )

        self.factories[type] = fn
        return fn


_NO_FACTORIES = EvalFactories()


class EvalContext:
    def __init__(
        self, factories: EvalFactories = _NO_FACTORIES, *, parent: Self | None = None
    ):
        self.values: Dict[Typeish, Any] = dict()
        self.factories = factories
        self.parent = parent

    def set(self, name: Typeish[T], value: T) -> None:
        if inspect.isclass(name) and not isinstance(value, name):
            raise ValueError(f"{value} is not an instance of {name}")

        if existing := self.values.get(name, None):
            raise ValueError(f"Value for type {name} is already assigned: {existing}")

        self.values[name] = value

    def eval(self, factory: Callable[..., T]) -> T:
        try:
            args = []
            kwargs = {}

            sig, allow_positional, allow_keyword = get_target_signature(factory)
            for name, param in sig.parameters.items():
                # Skip 'self' parameter for classes, as it is not passed by the caller.
                if name == "self" and inspect.isclass(factory):
                    continue

                if param.kind in (
                    inspect.Parameter.VAR_POSITIONAL,
                    inspect.Parameter.VAR_KEYWORD,
                ):
                    raise ValueError(
                        f"Factory {factory} cannot have *args or **kwargs parameters"
                    )

                # Inject dependencies for parameters with type annotations.
                if param.annotation is inspect.Parameter.empty:
                    raise ValueError(
                        f"Parameter '{name}' of {factory} must have a type annotation"
                    )

                value = self.get(param.annotation, default=param.default)
                if param.kind == inspect.Parameter.KEYWORD_ONLY:
                    if allow_keyword:
                        kwargs[name] = value
                elif allow_positional:
                    args.append(value)
                else:
                    raise ValueError(
                        f"Factory {factory} cannot have mixed parameter kinds"
                    )

            return factory(*args, **kwargs)
        except ValueError as e:
            raise ValueError(f"Error evaluating '{factory}':") from e

    def get(self, name: Typeish[T], default: T | None = None) -> T:
        """Gets a value by name, evaluating its factory if not found."""
        if name not in self.values:
            try:
                self.values[name] = self.eval(self.factories.get(name))
            except ValueError as e:
                if self.parent:
                    return self.parent.get(name)
                if default is not None and default is not inspect.Parameter.empty:
                    print(
                        f"Warning: {name} not found in context, using default value: {default}"
                    )
                    return default
                raise e

        return self.values[name]


_NON_VAR_PARAMS = (
    inspect.Parameter.POSITIONAL_ONLY,
    inspect.Parameter.POSITIONAL_OR_KEYWORD,
    inspect.Parameter.KEYWORD_ONLY,
)


def get_target_signature(
    target: Callable[..., Any],
) -> tuple[inspect.Signature, bool, bool]:
    if not inspect.isclass(target):
        return inspect.signature(target), True, True

    allow_positional = True
    allow_keyword = True
    # For classes, if the __init__ method defined to take args or kwargs, we
    # use the signature of its parent class's __init__ method, as the child
    # class will forward all args and kwargs to it.
    for cls in target.__mro__:
        sig = inspect.signature(cls.__init__)

        if all(p.kind in _NON_VAR_PARAMS for p in sig.parameters.values()):
            return sig, allow_positional, allow_keyword
        else:
            allow_positional = allow_positional and any(
                p.kind == inspect.Parameter.VAR_POSITIONAL
                for p in sig.parameters.values()
            )
            allow_keyword = allow_keyword and any(
                p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
            )

    raise ValueError(f"Could not find a suitable __init__ method for {target}")
