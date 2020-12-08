#!/usr/bin/env python3

"""Run Hypothesis tests on a module with inferred strategies."""
import argparse
import collections
import contextlib
import imp
import importlib
import io
import json
import pathlib
import re
import sys
from typing import List, Optional, Tuple, TextIO, Mapping, Any, MutableMapping, Union


class ParamsGeneral:
    """Represent general program parameters specified regardless of the subcommand."""

    def __init__(self, module: str, include: List[re.Pattern], exclude: List[re.Pattern]) -> None:
        self.module = module
        self.include = include
        self.exclude = exclude


def _parse_general_params(args: argparse.Namespace) -> Tuple[Optional[ParamsGeneral], List[str]]:
    """
    Try to parse general parameters of the program (regardless of the subcommand).

    Return (parsed parameters, error if any).
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

    if errors:
        return None, errors

    return ParamsGeneral(module=args.module, include=include, exclude=exclude), []


class ParamsTest:
    """Represent parameters of the subcommand "test"."""

    def __init__(self, setting: Mapping[str, Any]) -> None:
        self.setting = setting


_SETTING_STATEMENT_RE = re.compile(r'^(?P<identifier>[a-zA-Z_][a-zA-Z_0-9]*)\s*=\s*(?P<value>.*)\s*$')


def _parse_test_params(args: argparse.Namespace) -> Tuple[Optional[ParamsTest], List[str]]:
    """
    Try to parse the parameters of the subcommand "test".

    Return (parsed parameters, errors if any).
    """
    text = args.setting
    errors = []  # type: List[str]
    setting = collections.OrderedDict()  # type: MutableMapping[str, Any]
    parts = text.split(";")

    for i, part in enumerate(parts):
        mtch = _SETTING_STATEMENT_RE.match(part)
        if not mtch:
            errors.append("Invalid setting statement {}. Expected statement to match {}, but got: {}".format(
                i + 1, _SETTING_STATEMENT_RE.pattern, part))

            return None, errors

        identifier = mtch.group("identifier")
        value_str = mtch.group("value")

        try:
            value = json.loads(value_str)
        except json.decoder.JSONDecodeError as error:
            errors.append("Failed to parse the value of the setting {}: {}".format(identifier, error))
            return None, errors

        setting[identifier] = value

    return ParamsTest(setting=setting), []


class ParamsGhostwrite:
    """Represent parameters of the subcommand "ghostwrite"."""

    def __init__(self, output: Optional[pathlib.Path], explicit: bool) -> None:
        self.output = output
        self.explicit = explicit


def _parse_ghostwrite_params(args: argparse.Namespace) -> Tuple[Optional[ParamsGhostwrite], List[str]]:
    """
    Try to parse the parameters of the subcommand "ghostwrite".

    Return (parsed parameters, errors if any).
    """
    output = pathlib.Path(args.output) if args.output != '-' else None

    return ParamsGhostwrite(output=output, explicit=args.explicit), []


class Params:
    """Represent the parameters of the program."""

    def __init__(self, general: ParamsGeneral, subcommand: Union[ParamsTest, ParamsGhostwrite]) -> None:
        self.general = general
        self.subcommand = subcommand


def _parse_args_to_params(args: argparse.Namespace) -> Tuple[Optional[Params], List[str]]:
    """
    Parse the parameters from the command-line arguments.

    Return parsed parameters, errors if any
    """
    errors = []  # type: List[str]

    general, general_errors = _parse_general_params(args=args)
    errors.extend(general_errors)

    subcommand = None  # type: Optional[Union[ParamsTest, ParamsGhostwrite]]
    if args.command == 'test':
        test, subcommand_errors = _parse_test_params(args=args)
        errors.extend(subcommand_errors)

        subcommand = test

    elif args.command == 'ghostwrite':
        ghostwrite, subcommand_errors = _parse_ghostwrite_params(args=args)
        errors.extend(subcommand_errors)
        subcommand = ghostwrite

    if errors:
        return None, errors

    assert general is not None
    assert subcommand is not None

    return Params(general=general, subcommand=subcommand), []


def _make_argument_parser() -> argparse.ArgumentParser:
    """Create an instance of the argument parser to parse command-line arguments."""
    # TODO: see the interface of hypothesis ghostwrite
    parser = argparse.ArgumentParser(prog="pyicontract-hypothesis", description=__doc__)
    subparsers = parser.add_subparsers(help="Commands", dest='command')
    subparsers.required = True

    test_parser = subparsers.add_parser(
        "test", help="Test the functions automatically by inferring search strategies and preconditions")

    test_parser.add_argument(
        "--setting",
        help=("Specify settings for Hypothesis\n\n"
              "The settings are separated by ';' and assigned by '='."
              "The value of the setting needs to be encoded as JSON.\n\n"
              "Example: 'max_examples=500;deadline=5000;suppress_health_check=2"))

    ghostwriter_parser = subparsers.add_parser(
        "ghostwrite", help="Ghostwrite the unit test module based on inferred search strategies")

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

    for subparser in [test_parser, ghostwriter_parser]:
        subparser.add_argument("-m", "--module", help="Module to process", required=True)
        subparser.add_argument("-i", "--include", help="Regular expressions of the functions to process",
                               required=False,
                               nargs="*")
        subparser.add_argument("-e", "--exclude",
                               help="Regular expressions of the functions to exclude from processing",
                               required=False, nargs="*")

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


def testable_main(argv: List[str], stdout: TextIO, stderr: TextIO) -> int:
    """Execute the testable_main routine."""
    parser = _make_argument_parser()
    args, out, err = _parse_args(parser=parser, argv=argv)
    print(out, file=stdout)
    print(err, file=stderr)

    if args is None:
        return 1

    params, errs = _parse_args_to_params(args=args)
    if errs:
        for err in errs:
            print(err, file=stderr)
            return 1

    try:
        module = importlib.import_module(name=params.general.module)
    except Exception as err:
        raise RuntimeError("Error loading the module: {}".format(params.general.module)) from err

    print(dir(module))
    return 0


def main() -> int:
    """Wrap the main routine wit default arguments."""
    return testable_main(argv=sys.argv[1:], stdout=sys.stdout, stderr=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
