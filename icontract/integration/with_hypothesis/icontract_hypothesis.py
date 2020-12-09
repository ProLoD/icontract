#!/usr/bin/env python3

"""Run Hypothesis tests on a module with inferred strategies."""
import argparse
import collections
import contextlib
import importlib.machinery
import importlib
import inspect
import io
import json
import pathlib
import re
import sys
import tokenize
import types
from typing import List, Optional, Tuple, TextIO, Mapping, Any, MutableMapping, Union, Callable

import asttokens

import icontract


class LineRange:
    """Represent a line range (indexed from 1, both first and last inclusive)."""
    def __init__(self, first: int, last: int)->None:
        """Initialize with the given values."""
        self.first = first
        self.last = last

class ParamsGeneral:
    """Represent general program parameters specified regardless of the command."""

    # yapf: disable
    def __init__(
            self,
            include: List[Union[re.Pattern, LineRange]],
            exclude: List[Union[re.Pattern, LineRange]]
    ) -> None:
        # yapf: enable
        self.include = include
        self.exclude = exclude

_LINE_RANGE_RE = re.compile(r'^\s*(?P<first>[0-9]|[1-9][0-9]+)(\s*-\s*(?P<last>[1-9]|[1-9][0-9]+))?\s*$')

def _parse_point_spec(text: str)->Tuple[Optional[Union[LineRange, re.Pattern]], List[str]]:
    """
    Try to parse the given specification of function point(s).
    
    Return (parsed point spec, errors if any)
    """
    errors = []  # type: List[str]

    mtch = _LINE_RANGE_RE.match(text)
    if mtch:
        if mtch.group('last') is None:
            first = int(mtch.group('first'))
            if first <= 0:
                errors.append("Unexpected line index (expected to start from 1): {}".format(text))
                return None, errors

            return LineRange(first=int(mtch.group('first')), last=first), errors
        else:
            first = int(mtch.group('first'))
            last = int(mtch.group('last'))

            if first <= 0:
                errors.append("Unexpected line index (expected to start from 1): {}".format(text))
                return None, errors
                
            if last < first:
                errors.append("Unexpected line range (last < first): {}".format(text))
                return None, errors
            
            else:
                return LineRange(first=int(mtch.group('first')), last=int(mtch.group('last'))), errors

    try:
        pattern = re.compile(text)
        return pattern, errors
    except re.error as err:
        errors.append("Failed to parse the pattern {}: {}".format(text, err))
        return None, errors
        
def _parse_general_params(args: argparse.Namespace) -> Tuple[Optional[ParamsGeneral], List[str]]:
    """
    Try to parse general parameters of the program (regardless of the command).

    Return (parsed parameters, errors if any).
    """
    errors = []  # type: List[str]

    include = []  # type: List[re.Pattern]
    if args.include is not None:
        for include_str in args.include:
            point_spec, point_spec_errors = _parse_point_spec(text=include_str)
            errors.extend(point_spec_errors)
            
            if not point_spec_errors:
                include.append(point_spec)

    exclude = []  # type: List[re.Pattern]
    if args.exclude is not None:
        for exclude_str in args.exclude:
            point_spec, point_spec_errors = _parse_point_spec(text=exclude_str)
            errors.extend(point_spec_errors)

            if not point_spec_errors:
                exclude.append(point_spec)

    if errors:
        return None, errors

    return ParamsGeneral(include=include, exclude=exclude), errors


class ParamsTest:
    """Represent parameters of the command "test"."""

    def __init__(self, path: pathlib.Path, setting: Mapping[str, Any]) -> None:
        self.path = path
        self.setting = setting


_SETTING_STATEMENT_RE = re.compile(r'^(?P<identifier>[a-zA-Z_][a-zA-Z_0-9]*)\s*=\s*(?P<value>.*)\s*$')


def _parse_test_params(args: argparse.Namespace) -> Tuple[Optional[ParamsTest], List[str]]:
    """
    Try to parse the parameters of the command "test".

    Return (parsed parameters, errors if any).
    """
    errors = []  # type: List[str]

    path = pathlib.Path(args.path)

    setting = collections.OrderedDict()  # type: MutableMapping[str, Any]

    if args.setting is not None:
        for i, statement in enumerate(args.setting):
            mtch = _SETTING_STATEMENT_RE.match(statement)
            if not mtch:
                errors.append("Invalid setting statement {}. Expected statement to match {}, but got: {}".format(
                    i + 1, _SETTING_STATEMENT_RE.pattern, statement))

                return None, errors

            identifier = mtch.group("identifier")
            value_str = mtch.group("value")

            try:
                value = json.loads(value_str)
            except json.decoder.JSONDecodeError as error:
                errors.append("Failed to parse the value of the setting {}: {}".format(identifier, error))
                return None, errors

            setting[identifier] = value

    if errors:
        return None, errors

    return ParamsTest(path=path, setting=setting), errors


class ParamsGhostwrite:
    """Represent parameters of the command "ghostwrite"."""

    def __init__(self, module: str, output: Optional[pathlib.Path], explicit: bool, bare: bool) -> None:
        self.module = module
        self.output = output
        self.explicit = explicit
        self.bare = bare


def _parse_ghostwrite_params(args: argparse.Namespace) -> Tuple[Optional[ParamsGhostwrite], List[str]]:
    """
    Try to parse the parameters of the command "ghostwrite".

    Return (parsed parameters, errors if any).
    """
    output = pathlib.Path(args.output) if args.output != '-' else None

    return ParamsGhostwrite(module=args.module, output=output, explicit=args.explicit, bare=args.bare), []


class Params:
    """Represent the parameters of the program."""

    def __init__(self, general: ParamsGeneral, command: Union[ParamsTest, ParamsGhostwrite]) -> None:
        self.general = general
        self.command = command


def _parse_args_to_params(args: argparse.Namespace) -> Tuple[Optional[Params], List[str]]:
    """
    Parse the parameters from the command-line arguments.

    Return parsed parameters, errors if any
    """
    errors = []  # type: List[str]

    general, general_errors = _parse_general_params(args=args)
    errors.extend(general_errors)

    command = None  # type: Optional[Union[ParamsTest, ParamsGhostwrite]]
    if args.command == 'test':
        test, command_errors = _parse_test_params(args=args)
        errors.extend(command_errors)

        command = test

    elif args.command == 'ghostwrite':
        ghostwrite, command_errors = _parse_ghostwrite_params(args=args)
        errors.extend(command_errors)
        command = ghostwrite

    if errors:
        return None, errors

    assert general is not None
    assert command is not None

    return Params(general=general, command=command), []


def _make_argument_parser() -> argparse.ArgumentParser:
    """Create an instance of the argument parser to parse command-line arguments."""
    # TODO: see the interface of hypothesis ghostwrite
    parser = argparse.ArgumentParser(prog="pyicontract-hypothesis", description=__doc__)
    subparsers = parser.add_subparsers(help="Commands", dest='command')
    subparsers.required = True

    test_parser = subparsers.add_parser(
        "test", help="Test the functions automatically by inferring search strategies and preconditions")

    test_parser.add_argument("-p", "--path", help="Path to the Python file to test", required=True)

    test_parser.add_argument(
        "--setting",
        help=("Specify settings for Hypothesis\n\n"
              "The settings are separated by ';' and assigned by '='."
              "The value of the setting needs to be encoded as JSON.\n\n"
              "Example: max_examples=500"),
        nargs="*"
    )

    ghostwriter_parser = subparsers.add_parser(
        "ghostwrite", help="Ghostwrite the unit test module based on inferred search strategies")

    ghostwriter_parser.add_argument("-m", "--module", help="Module to process", required=True)

    ghostwriter_parser.add_argument(
        "-o", "--output",
        help="Path to the file where the output should be written. If '-', writes to STDOUT.",
        default="-")

    ghostwriter_parser.add_argument(
        "--explicit",
        help=("Write the strategies explicitly in the unit test module instead of inferring them at run-time\n\n"
              "This is practical if you want to tune and refine the strategies and "
              "just want to use ghostwriting as a starting point."),
        action='store_true')

    ghostwriter_parser.add_argument(
        "--bare",
        help=("Print only the body of the tests and omit header/footer "
              "(such as TestCase class or import statements).\n\n"
              "This is useful when you only want to inspect a single test or "
              "include a single test function in a custom test suite."),
        action='store_true')

    for subparser in [test_parser, ghostwriter_parser]:
        subparser.add_argument(
            "-i", "--include",
            help=("Regular expressions, lines or line ranges of the functions to process\n\n"
                  "If a line or line range overlaps the body of a function, the function is considered included."
                  "Example 1: ^do_something.*$\n"
                  "Example 2: 3\n"
                  "Example 3: 34-65"),
            required=False,
            nargs="*")

        subparser.add_argument(
            "-e", "--exclude",
            help=("Regular expressions of the functions to exclude from processing"
                  "If a line or line range overlaps the body of a function, the function is considered excluded."
                  "Example 1: ^do_something.*$\n"
                  "Example 2: 3\n"
                  "Example 3: 34-65"),
            default=['^_.*$'],
            nargs="*")

    return parser


def _parse_args(parser: argparse.ArgumentParser, argv: List[str]) -> Tuple[Optional[argparse.Namespace], str, str]:
    """
    Parse the command-line arguments.

    Return (parsed args or None if failure, captured stdout, captured stderr).
    """
    pass  # for pydocstyle

    # From https://stackoverflow.com/questions/18160078
    @contextlib.contextmanager
    def captured_output():
        new_out, new_err = io.StringIO(), io.StringIO()
        old_out, old_err = sys.stdout, sys.stderr
        try:
            sys.stdout, sys.stderr = new_out, new_err
            yield sys.stdout, sys.stderr
        finally:
            sys.stdout, sys.stderr = old_out, old_err

    with captured_output() as (out, err):
        try:
            parsed_args = parser.parse_args(argv)

            err.seek(0)
            out.seek(0)
            return parsed_args, out.read(), err.read()

        except SystemExit:
            err.seek(0)
            out.seek(0)
            return None, out.read(), err.read()

_PYICONTRACT_HYPOTHESIS_DIRECTIVE_RE = re.compile(r'#\s*pyicontract-hypothesis\s*:\s*(?P<value>disable|enable)')

class Point:
    """Represent a testable function."""
    @icontract.require(lambda srow: srow > 0)
    @icontract.require(lambda erow: erow > 0)
    @icontract.require(lambda srow, erow: srow <= erow)
    def __init__(self, first_row: int, last_row: int, func: Callable[..., Any]) -> None:
        """
        Initialize with the given values.

        First and last row are both inclusive.
        """
        self.first_row = first_row
        self.last_row = last_row
        self.func = func

def _select_points(
        source_code: str,
        mod: types.ModuleType,
        include: List[Union[LineRange, re.Pattern]],
        exclude: List[Union[LineRange, re.Pattern]]
)->Tuple[List[Callable[..., Any]], List[str]]:
    points = []  # type: List[Point]

    for key in dir(mod):
        value = getattr(mod, key)
        if inspect.isfunction(value):
            func = value  # type: Callable[..., Any]
            source_lines, srow = inspect.getsourcelines(func)

            point = Point(first_row=srow, last_row = srow+len(source_lines) - 1, func=func)
            points.append(point)

    # TODO: exclude functions if they have the directive in the body
    # TODO: exclude ranges of functions if the comment is in the root

    return [], []


def test(general: ParamsGeneral, command: ParamsTest)->List[str]:
    """
    Test the specified functions.

    Return errors if any.
    """
    if not command.path.exists():
        return ['The file to be tested does not exist: {}'.format(command.path)]

    try:
        source_code = command.path.read_text(encoding='utf-8')
    except Exception as error:
        return ['Failed to read the file {}: {}'.format(command.path, error)]

    fullname = re.sub(r'[^A-Za-z0-9_]', '_', command.path.stem)

    mod = None  # type: Optional[types.ModuleType]
    try:
        loader = importlib.machinery.SourceFileLoader(fullname=fullname, path=str(command.path))
        mod = types.ModuleType(loader.name)
        loader.exec_module(mod)
    except Exception as error:
        return ['Failed to import the file {}: {}'.format(command.path, error)]

    assert mod is not None, "Expected mod to be set before"

    points, errors = _select_points(source_code=source_code, mod=mod, include=general.include, exclude=general.exclude)
    if errors:
        return errors

    print(f"points is {points!r}")  # TODO: debug


def ghostwrite(general: ParamsGeneral, command: ParamsGhostwrite)->Tuple[str, List[str]]:
    """
    Write a unit test module for the specified functions.

    Return (generated code, errors if any).
    """
    raise NotImplementedError()

def testable_main(argv: List[str], stdout: TextIO, stderr: TextIO) -> int:
    """Execute the testable_main routine."""
    parser = _make_argument_parser()
    args, out, err = _parse_args(parser=parser, argv=argv)
    print(out, file=stdout)
    print(err, file=stderr)

    if args is None:
        return 1

    params, errors = _parse_args_to_params(args=args)
    if errors:
        for error in errors:
            print(error, file=stderr)
            return 1

    if isinstance(params.command, ParamsTest):
        errors = test(general=params.general, command=params.command)
    elif isinstance(params.command, ParamsGhostwrite):
        errors = ghostwrite(general=params.general, command=params.command)
    else:
        raise AssertionError("Unhandled command: {}".format(params))

    if errors:
        for error in errors:
            print(error, file=stderr)
            return 1

    return 0


def main() -> int:
    """Wrap the main routine wit default arguments."""
    return testable_main(argv=sys.argv[1:], stdout=sys.stdout, stderr=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
