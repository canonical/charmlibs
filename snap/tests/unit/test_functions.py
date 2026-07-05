# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

from charmlibs.snap import _functions
from charmlibs.snap import _snapd_snaps as _snapd
from charmlibs.snap._errors import NotFoundError
from charmlibs.snap._utils import normalize_channel


def make_info(
    channel: str = 'latest/stable',
    revision: int | str = 29,
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
def mock_snapd(monkeypatch: pytest.MonkeyPatch) -> MockSnapd:
    mocks = MockSnapd(info=MagicMock(), install=MagicMock(), refresh=MagicMock())
    monkeypatch.setattr(_snapd, 'info', mocks.info)
    monkeypatch.setattr(_snapd, 'install', mocks.install)
    monkeypatch.setattr(_snapd, 'refresh', mocks.refresh)
    return mocks


class TestGetInfo:
    def test_installed(self, mock_snapd: MockSnapd):
        expected = make_info()
        mock_snapd.info.return_value = expected
        result = _functions._get_info('hello-world')
        mock_snapd.info.assert_called_once_with('hello-world')
        assert result is expected

    def test_not_installed_returns_none(self, mock_snapd: MockSnapd):
        mock_snapd.info.side_effect = NotFoundError(
            'snap "hello-world" is not installed',
            kind='snap-not-found',
            value='',
            status_code=404,
            status='Not Found',
        )
        result = _functions._get_info('hello-world')
        assert result is None


class TestEnsureRevision:
    def test_not_installed(self, mock_snapd: MockSnapd):
        mock_snapd.info.return_value = None
        result = _functions.ensure_revision('hello-world', revision=5)
        mock_snapd.install.assert_called_once_with('hello-world', revision=5, classic=False)
        assert result is True

    def test_not_installed_classic(self, mock_snapd: MockSnapd):
        mock_snapd.info.return_value = None
        _functions.ensure_revision('hello-world', revision=5, classic=True)
        mock_snapd.install.assert_called_once_with('hello-world', revision=5, classic=True)

    def test_installed_same_revision(self, mock_snapd: MockSnapd):
        mock_snapd.info.return_value = make_info(revision=5)
        result = _functions.ensure_revision('hello-world', revision=5)
        mock_snapd.refresh.assert_not_called()
        assert result is False

    def test_installed_different_revision(self, mock_snapd: MockSnapd):
        mock_snapd.info.return_value = make_info(revision=5)
        result = _functions.ensure_revision('hello-world', revision=6)
        mock_snapd.refresh.assert_called_once_with('hello-world', revision=6)
        assert result is True

    def test_classic_not_passed_to_refresh(self, mock_snapd: MockSnapd):
        mock_snapd.info.return_value = make_info(revision=5)
        _functions.ensure_revision('hello-world', revision=6, classic=True)
        call_kwargs = mock_snapd.refresh.call_args.kwargs
        assert 'classic' not in call_kwargs


class TestEnsure:
    def test_not_installed(self, mock_snapd: MockSnapd):
        mock_snapd.info.return_value = None
        result = _functions.ensure('hello-world')
        mock_snapd.install.assert_called_once_with('hello-world', channel=None, classic=False)
        assert result is True

    def test_not_installed_channel(self, mock_snapd: MockSnapd):
        mock_snapd.info.return_value = None
        _functions.ensure('hello-world', channel='edge')
        mock_snapd.install.assert_called_once_with('hello-world', channel='edge', classic=False)

    def test_not_installed_classic(self, mock_snapd: MockSnapd):
        mock_snapd.info.return_value = None
        _functions.ensure('hello-world', classic=True)
        mock_snapd.install.assert_called_once_with('hello-world', channel=None, classic=True)

    def test_installed_different_channel(self, mock_snapd: MockSnapd):
        mock_snapd.info.return_value = make_info(channel='latest/stable')
        result = _functions.ensure('hello-world', channel='edge')
        mock_snapd.refresh.assert_called_once_with('hello-world', channel='edge')
        assert result is True

    def test_installed_same_channel_update_true(self, mock_snapd: MockSnapd):
        mock_snapd.info.return_value = make_info(channel='latest/stable')
        mock_snapd.refresh.return_value = True
        result = _functions.ensure('hello-world', channel='latest/stable')
        mock_snapd.refresh.assert_called_once_with('hello-world', channel='latest/stable')
        assert result is True

    def test_installed_same_channel_update_false(self, mock_snapd: MockSnapd):
        mock_snapd.info.return_value = make_info(channel='latest/stable')
        result = _functions.ensure('hello-world', channel='latest/stable', update=False)
        mock_snapd.refresh.assert_not_called()
        assert result is False

    def test_installed_no_channel_update_false(self, mock_snapd: MockSnapd):
        mock_snapd.info.return_value = make_info()
        result = _functions.ensure('hello-world', update=False)
        mock_snapd.refresh.assert_not_called()
        assert result is False

    def test_installed_normalized_channel(self, mock_snapd: MockSnapd):
        mock_snapd.info.return_value = make_info(channel='latest/stable')
        result = _functions.ensure('hello-world', channel='stable', update=False)
        mock_snapd.refresh.assert_not_called()
        assert result is False

    def test_no_updates_available_returns_false(self, mock_snapd: MockSnapd):
        mock_snapd.info.return_value = make_info(channel='latest/stable')
        mock_snapd.refresh.return_value = False
        result = _functions.ensure('hello-world', channel='latest/stable')
        assert result is False

    def test_classic_not_passed_to_refresh(self, mock_snapd: MockSnapd):
        mock_snapd.info.return_value = make_info(channel='latest/stable')
        _functions.ensure('hello-world', channel='edge', classic=True)
        call_kwargs = mock_snapd.refresh.call_args.kwargs
        assert 'classic' not in call_kwargs

    def test_empty_channel_treated_as_none(self, mock_snapd: MockSnapd):
        # channel='' is falsy, so it's treated the same as channel=None:
        # no channel-mismatch refresh, and with update=False no refresh at all.
        mock_snapd.info.return_value = make_info(channel='latest/stable')
        result = _functions.ensure('hello-world', channel='', update=False)
        mock_snapd.refresh.assert_not_called()
        assert result is False


@pytest.mark.parametrize(
    'channel,expected',
    [
        ('', ''),
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
    assert normalize_channel(channel) == expected
