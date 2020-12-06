# yapf: disable
# This is a patched ``_from_type`` part of
# https://github.com/HypothesisWorks/hypothesis/blob/aebab4ef071fac4fb5d1dcce523f817112c00047/hypothesis-python/src/hypothesis/strategies/_internal/core.py

# The original header is:
# This file is part of Hypothesis, which may be found at
# https://github.com/HypothesisWorks/hypothesis/
#
# Most of this work is copyright (C) 2013-2020 David R. MacIver
# (david@drmaciver.com), but it contains contributions by others. See
# CONTRIBUTING.rst for a full list of people who may hold copyright, and
# consult the git log if you need to determine who owns an individual
# contribution.
#
# This Source Code Form is subject to the terms of the Mozilla Public License,
# v. 2.0. If a copy of the MPL was not distributed with this file, You can
# obtain one at https://mozilla.org/MPL/2.0/.
#
# END HEADER

import enum
import sys
import typing
from decimal import Decimal
from fractions import Fraction
from inspect import isabstract
from typing import (
    Callable,
    Hashable,
    Tuple,
    Type,
    TypeVar,
    Union,
)

import attr
from hypothesis.errors import InvalidArgument, ResolutionFailed
from hypothesis.internal.compat import get_type_hints, typing_root_type
from hypothesis.internal.reflection import (
    is_typed_named_tuple,
    nicerepr,
    required_args,
)
from hypothesis.strategies._internal import SearchStrategy

# (mristin, 2020-12-06) Import only what the patched from_type needs
from hypothesis.strategies._internal.core import (
    cacheable,
    fixed_dictionaries,
    NOTHING,
    one_of,
    sampled_from,
    deferred
)
from hypothesis.strategies._internal.lazy import LazyStrategy
from hypothesis.strategies._internal.strategies import (
    Ex,
)

import icontract.integration.with_hypothesis

K = TypeVar("K")
V = TypeVar("V")
UniqueBy = Union[Callable[[Ex], Hashable], Tuple[Callable[[Ex], Hashable], ...]]
# See https://github.com/python/mypy/issues/3186 - numbers.Real is wrong!
Real = Union[int, float, Fraction, Decimal]

@cacheable
def from_type(thing: Type[Ex]) -> SearchStrategy[Ex]:
    """Looks up the appropriate search strategy for the given type.

    ``from_type`` is used internally to fill in missing arguments to
    :func:`~hypothesis.strategies.builds` and can be used interactively
    to explore what strategies are available or to debug type resolution.

    You can use :func:`~hypothesis.strategies.register_type_strategy` to
    handle your custom types, or to globally redefine certain strategies -
    for example excluding NaN from floats, or use timezone-aware instead of
    naive time and datetime strategies.

    The resolution logic may be changed in a future version, but currently
    tries these five options:

    1. If ``thing`` is in the default lookup mapping or user-registered lookup,
       return the corresponding strategy.  The default lookup covers all types
       with Hypothesis strategies, including extras where possible.
    2. If ``thing`` is from the :mod:`python:typing` module, return the
       corresponding strategy (special logic).
    3. If ``thing`` has one or more subtypes in the merged lookup, return
       the union of the strategies for those types that are not subtypes of
       other elements in the lookup.
    4. Finally, if ``thing`` has type annotations for all required arguments,
       and is not an abstract class, it is resolved via
       :func:`~hypothesis.strategies.builds`.
    5. Because :mod:`abstract types <python:abc>` cannot be instantiated,
       we treat abstract types as the union of their concrete subclasses.
       Note that this lookup works via inheritance but not via
       :obj:`~python:abc.ABCMeta.register`, so you may still need to use
       :func:`~hypothesis.strategies.register_type_strategy`.

    There is a valuable recipe for leveraging ``from_type()`` to generate
    "everything except" values from a specified type. I.e.

    .. code-block:: python

        def everything_except(excluded_types):
            return (
                from_type(type).flatmap(from_type)
                .filter(lambda x: not isinstance(x, excluded_types))
            )

    For example, ``everything_except(int)`` returns a strategy that can
    generate anything that ``from_type()`` can ever generate, except for
    instances of :class:`python:int`, and excluding instances of types
    added via :func:`~hypothesis.strategies.register_type_strategy`.

    This is useful when writing tests which check that invalid input is
    rejected in a certain way.
    """
    # This tricky little dance is because we want to show the repr of the actual
    # underlying strategy wherever possible, as a form of user education, but
    # would prefer to fall back to the default "from_type(...)" repr instead of
    # "deferred(...)" for recursive types or invalid arguments.
    try:
        return _from_type(thing)
    except Exception:
        return LazyStrategy(
            lambda thing: deferred(lambda: _from_type(thing)),
            (thing,),
            {},
            force_repr="from_type(%r)" % (thing,),
        )


def _from_type(thing: Type[Ex]) -> SearchStrategy[Ex]:
    # TODO: We would like to move this to the top level, but pending some major
    # refactoring it's hard to do without creating circular imports.
    import hypothesis.strategies._internal.types as types
    import icontract.integration.with_hypothesis.patched_types as patched_types

    if (
        hasattr(typing, "_TypedDictMeta")
        and type(thing) is typing._TypedDictMeta  # type: ignore
        or hasattr(types.typing_extensions, "_TypedDictMeta")
        and type(thing) is types.typing_extensions._TypedDictMeta  # type: ignore
    ):  # pragma: no cover
        # The __optional_keys__ attribute may or may not be present, but if there's no
        # way to tell and we just have to assume that everything is required.
        # See https://github.com/python/cpython/pull/17214 for details.
        optional = getattr(thing, "__optional_keys__", ())
        anns = {k: from_type(v) for k, v in thing.__annotations__.items()}
        return fixed_dictionaries(  # type: ignore
            mapping={k: v for k, v in anns.items() if k not in optional},
            optional={k: v for k, v in anns.items() if k in optional},
        )

    def as_strategy(strat_or_callable, thing, final=True):
        # User-provided strategies need some validation, and callables even more
        # of it.  We do this in three places, hence the helper function
        if not isinstance(strat_or_callable, SearchStrategy):
            assert callable(strat_or_callable)  # Validated in register_type_strategy
            try:
                # On Python 3.6, typing.Hashable is just an alias for abc.Hashable,
                # and the resolver function for Type throws an AttributeError because
                # Hashable has no __args__.  We discard such errors when attempting
                # to resolve subclasses, because the function was passed a weird arg.
                strategy = strat_or_callable(thing)
            except Exception:  # pragma: no cover
                if not final:
                    return NOTHING
                raise
        else:
            strategy = strat_or_callable
        if not isinstance(strategy, SearchStrategy):
            raise ResolutionFailed(
                "Error: %s was registered for %r, but returned non-strategy %r"
                % (thing, nicerepr(strat_or_callable), strategy)
            )
        if strategy.is_empty:
            raise ResolutionFailed("Error: %r resolved to an empty strategy" % (thing,))
        return strategy

    if not isinstance(thing, type):
        if types.is_a_new_type(thing):
            # Check if we have an explicitly registered strategy for this thing,
            # resolve it so, and otherwise resolve as for the base type.
            if thing in types._global_type_lookup:
                return as_strategy(types._global_type_lookup[thing], thing)
            return from_type(thing.__supertype__)
        # Under Python 3.6, Unions are not instances of `type` - but we
        # still want to resolve them!
        if getattr(thing, "__origin__", None) is typing.Union:
            args = sorted(thing.__args__, key=types.type_sorting_key)
            return one_of([from_type(t) for t in args])
    if not types.is_a_type(thing):
        raise InvalidArgument("thing=%s must be a type" % (thing,))
    # Now that we know `thing` is a type, the first step is to check for an
    # explicitly registered strategy.  This is the best (and hopefully most
    # common) way to resolve a type to a strategy.  Note that the value in the
    # lookup may be a strategy or a function from type -> strategy; and we
    # convert empty results into an explicit error.
    try:
        if thing in types._global_type_lookup:
            return as_strategy(types._global_type_lookup[thing], thing)
    except TypeError:  # pragma: no cover
        # This is due to a bizarre divergence in behaviour under Python 3.9.0:
        # typing.Callable[[], foo] has __args__ = (foo,) but collections.abc.Callable
        # has __args__ = ([], foo); and as a result is non-hashable.
        pass
    # We also have a special case for TypeVars.
    # They are represented as instances like `~T` when they come here.
    # We need to work with their type instead.
    if isinstance(thing, TypeVar) and type(thing) in types._global_type_lookup:
        return as_strategy(types._global_type_lookup[type(thing)], thing)
    # If there's no explicitly registered strategy, maybe a subtype of thing
    # is registered - if so, we can resolve it to the subclass strategy.
    # We'll start by checking if thing is from from the typing module,
    # because there are several special cases that don't play well with
    # subclass and instance checks.
    if isinstance(thing, typing_root_type) or (
        sys.version_info[:2] >= (3, 9)
        and isinstance(getattr(thing, "__origin__", None), type)
        and getattr(thing, "__args__", None)
    ):
        # (mristin, 2020-12-06): We need to propagate builds_with_preconditions.
        return icontract.integration.with_hypothesis.patched_types.from_typing_type(thing)

    # If it's not from the typing module, we get all registered types that are
    # a subclass of `thing` and are not themselves a subtype of any other such
    # type.  For example, `Number -> integers() | floats()`, but bools() is
    # not included because bool is a subclass of int as well as Number.
    strategies = [
        as_strategy(v, thing, final=False)
        for k, v in sorted(types._global_type_lookup.items(), key=repr)
        if isinstance(k, type)
        and issubclass(k, thing)
        and sum(types.try_issubclass(k, typ) for typ in types._global_type_lookup) == 1
    ]
    if any(not s.is_empty for s in strategies):
        return one_of(strategies)
    # If we don't have a strategy registered for this type or any subtype, we
    # may be able to fall back on type annotations.
    if issubclass(thing, enum.Enum):
        return sampled_from(thing)
    # If we know that builds(thing) will fail, give a better error message
    required = required_args(thing)
    if required and not any(
        [
            required.issubset(get_type_hints(thing)),
            attr.has(thing),
            # NamedTuples are weird enough that we need a specific check for them.
            is_typed_named_tuple(thing),
        ]
    ):
        raise ResolutionFailed(
            "Could not resolve %r to a strategy; consider "
            "using register_type_strategy" % (thing,)
        )
    # Finally, try to build an instance by calling the type object
    if not isabstract(thing):
        # (mristin, 2020-12-06) This hook propagates inferring strategies with preconditions.
        return icontract.integration.with_hypothesis.builds_with_preconditions(thing)

    subclasses = thing.__subclasses__()
    if not subclasses:
        raise ResolutionFailed(
            "Could not resolve %r to a strategy, because it is an abstract type "
            "without any subclasses. Consider using register_type_strategy" % (thing,)
        )
    return sampled_from(subclasses).flatmap(from_type)
