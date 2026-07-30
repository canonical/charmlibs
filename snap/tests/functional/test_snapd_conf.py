#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Functional tests for _snapd_conf: get, set, unset."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from charmlibs.snap import _client, _errors, _snapd_conf
from conftest import SNAPS_DIR, ensure_installed, ensure_removed, install_local

if TYPE_CHECKING:
    from collections.abc import Iterator

# A small Canonical-owned snap with a passthrough configure hook.
# Defined in https://github.com/canonical/snapd/tree/master/tests/lib/snaps
# Only published on latest/edge.
_SNAP = 'test-snapd-with-configure'
# A snap with no configure hook, so it can never hold configuration.
_NO_HOOK_SNAP = 'test-snapd-tools'
# A key prefix we use to avoid colliding with any other configuration on the snap.
_KEY = 'test-functional-key'
_KEY2 = 'test-functional-key2'

# A snap name that is never installed — used for error paths where any absent
# snap produces the same error response, avoiding unnecessary remove operations.
_ABSENT_SNAP = 'this-snap-does-not-exist-xyz-abc-123'


def _cleanup(*keys: str) -> None:
    """Unset test keys to avoid contaminating other tests."""
    _snapd_conf.unset(_SNAP, [_KEY, *keys])


# ---------------------------------------------------------------------------
# set and get roundtrip
# ---------------------------------------------------------------------------


def test_set_and_get_bool_true():
    ensure_installed(_SNAP, channel='latest/edge')
    _snapd_conf.set(_SNAP, {_KEY: True})
    assert _snapd_conf.get_one(_SNAP, _KEY) is True
    _cleanup()


def test_set_and_get_bool_false():
    ensure_installed(_SNAP, channel='latest/edge')
    _snapd_conf.set(_SNAP, {_KEY: False})
    assert _snapd_conf.get_one(_SNAP, _KEY) is False
    _cleanup()


def test_set_and_get_integer():
    ensure_installed(_SNAP, channel='latest/edge')
    _snapd_conf.set(_SNAP, {_KEY: 42})
    assert _snapd_conf.get_one(_SNAP, _KEY) == 42
    _cleanup()


def test_set_and_get_float():
    ensure_installed(_SNAP, channel='latest/edge')
    _snapd_conf.set(_SNAP, {_KEY: 3.14})
    assert _snapd_conf.get_one(_SNAP, _KEY) == 3.14
    _cleanup()


def test_set_and_get_string():
    ensure_installed(_SNAP, channel='latest/edge')
    _snapd_conf.set(_SNAP, {_KEY: 'hello'})
    assert _snapd_conf.get_one(_SNAP, _KEY) == 'hello'
    _cleanup()


def test_set_and_get_list():
    ensure_installed(_SNAP, channel='latest/edge')
    _snapd_conf.set(_SNAP, {_KEY: [1, 2, 3]})
    assert _snapd_conf.get_one(_SNAP, _KEY) == [1, 2, 3]
    _cleanup()


def test_set_and_get_dict():
    ensure_installed(_SNAP, channel='latest/edge')
    _snapd_conf.set(_SNAP, {_KEY: {'a': 1, 'b': 'two'}})
    assert _snapd_conf.get_one(_SNAP, _KEY) == {'a': 1, 'b': 'two'}
    # Dotted notation reads back a single nested value.
    assert _snapd_conf.get_one(_SNAP, f'{_KEY}.a') == 1
    _cleanup()


def test_set_null_unsets_key():
    # Setting a key to None (JSON null) unsets it at the top level.
    ensure_installed(_SNAP, channel='latest/edge')
    _snapd_conf.set(_SNAP, {_KEY: 'hello'})
    assert _snapd_conf.get(_SNAP, [_KEY]).get(_KEY) == 'hello'
    _snapd_conf.set(_SNAP, {_KEY: None})
    with pytest.raises(_errors.OptionNotFoundError):
        _snapd_conf.get(_SNAP, [_KEY])


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------


def test_get_all_keys():
    # get() with no keys returns all config as a dict. Nested values are returned in full:
    # the returned dict is keyed by top-level option, and each value keeps its full structure.
    ensure_installed(_SNAP, channel='latest/edge')
    _snapd_conf.set(_SNAP, {_KEY: 'value', _KEY2: {'nested': {'deep': 1}}})
    config = _snapd_conf.get(_SNAP)
    assert isinstance(config, dict)
    assert config.get(_KEY) == 'value'
    assert config.get(_KEY2) == {'nested': {'deep': 1}}
    _cleanup(_KEY2)


def test_get_mixed_dotted_and_non_dotted_keys():
    # Requesting an option and a dotted sub-key of it returns both as separate entries:
    # the plain key yields the full subtree, the dotted key yields the leaf, keyed by the
    # literal dotted string. The two do not merge or collide.
    ensure_installed(_SNAP, channel='latest/edge')
    _snapd_conf.set(_SNAP, {_KEY: {'nested': 'value'}})
    result = _snapd_conf.get(_SNAP, [_KEY, f'{_KEY}.nested'])
    assert result == {_KEY: {'nested': 'value'}, f'{_KEY}.nested': 'value'}
    _cleanup()


def test_get_specific_keys_returns_subset():
    ensure_installed(_SNAP, channel='latest/edge')
    _snapd_conf.set(_SNAP, {_KEY: 'alpha', _KEY2: 'beta'})
    subset = _snapd_conf.get(_SNAP, [_KEY])
    assert _KEY in subset
    assert _KEY2 not in subset
    _cleanup(_KEY2)


def test_get_multiple_specific_keys():
    ensure_installed(_SNAP, channel='latest/edge')
    _snapd_conf.set(_SNAP, {_KEY: 'alpha', _KEY2: 'beta'})
    result = _snapd_conf.get(_SNAP, [_KEY, _KEY2])
    assert result[_KEY] == 'alpha'
    assert result[_KEY2] == 'beta'
    _cleanup(_KEY2)


def test_get_option_not_found_raises():
    ensure_installed(_SNAP, channel='latest/edge')
    with pytest.raises(_errors.OptionNotFoundError) as ctx:
        _snapd_conf.get(_SNAP, ['key-that-should-not-exist'])
    assert ctx.value.kind == 'option-not-found'
    assert ctx.value.message


def test_get_option_not_found_value_contains_snap_and_key():
    ensure_installed(_SNAP, channel='latest/edge')
    with pytest.raises(_errors.OptionNotFoundError) as ctx:
        _snapd_conf.get(_SNAP, ['key-that-should-not-exist'])
    value = str(ctx.value.value)
    assert 'SnapName' in value
    assert 'Key' in value
    assert _SNAP in value
    assert 'key-that-should-not-exist' in value


def test_get_not_installed_snap_raises_not_found():
    # Config GET for a non-installed snap returns option-not-found (not snap-not-found), so
    # get() probes /v2/snaps/{snap} and raises _NotFoundError, consistent with set and unset.
    with pytest.raises(_errors.NotInstalledError) as ctx:
        _snapd_conf.get(_ABSENT_SNAP, ['any-key'])
    assert ctx.value.kind == 'snap-not-found'
    # get() raises snapd's own /v2/snaps/{snap} probe error unchanged: a terse message with the
    # snap name in value, which str() surfaces as 'snap not installed (<snap>)'. This reads
    # differently from set/unset (whose PUT error names the snap in the message) -- we pass each
    # endpoint's wording through rather than hand-building an error to normalise them.
    assert ctx.value.message == 'snap not installed'
    assert str(ctx.value.value) == _ABSENT_SNAP
    assert str(ctx.value) == f'snap not installed ({_ABSENT_SNAP})'


def test_get_not_installed_snap_error_is_not_chained():
    # snapd's misleading option-not-found error is suppressed ('raise ... from None'), so the
    # traceback is a single error and doesn't expose the internal /v2/snaps/{snap} probe.
    with pytest.raises(_errors.NotInstalledError) as ctx:
        _snapd_conf.get(_ABSENT_SNAP, ['any-key'])
    assert ctx.value.__cause__ is None
    assert ctx.value.__suppress_context__


def test_get_all_not_installed_snap_raises_not_found():
    # Config GET with no keys for a non-installed snap is a 200 with an empty result,
    # indistinguishable from an installed snap with no configuration, so get() probes
    # /v2/snaps/{snap} and raises _NotFoundError instead of returning {}.
    with pytest.raises(_errors.NotInstalledError) as ctx:
        _snapd_conf.get(_ABSENT_SNAP)
    assert ctx.value.kind == 'snap-not-found'
    assert ctx.value.message == 'snap not installed'
    assert str(ctx.value) == f'snap not installed ({_ABSENT_SNAP})'
    # No error was being handled when this was raised, so there's nothing to chain.
    assert ctx.value.__context__ is None


def test_raw_get_all_not_installed_snap_returns_empty_dict():
    # Pin the raw snapd behaviour that get()'s empty-config probe relies on: a bare conf GET (no
    # keys) for a non-installed snap is a 200 with an empty result, NOT an error. This is what
    # makes an absent snap indistinguishable from an installed snap with no configuration, and
    # hence why get() must probe. Asserted at the _client level because get() converts it to
    # _NotFoundError; if snapd ever reported the absent snap directly here, this fails loudly
    # rather than leaving get()'s probe branch as untested dead code.
    assert _client.get(f'/v2/snaps/{_ABSENT_SNAP}/conf') == {}


def test_get_all_installed_snap_with_no_config_returns_empty_dict():
    # The snap has no configure hook, so it can never have configuration. Unlike the CLI
    # (`snap get <snap>` errors with 'has no configuration'), get() returns an empty dict.
    ensure_installed(_NO_HOOK_SNAP)
    assert _snapd_conf.get(_NO_HOOK_SNAP) == {}


# ---------------------------------------------------------------------------
# get_one
#
# The single-value counterpart of get, used throughout this file to read back what was set.
# It is get(snap, [key])[key], so it inherits every error get raises; the tests below pin that
# it unwraps the value rather than changing which request is made or what fails.
# ---------------------------------------------------------------------------


def test_get_one_returns_the_value_not_a_dict():
    ensure_installed(_SNAP, channel='latest/edge')
    _snapd_conf.set(_SNAP, {_KEY: 'value'})
    assert _snapd_conf.get_one(_SNAP, _KEY) == 'value'
    assert _snapd_conf.get(_SNAP, [_KEY]) == {_KEY: 'value'}
    _cleanup()


def test_get_one_returns_a_subtree_for_a_key_that_names_one():
    # A key naming a subtree yields the whole nested dict -- get_one unwraps get's result by
    # one level, it doesn't flatten the value.
    ensure_installed(_SNAP, channel='latest/edge')
    _snapd_conf.set(_SNAP, {_KEY: {'nested': {'deep': 1}}})
    assert _snapd_conf.get_one(_SNAP, _KEY) == {'nested': {'deep': 1}}
    _cleanup()


def test_get_one_dotted_key_returns_the_leaf():
    ensure_installed(_SNAP, channel='latest/edge')
    _snapd_conf.set(_SNAP, {_KEY: {'nested': 'value'}})
    assert _snapd_conf.get_one(_SNAP, f'{_KEY}.nested') == 'value'
    _cleanup()


def test_get_one_missing_key_raises_option_not_found():
    # Never a KeyError: get raises before there is a dict to subscript.
    ensure_installed(_SNAP, channel='latest/edge')
    with pytest.raises(_errors.OptionNotFoundError) as ctx:
        _snapd_conf.get_one(_SNAP, 'key-that-should-not-exist')
    assert ctx.value.kind == 'option-not-found'


def test_get_one_not_installed_snap_raises_not_found():
    with pytest.raises(_errors.NotInstalledError) as ctx:
        _snapd_conf.get_one(_ABSENT_SNAP, 'any-key')
    assert ctx.value.kind == 'snap-not-found'
    assert ctx.value.message == 'snap not installed'


@pytest.mark.parametrize('key', ['', ' ', '\t', ',', 'a,b', ' a', 'a\n'])
def test_get_one_rejects_keys_that_snapd_would_alter(key: str):
    # The same client-side rejection get applies: a key snapd's 'keys' parsing would alter or
    # drop is a ValueError rather than a request, which is also what makes the subscript safe.
    with pytest.raises(ValueError):
        _snapd_conf.get_one(_SNAP, key)


@pytest.mark.parametrize('snap', ['', '.', '..', 'lxd/conf'])
def test_get_one_invalid_snap_name_raises_value_error(snap: str):
    with pytest.raises(ValueError):
        _snapd_conf.get_one(snap, _KEY)


# ---------------------------------------------------------------------------
# get and unset: a bare string is one key
#
# A string is iterable, so a bare key would otherwise be split into single-character keys -- a
# request for 'p', 'o', 'r', 't' rather than 'port'. Taking it as one key is what every caller
# means by it, and is why the type checker accepting it (str is an Iterable[str]) is no longer a
# trap. The result is still a dict, so reading one value is get_one(snap, key).
# ---------------------------------------------------------------------------


def test_get_bare_string_is_one_key():
    ensure_installed(_SNAP, channel='latest/edge')
    _snapd_conf.set(_SNAP, {_KEY: 'value'})
    assert _snapd_conf.get(_SNAP, _KEY) == {_KEY: 'value'}
    assert _snapd_conf.get(_SNAP, _KEY) == _snapd_conf.get(_SNAP, [_KEY])
    _cleanup()


def test_get_bare_string_dotted_key():
    ensure_installed(_SNAP, channel='latest/edge')
    _snapd_conf.set(_SNAP, {_KEY: {'nested': 'value'}})
    assert _snapd_conf.get(_SNAP, f'{_KEY}.nested') == {f'{_KEY}.nested': 'value'}
    _cleanup()


def test_get_bare_string_is_validated_like_a_key_in_a_list():
    # A comma in a single key would still become two keys once joined into the query parameter.
    with pytest.raises(ValueError, match='must not contain a comma'):
        _snapd_conf.get(_SNAP, f'{_KEY},{_KEY2}')


def test_unset_bare_string_is_one_key():
    ensure_installed(_SNAP, channel='latest/edge')
    _snapd_conf.set(_SNAP, {_KEY: 'value'})
    _snapd_conf.unset(_SNAP, _KEY)
    with pytest.raises(_errors.OptionNotFoundError):
        _snapd_conf.get(_SNAP, _KEY)


# ---------------------------------------------------------------------------
# get: keys=[] ("give me nothing") vs keys=None ("give me everything")
# ---------------------------------------------------------------------------


def test_get_empty_keys_returns_empty_dict():
    # keys=[] is a deliberate "no keys requested" query, distinct from the CLI-following
    # default of keys=None ("give me everything"). It never reaches the conf endpoint, but
    # still confirms the snap is installed before returning {}.
    ensure_installed(_SNAP, channel='latest/edge')
    _snapd_conf.set(_SNAP, {_KEY: 'value'})
    assert _snapd_conf.get(_SNAP, []) == {}
    _cleanup()


def test_get_empty_keys_not_installed_snap_raises_not_found():
    with pytest.raises(_errors.NotInstalledError) as ctx:
        _snapd_conf.get(_ABSENT_SNAP, [])
    assert ctx.value.kind == 'snap-not-found'
    assert ctx.value.message == 'snap not installed'
    assert str(ctx.value) == f'snap not installed ({_ABSENT_SNAP})'


@pytest.mark.parametrize('keys', [[''], ['', ''], [' '], ['\t'], [','], ['a,b'], [' a'], ['a\n']])
def test_get_keys_that_snapd_would_alter_raise_value_error(keys: list[str]):
    # The public contract: a key that snapd's 'keys' parsing would alter is a ValueError rather
    # than a request. The tests below pin what that parsing does, and so what these would mean.
    with pytest.raises(ValueError):
        _snapd_conf.get(_SNAP, keys)


@pytest.mark.parametrize('keys', ['', ',', ' ', '\t', '\xa0', ' , '])
def test_raw_get_keys_that_parse_away_returns_the_full_config(keys: str):
    # Undocumented snapd quirk, and the reason get() rejects these rather than passing them
    # through: keys=[''] and keys=[' '] are NOT the same as our own keys=[] contract above.
    # keys=[] is caught by our own `keys == []` check before any network call is made, but a
    # list whose keys all parse away doesn't match that check, so it used to fall through to
    # being joined into the 'keys' query parameter. snapd's parsing of that treats it the same
    # as no 'keys' param at all, so the full config comes back -- keys=None, not keys=[].
    ensure_installed(_SNAP, channel='latest/edge')
    _snapd_conf.set(_SNAP, {_KEY: 'value'})
    full_config = _snapd_conf.get(_SNAP)
    assert full_config != {}
    assert _client.get(f'/v2/snaps/{_SNAP}/conf', query={'keys': keys}) == full_config
    _cleanup()


def test_raw_get_keys_that_parse_away_hide_a_not_installed_snap():
    # The same quirk on a snap that isn't installed, which is what made this a bug rather than a
    # surprise: snapd answers a request for the whole configuration with an empty result whether
    # or not the snap exists, and get()'s not-installed probe only runs for keys=None. A key that
    # parsed away therefore turned a _NotFoundError into an empty dict. Rejecting the key makes
    # the request unmakeable; this pins the snapd behaviour that made it wrong.
    assert _client.get(f'/v2/snaps/{_ABSENT_SNAP}/conf', query={'keys': ''}) == {}
    with pytest.raises(ValueError):
        _snapd_conf.get(_ABSENT_SNAP, [''])


def test_raw_get_padded_key_returns_the_stripped_key():
    # Whitespace is stripped from each key, so a padded key addresses the key it names once
    # stripped, and the result is keyed by the stripped name -- meaning result[' key '] would
    # raise KeyError on a request that appeared to succeed.
    ensure_installed(_SNAP, channel='latest/edge')
    _snapd_conf.set(_SNAP, {_KEY: 'value'})
    assert _client.get(f'/v2/snaps/{_SNAP}/conf', query={'keys': f' {_KEY} '}) == {_KEY: 'value'}
    _cleanup()


def test_raw_get_comma_in_a_key_queries_two_keys():
    # A comma inside one key is not escaped by url-encoding it: snapd decodes the parameter
    # before splitting, so one key becomes two. This is why a comma is rejected.
    ensure_installed(_SNAP, channel='latest/edge')
    _snapd_conf.set(_SNAP, {_KEY: 'value', _KEY2: 'value2'})
    result = _client.get(f'/v2/snaps/{_SNAP}/conf', query={'keys': f'{_KEY},{_KEY2}'})
    assert result == {_KEY: 'value', _KEY2: 'value2'}
    _cleanup(_KEY2)


# ---------------------------------------------------------------------------
# unset
# ---------------------------------------------------------------------------


def test_unset_key():
    ensure_installed(_SNAP, channel='latest/edge')
    _snapd_conf.set(_SNAP, {_KEY: 'hello'})
    assert _snapd_conf.get(_SNAP, [_KEY]).get(_KEY) == 'hello'
    _snapd_conf.unset(_SNAP, [_KEY])
    with pytest.raises(_errors.OptionNotFoundError):
        _snapd_conf.get(_SNAP, [_KEY])


def test_unset_nonexistent_key_no_error():
    # Unsetting a key that doesn't exist should not raise.
    ensure_installed(_SNAP, channel='latest/edge')
    _snapd_conf.unset(_SNAP, ['key-that-does-not-exist'])


def test_unset_nonexistent_key_deeply_dotted_no_error():
    # Unsetting a dotted-path key that doesn't exist should not raise.
    ensure_installed(_SNAP, channel='latest/edge')
    _snapd_conf.unset(_SNAP, ['key-that-does-not-exist.nested.deep'])


def test_unset_multiple_keys():
    ensure_installed(_SNAP, channel='latest/edge')
    _snapd_conf.set(_SNAP, {_KEY: 'val1', _KEY2: 'val2'})
    _snapd_conf.unset(_SNAP, [_KEY, _KEY2])
    with pytest.raises(_errors.OptionNotFoundError):
        _snapd_conf.get(_SNAP, [_KEY])
    with pytest.raises(_errors.OptionNotFoundError):
        _snapd_conf.get(_SNAP, [_KEY2])


def test_unset_empty_keys_is_noop():
    ensure_installed(_SNAP, channel='latest/edge')
    _snapd_conf.set(_SNAP, {_KEY: 'value'})
    _snapd_conf.unset(_SNAP, [])  # Should not raise, and should not touch existing config.
    assert _snapd_conf.get_one(_SNAP, _KEY) == 'value'
    _cleanup()


# ---------------------------------------------------------------------------
# not-installed snap (uses a never-installed name to avoid churn)
# ---------------------------------------------------------------------------


# An empty body is checked alongside a non-empty one: snapd validates that the snap is
# installed regardless of the patch contents, so both raise the same error.
@pytest.mark.parametrize('config', [{'test-key': 'value'}, {}])
def test_set_not_installed_snap_raises_snap_not_found(config: dict[str, Any]):
    with pytest.raises(_errors.NotInstalledError) as ctx:
        _snapd_conf.set(_ABSENT_SNAP, config)
    assert ctx.value.kind == 'snap-not-found'
    # set/unset surface snapd's PUT error directly, which names the snap in the message. get()
    # differs -- it raises the terse /v2/snaps probe error (name in value) -- because snapd words
    # its two endpoints differently and we pass each through rather than normalising them.
    assert ctx.value.message == f'snap "{_ABSENT_SNAP}" is not installed'


def test_unset_not_installed_snap_raises_snap_not_found():
    with pytest.raises(_errors.NotInstalledError) as ctx:
        _snapd_conf.unset(_ABSENT_SNAP, ['test-key'])
    assert ctx.value.kind == 'snap-not-found'
    assert ctx.value.message == f'snap "{_ABSENT_SNAP}" is not installed'


# ---------------------------------------------------------------------------
# set
# ---------------------------------------------------------------------------


def test_set_multiple_keys_at_once():
    ensure_installed(_SNAP, channel='latest/edge')
    values: dict[str, Any] = {_KEY: 'v1', _KEY2: 'v2'}
    _snapd_conf.set(_SNAP, values)
    result = _snapd_conf.get(_SNAP, [_KEY, _KEY2])
    assert result[_KEY] == 'v1'
    assert result[_KEY2] == 'v2'
    _cleanup(_KEY2)


def test_set_empty_dict_is_noop():
    # set(snap, {}) is a no-op — the API accepts an empty body without error, and existing
    # configuration is left untouched (an empty body does NOT unset all keys).
    ensure_installed(_SNAP, channel='latest/edge')
    _snapd_conf.set(_SNAP, {_KEY: 'before-empty-set'})
    _snapd_conf.set(_SNAP, {})
    assert _snapd_conf.get_one(_SNAP, _KEY) == 'before-empty-set'
    _cleanup()


# ---------------------------------------------------------------------------
# set and unset: keys snapd cannot use
#
# These go in a JSON body rather than the 'keys' query parameter, so nothing alters them in
# transit and snapd reports an unusable key itself. It only does so once the configure hook
# runs, though, and calls an empty key an 'internal error', so set() and unset() reject empty
# and blank keys up front. These tests go through _client to pin what snapd would have said.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('key', ['', ' ', '\t'])
@pytest.mark.parametrize('func', [_snapd_conf.set, _snapd_conf.unset], ids=['set', 'unset'])
def test_set_and_unset_reject_empty_and_blank_keys(func: Any, key: str):
    ensure_installed(_SNAP, channel='latest/edge')
    with pytest.raises(ValueError):
        func(_SNAP, {key: 'value'} if func is _snapd_conf.set else [key])


@pytest.mark.parametrize(
    ('key', 'expected'),
    [
        ('', 'internal error: key cannot be an empty string'),
        (' ', 'invalid option name: " "'),
        ('\t', 'invalid option name: "\\t"'),
        (' padded ', 'invalid option name: " padded "'),
        ('a,b', 'invalid option name: "a,b"'),
    ],
)
def test_raw_put_unusable_key_fails_the_change(key: str, expected: str):
    # snapd names the offending key verbatim, without stripping it, and fails the whole change.
    # The empty key is the odd one out: it's reported as an internal error rather than as an
    # invalid option name, which is the message a caller would otherwise have had to read.
    ensure_installed(_SNAP, channel='latest/edge')
    with pytest.raises(_errors.ChangeError) as ctx:
        _client.put(f'/v2/snaps/{_SNAP}/conf', body={key: 'value'})
    assert expected in ctx.value.message


# A key with an empty dotted segment is neither empty nor blank, so it isn't guarded client-side
# and reaches snapd -- which splits it on dots and blames the empty segment, naming a value the
# caller never passed. These go through the public API rather than _client, since that is how a
# caller reaches them.


@pytest.mark.parametrize('key', ['a.', '.a', 'a..b', '.'])
def test_get_key_with_an_empty_dotted_segment_raises(key: str):
    # On the read side this is at least immediate: a synchronous APIError, no change, no hook.
    ensure_installed(_SNAP, channel='latest/edge')
    with pytest.raises(_errors.APIError) as ctx:
        _snapd_conf.get(_SNAP, [key])
    assert not ctx.value.kind
    assert ctx.value.message == 'invalid option name: ""'


@pytest.mark.parametrize('key', ['a.', '.a', 'a..b', '.'])
def test_set_key_with_an_empty_dotted_segment_fails_the_change(key: str):
    # On the write side it costs a round trip and a configure hook run before failing.
    ensure_installed(_SNAP, channel='latest/edge')
    with pytest.raises(_errors.ChangeError) as ctx:
        _snapd_conf.set(_SNAP, {key: 'value'})
    assert 'invalid option name: ""' in ctx.value.message


def test_raw_put_unusable_key_rolls_back_the_valid_keys():
    # The change is all-or-nothing, so a valid key sent alongside an unusable one is not applied.
    ensure_installed(_SNAP, channel='latest/edge')
    _snapd_conf.set(_SNAP, {_KEY: 'before'})
    with pytest.raises(_errors.ChangeError):
        _client.put(f'/v2/snaps/{_SNAP}/conf', body={'': 'value', _KEY: 'after'})
    assert _snapd_conf.get_one(_SNAP, _KEY) == 'before'
    _cleanup()


def test_get_mixed_keys_raises_option_not_found():
    # When some requested keys exist and some don't, the API raises option-not-found
    # for the first missing key rather than returning partial results.
    ensure_installed(_SNAP, channel='latest/edge')
    _snapd_conf.set(_SNAP, {_KEY: 'exists'})
    with pytest.raises(_errors.OptionNotFoundError) as ctx:
        _snapd_conf.get(_SNAP, [_KEY, 'key-that-does-not-exist-xyz'])
    assert ctx.value.kind == 'option-not-found'
    _cleanup()


def test_unset_dotted_path_no_error():
    # unset() accepts dotted-path keys and the API handles them without error.
    ensure_installed(_SNAP, channel='latest/edge')
    _snapd_conf.set(_SNAP, {_KEY: {'nested': 'value'}})
    _snapd_conf.unset(_SNAP, [f'{_KEY}.nested'])  # Should not raise.
    _cleanup()


# ---------------------------------------------------------------------------
# configure hook failure -> ChangeError
# ---------------------------------------------------------------------------


def test_set_no_configure_hook_raises_change_error():
    # set/unset run the snap's configure hook as an async change. This snap has no
    # configure hook, so snapd fails the change and we surface it as a ChangeError.
    ensure_installed(_NO_HOOK_SNAP)
    with pytest.raises(_errors.ChangeError):
        _snapd_conf.set(_NO_HOOK_SNAP, {'any-key': 'value'})


def test_unset_no_configure_hook_raises_change_error():
    ensure_installed(_NO_HOOK_SNAP)
    with pytest.raises(_errors.ChangeError):
        _snapd_conf.unset(_NO_HOOK_SNAP, ['any-key'])


def test_set_empty_dict_no_configure_hook_is_noop():
    # An empty patch is the exception to the rule above: snapd marks the configure hook optional
    # when there is nothing to set (Optional: len(patch) == 0), so a missing hook is not an
    # error and the change completes as a no-op. Contrast test_set_no_configure_hook_*, where a
    # non-empty patch on the same hook-less snap does raise.
    ensure_installed(_NO_HOOK_SNAP)
    _snapd_conf.set(_NO_HOOK_SNAP, {})  # Should not raise.


# ---------------------------------------------------------------------------
# configure hook validation -> ChangeError
# ---------------------------------------------------------------------------
# A snap's configure hook can validate incoming configuration (read via snapctl get) and
# reject it by exiting non-zero. test-configure-snap (tests/functional/snaps) rejects any
# value for 'bad-key' and accepts everything else.


@pytest.fixture(scope='module')
def configure_snap() -> Iterator[None]:
    install_local(SNAPS_DIR / 'test-configure-snap_1.0.snap', dangerous=True)
    yield
    ensure_removed('test-configure-snap')


def test_set_rejected_by_configure_hook_raises_change_error(configure_snap: None):
    with pytest.raises(_errors.ChangeError) as ctx:
        _snapd_conf.set('test-configure-snap', {'bad-key': 'x'})
    # The hook's stderr is embedded in the change error message.
    assert 'bad-key is not allowed' in ctx.value.message
    # The rejected change is rolled back: nothing was stored.
    with pytest.raises(_errors.OptionNotFoundError):
        _snapd_conf.get('test-configure-snap', ['bad-key'])


def test_set_accepted_by_configure_hook(configure_snap: None):
    _snapd_conf.set('test-configure-snap', {'good-key': 'hello'})
    assert _snapd_conf.get('test-configure-snap', ['good-key']) == {'good-key': 'hello'}
    _snapd_conf.unset('test-configure-snap', ['good-key'])


def test_rejected_set_rolls_back_entire_transaction(configure_snap: None):
    # Configuration changes are transactional: if the hook rejects any key, no key in the
    # request is applied, and previously stored values are preserved.
    _snapd_conf.set('test-configure-snap', {'good-key': 'before'})
    with pytest.raises(_errors.ChangeError):
        _snapd_conf.set('test-configure-snap', {'good-key': 'after', 'bad-key': 'x'})
    assert _snapd_conf.get('test-configure-snap', ['good-key']) == {'good-key': 'before'}
    _snapd_conf.unset('test-configure-snap', ['good-key'])


# ---------------------------------------------------------------------------
# empty and non-canonical snap names -> ValueError
# ---------------------------------------------------------------------------
# These names are rejected before a request is made. Without that, an empty name builds
# '/v2/snaps//conf', which snapd answers with an empty-bodied 301 to '/v2/snaps/conf' -- a
# BadResponseError about invalid JSON, indistinguishable from a transport fault. A name with a
# path separator is worse: snapd's router decodes '%2F' before matching, so get('<snap>/conf')
# would have read '/v2/snaps/<snap>/conf' -- another snap's configuration. See
# tests/functional/test_client for both behaviours against the raw client.


@pytest.mark.parametrize('snap', ['', '.', '..', 'test-configure-snap/conf'])
def test_conf_invalid_snap_name_raises_value_error(snap: str):
    with pytest.raises(ValueError):
        _snapd_conf.get(snap)
    with pytest.raises(ValueError):
        _snapd_conf.get(snap, [_KEY])
    with pytest.raises(ValueError):
        _snapd_conf.get(snap, _KEY)  # A bare string key.
    with pytest.raises(ValueError):
        _snapd_conf.get(snap, [])  # The installed-snap probe path.
    with pytest.raises(ValueError):
        _snapd_conf.set(snap, {_KEY: 'x'})
    with pytest.raises(ValueError):
        _snapd_conf.unset(snap, [_KEY])
    with pytest.raises(ValueError):
        _snapd_conf.unset(snap, _KEY)  # A bare string key.
