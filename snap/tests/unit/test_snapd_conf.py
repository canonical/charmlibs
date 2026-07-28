# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

# pyright: reportPrivateUsage=false

from __future__ import annotations

import traceback
from typing import TYPE_CHECKING, Any

import pytest

from charmlibs.snap import _snapd_conf
from charmlibs.snap._errors import ChangeError, NotFoundError, OptionNotFoundError
from conftest import result_of

if TYPE_CHECKING:
    from conftest import MockClient


class TestGet:
    def test_get_all(self, mock_client: MockClient):
        mock_client.get.return_value = result_of('conf_lxd_all.json')
        _snapd_conf.get('lxd')
        mock_client.get.assert_called_once_with('/v2/snaps/lxd/conf', query=None)

    def test_get_all_explicit_keys_none(self, mock_client: MockClient):
        mock_client.get.return_value = result_of('conf_lxd_all.json')
        _snapd_conf.get('lxd', keys=None)
        mock_client.get.assert_called_once_with('/v2/snaps/lxd/conf', query=None)

    def test_get_specific_key(self, mock_client: MockClient):
        mock_client.get.return_value = result_of('conf_lxd_single_key.json')
        _snapd_conf.get('lxd', ['integer'])
        mock_client.get.assert_called_once_with('/v2/snaps/lxd/conf', query={'keys': 'integer'})

    def test_get_multiple_keys(self, mock_client: MockClient):
        mock_client.get.return_value = {'a': 1, 'b': 2}
        _snapd_conf.get('lxd', ['a', 'b'])
        query = mock_client.get.call_args.kwargs['query']
        assert query == {'keys': 'a,b'}

    def test_get_accepts_arbitrary_iterable(self, mock_client: MockClient):
        # keys need not be a list -- any non-string iterable of strings works.
        mock_client.get.return_value = {'a': 1, 'b': 2}
        _snapd_conf.get('lxd', (k for k in ('a', 'b')))
        query = mock_client.get.call_args.kwargs['query']
        assert query == {'keys': 'a,b'}

    # Keys that snapd's comma-separated list parser would alter are rejected before the request.
    # A key that parses away to nothing is the dangerous one: it doesn't match our own keys=[]
    # short-circuit (`keys == []`), so it used to reach snapd as an empty 'keys' value, which
    # snapd reads as "no keys given" and answers with the whole configuration -- and, for a snap
    # that isn't installed, with an empty result that get() returned instead of raising
    # NotFoundError. See the functional tests for the snapd behaviour behind each case.
    @pytest.mark.parametrize(
        ('keys', 'match'),
        [
            ([''], 'must not be empty'),
            (['', ''], 'must not be empty'),
            (['a', ''], 'must not be empty'),
            ([' '], 'must not be blank'),
            (['\t'], 'must not be blank'),
            (['a', ' '], 'must not be blank'),
            ([','], 'must not contain a comma'),
            (['a,b'], 'must not contain a comma'),
            ([' a'], 'must not have leading or trailing whitespace'),
            (['a '], 'must not have leading or trailing whitespace'),
            (['\ta\n'], 'must not have leading or trailing whitespace'),
        ],
    )
    def test_get_unsafe_keys_raise_value_error_without_request(
        self, mock_client: MockClient, keys: list[str], match: str
    ):
        with pytest.raises(ValueError, match=match):
            _snapd_conf.get('lxd', keys)
        mock_client.get.assert_not_called()

    @pytest.mark.parametrize('key', ['a', 'a.b', 'a-b', 'a b', 'a\u200bb', 'A_B', '1'])
    def test_get_keys_that_survive_the_parser_are_sent(self, mock_client: MockClient, key: str):
        # Only what snapd's parser would alter is rejected -- interior whitespace and zero-width
        # characters survive it unchanged, so they're snapd's to reject, not ours.
        mock_client.get.return_value = {key: 1}
        _snapd_conf.get('lxd', [key])
        mock_client.get.assert_called_once_with('/v2/snaps/lxd/conf', query={'keys': key})

    def test_get_returns_dict(self, mock_client: MockClient):
        mock_client.get.return_value = result_of('conf_lxd_all.json')
        result = _snapd_conf.get('lxd')
        assert isinstance(result, dict)
        assert 'criu' in result

    def test_get_string_keys_raises_typeerror(self, mock_client: MockClient):
        # A bare string is iterable, so it's rejected explicitly rather than being
        # silently split into single-character keys.
        with pytest.raises(TypeError):
            _snapd_conf.get('lxd', 'integer')
        mock_client.get.assert_not_called()


class TestGetEmptyKeys:
    def test_get_empty_keys_returns_empty_dict(self, mock_client: MockClient):
        mock_client.get.return_value = result_of('snap_info_hello_world.json')
        assert _snapd_conf.get('hello-world', []) == {}

    def test_get_empty_keys_probes_installed_snap_not_conf_endpoint(self, mock_client: MockClient):
        mock_client.get.return_value = result_of('snap_info_hello_world.json')
        _snapd_conf.get('hello-world', [])
        mock_client.get.assert_called_once_with('/v2/snaps/hello-world')

    def test_get_empty_keys_not_installed_raises_not_found(self, mock_client: MockClient):
        mock_client.get.side_effect = NotFoundError(
            'snap not installed', kind='snap-not-found', value='hello-world'
        )
        with pytest.raises(NotFoundError) as ctx:
            _snapd_conf.get('hello-world', [])
        # snapd's own probe error is raised unchanged: terse message, snap name in value (which
        # str() surfaces). Not chained -- the probe's error was handled, not propagated.
        assert ctx.value.message == 'snap not installed'
        assert ctx.value.value == 'hello-world'
        assert str(ctx.value) == 'snap not installed (hello-world)'
        assert ctx.value.__context__ is None

    def test_get_empty_keys_system_not_probed(self, mock_client: MockClient):
        # system/core skip the installed-snap probe entirely, so no network call is made.
        assert _snapd_conf.get('system', []) == {}
        mock_client.get.assert_not_called()


class TestGetAbsentSnapProbe:
    # The conf GET endpoint alone can't distinguish an absent snap from a missing key (or from
    # empty configuration), so get() probes /v2/snaps/{snap} on those paths to raise
    # NotFoundError, consistent with set and unset. See the functional tests for captured
    # responses.
    # Built fresh per call, not shared: raising an exception mutates its __context__, and the
    # probe now re-raises snapd's own error object, so a shared instance would leak chaining
    # state between tests (in production each probe gets a freshly parsed exception).
    @staticmethod
    def _option_not_found() -> OptionNotFoundError:
        return OptionNotFoundError(
            'snap "hello-world" has no "mykey" configuration option',
            kind='option-not-found',
            # snapd sends this value as a JSON object, not a string (see the conf fixture).
            value={'SnapName': 'hello-world', 'Key': 'mykey'},
        )

    @staticmethod
    def _snap_not_found() -> NotFoundError:
        return NotFoundError('snap not installed', kind='snap-not-found', value='hello-world')

    def test_missing_key_on_installed_snap_reraises_option_not_found(
        self, mock_client: MockClient
    ):
        mock_client.get.side_effect = [
            self._option_not_found(),
            result_of('snap_info_hello_world.json'),
        ]
        with pytest.raises(OptionNotFoundError):
            _snapd_conf.get('hello-world', ['mykey'])
        probe_call = mock_client.get.call_args_list[1]
        assert probe_call.args[0] == '/v2/snaps/hello-world'

    def test_missing_key_on_absent_snap_raises_not_found(self, mock_client: MockClient):
        mock_client.get.side_effect = [self._option_not_found(), self._snap_not_found()]
        with pytest.raises(NotFoundError) as ctx:
            _snapd_conf.get('hello-world', ['mykey'])
        assert ctx.value.message == 'snap not installed'
        assert ctx.value.value == 'hello-world'
        assert str(ctx.value) == 'snap not installed (hello-world)'

    def test_missing_key_on_absent_snap_does_not_chain_option_not_found(
        self, mock_client: MockClient
    ):
        # The misleading option-not-found error snapd sent for the absent snap is suppressed
        # ('raise ... from None'), so the user sees a single traceback.
        mock_client.get.side_effect = [self._option_not_found(), self._snap_not_found()]
        with pytest.raises(NotFoundError) as ctx:
            _snapd_conf.get('hello-world', ['mykey'])
        assert ctx.value.__cause__ is None
        assert ctx.value.__suppress_context__

    def test_missing_key_on_absent_snap_traceback_excludes_probe(self, mock_client: MockClient):
        # check_installed clears the probe's traceback, so the re-raised error starts at get()'s
        # own raise and never walks back through the internal /v2/snaps/{snap} probe GET.
        mock_client.get.side_effect = [self._option_not_found(), self._snap_not_found()]
        with pytest.raises(NotFoundError) as ctx:
            _snapd_conf.get('hello-world', ['mykey'])
        files = [frame.filename for frame in traceback.extract_tb(ctx.value.__traceback__)]
        assert not any(f.endswith('_utils.py') for f in files)

    def test_get_all_empty_on_absent_snap_raises_not_found(self, mock_client: MockClient):
        # A bare conf GET on an absent snap is a 200 with an empty result, so the probe is
        # what turns it into an error.
        mock_client.get.side_effect = [{}, self._snap_not_found()]
        with pytest.raises(NotFoundError) as ctx:
            _snapd_conf.get('hello-world')
        assert ctx.value.message == 'snap not installed'
        assert str(ctx.value) == 'snap not installed (hello-world)'
        assert ctx.value.__context__ is None

    def test_get_all_empty_on_installed_snap_returns_empty_dict(self, mock_client: MockClient):
        mock_client.get.side_effect = [{}, result_of('snap_info_hello_world.json')]
        assert _snapd_conf.get('hello-world') == {}

    def test_get_all_nonempty_is_not_probed(self, mock_client: MockClient):
        mock_client.get.return_value = result_of('conf_lxd_all.json')
        _snapd_conf.get('lxd')
        mock_client.get.assert_called_once()

    def test_missing_key_on_system_is_not_probed(self, mock_client: MockClient):
        # /v2/snaps/system always 404s while its conf is served, so system names skip the probe.
        mock_client.get.side_effect = self._option_not_found()
        with pytest.raises(OptionNotFoundError):
            _snapd_conf.get('system', ['mykey'])
        mock_client.get.assert_called_once()

    def test_get_all_empty_on_core_is_not_probed(self, mock_client: MockClient):
        mock_client.get.return_value = {}
        assert _snapd_conf.get('core') == {}
        mock_client.get.assert_called_once()


class TestSet:
    def test_set(self, mock_client: MockClient):
        _snapd_conf.set('lxd', {'mykey': 'myval'})
        mock_client.put.assert_called_once_with('/v2/snaps/lxd/conf', body={'mykey': 'myval'})


class TestUnset:
    def test_unset_single(self, mock_client: MockClient):
        _snapd_conf.unset('lxd', ['mykey'])
        mock_client.put.assert_called_once_with('/v2/snaps/lxd/conf', body={'mykey': None})

    def test_unset_multiple(self, mock_client: MockClient):
        _snapd_conf.unset('lxd', ['a', 'b'])
        body = mock_client.put.call_args.kwargs['body']
        assert body == {'a': None, 'b': None}

    def test_unset_accepts_arbitrary_iterable(self, mock_client: MockClient):
        _snapd_conf.unset('lxd', (k for k in ('a', 'b')))
        body = mock_client.put.call_args.kwargs['body']
        assert body == {'a': None, 'b': None}

    def test_unset_string_keys_raises_typeerror(self, mock_client: MockClient):
        # A bare string is iterable, so it's rejected explicitly rather than being
        # silently split into single-character keys.
        with pytest.raises(TypeError):
            _snapd_conf.unset('lxd', 'mykey')
        mock_client.put.assert_not_called()

    def test_unset_empty_keys_is_noop(self, mock_client: MockClient):
        _snapd_conf.unset('lxd', [])
        mock_client.put.assert_called_once_with('/v2/snaps/lxd/conf', body={})


class TestSetAdditional:
    def test_set_empty_dict(self, mock_client: MockClient):
        # set({}) sends an empty body — the API accepts it as a no-op.
        _snapd_conf.set('lxd', {})
        mock_client.put.assert_called_once_with('/v2/snaps/lxd/conf', body={})


class TestUnsetAdditional:
    def test_unset_dotted_path(self, mock_client: MockClient):
        # unset() with a dotted-path key passes it as-is to the API.
        _snapd_conf.unset('lxd', ['parent.child'])
        mock_client.put.assert_called_once_with('/v2/snaps/lxd/conf', body={'parent.child': None})


class TestSetAndUnsetKeys:
    # set and unset send their keys in a JSON body rather than a comma-separated query parameter,
    # so snapd sees them exactly as passed and rejects an unusable one itself. It only does so
    # once the configure hook runs, though, reporting an empty key as an 'internal error' inside a
    # ChangeError, so we reject empty and blank keys up front to match get().
    @pytest.mark.parametrize(('key', 'match'), [('', 'empty'), (' ', 'blank'), ('\t', 'blank')])
    def test_set_unusable_key_raises_value_error_without_request(
        self, mock_client: MockClient, key: str, match: str
    ):
        with pytest.raises(ValueError, match=f'config key must not be {match}'):
            _snapd_conf.set('lxd', {key: 'myval', 'valid-key': 'myval'})
        mock_client.put.assert_not_called()

    @pytest.mark.parametrize(('key', 'match'), [('', 'empty'), (' ', 'blank'), ('\t', 'blank')])
    def test_unset_unusable_key_raises_value_error_without_request(
        self, mock_client: MockClient, key: str, match: str
    ):
        with pytest.raises(ValueError, match=f'config key must not be {match}'):
            _snapd_conf.unset('lxd', [key, 'valid-key'])
        mock_client.put.assert_not_called()

    @pytest.mark.parametrize('key', [' padded ', 'a,b'])
    def test_other_unusable_keys_are_left_to_snapd(self, mock_client: MockClient, key: str):
        # Unlike get(), nothing here alters the key in transit, so a key snapd will reject is
        # snapd's to report -- it names the offending key and rolls the whole change back.
        _snapd_conf.set('lxd', {key: 'myval'})
        mock_client.put.assert_called_once_with('/v2/snaps/lxd/conf', body={key: 'myval'})

    def test_unset_validates_keys_before_the_request(self, mock_client: MockClient):
        # The keys are materialised to validate them, so a generator is still sent in full.
        _snapd_conf.unset('lxd', (k for k in ('a', 'b')))
        mock_client.put.assert_called_once_with('/v2/snaps/lxd/conf', body={'a': None, 'b': None})


class TestConfigureHookFailure:
    # Setting or unsetting config runs the snap's configure hook as an async change. A failing
    # hook (including a snap with no configure hook) surfaces as a ChangeError.
    _CHANGE_ERROR = ChangeError(
        'cannot perform the following tasks:\n'
        '- Run configure hook of "hello-world" snap (snap "hello-world" has no "configure" hook)',
        kind='charmlibs-snap-change-error',
        value='63',
        status='Error',
    )

    def test_set_change_error_propagates(self, mock_client: MockClient):
        mock_client.put.side_effect = self._CHANGE_ERROR
        with pytest.raises(ChangeError):
            _snapd_conf.set('hello-world', {'mykey': 'myval'})

    def test_unset_change_error_propagates(self, mock_client: MockClient):
        mock_client.put.side_effect = self._CHANGE_ERROR
        with pytest.raises(ChangeError):
            _snapd_conf.unset('hello-world', ['mykey'])


class TestSnapNameInPath:
    # get, set and unset all interpolate the snap name into the URL path. An unvalidated empty
    # name builds '/v2/snaps//conf', which snapd answers with an empty-bodied 301 to
    # '/v2/snaps/conf' -- previously surfaced as a BadResponseError about invalid JSON.
    @pytest.mark.parametrize('snap', ['', '.', '..', 'hello-world/conf'])
    def test_get_invalid_name_raises_value_error_without_request(
        self, mock_client: MockClient, snap: str
    ):
        with pytest.raises(ValueError):
            _snapd_conf.get(snap)
        mock_client.get.assert_not_called()

    @pytest.mark.parametrize('keys', [None, [], ['mykey'], 'mykey'])
    def test_get_empty_name_raises_value_error_for_any_keys(
        self, mock_client: MockClient, keys: Any
    ):
        # Including keys=[] (the installed-snap probe) and a string (a TypeError otherwise),
        # so that every path through get() reports the empty name the same way.
        with pytest.raises(ValueError, match='must not be empty'):
            _snapd_conf.get('', keys)
        mock_client.get.assert_not_called()

    @pytest.mark.parametrize('snap', ['', '.', '..', 'hello-world/conf'])
    def test_set_invalid_name_raises_value_error_without_request(
        self, mock_client: MockClient, snap: str
    ):
        with pytest.raises(ValueError):
            _snapd_conf.set(snap, {'mykey': 'myval'})
        mock_client.put.assert_not_called()

    @pytest.mark.parametrize('snap', ['', '.', '..', 'hello-world/conf'])
    def test_unset_invalid_name_raises_value_error_without_request(
        self, mock_client: MockClient, snap: str
    ):
        with pytest.raises(ValueError):
            _snapd_conf.unset(snap, ['mykey'])
        mock_client.put.assert_not_called()

    def test_unset_validates_name_before_keys(self, mock_client: MockClient):
        with pytest.raises(ValueError, match='must not be empty'):
            _snapd_conf.unset('', 'mykey')  # A string 'keys' would otherwise be a TypeError.

    def test_name_is_percent_encoded(self, mock_client: MockClient):
        _snapd_conf.set('hello world', {'mykey': 'myval'})
        mock_client.put.assert_called_once_with(
            '/v2/snaps/hello%20world/conf', body={'mykey': 'myval'}
        )
