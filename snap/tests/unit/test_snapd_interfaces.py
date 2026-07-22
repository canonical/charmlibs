# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

# pyright: reportPrivateUsage=false

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from charmlibs.snap import _snapd_interfaces
from charmlibs.snap._errors import APIError, NotFoundError, _InterfacesUnchangedError

if TYPE_CHECKING:
    from conftest import MockClient


def _api_error(message: str = 'boom') -> APIError:
    return APIError(message, kind='', value='', status_code=400)


def _not_found(message: str = 'not found') -> NotFoundError:
    return NotFoundError(message, kind='snap-not-found', value='', status_code=404)


class TestConnect:
    def test_connect_plug_only_auto_resolves_slot(self, mock_client: MockClient):
        # slot=None -> empty slot snap and name, so snapd auto-resolves the system slot.
        _snapd_interfaces.connect(('vlc', 'mount-observe'))
        body = mock_client.post.call_args.kwargs['body']
        assert body['plugs'] == [{'snap': 'vlc', 'plug': 'mount-observe'}]
        assert body['slots'] == [{'snap': '', 'slot': ''}]

    def test_connect_slot_bare_snap_name(self, mock_client: MockClient):
        # A bare snap-name slot means 'resolve the matching slot on this snap'.
        _snapd_interfaces.connect(('vlc', 'mount-observe'), 'core')
        body = mock_client.post.call_args.kwargs['body']
        assert body['slots'] == [{'snap': 'core', 'slot': ''}]

    def test_connect_slot_explicit_pair(self, mock_client: MockClient):
        _snapd_interfaces.connect(('vlc', 'plug'), ('core', 'myslot'))
        body = mock_client.post.call_args.kwargs['body']
        assert body['plugs'] == [{'snap': 'vlc', 'plug': 'plug'}]
        assert body['slots'] == [{'snap': 'core', 'slot': 'myslot'}]

    def test_connect_slot_pair_with_empty_name(self, mock_client: MockClient):
        # An explicit pair with an empty slot name is passed through unchanged.
        _snapd_interfaces.connect(('vlc', 'plug'), ('core', ''))
        body = mock_client.post.call_args.kwargs['body']
        assert body['slots'] == [{'snap': 'core', 'slot': ''}]

    def test_connect_slot_pair_with_empty_snap(self, mock_client: MockClient):
        # An explicit pair with an empty slot snap (the ':name' / system-slot form) is passed
        # through unchanged, for snapd to resolve the empty snap to the system snap.
        _snapd_interfaces.connect(('vlc', 'plug'), ('', 'myslot'))
        body = mock_client.post.call_args.kwargs['body']
        assert body['slots'] == [{'snap': '', 'slot': 'myslot'}]

    def test_connect_slot_none_and_empty_pair_and_empty_string_all_equivalent(
        self, mock_client: MockClient
    ):
        # None, ('', ''), and '' all normalise to a fully-empty slot for snapd to resolve.
        bodies: list[object] = []
        for slot in (None, ('', ''), ''):
            _snapd_interfaces.connect(('vlc', 'mount-observe'), slot)
            bodies.append(mock_client.post.call_args.kwargs['body']['slots'])
        assert bodies == [[{'snap': '', 'slot': ''}]] * 3

    def test_connect_action_and_endpoint(self, mock_client: MockClient):
        _snapd_interfaces.connect(('vlc', 'mount-observe'))
        mock_client.post.assert_called_once()
        assert mock_client.post.call_args.args[0] == '/v2/interfaces'
        assert mock_client.post.call_args.kwargs['body']['action'] == 'connect'

    def test_connect_bare_string_plug_normalises_to_empty_plug_name(self, mock_client: MockClient):
        # A bare string plug normalises to (snap, '') -- the whole string is the snap name, so
        # it is never split into characters. snapd then rejects the empty plug name. Even a
        # 2-char string (which would unpack silently) is treated as the snap name.
        _snapd_interfaces.connect('ab')  # pyright: ignore[reportArgumentType]
        body = mock_client.post.call_args.kwargs['body']
        assert body['plugs'] == [{'snap': 'ab', 'plug': ''}]

    def test_connect_non_pair_tuple_raises(self, mock_client: MockClient):
        # A tuple that is not a 2-item pair fails fast with a ValueError.
        with pytest.raises(ValueError, match='unpack'):
            _snapd_interfaces.connect(('a', 'b', 'c'))  # pyright: ignore[reportArgumentType]
        mock_client.post.assert_not_called()

    def test_connect_probes_plug_before_slot_on_api_error(self, mock_client: MockClient):
        # On an API error, connect probes the named snaps -- plug first -- and re-raises the
        # not-installed one as NotFoundError. Here the plug snap is installed and the slot is not.
        mock_client.post.side_effect = _api_error()

        def fake_get(path: str, query: object = None) -> dict[str, object]:
            if path == '/v2/snaps/absent-slot':
                raise _not_found()
            return {}  # plug snap is installed

        mock_client.get.side_effect = fake_get
        with pytest.raises(NotFoundError):
            _snapd_interfaces.connect(('installed-plug', 'p'), ('absent-slot', 's'))
        # The plug snap is probed before the slot snap (matching snapd's blame order).
        assert mock_client.get.call_args_list[0].args[0] == '/v2/snaps/installed-plug'

    def test_connect_reraises_original_when_snaps_installed(self, mock_client: MockClient):
        # If the probe finds every named snap installed, the original API error is re-raised
        # unchanged (the failure was something other than a missing snap).
        original = _api_error('snap "installed" has no plug named "foo"')
        mock_client.post.side_effect = original
        mock_client.get.return_value = {}  # all probed snaps installed
        with pytest.raises(APIError) as ctx:
            _snapd_interfaces.connect(('installed', 'foo'), 'snapd')
        assert ctx.value is original


class TestDisconnect:
    def test_disconnect_plug_only(self, mock_client: MockClient):
        # Single-sided: plug specified, slot side left empty for snapd to match against.
        _snapd_interfaces.disconnect(('vlc', 'mount-observe'))
        body = mock_client.post.call_args.kwargs['body']
        assert body['plugs'] == [{'snap': 'vlc', 'plug': 'mount-observe'}]
        assert body['slots'] == [{'snap': '', 'slot': ''}]

    def test_disconnect_slot_only(self, mock_client: MockClient):
        _snapd_interfaces.disconnect(slot=('core', 'myslot'))
        body = mock_client.post.call_args.kwargs['body']
        assert body['plugs'] == [{'snap': '', 'plug': ''}]
        assert body['slots'] == [{'snap': 'core', 'slot': 'myslot'}]

    def test_disconnect_both_sides(self, mock_client: MockClient):
        _snapd_interfaces.disconnect(('vlc', 'plug'), ('core', 'slot'))
        body = mock_client.post.call_args.kwargs['body']
        assert body['plugs'] == [{'snap': 'vlc', 'plug': 'plug'}]
        assert body['slots'] == [{'snap': 'core', 'slot': 'slot'}]

    def test_disconnect_empty_snap_pairs_pass_through(self, mock_client: MockClient):
        # An empty snap with a name (the 'empty snap means system' form) is passed through as-is
        # for snapd to remap to the system snap -- on either the plug or the slot side.
        _snapd_interfaces.disconnect(('', 'myplug'))
        plugs = mock_client.post.call_args.kwargs['body']['plugs']
        assert plugs == [{'snap': '', 'plug': 'myplug'}]
        _snapd_interfaces.disconnect(slot=('', 'myslot'))
        slots = mock_client.post.call_args.kwargs['body']['slots']
        assert slots == [{'snap': '', 'slot': 'myslot'}]

    def test_disconnect_all_empty_flows_through_to_api(self, mock_client: MockClient):
        # No client-side guard: an all-empty disconnect (from no args, or from explicit empty
        # pairs, which encode identically) is sent to snapd, which rejects it. This matches
        # connect's all-empty behaviour -- we don't second-guess snapd's validation.
        for args in [(), (('', ''),), (('', ''), ('', ''))]:
            mock_client.post.reset_mock()
            _snapd_interfaces.disconnect(*args)
            body = mock_client.post.call_args.kwargs['body']
            assert body['plugs'] == [{'snap': '', 'plug': ''}]
            assert body['slots'] == [{'snap': '', 'slot': ''}]

    def test_disconnect_forget(self, mock_client: MockClient):
        _snapd_interfaces.disconnect(('vlc', 'mount-observe'), forget=True)
        body = mock_client.post.call_args.kwargs['body']
        assert body['forget'] is True

    def test_disconnect_no_forget_key_by_default(self, mock_client: MockClient):
        _snapd_interfaces.disconnect(('vlc', 'mount-observe'))
        assert 'forget' not in mock_client.post.call_args.kwargs['body']

    def test_disconnect_action(self, mock_client: MockClient):
        _snapd_interfaces.disconnect(('vlc', 'mount-observe'))
        body = mock_client.post.call_args.kwargs['body']
        assert body['action'] == 'disconnect'

    def test_disconnect_interfaces_unchanged_suppressed(self, mock_client: MockClient):
        # The try/except in disconnect() suppresses _InterfacesUnchangedError
        # to make disconnect symmetric with connect (both are no-ops when nothing changes).
        mock_client.post.side_effect = _InterfacesUnchangedError(
            'nothing to do',
            kind='interfaces-unchanged',
            value='',
            status_code=400,
            status='Bad Request',
        )
        _snapd_interfaces.disconnect(('vlc', 'mount-observe'))  # Should not raise.

    def test_disconnect_interfaces_unchanged_suppressed_with_forget(self, mock_client: MockClient):
        # _InterfacesUnchangedError is suppressed even when forget=True.
        mock_client.post.side_effect = _InterfacesUnchangedError(
            'nothing to do',
            kind='interfaces-unchanged',
            value='',
            status_code=400,
            status='Bad Request',
        )
        _snapd_interfaces.disconnect(('vlc', 'mount-observe'), forget=True)  # Should not raise.

    def test_disconnect_probes_and_raises_not_found(self, mock_client: MockClient):
        # disconnect also converts a not-installed API error into a typed NotFoundError.
        mock_client.post.side_effect = _api_error()
        mock_client.get.side_effect = _not_found()
        with pytest.raises(NotFoundError):
            _snapd_interfaces.disconnect(('absent', 'p'))

    def test_disconnect_unchanged_suppressed_before_probe(self, mock_client: MockClient):
        # _InterfacesUnchangedError is caught before the not-installed probe: it is suppressed,
        # and the probe (which would raise) is never reached.
        mock_client.post.side_effect = _InterfacesUnchangedError(
            'nothing to do', kind='interfaces-unchanged', value='', status_code=400
        )
        mock_client.get.side_effect = _not_found()  # would raise if the probe ran
        _snapd_interfaces.disconnect(('vlc', 'mount-observe'))  # Should not raise.
        mock_client.get.assert_not_called()
