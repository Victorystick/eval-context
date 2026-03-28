from itertools import repeat
import unittest
from typing import NewType
from context import EvalContext, EvalFactories


MyInt = NewType("MyInt", int)


def missing_return_type():
    return "value"


def me(times: int) -> str:
    return " ".join(repeat("me!", times))


class Base:
    def __init__(self, times: int, *, msg: str = "Hi!"):
        self.times = times
        self.msg = msg

    def __str__(self):
        return " ".join(repeat(self.msg, self.times))


class SubPass(Base):
    pass


class SubForwardPositional(Base):
    def __init__(self, *args):
        super().__init__(*args)


class SubForwardAll(Base):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class TestEvalFactories(unittest.TestCase):
    def test_factory_must_have_return_type_annotation(self):
        factories = EvalFactories()

        with self.assertRaises(ValueError) as cm:
            factories.register(missing_return_type)

        self.assertEqual(
            str(cm.exception),
            f"{missing_return_type} must have a return type annotation",
        )

    def test_factory_cannot_be_registered_twice(self):
        factories = EvalFactories()

        @factories.register
        def provide_string() -> str:
            return "value"

        with self.assertRaises(ValueError) as cm:
            factories.register(provide_string)

        self.assertEqual(
            str(cm.exception),
            f"Factory for type <class 'str'> is already registered: {provide_string}",
        )

    def test_factory_can_be_registered_and_retrieved(self):
        factories = EvalFactories()

        @factories.register
        def provide_string() -> str:
            return "value"

        self.assertEqual(factories.get(str), provide_string)

    def test_getting_unregistered_factory_raises(self):
        factories = EvalFactories()

        with self.assertRaises(ValueError) as cm:
            factories.get(str)

        self.assertEqual(str(cm.exception), "Missing factory for <class 'str'>")


class TestEvalContext(unittest.TestCase):
    def test_can_get_and_set_values(self):
        context = EvalContext()
        context.set(str, "value")
        self.assertEqual(context.get(str), "value")

    def test_setting_already_set_value_raises(self):
        context = EvalContext()
        context.set(str, "value")

        with self.assertRaises(ValueError) as cm:
            context.set(str, "other value")

        self.assertEqual(
            str(cm.exception),
            "Value for type <class 'str'> is already assigned: value",
        )

    def test_setting_value_of_wrong_type_raises(self):
        context = EvalContext()

        with self.assertRaises(ValueError) as cm:
            context.set(str, 123)

        self.assertEqual(str(cm.exception), "123 is not an instance of <class 'str'>")

    def test_can_set_newtypes(self):
        context = EvalContext()

        context.set(MyInt, 123)

        self.assertEqual(context.get(MyInt), 123)

    def test_getting_an_unset_value_raises(self):
        context = EvalContext()

        with self.assertRaises(ValueError) as cm:
            context.get(str)

        self.assertEqual(str(cm.exception), "Missing factory for <class 'str'>")

    def test_only_evaluates_factory_once(self):
        call_count = 0

        factories = EvalFactories()

        @factories.register
        def provide_string() -> str:
            nonlocal call_count
            call_count += 1
            return "value"

        context = EvalContext(factories)

        self.assertEqual(context.get(str), "value")
        self.assertEqual(context.get(str), "value")
        self.assertEqual(call_count, 1)

    def test_can_eval_functions(self):
        context = EvalContext()
        context.set(int, 2)

        self.assertEqual(context.eval(me), "me! me!")

    def test_eval_with_missing_factory_raises(self):
        context = EvalContext()

        with self.assertRaises(ValueError):
            context.eval(me)

    def test_can_instantiate_classes(self):
        context = EvalContext()
        context.set(int, 2)

        instance = context.eval(Base)
        self.assertIsInstance(instance, Base)
        self.assertEqual(str(instance), "Hi! Hi!")

    def test_can_instantiate_classes_with_optional(self):
        context = EvalContext()
        context.set(int, 2)
        context.set(str, "Yo!")

        instance = context.eval(Base)
        self.assertIsInstance(instance, Base)
        self.assertEqual(str(instance), "Yo! Yo!")

    def test_can_instantiate_subclasses_without_explicit_init(self):
        context = EvalContext()
        context.set(int, 2)

        instance = context.eval(SubPass)
        self.assertIsInstance(instance, SubPass)
        self.assertEqual(str(instance), "Hi! Hi!")

    def test_can_instantiate_subclasses_with_varargs(self):
        context = EvalContext()
        context.set(int, 3)
        # Ignored as SubForwardPositional only forwards positional args.
        context.set(str, "Yo!")

        instance = context.eval(SubForwardPositional)
        self.assertEqual(str(instance), "Hi! Hi! Hi!")

    def test_can_instantiate_subclasses_with_varargs_and_kwargs(self):
        context = EvalContext()
        context.set(int, 1)
        context.set(str, "Yo!")

        instance = context.eval(SubForwardAll)
        self.assertEqual(str(instance), "Yo!")

    def test_falls_back_to_parent_context_for_missing_values(self):
        parent = EvalContext()
        parent.set(str, "value")

        child = EvalContext(parent=parent)

        self.assertEqual(child.get(str), "value")

    def test_child_and_parent_shares_factory_return_value(self):
        factories = EvalFactories()

        @factories.register
        def provide_string() -> dict:
            return {}

        parent = EvalContext(factories)

        child = EvalContext(parent=parent)

        self.assertIs(child.get(dict), parent.get(dict))
