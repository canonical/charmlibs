# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from charmlibs.snap import _snapd_apps
from charmlibs.snap._errors import AppNotFoundError, NotFoundError
from conftest import result_of

if TYPE_CHECKING:
    from conftest import MockClient


class TestStart:
    def test_start_snap_only(self, mock_client: MockClient):
        _snapd_apps.start('lxd')
        mock_client.post.assert_called_once_with(
            '/v2/apps', body={'action': 'start', 'names': ['lxd']}
        )

    def test_start_services_none_is_the_default(self, mock_client: MockClient):
        _snapd_apps.start('lxd', services=None)
        mock_client.post.assert_called_once_with(
            '/v2/apps', body={'action': 'start', 'names': ['lxd']}
        )

    def test_start_with_service(self, mock_client: MockClient):
        _snapd_apps.start('lxd', 'daemon')
        body = mock_client.post.call_args.kwargs['body']
        assert body['names'] == ['lxd.daemon']

    def test_start_multiple_services(self, mock_client: MockClient):
        _snapd_apps.start('lxd', ['daemon', 'user-daemon'])
        body = mock_client.post.call_args.kwargs['body']
        assert body['names'] == ['lxd.daemon', 'lxd.user-daemon']

    def test_start_enable(self, mock_client: MockClient):
        _snapd_apps.start('lxd', enable=True)
        body = mock_client.post.call_args.kwargs['body']
        assert body['enable'] is True


class TestStop:
    def test_stop_snap_only(self, mock_client: MockClient):
        _snapd_apps.stop('lxd')
        mock_client.post.assert_called_once_with(
            '/v2/apps', body={'action': 'stop', 'names': ['lxd']}
        )

    def test_stop_with_service(self, mock_client: MockClient):
        _snapd_apps.stop('lxd', 'daemon')
        body = mock_client.post.call_args.kwargs['body']
        assert body['names'] == ['lxd.daemon']

    def test_stop_disable(self, mock_client: MockClient):
        _snapd_apps.stop('lxd', disable=True)
        body = mock_client.post.call_args.kwargs['body']
        assert body['disable'] is True


class TestRestart:
    def test_restart_snap_only(self, mock_client: MockClient):
        _snapd_apps.restart('lxd')
        mock_client.post.assert_called_once_with(
            '/v2/apps', body={'action': 'restart', 'names': ['lxd']}
        )

    def test_restart_with_service(self, mock_client: MockClient):
        _snapd_apps.restart('lxd', 'daemon')
        body = mock_client.post.call_args.kwargs['body']
        assert body['names'] == ['lxd.daemon']


_FUNCTIONS = [_snapd_apps.start, _snapd_apps.stop, _snapd_apps.restart]


class TestServicesArgument:
    # services=None means every service the snap has, services=[] means none of them, and a bare
    # string means that one service. A string is iterable, so without the last rule 'daemon'
    # would silently mean the services 'd', 'a', 'e', ...
    @pytest.mark.parametrize('func', _FUNCTIONS, ids=lambda f: f.__name__)
    def test_bare_string_is_one_service(self, mock_client: MockClient, func: Any):
        func('lxd', 'daemon')
        assert mock_client.post.call_args.kwargs['body']['names'] == ['lxd.daemon']

    @pytest.mark.parametrize('func', _FUNCTIONS, ids=lambda f: f.__name__)
    def test_single_element_list_is_the_same_as_a_bare_string(
        self, mock_client: MockClient, func: Any
    ):
        func('lxd', ['daemon'])
        assert mock_client.post.call_args.kwargs['body']['names'] == ['lxd.daemon']

    @pytest.mark.parametrize('func', _FUNCTIONS, ids=lambda f: f.__name__)
    def test_arbitrary_iterable_is_accepted(self, mock_client: MockClient, func: Any):
        # The names are iterated to validate them and then to build the request, so a generator
        # must be materialised rather than consumed by the first pass.
        func('lxd', (s for s in ('daemon', 'user-daemon')))
        assert mock_client.post.call_args.kwargs['body']['names'] == [
            'lxd.daemon',
            'lxd.user-daemon',
        ]

    @pytest.mark.parametrize('func', _FUNCTIONS, ids=lambda f: f.__name__)
    def test_none_names_the_snap_itself(self, mock_client: MockClient, func: Any):
        # Naming the snap is how snapd is asked to act on all of its services.
        func('lxd', None)
        assert mock_client.post.call_args.kwargs['body']['names'] == ['lxd']


class TestEmptyServices:
    # services=[] is a deliberate "no services requested", distinct from services=None ("all of
    # them"). No action is posted, but the snap named alongside it is still checked -- asking a
    # snap that isn't installed to do nothing is an error, not a no-op.
    @pytest.mark.parametrize('func', _FUNCTIONS, ids=lambda f: f.__name__)
    def test_empty_services_posts_nothing(self, mock_client: MockClient, func: Any):
        mock_client.get.return_value = result_of('snap_info_hello_world.json')
        assert func('hello-world', []) is None
        mock_client.post.assert_not_called()

    @pytest.mark.parametrize('func', _FUNCTIONS, ids=lambda f: f.__name__)
    def test_empty_services_probes_installed_snap(self, mock_client: MockClient, func: Any):
        mock_client.get.return_value = result_of('snap_info_hello_world.json')
        func('hello-world', [])
        mock_client.get.assert_called_once_with('/v2/snaps/hello-world')

    @pytest.mark.parametrize('func', _FUNCTIONS, ids=lambda f: f.__name__)
    def test_empty_services_not_installed_raises_not_found(
        self, mock_client: MockClient, func: Any
    ):
        mock_client.get.side_effect = NotFoundError(
            'snap not installed', kind='snap-not-found', value='hello-world'
        )
        with pytest.raises(NotFoundError) as ctx:
            func('hello-world', [])
        # snapd's own probe error is raised unchanged: terse message, snap name in value (which
        # str() surfaces). Not chained -- the probe's error was handled, not propagated.
        assert ctx.value.message == 'snap not installed'
        assert ctx.value.value == 'hello-world'
        assert str(ctx.value) == 'snap not installed (hello-world)'
        assert ctx.value.__context__ is None
        mock_client.post.assert_not_called()

    @pytest.mark.parametrize('func', _FUNCTIONS, ids=lambda f: f.__name__)
    @pytest.mark.parametrize('snap', ['system', 'core'])
    def test_system_names_are_probed(self, mock_client: MockClient, func: Any, snap: str):
        # Unlike the conf and interfaces endpoints, /v2/apps has no 'system' alias and treats
        # 'core' as an ordinary snap, so neither name skips the probe.
        mock_client.get.side_effect = NotFoundError(
            'snap not installed', kind='snap-not-found', value=snap
        )
        with pytest.raises(NotFoundError):
            func(snap, [])
        mock_client.get.assert_called_once_with(f'/v2/snaps/{snap}')

    @pytest.mark.parametrize('func', _FUNCTIONS, ids=lambda f: f.__name__)
    def test_empty_services_still_validates_service_names(
        self, mock_client: MockClient, func: Any
    ):
        # Nothing to validate in an empty list, but an unusable name alongside others is still
        # rejected before the emptiness of the list is considered.
        with pytest.raises(ValueError, match='service name must not be empty'):
            func('hello-world', [''])
        mock_client.get.assert_not_called()

    @pytest.mark.parametrize('func', _FUNCTIONS, ids=lambda f: f.__name__)
    def test_empty_string_is_not_empty_services(self, mock_client: MockClient, func: Any):
        # The one case the bare-string rule makes ambiguous: '' is one (unusable) service name,
        # not an empty collection of them, so it's a ValueError rather than a no-op.
        with pytest.raises(ValueError, match='service name must not be empty'):
            func('hello-world', '')
        mock_client.get.assert_not_called()
        mock_client.post.assert_not_called()


class TestAppNotFoundConversion:
    # snapd answers app-not-found both for a snap that isn't installed and for a service an
    # installed snap doesn't have, so start/stop/restart probe /v2/snaps/{snap} to tell them
    # apart. An absent snap raises NotFoundError as it does elsewhere in the library, leaving
    # AppNotFoundError to mean the snap is installed but has no such service.
    # Built fresh per call: raising an exception mutates its __context__, so a shared instance
    # would leak chaining state between tests.
    @staticmethod
    def _app_not_found() -> AppNotFoundError:
        return AppNotFoundError(
            'snap "hello-world" has no service "daemon"', kind='app-not-found', value=''
        )

    @staticmethod
    def _snap_not_found() -> NotFoundError:
        return NotFoundError('snap not installed', kind='snap-not-found', value='hello-world')

    @pytest.mark.parametrize('func', _FUNCTIONS, ids=lambda f: f.__name__)
    def test_absent_snap_raises_not_found(self, mock_client: MockClient, func: Any):
        mock_client.post.side_effect = self._app_not_found()
        mock_client.get.side_effect = self._snap_not_found()
        with pytest.raises(NotFoundError) as ctx:
            func('hello-world', 'daemon')
        assert ctx.value.kind == 'snap-not-found'
        assert str(ctx.value) == 'snap not installed (hello-world)'
        mock_client.get.assert_called_once_with('/v2/snaps/hello-world')

    @pytest.mark.parametrize('func', _FUNCTIONS, ids=lambda f: f.__name__)
    def test_absent_snap_does_not_chain_app_not_found(self, mock_client: MockClient, func: Any):
        # snapd's misleading app-not-found is suppressed ('raise ... from None'), so the user
        # sees a single traceback that doesn't mention a service they may not have named.
        mock_client.post.side_effect = self._app_not_found()
        mock_client.get.side_effect = self._snap_not_found()
        with pytest.raises(NotFoundError) as ctx:
            func('hello-world', 'daemon')
        assert ctx.value.__cause__ is None
        assert ctx.value.__suppress_context__

    @pytest.mark.parametrize('func', _FUNCTIONS, ids=lambda f: f.__name__)
    def test_missing_service_on_installed_snap_reraises_app_not_found(
        self, mock_client: MockClient, func: Any
    ):
        mock_client.post.side_effect = self._app_not_found()
        mock_client.get.return_value = result_of('snap_info_hello_world.json')
        with pytest.raises(AppNotFoundError) as ctx:
            func('hello-world', 'daemon')
        assert ctx.value.kind == 'app-not-found'
        mock_client.get.assert_called_once_with('/v2/snaps/hello-world')

    @pytest.mark.parametrize('func', _FUNCTIONS, ids=lambda f: f.__name__)
    def test_snap_with_no_services_reraises_app_not_found(
        self, mock_client: MockClient, func: Any
    ):
        # services=None on an installed snap with no services: the probe finds the snap, so
        # snapd's own error stands.
        mock_client.post.side_effect = self._app_not_found()
        mock_client.get.return_value = result_of('snap_info_hello_world.json')
        with pytest.raises(AppNotFoundError):
            func('hello-world')

    @pytest.mark.parametrize('func', _FUNCTIONS, ids=lambda f: f.__name__)
    def test_successful_call_is_not_probed(self, mock_client: MockClient, func: Any):
        func('hello-world', 'daemon')
        mock_client.get.assert_not_called()


class TestInvalidSnapName:
    # /v2/apps takes the snap name in the request body, where snapd already answers an empty name
    # with a typed 'snap "" not found'. We still reject it up front, so that every function in the
    # library reports an empty snap name the same way -- and so that the not-installed probe,
    # which builds a URL path from the name, can't raise ValueError from inside the handler for
    # snapd's app-not-found and mask the error being classified.
    @pytest.mark.parametrize('func', _FUNCTIONS, ids=lambda f: f.__name__)
    def test_empty_name_raises_value_error_without_request(
        self, mock_client: MockClient, func: Any
    ):
        with pytest.raises(ValueError, match='must not be empty'):
            func('')
        mock_client.post.assert_not_called()

    @pytest.mark.parametrize('func', _FUNCTIONS, ids=lambda f: f.__name__)
    def test_empty_name_with_services_raises(self, mock_client: MockClient, func: Any):
        with pytest.raises(ValueError, match='must not be empty'):
            func('', 'daemon')
        mock_client.post.assert_not_called()

    @pytest.mark.parametrize('func', _FUNCTIONS, ids=lambda f: f.__name__)
    @pytest.mark.parametrize('services', [None, [], ['daemon'], 'daemon'])
    @pytest.mark.parametrize('snap', ['.', '..', 'hello-world/conf'])
    def test_name_that_is_not_a_path_segment_raises(
        self, mock_client: MockClient, func: Any, services: Any, snap: str
    ):
        # Checked for every form of the services argument, so that every path through the
        # function reports an unusable name the same way.
        with pytest.raises(ValueError, match='single path segment'):
            func(snap, services)
        mock_client.post.assert_not_called()
        mock_client.get.assert_not_called()


class TestEmptyOrBlankServiceName:
    # An empty or blank service name builds a name like 'lxd.', which snapd reports as a service
    # that doesn't exist -- loudly, but only after a round trip, and it aborts the whole request,
    # so a valid service named alongside it isn't acted on either.
    @pytest.mark.parametrize('func', _FUNCTIONS, ids=lambda f: f.__name__)
    @pytest.mark.parametrize(('value', 'match'), [('', 'empty'), (' ', 'blank'), ('\t', 'blank')])
    def test_raises_value_error_without_request(
        self, mock_client: MockClient, func: Any, value: str, match: str
    ):
        with pytest.raises(ValueError, match=f'service name must not be {match}'):
            func('lxd', value)
        mock_client.post.assert_not_called()

    @pytest.mark.parametrize('func', _FUNCTIONS, ids=lambda f: f.__name__)
    def test_raises_among_valid_service_names(self, mock_client: MockClient, func: Any):
        with pytest.raises(ValueError, match='service name must not be empty'):
            func('lxd', ['daemon', ''])
        mock_client.post.assert_not_called()

    @pytest.mark.parametrize('func', _FUNCTIONS, ids=lambda f: f.__name__)
    def test_other_unusable_names_are_left_to_snapd(self, mock_client: MockClient, func: Any):
        # The names go in a JSON body, so snapd sees them exactly as passed: a padded or
        # comma-containing name is reported as the service it is, not silently altered.
        func('lxd', ' daemon ')
        assert mock_client.post.call_args.kwargs['body']['names'] == ['lxd. daemon ']
