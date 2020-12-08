# pylint: disable=missing-docstring
# pylint: disable=invalid-name
# pylint: disable=unused-argument
import io
import re
import textwrap
import unittest

import icontract.integration.with_hypothesis.icontract_hypothesis as icontract_hypothesis


class TestMain(unittest.TestCase):
    def test_no_command(self) -> None:
        argv = ['-m', 'some_module']

        stdout, stderr = io.StringIO(), io.StringIO()

        icontract_hypothesis.testable_main(argv=argv, stdout=stdout, stderr = stderr)

        stdout.seek(0)
        out = stdout.read()

        stderr.seek(0)
        err = stderr.read()

        self.assertEqual('', out.strip())
        self.assertEqual(
            textwrap.dedent('''\
                usage: pyicontract-hypothesis [-h] -m MODULE [-i [INCLUDE [INCLUDE ...]]]
                                              [-e [EXCLUDE [EXCLUDE ...]]]
                                              {test,ghostwrite} ...
                pyicontract-hypothesis: error: the following arguments are required: command'''),
            err.strip())

    def test_general_argument_parsing(self) -> None:
        argv = ['test',
                '-m', 'some_module', '-i', 'include-something', 'include-another',
                '-e', 'exclude-something', 'exclude-another']

        parser = icontract_hypothesis._make_argument_parser()
        args, out, err = icontract_hypothesis._parse_args(parser=parser, argv=argv)
        assert args is not None, "Failed to parse argv {!r}: {}".format(argv, err)

        general, errs = icontract_hypothesis._parse_general_params(args=args)

        self.assertListEqual([], errs)
        self.assertEqual("some_module", general.module)
        self.assertListEqual(
            [re.compile(pattern) for pattern in ["include-something", "include-another"]], general.include)
        self.assertListEqual(
            [re.compile(pattern) for pattern in ["exclude-something", "exclude-another"]], general.exclude)


if __name__ == '__main__':
    unittest.main()
