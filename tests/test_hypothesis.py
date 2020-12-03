# pylint: disable=missing-docstring
# pylint: disable=invalid-name
# pylint: disable=unused-argument
# pylint: disable=no-value-for-parameter
import dataclasses
import enum
import fractions
import math
import unittest
import datetime
import decimal
from typing import List, Optional, Tuple, Any, TypedDict

import hypothesis.strategies

import icontract.integration.with_hypothesis


class TestAssumePreconditions(unittest.TestCase):
    def test_without_preconditions(self) -> None:
        recorded_inputs = []  # type: List[Any]

        def some_func(x: int) -> None:
            recorded_inputs.append(x)

        assume_preconditions = icontract.integration.with_hypothesis.make_assume_preconditions(some_func)

        @hypothesis.given(x=hypothesis.strategies.integers())
        def execute(x: int) -> None:
            assume_preconditions(x)
            some_func(x)

        execute()

        # 10 is an arbitrary, but plausible value.
        self.assertGreater(len(recorded_inputs), 10)

    def test_with_a_single_precondition(self) -> None:
        recorded_inputs = []  # type: List[int]

        @icontract.require(lambda x: x > 0)
        def some_func(x: int) -> None:
            recorded_inputs.append(x)

        assume_preconditions = icontract.integration.with_hypothesis.make_assume_preconditions(some_func)

        samples = [-1, 1]

        @hypothesis.given(x=hypothesis.strategies.sampled_from(samples))
        def execute(x: int) -> None:
            samples.append(x)
            assume_preconditions(x)
            some_func(x)

        execute()

        self.assertSetEqual({1}, set(recorded_inputs))

    def test_with_two_preconditions(self) -> None:
        recorded_inputs = []  # type: List[int]

        @icontract.require(lambda x: x > 0)
        @icontract.require(lambda x: x % 3 == 0)
        def some_func(x: int) -> None:
            recorded_inputs.append(x)

        assume_preconditions = icontract.integration.with_hypothesis.make_assume_preconditions(some_func)

        samples = [-1, 1, 3]

        @hypothesis.given(x=hypothesis.strategies.sampled_from(samples))
        def execute(x: int) -> None:
            samples.append(x)
            assume_preconditions(x)
            some_func(x)

        execute()

        self.assertSetEqual({3}, set(recorded_inputs))


class TestAssumeWeakenedPreconditions(unittest.TestCase):
    def test_with_a_single_precondition(self) -> None:
        class A(icontract.DBC):
            @icontract.require(lambda x: x % 3 == 0)
            def some_func(self, x: int) -> None:
                pass

        recorded_inputs = []  # type: List[int]

        class B(A):
            @icontract.require(lambda x: x % 7 == 0)
            def some_func(self, x: int) -> None:
                # The inputs from B.some_func need to satisfy either their own preconditions or
                # the preconditions of A.some_func ("require else").
                recorded_inputs.append(x)

        b = B()
        assume_preconditions = icontract.integration.with_hypothesis.make_assume_preconditions(b.some_func)

        @hypothesis.given(x=hypothesis.strategies.sampled_from([-14, -3, 5, 7, 9]))
        def execute(x: int) -> None:
            assume_preconditions(x)
            b.some_func(x)

        execute()

        self.assertSetEqual({-14, -3, 7, 9}, set(recorded_inputs))

    def test_with_two_preconditions(self) -> None:
        class A(icontract.DBC):
            @icontract.require(lambda x: x % 3 == 0)
            def some_func(self, x: int) -> None:
                pass

        recorded_inputs = []  # type: List[int]

        class B(A):
            @icontract.require(lambda x: x > 0)
            @icontract.require(lambda x: x % 7 == 0)
            def some_func(self, x: int) -> None:
                # The inputs from B.some_func need to satisfy either their own preconditions or
                # the preconditions of A.some_func ("require else").
                recorded_inputs.append(x)

        b = B()
        assume_preconditions = icontract.integration.with_hypothesis.make_assume_preconditions(b.some_func)

        @hypothesis.given(x=hypothesis.strategies.sampled_from([-14, 3, 7, 9, 10, 14]))
        def execute(x: int) -> None:
            assume_preconditions(x)
            b.some_func(x)

        execute()

        self.assertSetEqual({3, 7, 9, 14}, set(recorded_inputs))


class TestWithInferredStrategies(unittest.TestCase):
    def test_fail_without_type_hints(self) -> None:
        @icontract.require(lambda x: x > 0)
        def some_func(x) -> None:  # type: ignore
            pass

        type_error = None  # type: Optional[TypeError]
        try:
            icontract.integration.with_hypothesis.test_with_inferred_strategies(some_func)
        except TypeError as err:
            type_error = err

        assert type_error is not None
        self.assertTrue(
            str(type_error).startswith(
                'The argument types can not be inferred since the type hints are missing for the function:'))

    def test_without_preconditions(self) -> None:
        recorded_inputs = []  # type: List[Any]

        def some_func(x: int) -> None:
            recorded_inputs.append(x)

        icontract.integration.with_hypothesis.test_with_inferred_strategies(some_func)

        # 10 is an arbitrary, but plausible value.
        self.assertGreater(len(recorded_inputs), 10)

    def test_unmatched_pattern(self) -> None:
        recorded_inputs = []  # type: List[Any]

        @icontract.require(lambda x: x > 0 and x > math.sqrt(x))
        def some_func(x: float) -> None:
            recorded_inputs.append(x)

        icontract.integration.with_hypothesis.test_with_inferred_strategies(some_func)

        # 10 is an arbitrary, but plausible value.
        self.assertGreater(len(recorded_inputs), 10)

    def test_with_multiple_preconditions(self) -> None:
        recorded_inputs = []  # type: List[Any]

        hundred = 100

        @icontract.require(lambda x: x > 0)
        @icontract.require(lambda x: x >= 1)
        @icontract.require(lambda x: x < 100)
        @icontract.require(lambda x: x <= 90)
        @icontract.require(lambda y: 0 < y <= 100)
        @icontract.require(lambda y: 1 <= y < 90)
        @icontract.require(lambda z: 0 > z >= -math.sqrt(hundred))
        def some_func(x: int, y: int, z: int) -> None:
            recorded_inputs.append((x, y, z))

        icontract.integration.with_hypothesis.test_with_inferred_strategies(some_func)

        # 10 is an arbitrary, but plausible value.
        self.assertGreater(len(recorded_inputs), 10)

    def test_with_dates(self) -> None:
        SOME_DATE = datetime.date(2014, 3, 2)

        recorded_inputs = []  # type: List[Any]

        # The preconditions were picked s.t. to also test that we can recompute everything.
        @icontract.require(lambda a: a < SOME_DATE + datetime.timedelta(days=3))
        @icontract.require(lambda b: b < SOME_DATE + datetime.timedelta(days=2))
        @icontract.require(lambda c: c < max(SOME_DATE, datetime.date(2020, 1, 1)))
        @icontract.require(lambda d: d < (
                SOME_DATE if SOME_DATE > datetime.date(2020, 1, 1) else datetime.date(2020, 12, 5)))
        def some_func(a: datetime.date, b: datetime.date, c: datetime.date, d: datetime.date) -> None:
            recorded_inputs.append((a, b, c, d))

        icontract.integration.with_hypothesis.test_with_inferred_strategies(some_func)

        # 10 is an arbitrary, but plausible value.
        self.assertGreater(len(recorded_inputs), 10)

    def test_with_datetimes(self) -> None:
        SOME_DATETIME = datetime.datetime(2014, 3, 2, 10, 20, 30)

        recorded_inputs = []  # type: List[Any]

        @icontract.require(lambda a: a < SOME_DATETIME)
        def some_func(a: datetime.datetime) -> None:
            recorded_inputs.append(a)

        icontract.integration.with_hypothesis.test_with_inferred_strategies(some_func)

        # 10 is an arbitrary, but plausible value.
        self.assertGreater(len(recorded_inputs), 10)

    def test_with_times(self) -> None:
        SOME_TIME = datetime.time(1, 2, 3)

        recorded_inputs = []  # type: List[Any]

        @icontract.require(lambda a: a < SOME_TIME)
        def some_func(a: datetime.time) -> None:
            recorded_inputs.append(a)

        icontract.integration.with_hypothesis.test_with_inferred_strategies(some_func)

        # 10 is an arbitrary, but plausible value.
        self.assertGreater(len(recorded_inputs), 10)

    def test_with_timedeltas(self) -> None:
        SOME_TIMEDELTA = datetime.timedelta(days=3)

        recorded_inputs = []  # type: List[Any]

        @icontract.require(lambda a: a < SOME_TIMEDELTA)
        def some_func(a: datetime.timedelta) -> None:
            recorded_inputs.append(a)

        icontract.integration.with_hypothesis.test_with_inferred_strategies(some_func)

        # 10 is an arbitrary, but plausible value.
        self.assertGreater(len(recorded_inputs), 10)

    def test_with_fractions(self) -> None:
        SOME_FRACTION = fractions.Fraction(3, 2)

        recorded_inputs = []  # type: List[Any]

        @icontract.require(lambda a: a < SOME_FRACTION)
        def some_func(a: fractions.Fraction) -> None:
            recorded_inputs.append(a)

        icontract.integration.with_hypothesis.test_with_inferred_strategies(some_func)

        # 10 is an arbitrary, but plausible value.
        self.assertGreater(len(recorded_inputs), 10)

    def test_with_decimals(self) -> None:
        SOME_DECIMAL = decimal.Decimal(10)

        recorded_inputs = []  # type: List[Any]

        @icontract.require(lambda a: not decimal.Decimal.is_nan(a))
        @icontract.require(lambda a: a < SOME_DECIMAL)
        def some_func(a: decimal.Decimal) -> None:
            recorded_inputs.append(a)

        icontract.integration.with_hypothesis.test_with_inferred_strategies(some_func)

        # 10 is an arbitrary, but plausible value.
        self.assertGreater(len(recorded_inputs), 10)

    def test_with_weakened_preconditions(self) -> None:
        class A(icontract.DBC):
            @icontract.require(lambda x: 0 < x < 20)
            @icontract.require(lambda x: x % 3 == 0)
            def some_func(self, x: int) -> None:
                pass

        recorded_inputs = []  # type: List[int]

        class B(A):
            @icontract.require(lambda x: 0 < x < 20)
            @icontract.require(lambda x: x % 7 == 0)
            def some_func(self, x: int) -> None:
                # The inputs from B.some_func need to satisfy either their own preconditions or
                # the preconditions of A.some_func ("require else").
                recorded_inputs.append(x)

        b = B()

        icontract.integration.with_hypothesis.test_with_inferred_strategies(b.some_func)

        # 10 is an arbitrary, but plausible value.
        self.assertGreater(len(recorded_inputs), 10)


class TestWithInferredStrategiesOnClasses(unittest.TestCase):
    def test_no_preconditions_and_no_argument_init(self) -> None:
        class A:
            def __repr__(self) -> str:
                return "A()"

        recorded_inputs = []  # type: List[Any]

        def some_func(a: A) -> None:
            recorded_inputs.append(a)

        icontract.integration.with_hypothesis.test_with_inferred_strategies(some_func)

    def test_no_preconditions_and_init(self) -> None:
        class A:
            def __init__(self, x: int):
                self.x = x

            def __repr__(self) -> str:
                return "A(x={})".format(self.x)

        recorded_inputs = []  # type: List[Any]

        def some_func(a: A) -> None:
            recorded_inputs.append(a)

        icontract.integration.with_hypothesis.test_with_inferred_strategies(some_func)

    def test_preconditions_with_heuristics(self) -> None:
        class A:
            @icontract.require(lambda x: x > 0)
            def __init__(self, x: int):
                self.x = x

            def __repr__(self) -> str:
                return "A(x={})".format(self.x)

        recorded_inputs = []  # type: List[Any]

        def some_func(a: A) -> None:
            recorded_inputs.append(a)

        icontract.integration.with_hypothesis.test_with_inferred_strategies(some_func)

    def test_preconditions_without_heuristics(self) -> None:
        class A:
            @icontract.require(lambda x: x > 0)
            @icontract.require(lambda x: x > math.sqrt(x))
            def __init__(self, x: float):
                self.x = x

            def __repr__(self) -> str:
                return "A(x={})".format(self.x)

        recorded_inputs = []  # type: List[Any]

        def some_func(a: A) -> None:
            recorded_inputs.append(a)

        icontract.integration.with_hypothesis.test_with_inferred_strategies(some_func)


    def test_recursion(self) -> None:
        class A:
            @icontract.require(lambda x: x > 0)
            def __init__(self, x: int):
                self.x = x

            def __repr__(self) -> str:
                return "A(x={})".format(self.x)

        class B:
            @icontract.require(lambda y: y > 2020)
            def __init__(self, a: A, y: int):
                self.a = a
                self.y = y

            def __repr__(self) -> str:
                return "B(a={!r}, y={})".format(self.a, self.y)

        recorded_inputs = []  # type: List[Any]

        def some_func(b: B) -> None:
            recorded_inputs.append(b)

        icontract.integration.with_hypothesis.test_with_inferred_strategies(some_func)

    def test_enum(self) -> None:
        class A(enum.Enum):
            SOMETHING = 1
            ELSE = 2

        recorded_inputs = []  # type: List[Any]

        def some_func(a: A) -> None:
            recorded_inputs.append(a)

        icontract.integration.with_hypothesis.test_with_inferred_strategies(some_func)

    def test_data_class(self) -> None:
        class A:
            @icontract.require(lambda x: x > 0)
            def __init__(self, x: int):
                self.x = x

            def __repr__(self) -> str:
                return "A(x={})".format(self.x)

        @dataclasses.dataclass
        class B:
            a: A

        recorded_inputs = []  # type: List[Any]

        def some_func(b: B) -> None:
            recorded_inputs.append(b)

        # TODO: this test needs to be fixed -- recursion is not working as expected
        icontract.integration.with_hypothesis.test_with_inferred_strategies(some_func)

    def test_typed_dict(self) -> None:
        class A:
            @icontract.require(lambda x: x > 0)
            def __init__(self, x: int):
                self.x = x

            def __repr__(self) -> str:
                return "A(x={})".format(self.x)

        class B(TypedDict):
            a: A

        recorded_inputs = []  # type: List[Any]

        def some_func(b: B) -> None:
            recorded_inputs.append(b)

        # TODO: this test needs to be fixed -- recursion is not working as expected
        icontract.integration.with_hypothesis.test_with_inferred_strategies(some_func)

    def test_list(self) -> None:
        class A:
            @icontract.require(lambda x: x > 0)
            def __init__(self, x: int):
                self.x = x

            def __repr__(self) -> str:
                return "A(x={})".format(self.x)

        recorded_inputs = []  # type: List[Any]

        def some_func(aa: List[A]) -> None:
            recorded_inputs.append(aa)

        # TODO: this test needs to be fixed -- recursion is not working as expected
        icontract.integration.with_hypothesis.test_with_inferred_strategies(some_func)

# TODO: test named tuples!
# TODO: test with union!

if __name__ == '__main__':
    unittest.main()
