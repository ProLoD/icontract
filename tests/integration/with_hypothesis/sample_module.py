"""A sample module meant for testing pyicontract-hypothesis."""

import icontract


@icontract.require(lambda x: x > 0)
def some_func(x: int) -> None:
    pass


def some_func_to_be_excluded(x: int) -> None:
    pass


def another_func_to_be_excluded(x: int) -> None:
    # pyicontract-hypothesis: disable
    pass


class A:
    @icontract.require(lambda x: x > 0)
    def __init__(self, x: int) -> None:
        self.x = x

    @icontract.require(lambda y: y > 0)
    @icontract.ensure(lambda result: result > 0)
    def some_method(self, y: int) -> int:
        return self.x + y
