# yapf: disable
# This is a patched ``from_typing_type`` part of
# https://github.com/HypothesisWorks/hypothesis/blob/aebab4ef071fac4fb5d1dcce523f817112c00047/hypothesis-python/src/hypothesis/strategies/_internal/types.py

# The original header is:
#
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

import collections
import sys
import typing

from hypothesis import strategies as st
from hypothesis.errors import ResolutionFailed
from hypothesis.internal.compat import ForwardRef, typing_root_type
from hypothesis.strategies._internal.lazy import unwrap_strategies
from hypothesis.strategies._internal.strategies import OneOfStrategy

# (mristin, 2020-12-06) We have to hook st.from_type with our own from_type.
from icontract.integration.with_hypothesis.patched_from_type import from_type as icontract_from_type

# (mristin, 2020-12-06) Import only what the patched from_typing_type needs
from hypothesis.strategies._internal.types import (
    is_typing_literal,
    _global_type_lookup,
    is_generic_type,
    try_issubclass,
    register,
    ALWAYS_HASHABLE_TYPES,
    GeneratorStrategy,
    _can_hash,
    _try_import_forward_ref
)

try:
    import typing_extensions
except ImportError:
    typing_extensions = None  # type: ignore

try:
    from typing import GenericMeta as _GenericMeta  # python < 3.7
except ImportError:
    _GenericMeta = ()  # type: ignore

try:
    from typing import _GenericAlias  # type: ignore  # python >= 3.7
except ImportError:
    _GenericAlias = ()


def from_typing_type(thing):
    # We start with special-case support for Union and Tuple - the latter
    # isn't actually a generic type. Then we handle Literal since it doesn't
    # support `isinstance`.
    #
    # We then explicitly error on non-Generic types, which don't carry enough
    # information to sensibly resolve to strategies at runtime.
    # Finally, we run a variation of the subclass lookup in `st.from_type`
    # among generic types in the lookup.
    if getattr(thing, "__origin__", None) == tuple or isinstance(
        thing, getattr(typing, "TupleMeta", ())
    ):
        elem_types = getattr(thing, "__tuple_params__", None) or ()
        elem_types += getattr(thing, "__args__", None) or ()
        if (
            getattr(thing, "__tuple_use_ellipsis__", False)
            or len(elem_types) == 2
            and elem_types[-1] is Ellipsis
        ):
            return st.lists(icontract_from_type(elem_types[0])).map(tuple)
        elif len(elem_types) == 1 and elem_types[0] == ():
            return st.tuples()  # Empty tuple; see issue #1583
        return st.tuples(*map(icontract_from_type, elem_types))
    if hasattr(typing, "Final") and getattr(thing, "__origin__", None) == typing.Final:
        return st.one_of([icontract_from_type(t) for t in thing.__args__])
    if is_typing_literal(thing):
        args_dfs_stack = list(thing.__args__)
        literals = []
        while args_dfs_stack:
            arg = args_dfs_stack.pop()
            if is_typing_literal(arg):
                args_dfs_stack.extend(reversed(arg.__args__))
            else:
                literals.append(arg)
        return st.sampled_from(literals)
    # Now, confirm that we're dealing with a generic type as we expected
    if sys.version_info[:2] < (3, 9) and not isinstance(
        thing, typing_root_type
    ):  # pragma: no cover
        raise ResolutionFailed("Cannot resolve %s to a strategy" % (thing,))

    # Some "generic" classes are not generic *in* anything - for example both
    # Hashable and Sized have `__args__ == ()` on Python 3.7 or later.
    # (In 3.6 they're just aliases for the collections.abc classes)
    origin = getattr(thing, "__origin__", thing)
    if (
        typing.Hashable is not collections.abc.Hashable
        and origin in vars(collections.abc).values()
        and len(getattr(thing, "__args__", None) or []) == 0
    ):
        return icontract_from_type(origin)

    # Parametrised generic types have their __origin__ attribute set to the
    # un-parametrised version, which we need to use in the subclass checks.
    # e.g.:     typing.List[int].__origin__ == typing.List
    mapping = {
        k: v
        for k, v in _global_type_lookup.items()
        if is_generic_type(k) and try_issubclass(k, thing)
    }
    if typing.Dict in mapping or typing.Set in mapping:
        # ItemsView can cause test_lookup.py::test_specialised_collection_types
        # to fail, due to weird isinstance behaviour around the elements.
        mapping.pop(typing.ItemsView, None)
        if sys.version_info[:2] == (3, 6):  # pragma: no cover
            # `isinstance(dict().values(), Container) is False` on py36 only -_-
            mapping.pop(typing.ValuesView, None)
    if typing.Deque in mapping and len(mapping) > 1:
        # Resolving generic sequences to include a deque is more trouble for e.g.
        # the ghostwriter than it's worth, via undefined names in the repr.
        mapping.pop(typing.Deque)
    if len(mapping) > 1:
        # issubclass treats bytestring as a kind of sequence, which it is,
        # but treating it as such breaks everything else when it is presumed
        # to be a generic sequence or container that could hold any item.
        # Except for sequences of integers, or unions which include integer!
        # See https://github.com/HypothesisWorks/hypothesis/issues/2257
        #
        # This block drops ByteString from the types that can be generated
        # if there is more than one allowed type, and the element type is
        # not either `int` or a Union with `int` as one of its elements.
        elem_type = (getattr(thing, "__args__", None) or ["not int"])[0]
        if getattr(elem_type, "__origin__", None) is typing.Union:
            union_elems = elem_type.__args__
        else:
            union_elems = ()
        if not any(
            isinstance(T, type) and issubclass(int, T)
            for T in list(union_elems) + [elem_type]
        ):
            mapping.pop(typing.ByteString, None)
    strategies = [
        v if isinstance(v, st.SearchStrategy) else v(thing)
        for k, v in mapping.items()
        if sum(try_issubclass(k, T) for T in mapping) == 1
    ]
    empty = ", ".join(repr(s) for s in strategies if s.is_empty)
    if empty or not strategies:
        raise ResolutionFailed(
            "Could not resolve %s to a strategy; consider using "
            "register_type_strategy" % (empty or thing,)
        )
    return st.one_of(strategies)



@register(typing.List, st.builds(list))
def resolve_List(thing):
    return st.lists(icontract_from_type(thing.__args__[0]))

def _from_hashable_type(type_):
    if type_ in ALWAYS_HASHABLE_TYPES:
        return icontract_from_type(type_)
    else:
        return icontract_from_type(type_).filter(_can_hash)

@register(typing.Dict, st.builds(dict))
def resolve_Dict(thing):
    # If thing is a Collection instance, we need to fill in the values
    keys_vals = thing.__args__ * 2
    return st.dictionaries(
        _from_hashable_type(keys_vals[0]), icontract_from_type(keys_vals[1])
    )



@register(typing.ValuesView, st.builds(dict).map(dict.values))
def resolve_ValuesView(thing):
    return st.dictionaries(st.integers(), icontract_from_type(thing.__args__[0])).map(
        dict.values
    )


@register(typing.Iterator, st.iterables(st.nothing()))
def resolve_Iterator(thing):
    return st.iterables(icontract_from_type(thing.__args__[0]))


@register(typing.Counter, st.builds(collections.Counter))
def resolve_Counter(thing):
    return st.dictionaries(
        keys=icontract_from_type(thing.__args__[0]),
        values=st.integers(),
    ).map(collections.Counter)


@register(typing.Deque, st.builds(collections.deque))
def resolve_deque(thing):
    return st.lists(icontract_from_type(thing.__args__[0])).map(collections.deque)

@register(typing.Generator, GeneratorStrategy(st.none(), st.none()))
def resolve_Generator(thing):
    yields, _, returns = thing.__args__
    return GeneratorStrategy(icontract_from_type(yields), icontract_from_type(returns))


@register(typing.Callable, st.functions())
def resolve_Callable(thing):
    # Generated functions either accept no arguments, or arbitrary arguments.
    # This is looser than ideal, but anything tighter would generally break
    # use of keyword arguments and we'd rather not force positional-only.
    if not thing.__args__:  # pragma: no cover  # varies by minor version
        return st.functions()
    # Note that a list can only appear in __args__ under Python 3.9 with the
    # collections.abc version; see https://bugs.python.org/issue42195
    return st.functions(
        like=(lambda: None)
        if len(thing.__args__) == 1 or thing.__args__[0] == []
        else (lambda *a, **k: None),
        returns=icontract_from_type(thing.__args__[-1]),
    )


@register(typing.TypeVar)
def resolve_TypeVar(thing):
    type_var_key = "typevar=%r" % (thing,)

    if getattr(thing, "__bound__", None) is not None:
        bound = thing.__bound__
        if isinstance(bound, ForwardRef):
            bound = _try_import_forward_ref(thing, bound)
        strat = unwrap_strategies(icontract_from_type(bound))
        if not isinstance(strat, OneOfStrategy):
            return strat
        # The bound was a union, or we resolved it as a union of subtypes,
        # so we need to unpack the strategy to ensure consistency across uses.
        # This incantation runs a sampled_from over the strategies inferred for
        # each part of the union, wraps that in shared so that we only generate
        # from one type per testcase, and flatmaps that back to instances.
        return st.shared(
            st.sampled_from(strat.original_strategies), key=type_var_key
        ).flatmap(lambda s: s)

    builtin_scalar_types = [type(None), bool, int, float, str, bytes]
    return st.shared(
        st.sampled_from(
            # Constraints may be None or () on various Python versions.
            getattr(thing, "__constraints__", None)
            or builtin_scalar_types,
        ),
        key=type_var_key,
    ).flatmap(icontract_from_type)
