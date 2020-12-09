# pylint: disable=missing-docstring
# pylint: disable=invalid-name
# pylint: disable=unused-argument
import io
import os
import pathlib
import re
import textwrap
import unittest
import uuid

import icontract.integration.with_hypothesis.icontract_hypothesis as icontract_hypothesis


class TestLineRangeRe(unittest.TestCase):
    def test_only_first(self) -> None:
        mtch = icontract_hypothesis._LINE_RANGE_RE.match(' 123 ')
        assert mtch is not None

        self.assertEqual('123', mtch.group('first'))
        self.assertIsNone(mtch.group('last'), "Unexpected last group: {}".format(mtch.group('last')))

    def test_first_and_last(self) -> None:
        mtch = icontract_hypothesis._LINE_RANGE_RE.match(' 123 - 435 ')
        assert mtch is not None

        self.assertEqual('123', mtch.group('first'))
        self.assertEqual('435', mtch.group('last'))

    def test_no_match(self) -> None:
        mtch = icontract_hypothesis._LINE_RANGE_RE.match('123aa')
        assert mtch is None, "Expected no match, but got: {}".format(mtch)


class TestParsingOfPointSpecs(unittest.TestCase):
    def test_single_line(self) -> None:
        text = '123'
        point_spec, errors = icontract_hypothesis._parse_point_spec(text=text)

        self.assertListEqual([], errors)
        assert isinstance(point_spec, icontract_hypothesis.LineRange)
        self.assertEqual(123, point_spec.first)
        self.assertEqual(123, point_spec.last)

    def test_line_range(self) -> None:
        text = '123-345'
        point_spec, errors = icontract_hypothesis._parse_point_spec(text=text)

        self.assertListEqual([], errors)
        assert isinstance(point_spec, icontract_hypothesis.LineRange)
        self.assertEqual(123, point_spec.first)
        self.assertEqual(345, point_spec.last)

    def test_invalid_line_range(self) -> None:
        text = '345-123'
        point_spec, errors = icontract_hypothesis._parse_point_spec(text=text)

        assert point_spec is None
        self.assertListEqual(['Unexpected line range (last < first): 345-123'], errors)

    def test_pattern(self) -> None:
        text = r'^do_.*$'
        point_spec, errors = icontract_hypothesis._parse_point_spec(text=text)

        assert isinstance(point_spec, re.Pattern)
        self.assertListEqual([], errors)
        self.assertEqual(text, point_spec.pattern)


class TestParsingOfParameters(unittest.TestCase):
    def test_no_command(self) -> None:
        argv = ['-m', 'some_module']

        stdout, stderr = io.StringIO(), io.StringIO()

        icontract_hypothesis.testable_main(argv=argv, stdout=stdout, stderr=stderr)

        stdout.seek(0)
        out = stdout.read()

        stderr.seek(0)
        err = stderr.read()

        self.assertEqual('', out.strip())
        self.assertEqual(
            '''\
usage: pyicontract-hypothesis [-h] {test,ghostwrite} ...
pyicontract-hypothesis: error: argument command: invalid choice: 'some_module' (choose from 'test', 'ghostwrite')''',
            err.strip())

    def test_subcommand_test(self) -> None:
        # yapf: disable
        argv = ['test',
                '--path', 'some_module.py', '--include', 'include-something',
                '--exclude', 'exclude-something',
                '--setting', 'suppress_health_check=[2, 3]']
        # yapf: enable

        parser = icontract_hypothesis._make_argument_parser()
        args, out, err = icontract_hypothesis._parse_args(parser=parser, argv=argv)
        assert args is not None, "Failed to parse argv {!r}: {}".format(argv, err)

        general, errs = icontract_hypothesis._parse_general_params(args=args)

        self.assertListEqual([], errs)
        self.assertListEqual([re.compile(pattern) for pattern in ["include-something"]], general.include)
        self.assertListEqual([re.compile(pattern) for pattern in ["exclude-something"]], general.exclude)

        test, errs = icontract_hypothesis._parse_test_params(args=args)

        self.assertListEqual([], errs)
        self.assertEqual(pathlib.Path('some_module.py'), test.path)
        self.assertDictEqual({"suppress_health_check": [2, 3]}, dict(test.setting))

    def test_subcommand_ghostwrite(self) -> None:
        # yapf: disable
        argv = ['ghostwrite',
                '--module', 'some_module',
                '--include', 'include-something',
                '--exclude', 'exclude-something',
                '--explicit',
                '--bare']
        # yapf: enable
        parser = icontract_hypothesis._make_argument_parser()
        args, out, err = icontract_hypothesis._parse_args(parser=parser, argv=argv)
        assert args is not None, "Failed to parse argv {!r}: {}".format(argv, err)

        general, errs = icontract_hypothesis._parse_general_params(args=args)

        self.assertListEqual([], errs)
        self.assertListEqual([re.compile(pattern) for pattern in ["include-something"]], general.include)
        self.assertListEqual([re.compile(pattern) for pattern in ["exclude-something"]], general.exclude)

        ghostwrite, errs = icontract_hypothesis._parse_ghostwrite_params(args=args)

        self.assertListEqual([], errs)
        self.assertEqual('some_module', ghostwrite.module)
        self.assertTrue(ghostwrite.explicit)
        self.assertTrue(ghostwrite.bare)


# TODO: implement filtering based on the module
# TODO:     include # pyicontract-hypothesis: disable / # pyicntract-hypothesis: enable as statement
# TODO: test filtering


class TestOnSampleModule(unittest.TestCase):
    def test_test_nonexisting_file(self) -> None:
        path = "doesnt-exist.{}".format(uuid.uuid4())
        argv = ['test', '--path', path]

        stdout = io.StringIO()
        stderr = io.StringIO()

        exit_code = icontract_hypothesis.testable_main(argv=argv, stdout=stdout, stderr=stderr)

        stderr.seek(0)
        err = stderr.read()

        self.assertEqual("The file to be tested does not exist: {}".format(path), err.strip())
        self.assertEqual(exit_code, 1)

    def test_test(self) -> None:
        this_dir = pathlib.Path(os.path.realpath(__file__)).parent

        # yapf: disable
        argv = ['test',
                '--path', str(this_dir / "sample_module.py"),
                '--include', '^testable_.*$',
                '--exclude', '^untestable_.*$'
                ]
        # yapf: enable

        stdout = io.StringIO()
        stderr = io.StringIO()

        exit_code = icontract_hypothesis.testable_main(argv=argv, stdout=stdout, stderr=stderr)

        stdout.seek(0)
        out = stdout.read()

        stderr.seek(0)
        err = stderr.read()

        self.assertEqual('', err.strip())
        self.assertEqual(exit_code, 0)


if __name__ == '__main__':
    unittest.main()
