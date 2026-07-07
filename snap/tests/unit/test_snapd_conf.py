# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

# pyright: reportPrivateUsage=false

from __future__ import annotations

from typing import TYPE_CHECKING

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

    def test_get_specific_key(self, mock_client: MockClient):
        mock_client.get.return_value = result_of('conf_lxd_single_key.json')
        _snapd_conf.get('lxd', 'integer')
        mock_client.get.assert_called_once_with('/v2/snaps/lxd/conf', query={'keys': 'integer'})

    def test_get_multiple_keys(self, mock_client: MockClient):
        mock_client.get.return_value = {'a': 1, 'b': 2}
        _snapd_conf.get('lxd', 'a', 'b')
        query = mock_client.get.call_args.kwargs['query']
        assert query == {'keys': 'a,b'}

    def test_get_returns_dict(self, mock_client: MockClient):
        mock_client.get.return_value = result_of('conf_lxd_all.json')
        result = _snapd_conf.get('lxd')
        assert isinstance(result, dict)
        assert 'criu' in result


class TestGetAbsentSnapProbe:
    # The conf GET endpoint alone can't distinguish an absent snap from a missing key (or from
    # empty configuration), so get() probes /v2/snaps/{snap} on those paths to raise
    # NotFoundError, consistent with set and unset. See the functional tests for captured
    # responses.
    _OPTION_NOT_FOUND = OptionNotFoundError(
        'snap "hello-world" has no "mykey" configuration option',
        kind='option-not-found',
        value="{'SnapName': 'hello-world', 'Key': 'mykey'}",
    )
    _SNAP_NOT_FOUND = NotFoundError(
        'snap not installed', kind='snap-not-found', value='hello-world'
    )

    def test_missing_key_on_installed_snap_reraises_option_not_found(
        self, mock_client: MockClient
    ):
        mock_client.get.side_effect = [
            self._OPTION_NOT_FOUND,
            result_of('snap_info_hello_world.json'),
        ]
        with pytest.raises(OptionNotFoundError):
            _snapd_conf.get('hello-world', 'mykey')
        probe_call = mock_client.get.call_args_list[1]
        assert probe_call.args[0] == '/v2/snaps/hello-world'

    def test_missing_key_on_absent_snap_raises_not_found(self, mock_client: MockClient):
        mock_client.get.side_effect = [self._OPTION_NOT_FOUND, self._SNAP_NOT_FOUND]
        with pytest.raises(NotFoundError):
            _snapd_conf.get('hello-world', 'mykey')

    def test_get_all_empty_on_absent_snap_raises_not_found(self, mock_client: MockClient):
        # A bare conf GET on an absent snap is a 200 with an empty result, so the probe is
        # what turns it into an error.
        mock_client.get.side_effect = [{}, self._SNAP_NOT_FOUND]
        with pytest.raises(NotFoundError):
            _snapd_conf.get('hello-world')

    def test_get_all_empty_on_installed_snap_returns_empty_dict(self, mock_client: MockClient):
        mock_client.get.side_effect = [{}, result_of('snap_info_hello_world.json')]
        assert _snapd_conf.get('hello-world') == {}

    def test_get_all_nonempty_is_not_probed(self, mock_client: MockClient):
        mock_client.get.return_value = result_of('conf_lxd_all.json')
        _snapd_conf.get('lxd')
        mock_client.get.assert_called_once()

    def test_missing_key_on_system_is_not_probed(self, mock_client: MockClient):
        # /v2/snaps/system always 404s while its conf is served, so system names skip the probe.
        mock_client.get.side_effect = self._OPTION_NOT_FOUND
        with pytest.raises(OptionNotFoundError):
            _snapd_conf.get('system', 'mykey')
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
        _snapd_conf.unset('lxd', 'mykey')
        mock_client.put.assert_called_once_with('/v2/snaps/lxd/conf', body={'mykey': None})

    def test_unset_multiple(self, mock_client: MockClient):
        _snapd_conf.unset('lxd', 'a', 'b')
        body = mock_client.put.call_args.kwargs['body']
        assert body == {'a': None, 'b': None}


class TestSetAdditional:
    def test_set_empty_dict(self, mock_client: MockClient):
        # set({}) sends an empty body — the API accepts it as a no-op.
        _snapd_conf.set('lxd', {})
        mock_client.put.assert_called_once_with('/v2/snaps/lxd/conf', body={})


class TestUnsetAdditional:
    def test_unset_dotted_path(self, mock_client: MockClient):
        # unset() with a dotted-path key passes it as-is to the API.
        _snapd_conf.unset('lxd', 'parent.child')
        mock_client.put.assert_called_once_with('/v2/snaps/lxd/conf', body={'parent.child': None})


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
            _snapd_conf.unset('hello-world', 'mykey')
