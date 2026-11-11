# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

# pyright: reportPrivateUsage=false

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from charmlibs.snap import _snapd_system_info as _snapd
from charmlibs.snap._errors import BadResponseError
from conftest import result_of

if TYPE_CHECKING:
    from conftest import MockClient


class TestSystemArch:
    def test_system_arch(self, mock_client: MockClient):
        # Captured from a real GET /v2/system-info on Ubuntu 26.04 with snapd 2.78.
        mock_client.get.return_value = result_of('system_info.json')
        assert _snapd.system_arch() == 'amd64'
        mock_client.get.assert_called_once_with('/v2/system-info')

    def test_system_arch_returned_verbatim(self, mock_client: MockClient):
        # No validation against a fixed set of architectures: snapd defines the vocabulary,
        # so a value this library doesn't know is passed through unchanged.
        mock_client.get.return_value = {'architecture': 'future-arch'}
        assert _snapd.system_arch() == 'future-arch'

    def test_non_dict_result_raises_bad_response(self, mock_client: MockClient):
        mock_client.get.return_value = ['amd64']
        with pytest.raises(BadResponseError) as ctx:
            _snapd.system_arch()
        assert 'Unexpected response type' in ctx.value.message
        assert "'list'" in ctx.value.message
        assert ctx.value._response == ['amd64']

    def test_missing_architecture_raises_bad_response(self, mock_client: MockClient):
        result = {'version': '2.78'}
        mock_client.get.return_value = result
        with pytest.raises(BadResponseError) as ctx:
            _snapd.system_arch()
        assert 'Could not read' in ctx.value.message
        assert ctx.value._response == result

    @pytest.mark.parametrize('architecture', [42, ['amd64'], {'name': 'amd64'}])
    def test_non_string_architecture_raises_bad_response(
        self, mock_client: MockClient, architecture: object
    ):
        result = {'architecture': architecture}
        mock_client.get.return_value = result
        with pytest.raises(BadResponseError) as ctx:
            _snapd.system_arch()
        assert 'Could not read' in ctx.value.message
        assert ctx.value._response == result

    def test_empty_architecture_raises_bad_response(self, mock_client: MockClient):
        result = {'architecture': ''}
        mock_client.get.return_value = result
        with pytest.raises(BadResponseError) as ctx:
            _snapd.system_arch()
        assert 'Could not read' in ctx.value.message
        assert ctx.value._response == result
