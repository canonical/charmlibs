# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

from charmlibs.snap import _functions, _snapd_conf
from charmlibs.snap._errors import BadResponseError, OptionNotFoundError


@dataclass
class MockConf:
    get_one: MagicMock
    set: MagicMock


@pytest.fixture
def mock_conf(monkeypatch: pytest.MonkeyPatch) -> MockConf:
    mocks = MockConf(get_one=MagicMock(), set=MagicMock())
    monkeypatch.setattr(_snapd_conf, 'get_one', mocks.get_one)
    monkeypatch.setattr(_snapd_conf, 'set', mocks.set)
    return mocks


class TestEnsureVitalityHint:
    def test_unset_adds_snap(self, mock_conf: MockConf):
        # Captured from snapd when the option has never been set (or was unset).
        mock_conf.get_one.side_effect = OptionNotFoundError(
            'snap "core" has no "resilience" configuration option',
            kind='option-not-found',
            value={'SnapName': 'core', 'Key': 'resilience'},
        )
        result = _functions.ensure_vitality_hint('foo')
        mock_conf.get_one.assert_called_once_with('system', 'resilience.vitality-hint')
        mock_conf.set.assert_called_once_with('system', {'resilience.vitality-hint': 'foo'})
        assert result is True

    def test_empty_string_adds_snap(self, mock_conf: MockConf):
        # snapd stores '' when the option is set to an empty string.
        mock_conf.get_one.return_value = ''
        result = _functions.ensure_vitality_hint('foo')
        mock_conf.set.assert_called_once_with('system', {'resilience.vitality-hint': 'foo'})
        assert result is True

    def test_appends_after_existing_snaps(self, mock_conf: MockConf):
        mock_conf.get_one.return_value = 'bar,baz'
        result = _functions.ensure_vitality_hint('foo')
        mock_conf.set.assert_called_once_with(
            'system', {'resilience.vitality-hint': 'bar,baz,foo'}
        )
        assert result is True

    @pytest.mark.parametrize('current', ['foo', 'foo,bar', 'bar,foo', 'bar,foo,baz'])
    def test_already_listed_is_no_op(self, mock_conf: MockConf, current: str):
        mock_conf.get_one.return_value = current
        result = _functions.ensure_vitality_hint('foo')
        mock_conf.set.assert_not_called()
        assert result is False

    def test_instance_name_is_distinct_from_snap_name(self, mock_conf: MockConf):
        mock_conf.get_one.return_value = 'foo'
        result = _functions.ensure_vitality_hint('foo_bar')
        mock_conf.set.assert_called_once_with(
            'system', {'resilience.vitality-hint': 'foo,foo_bar'}
        )
        assert result is True

    @pytest.mark.parametrize('snap', ['', ' ', 'foo,bar', ' foo', 'foo '])
    def test_invalid_snap_name_raises_before_request(self, mock_conf: MockConf, snap: str):
        with pytest.raises(ValueError, match='snap name'):
            _functions.ensure_vitality_hint(snap)
        mock_conf.get_one.assert_not_called()
        mock_conf.set.assert_not_called()

    def test_non_string_value_raises_bad_response(self, mock_conf: MockConf):
        mock_conf.get_one.return_value = {'foo': 1}
        with pytest.raises(BadResponseError):
            _functions.ensure_vitality_hint('foo')
        mock_conf.set.assert_not_called()

    def test_snapd_raises_before_request(self, mock_conf: MockConf):
        with pytest.raises(ValueError, match='snapd'):
            _functions.ensure_vitality_hint('snapd')
        mock_conf.get_one.assert_not_called()
        mock_conf.set.assert_not_called()
