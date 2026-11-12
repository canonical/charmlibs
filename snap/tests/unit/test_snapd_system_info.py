# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

# pyright: reportPrivateUsage=false

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from charmlibs.snap import _snapd_system_info as _snapd
from charmlibs.snap._errors import BadResponseError

if TYPE_CHECKING:
    from conftest import MockClient


class TestSystemInfo:
    def test_system_info(self, mock_client: MockClient):
        # A minimal GET /v2/system-info response, plus one field we don't read to pin
        # that additional fields are ignored.
        mock_client.get.return_value = {'architecture': 'amd64', 'version': '2.78'}
        info = _snapd.system_info()
        assert info.architecture == 'amd64'
        mock_client.get.assert_called_once_with('/v2/system-info')

    def test_architecture_returned_verbatim(self, mock_client: MockClient):
        # No validation against a fixed set of architectures: snapd defines the vocabulary,
        # so a value this library doesn't know is passed through unchanged.
        mock_client.get.return_value = {'architecture': 'future-arch'}
        assert _snapd.system_info().architecture == 'future-arch'

    def test_repr(self, mock_client: MockClient):
        mock_client.get.return_value = {'architecture': 'amd64'}
        assert repr(_snapd.system_info()) == "SystemInfo(architecture='amd64')"

    def test_non_dict_result_raises_bad_response(self, mock_client: MockClient):
        result = ['amd64']
        mock_client.get.return_value = result
        with pytest.raises(BadResponseError) as ctx:
            _snapd.system_info()
        assert 'Unexpected response type' in ctx.value.message
        assert "'list'" in ctx.value.message
        assert ctx.value._response == result

    def test_missing_architecture_raises_bad_response(self, mock_client: MockClient):
        result = {'version': '2.78'}
        mock_client.get.return_value = result
        with pytest.raises(BadResponseError) as ctx:
            _snapd.system_info()
        assert 'Could not read' in ctx.value.message
        assert 'architecture' in ctx.value.message  # the KeyError is included in the message
        assert ctx.value._response == result
