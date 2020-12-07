# pylint: disable=missing-docstring
# pylint: disable=invalid-name
# pylint: disable=unused-argument
import re
import unittest

import icontract.integration.with_hypothesis.icontract_hypothesis


class TestMain(unittest.TestCase):
    def test_argument_parsing_short(self) -> None:
        argv = ['-m', 'some_module', '-i', 'include-something', 'include-another',
                '-e', 'exclude-something', 'exclude-another', '--reveal']

        parser = icontract.integration.with_hypothesis.icontract_hypothesis._make_argument_parser()
        args = parser.parse_args(args=argv)
        params, errs = icontract.integration.with_hypothesis.icontract_hypothesis._parse_args_to_params(args=args)

        self.assertListEqual([], errs)
        self.assertEqual("some_module", params.module)
        self.assertListEqual(
            [re.compile(pattern) for pattern in ["include-something", "include-another"]], params.include)
        self.assertListEqual(
            [re.compile(pattern) for pattern in ["exclude-something", "exclude-another"]], params.exclude)
        self.assertTrue(params.reveal)


if __name__ == '__main__':
    unittest.main()
