# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

from charmlibs.snap import _functions, _snapd
from charmlibs.snap._utils import _normalize_channel

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from pytest_mock import MockerFixture


def make_info(
    channel: str = 'latest/stable',
    revision: int = 29,
    classic: bool = False,
    hold: str | None = None,
) -> _snapd.Info:
    return _snapd.Info(
        name='hello-world',
        channel=channel,
        revision=revision,
        version='6.4',
        classic=classic,
        hold=hold,
    )


@dataclass
class MockSnapd:
    info: MagicMock
    install: MagicMock
    refresh: MagicMock


@pytest.fixture
def mock_snapd(mocker: MockerFixture) -> MockSnapd:
    return MockSnapd(
        info=mocker.patch('charmlibs.snap._snapd.info'),
        install=mocker.patch('charmlibs.snap._snapd.install'),
        refresh=mocker.patch('charmlibs.snap._snapd.refresh'),
    )


class TestEnsure:
    def test_not_installed(self, mock_snapd: MockSnapd):
        mock_snapd.info.return_value = None
        result = _functions.ensure('hello-world')
        mock_snapd.install.assert_called_once()
        assert result is True

    def test_not_installed_channel(self, mock_snapd: MockSnapd):
        mock_snapd.info.return_value = None
        _functions.ensure('hello-world', channel='edge')
        mock_snapd.install.assert_called_once_with(
            'hello-world', channel='edge', revision=None, classic=False
        )

    def test_not_installed_revision(self, mock_snapd: MockSnapd):
        mock_snapd.info.return_value = None
        _functions.ensure('hello-world', revision=5)
        mock_snapd.install.assert_called_once_with(
            'hello-world', channel=None, revision=5, classic=False
        )

    def test_not_installed_classic(self, mock_snapd: MockSnapd):
        mock_snapd.info.return_value = None
        _functions.ensure('hello-world', classic=True)
        mock_snapd.install.assert_called_once_with(
            'hello-world', channel=None, revision=None, classic=True
        )

    def test_installed_same_channel(self, mock_snapd: MockSnapd):
        mock_snapd.info.return_value = make_info(channel='latest/stable')
        result = _functions.ensure('hello-world', channel='latest/stable')
        mock_snapd.refresh.assert_not_called()
        assert result is False

    def test_installed_normalized_channel(self, mock_snapd: MockSnapd):
        mock_snapd.info.return_value = make_info(channel='latest/stable')
        # 'stable' normalizes to 'latest/stable'
        result = _functions.ensure('hello-world', channel='stable')
        mock_snapd.refresh.assert_not_called()
        assert result is False

    def test_installed_diff_channel(self, mock_snapd: MockSnapd):
        mock_snapd.info.return_value = make_info(channel='latest/stable')
        result = _functions.ensure('hello-world', channel='edge')
        mock_snapd.refresh.assert_called_once()
        assert result is True

    def test_installed_same_revision(self, mock_snapd: MockSnapd):
        mock_snapd.info.return_value = make_info(revision=5)
        result = _functions.ensure('hello-world', revision=5)
        mock_snapd.refresh.assert_not_called()
        assert result is False

    def test_installed_diff_revision(self, mock_snapd: MockSnapd):
        mock_snapd.info.return_value = make_info(revision=5)
        result = _functions.ensure('hello-world', revision=6)
        mock_snapd.refresh.assert_called_once()
        assert result is True

    def test_no_channel_no_revision(self, mock_snapd: MockSnapd):
        mock_snapd.info.return_value = make_info()
        result = _functions.ensure('hello-world')
        mock_snapd.install.assert_not_called()
        mock_snapd.refresh.assert_not_called()
        assert result is False

    def test_both_raises(self, mock_snapd: MockSnapd):
        with pytest.raises(ValueError):
            _functions.ensure('hello-world', channel='edge', revision=5)
        mock_snapd.info.assert_not_called()

    def test_classic_passed_to_install(self, mock_snapd: MockSnapd):
        mock_snapd.info.return_value = None
        _functions.ensure('hello-world', classic=True)
        call_kwargs = mock_snapd.install.call_args.kwargs
        assert call_kwargs['classic'] is True


@pytest.mark.parametrize(
    'channel,expected',
    [
        ('stable', 'latest/stable'),
        ('candidate', 'latest/candidate'),
        ('beta', 'latest/beta'),
        ('edge', 'latest/edge'),
        ('mytrack', 'mytrack/stable'),
        ('latest/stable', 'latest/stable'),
        ('latest/stable/hotfix', 'latest/stable/hotfix'),
        ('3/stable', '3/stable'),
    ],
)
def test_normalize_channel(channel: str, expected: str):
    assert _normalize_channel(channel) == expected
