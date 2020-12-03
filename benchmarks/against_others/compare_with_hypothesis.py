#!/usr/bin/env python3
"""Benchmark icontract against deal when used together with hypothesis."""

import math
import os
import sys
import timeit
from typing import List

import deal
import tabulate

import icontract
import icontract.integration.with_hypothesis

def benchmark_icontract_only_type_hints()->None:
    """Benchmark the Hypothesis testing with icontract."""
    count = 0

    @icontract.require(lambda some_arg: some_arg > 0)
    def some_func(some_arg: int) -> float:
        nonlocal count
        count += 1
        return math.sqrt(some_arg)

    icontract.integration.with_hypothesis.test_with_inferred_argument_types(some_func)

    # Assert the count of function executions for fair tests
    assert count == 100

def benchmark_icontract_type_hints_and_heuristics()->None:
    """Benchmark the Hypothesis testing with icontract."""
    count = 0

    @icontract.require(lambda some_arg: some_arg > 0)
    def some_func(some_arg: int) -> float:
        nonlocal count
        count += 1
        return math.sqrt(some_arg)

    icontract.integration.with_hypothesis.test_with_inferred_strategies(some_func)

    # Assert the count of function executions for fair tests
    assert count == 100

def benchmark_deal()->None:
    """Benchmark the Hypothesis testing with deal."""
    count = 0

    @deal.pre(lambda _: _.some_arg > 0)
    def some_func(some_arg: int) -> float:
        nonlocal count
        count += 1
        return math.sqrt(some_arg)

    # Icontract uses ``filter`` with Hypothesis to do the rejection sampling and stops only when enough samples have
    # been drawn.
    # In contrast, deal draws a certain number of samples and rejects samples from this fixed set.
    # Therefore we need to double the number of samples for deal to get approximately the same number of
    # tested cases.
    for case in deal.cases(some_func, count=200):
        case()

    # Assert the count of function executions for fair tests
    assert abs(count - 100) < 25, "Expected the function to be called about 100 times, but got: {}".format(count)

def writeln_utf8(text: str) -> None:
    """
    Write the text to STDOUT using UTF-8 encoding followed by a new-line character.

    We can not use ``print()`` as we can not rely on the correct encoding in Windows.
    See: https://stackoverflow.com/questions/31469707/changing-the-locale-preferred-encoding-in-python-3-in-windows
    """
    sys.stdout.buffer.write(text.encode('utf-8'))
    sys.stdout.buffer.write(os.linesep.encode('utf-8'))


def measure_functions() -> None:
    # yapf: disable
    funcs = [
        'benchmark_icontract_type_hints_and_heuristics',
        'benchmark_icontract_only_type_hints',
        'benchmark_deal'
    ]
    # yapf: enable

    durations = [0.0] * len(funcs)

    number = 10

    for i, func in enumerate(funcs):
        duration = timeit.timeit("{}()".format(func), setup="from __main__ import {}".format(func), number=number)
        durations[i] = duration

    table = []  # type: List[List[str]]

    for func, duration in zip(funcs, durations):
        # yapf: disable
        table.append([
            '`{}`'.format(func),
            '{:.2f} s'.format(duration),
            '{:.2f} μs'.format(duration * 1000 * 1000 / number),
            '{:.0f}%'.format(duration * 100 / durations[0])
        ])
        # yapf: enable

    # yapf: disable
    table_str = tabulate.tabulate(
        table,
        headers=['Case', 'Total time', 'Time per run', 'Relative time per run'],
        colalign=('left', 'right', 'right', 'right'),
        tablefmt='rst')
    # yapf: enable

    writeln_utf8(table_str)


if __name__ == "__main__":
    writeln_utf8("Benchmarking Hypothesis testing:")
    writeln_utf8('')
    measure_functions()
# TODO: include this in Readme