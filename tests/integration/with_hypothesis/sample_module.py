"""A sample module meant for testing pyicontract-hypothesis."""

import icontract


@icontract.require(lambda x: x > 0)
def testable_some_func(x: int) -> None:
    pass


def untestable_some_func(x: int) -> None:
    # We need more lines so that we can test the overlaps easily.
    pass
    pass
    pass

def untestable_another_func(x: int) -> None:
    # pyicontract-hypothesis: disable-for-this-function
    pass

# pyicontract-hypothesis: disable
def untestable_yet_another_func(x: int) -> None:
    pass
# pyicontract-hypothesis: enable


class A:
    @icontract.require(lambda x: x > 0)
    def __init__(self, x: int) -> None:
        self.x = x

    @icontract.require(lambda y: y > 0)
    @icontract.ensure(lambda result: result > 0)
    def some_method(self, y: int) -> int:
        return self.x + y
