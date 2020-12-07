#!/usr/bin/env python3

"""Run Hypothesis tests on a module with inferred strategies."""
import argparse
import imp
import importlib
import re
import sys
from typing import List, Optional, Tuple, TextIO


class Params:
    """Represent program parameters."""

    def __init__(self, module: str, include: List[re.Pattern], exclude: List[re.Pattern], reveal: bool) -> None:
        self.module = module
        self.include = include
        self.exclude = exclude
        self.reveal = reveal


def _parse_args_to_params(args: argparse.Namespace) -> Tuple[Optional[Params], List[str]]:
    """
    Parse the parameters from the command-line arguments.

    Return parsed parameters, errors if any
    """
    errors = []  # type: List[str]

    include = []  # type: List[re.Pattern]
    if args.include is not None:
        for pattern_str in args.include:
            try:
                pattern = re.compile(pattern_str)
                include.append(pattern)
            except re.error as err:
                errors.append("Failed to parse the include pattern {}: {}".format(pattern_str, err))

    exclude = []  # type: List[re.Pattern]
    if args.exclude is not None:
        for pattern_str in args.exclude:
            try:
                pattern = re.compile(pattern_str)
                exclude.append(pattern)
            except re.error as err:
                errors.append("Failed to parse the exclude pattern {}: {}".format(pattern_str, err))

    return Params(module=args.module, include=include, exclude=exclude, reveal=args.reveal), errors


def _make_argument_parser() -> argparse.ArgumentParser:
    """Create an instance of the argument parser to parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-m", "--module", help="Module to test", required=True)
    parser.add_argument("-i", "--include", help="Regular expressions of the functions to test", required=False,
                        nargs="*")
    parser.add_argument("-e", "--exclude", help="Regular expressions of the functions to exclude from testing",
                        required=False, nargs="*")
    parser.add_argument("--reveal", help="Print the functions and the corresponding inferred search strategies",
                        action='store_true')
    return parser


def main(argv: List[str], stdout: TextIO, stderr: TextIO) -> int:
    """Execute the main routine."""
    parser = _make_argument_parser()
    args = parser.parse_args(args=argv)

    params, errs = _parse_args_to_params(args=args)
    if errs:
        for err in errs:
            print(err, file=stderr)
            return 1

    try:
        module = importlib.import_module(name=params.module)
    except Exception as err:
        raise RuntimeError("Error loading the module: {}".format(params.module)) from err

    print(dir(module))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
