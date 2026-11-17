# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

# pyright: reportPrivateUsage=false

"""Unit tests for _snapd_quotas: get_quota, list_quotas, set_quota, remove_quota."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from charmlibs.snap import _snapd_quotas, _utils
from charmlibs.snap._errors import (
    APIError,
    BadResponseError,
    NotInstalledError,
    QuotaHasSubgroupsError,
    QuotaNotFoundError,
    _NotFoundError,
)

if TYPE_CHECKING:
    from conftest import MockClient


def _api_error(message: str = 'boom', status_code: int = 400) -> APIError:
    # snapd's quota failures are kindless: HTTP 400 with only a message.
    return APIError(message, kind='', value='', status_code=status_code)


def _not_found(snap: str) -> _NotFoundError:
    # Mirrors snapd's GET /v2/snaps/{snap}: a terse message with the snap name in `value`.
    return _NotFoundError('snap not installed', kind='snap-not-found', value=snap, status_code=404)


# A group response as snapd sends it: zero values and empty lists omitted, 'cpu-set'
# present-but-empty whenever a cpu limit is set, and 'current' present-but-empty when
# no usage is measured. (Captured from snapd 2.78 in fixtures/quotas.json.)
def _group_dict(
    name: str = 'my-group',
    *,
    parent: str | None = None,
    subgroups: list[str] | None = None,
    snaps: list[str] | None = None,
    services: list[str] | None = None,
    constraints: dict[str, object] | None = None,
    current: dict[str, object] | None = None,
) -> dict[str, object]:
    result: dict[str, object] = {'group-name': name}
    if parent is not None:
        result['parent'] = parent
    if subgroups:
        result['subgroups'] = subgroups
    if snaps:
        result['snaps'] = snaps
    if services:
        result['services'] = services
    if constraints is not None:
        result['constraints'] = constraints
    if current is not None:
        result['current'] = current
    return result


class TestUnchanged:
    def test_repr(self):
        assert repr(_utils.UNCHANGED) == 'UNCHANGED'

    def test_cannot_be_instantiated(self):
        with pytest.raises(TypeError, match='sentinel'):
            _utils.UNCHANGED()


class TestQuotaInfoParsing:
    def test_full_group(self):
        info = _snapd_quotas.QuotaInfo._from_dict(
            _group_dict(
                parent='parent-group',
                subgroups=['sub-a', 'sub-b'],
                snaps=['snap-a', 'snap-b'],
                services=['snap-c.serv1', 'snap-c.serv2', 'snap-d.serv1'],
                constraints={
                    'memory': 67108864,
                    'cpu': {'count': 2, 'percentage': 50},
                    'cpu-set': {'cpus': [0, 3]},
                    'threads': 32,
                    'journal': {'size': 16777216},
                },
                current={'memory': 647168, 'threads': 3},
            )
        )
        assert info.name == 'my-group'
        assert info.parent == 'parent-group'
        assert info.subgroups == ['sub-a', 'sub-b']
        assert info.snaps == ['snap-a', 'snap-b']
        # Qualified snap.service names are split at the first dot.
        assert info.services == {'snap-c': ['serv1', 'serv2'], 'snap-d': ['serv1']}
        assert info.memory == 67108864
        assert info.cpu == (2, 50)
        assert info.cpu_set == [0, 3]
        assert info.threads == 32
        assert info.memory_usage == 647168
        assert info.threads_usage == 3
        # The raw constraints are kept, including entries the library has no argument for.
        assert info._constraints['journal'] == {'size': 16777216}

    def test_minimal_group(self):
        # Everything snapd omits: no parent, no lists, no constraints, no current.
        info = _snapd_quotas.QuotaInfo._from_dict({'group-name': 'my-group'})
        assert info.name == 'my-group'
        assert info.parent is None
        assert info.subgroups == []
        assert info.snaps == []
        assert info.services == {}
        assert info.memory is None
        assert info.cpu is None
        assert info.cpu_set is None
        assert info.threads is None
        assert info.memory_usage is None
        assert info.threads_usage is None
        assert info._constraints == {}

    def test_zero_limits_mean_not_set(self):
        info = _snapd_quotas.QuotaInfo._from_dict(
            _group_dict(
                constraints={'memory': 0, 'threads': 0, 'cpu': {'count': 0, 'percentage': 0}},
                current={'memory': 0, 'threads': 0},
            )
        )
        assert info.memory is None
        assert info.threads is None
        assert info.cpu is None
        assert info.memory_usage is None
        assert info.threads_usage is None

    def test_cpu_percentage_only(self):
        # '50%' is sent and reported with no count: the percentage applies to all cores.
        info = _snapd_quotas.QuotaInfo._from_dict(
            _group_dict(constraints={'cpu': {'percentage': 50}, 'cpu-set': {}})
        )
        assert info.cpu == (None, 50)
        # An empty cpu-set object (as snapd sends alongside every cpu limit) is not a limit.
        assert info.cpu_set is None

    def test_cpu_set_only(self):
        info = _snapd_quotas.QuotaInfo._from_dict(
            _group_dict(constraints={'cpu-set': {'cpus': [1, 2]}})
        )
        assert info.cpu is None
        assert info.cpu_set == [1, 2]

    def test_usage_defaults_to_zero_when_limit_set(self):
        info = _snapd_quotas.QuotaInfo._from_dict(
            _group_dict(constraints={'memory': 1024, 'threads': 4}, current={})
        )
        assert info.memory_usage == 0
        assert info.threads_usage == 0

    def test_repr(self):
        info = _snapd_quotas.QuotaInfo._from_dict(
            _group_dict(snaps=['snap-a'], constraints={'memory': 1024})
        )
        assert repr(info) == (
            "QuotaInfo('my-group', parent=None, subgroups=[], snaps=['snap-a'], "
            'services={}, memory=1024, cpu=None, cpu_set=None, threads=None, '
            'memory_usage=0, threads_usage=None)'
        )


class TestGetQuota:
    def test_request_path(self, mock_client: MockClient):
        mock_client.get.return_value = _group_dict()
        _snapd_quotas.get_quota('my-group')
        mock_client.get.assert_called_once_with('/v2/quotas/my-group')

    def test_name_is_encoded(self, mock_client: MockClient):
        # Characters that would break the path are percent-encoded.
        mock_client.get.return_value = _group_dict()
        _snapd_quotas.get_quota('my?group')
        mock_client.get.assert_called_once_with('/v2/quotas/my%3Fgroup')

    def test_returns_parsed_info(self, mock_client: MockClient):
        mock_client.get.return_value = _group_dict(snaps=['snap-a'], constraints={'memory': 1024})
        info = _snapd_quotas.get_quota('my-group')
        assert info.snaps == ['snap-a']
        assert info.memory == 1024

    def test_not_found(self, mock_client: MockClient):
        # Classified by the 404 status code, not by the message.
        mock_client.get.side_effect = _api_error('cannot find quota group "absent"', 404)
        with pytest.raises(QuotaNotFoundError) as ctx:
            _snapd_quotas.get_quota('absent')
        assert ctx.value.message == 'cannot find quota group "absent"'
        assert ctx.value._status_code == 404

    def test_other_errors_are_reraised(self, mock_client: MockClient):
        original = _api_error('cannot find quota group "nope"', 400)
        mock_client.get.side_effect = original
        with pytest.raises(APIError) as ctx:
            _snapd_quotas.get_quota('nope')
        assert ctx.value is original
        assert not isinstance(ctx.value, QuotaNotFoundError)

    def test_bad_response_type(self, mock_client: MockClient):
        mock_client.get.return_value = ['not', 'a', 'dict']
        with pytest.raises(BadResponseError):
            _snapd_quotas.get_quota('my-group')

    def test_unreadable_group(self, mock_client: MockClient):
        mock_client.get.return_value = {'no-group-name': True}
        with pytest.raises(BadResponseError):
            _snapd_quotas.get_quota('my-group')


class TestListQuotas:
    def test_empty(self, mock_client: MockClient):
        mock_client.get.return_value = []
        assert _snapd_quotas.list_quotas() == []
        mock_client.get.assert_called_once_with('/v2/quotas')

    def test_parses_captured_response(self, mock_client: MockClient):
        # fixtures/quotas.json was captured from snapd 2.78 with five groups covering
        # every limit kind, a parent/sub-group pair, and a service entry.
        from conftest import result_of

        mock_client.get.return_value = result_of('quotas.json')
        infos = {info.name: info for info in _snapd_quotas.list_quotas()}
        assert sorted(infos) == [
            'fixture-journal',
            'fixture-parent',
            'fixture-sub',
            'fixture-svc',
            'fixture-svc-sub',
        ]
        assert infos['fixture-journal'].memory is None
        assert infos['fixture-journal']._constraints == {'journal': {'size': 16000000}}
        assert infos['fixture-parent'].subgroups == ['fixture-sub']
        assert infos['fixture-sub'].parent == 'fixture-parent'
        assert infos['fixture-sub'].cpu == (2, 50)
        assert infos['fixture-sub'].cpu_set is None
        assert infos['fixture-sub'].threads == 32
        assert infos['fixture-svc'].memory == 64000000
        assert infos['fixture-svc'].memory_usage == 647168
        assert infos['fixture-svc-sub'].services == {'test-service-snap': ['daemon']}
        assert infos['fixture-svc-sub'].cpu == (None, 50)

    def test_bad_response_type(self, mock_client: MockClient):
        mock_client.get.return_value = {'not': 'a list'}
        with pytest.raises(BadResponseError):
            _snapd_quotas.list_quotas()

    def test_bad_entry_type(self, mock_client: MockClient):
        mock_client.get.return_value = ['not-a-dict']
        with pytest.raises(BadResponseError):
            _snapd_quotas.list_quotas()

    def test_unreadable_entry(self, mock_client: MockClient):
        mock_client.get.return_value = [{'no-group-name': True}]
        with pytest.raises(BadResponseError):
            _snapd_quotas.list_quotas()


class TestSetQuota:
    def test_full_request_body(self, mock_client: MockClient):
        _snapd_quotas.set_quota(
            'my-group',
            ['snap-a', 'snap-b'],
            services={'snap-c': ['serv1', 'serv2'], 'snap-d': 'serv3'},
            parent='parent-group',
            memory=67108864,
            cpu=(2, 50),
            cpu_set=[0, 3],
            threads=32,
        )
        mock_client.post.assert_called_once_with(
            '/v2/quotas',
            body={
                'action': 'ensure',
                'group-name': 'my-group',
                'parent': 'parent-group',
                'snaps': ['snap-a', 'snap-b'],
                'services': ['snap-c.serv1', 'snap-c.serv2', 'snap-d.serv3'],
                'constraints': {
                    'memory': 67108864,
                    'cpu': {'count': 2, 'percentage': 50},
                    'cpu-set': {'cpus': [0, 3]},
                    'threads': 32,
                },
            },
        )

    def test_bare_snap_name(self, mock_client: MockClient):
        _snapd_quotas.set_quota('my-group', 'snap-a', memory=1024)
        body = mock_client.post.call_args.kwargs['body']
        assert body['snaps'] == ['snap-a']

    def test_nothing_given_sends_bare_ensure(self, mock_client: MockClient):
        _snapd_quotas.set_quota('my-group')
        mock_client.post.assert_called_once_with(
            '/v2/quotas', body={'action': 'ensure', 'group-name': 'my-group'}
        )

    def test_cpu_count_none_is_left_out(self, mock_client: MockClient):
        # (None, 50) is '50%': the percentage applies to every available core, so no
        # count is sent -- sending one would pin it.
        _snapd_quotas.set_quota('my-group', cpu=(None, 50))
        body = mock_client.post.call_args.kwargs['body']
        assert body['constraints'] == {'cpu': {'percentage': 50}}

    def test_empty_snaps_and_services_add_nothing(self, mock_client: MockClient):
        _snapd_quotas.set_quota('my-group', [], services={}, memory=1024)
        mock_client.post.assert_called_once_with(
            '/v2/quotas',
            body={
                'action': 'ensure',
                'group-name': 'my-group',
                'constraints': {'memory': 1024},
            },
        )

    def test_serviceless_snap_entry_adds_nothing(self, mock_client: MockClient):
        _snapd_quotas.set_quota('my-group', services={'snap-a': []}, memory=1024)
        assert 'services' not in mock_client.post.call_args.kwargs['body']

    @pytest.mark.parametrize(
        ('kwargs', 'match'),
        [
            ({'snaps': ['']}, 'must not be empty'),
            ({'snaps': [' ']}, 'must not be blank'),
            ({'snaps': ['a/b']}, 'must be a single path segment'),
            ({'snaps': ['..']}, 'must be a single path segment'),
            ({'services': {'': ['serv1']}}, 'must not be empty'),
            ({'services': {'a/b': ['serv1']}}, 'must be a single path segment'),
            ({'services': {'snap-a': [' ']}}, 'must not be blank'),
            ({'parent': ''}, 'parent group name must not be empty'),
            ({'parent': ' '}, 'parent group name must not be blank'),
            ({'parent': 'a/b'}, 'parent group name must be a single path segment'),
            ({'memory': 0}, 'memory must be'),
            ({'memory': -1}, 'memory must be'),
            ({'threads': 0}, 'threads must be'),
            ({'threads': -1}, 'threads must be'),
            ({'cpu': (None, 0)}, 'cpu percentage must be'),
            ({'cpu': (None, 101)}, 'cpu percentage must be'),
            ({'cpu': (0, 50)}, 'cpu count must be'),
            ({'cpu': (-1, 50)}, 'cpu count must be'),
            ({'cpu_set': []}, 'cpu_set must not be empty'),
            ({'cpu_set': [0, -1]}, 'cpu_set must not contain negative'),
        ],
    )
    def test_value_error_without_request(
        self, mock_client: MockClient, kwargs: dict[str, object], match: str
    ):
        with pytest.raises(ValueError, match=match):
            _snapd_quotas.set_quota('my-group', **kwargs)  # pyright: ignore[reportArgumentType]
        mock_client.post.assert_not_called()

    @pytest.mark.parametrize('name', ['parent', 'memory', 'cpu', 'cpu_set', 'threads'])
    def test_none_is_a_type_error(self, mock_client: MockClient, name: str):
        # None means 'must be absent', which only ensure_quota can ask for.
        with pytest.raises(TypeError, match='ensure_quota'):
            _snapd_quotas.set_quota('my-group', **{name: None})  # pyright: ignore[reportArgumentType]
        mock_client.post.assert_not_called()

    def test_not_installed_snap(self, mock_client: MockClient):
        # snapd's kindless 'cannot use snap ...' error becomes a typed NotInstalledError,
        # probed in the order the snaps were named.
        mock_client.post.side_effect = _api_error('cannot use snap "absent" in group')
        mock_client.get.side_effect = _not_found('absent')
        with pytest.raises(NotInstalledError) as ctx:
            _snapd_quotas.set_quota('my-group', ['absent'], memory=1024)
        assert ctx.value._value == 'absent'
        mock_client.get.assert_called_once_with('/v2/snaps/absent')

    def test_not_installed_services_snap(self, mock_client: MockClient):
        # Snaps named only in the services mapping are probed too.
        mock_client.post.side_effect = _api_error('cannot add snap service')
        mock_client.get.side_effect = _not_found('absent')
        with pytest.raises(NotInstalledError):
            _snapd_quotas.set_quota('my-group', services={'absent': ['serv1']}, memory=1024)

    def test_reraises_original_when_snaps_installed(self, mock_client: MockClient):
        original = _api_error('cannot decrease memory limit, remove and re-create it')
        mock_client.post.side_effect = original
        mock_client.get.return_value = {}  # every probed snap installed
        with pytest.raises(APIError) as ctx:
            _snapd_quotas.set_quota('my-group', ['snap-a'], memory=1024)
        assert ctx.value is original


class TestRemoveQuota:
    def test_request_body(self, mock_client: MockClient):
        _snapd_quotas.remove_quota('my-group')
        mock_client.post.assert_called_once_with(
            '/v2/quotas', body={'action': 'remove', 'group-name': 'my-group'}
        )

    def test_not_found(self, mock_client: MockClient):
        # The remove fails, and the classifying lookup 404s: the group does not exist.
        mock_client.post.side_effect = _api_error('cannot remove non-existent quota group')
        mock_client.get.side_effect = _api_error('cannot find quota group', 404)
        with pytest.raises(QuotaNotFoundError) as ctx:
            _snapd_quotas.remove_quota('absent')
        # The error is built from the remove failure, keeping its message.
        assert ctx.value.message == 'cannot remove non-existent quota group'
        mock_client.get.assert_called_once_with('/v2/quotas/absent')

    def test_has_subgroups(self, mock_client: MockClient):
        mock_client.post.side_effect = _api_error('cannot remove quota group with sub-groups')
        mock_client.get.return_value = _group_dict(subgroups=['sub-a'])
        with pytest.raises(QuotaHasSubgroupsError):
            _snapd_quotas.remove_quota('my-group')

    def test_reraises_original_for_other_failures(self, mock_client: MockClient):
        # The group exists and has no sub-groups, so the failure was something else.
        original = _api_error('conflict: change in progress')
        mock_client.post.side_effect = original
        mock_client.get.return_value = _group_dict()
        with pytest.raises(APIError) as ctx:
            _snapd_quotas.remove_quota('my-group')
        assert ctx.value is original
