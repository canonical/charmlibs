# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

# pyright: reportPrivateUsage=false

from __future__ import annotations

from charmlibs.snap._errors import (
    SnapAlreadyInstalledError,
    SnapAPIError,
    SnapBadResponseError,
    SnapChangeError,
    SnapError,
    SnapNeedsClassicError,
    SnapNotFoundError,
    SnapOptionNotFoundError,
    _error_type_from_result_kind,
    _SnapInterfacesUnchangedError,
    _SnapNoUpdatesAvailableError,
)


class TestErrorTypeFromResultKind:
    def test_snap_already_installed(self):
        assert _error_type_from_result_kind('snap-already-installed') is SnapAlreadyInstalledError

    def test_option_not_found(self):
        assert _error_type_from_result_kind('option-not-found') is SnapOptionNotFoundError

    def test_snap_needs_classic(self):
        assert _error_type_from_result_kind('snap-needs-classic') is SnapNeedsClassicError

    def test_snap_not_found(self):
        assert _error_type_from_result_kind('snap-not-found') is SnapNotFoundError

    def test_snap_not_installed(self):
        assert _error_type_from_result_kind('snap-not-installed') is SnapNotFoundError

    def test_snap_no_update_available(self):
        assert (
            _error_type_from_result_kind('snap-no-update-available')
            is _SnapNoUpdatesAvailableError
        )

    def test_interfaces_unchanged(self):
        assert (
            _error_type_from_result_kind('interfaces-unchanged') is _SnapInterfacesUnchangedError
        )

    def test_unknown_kind(self):
        assert _error_type_from_result_kind('bogus-kind') is SnapAPIError

    def test_empty_string(self):
        assert _error_type_from_result_kind('') is SnapAPIError

    def test_all_results_are_snap_api_error_subclasses(self):
        kinds = [
            'snap-already-installed',
            'app-not-found',
            'option-not-found',
            'snap-needs-classic',
            'snap-not-found',
            'snap-not-installed',
            'snap-no-update-available',
            'interfaces-unchanged',
            'bogus-kind',
            '',
        ]
        for kind in kinds:
            assert issubclass(_error_type_from_result_kind(kind), SnapAPIError), kind


class TestSnapError:
    def _make(
        self,
        message: str = 'something went wrong',
        kind: str = 'charmlibs-snap',
        value: str = 'extra-info',
        status_code: int | None = 400,
        status: str | None = 'Bad Request',
    ) -> SnapError:
        return SnapError(
            message=message,
            kind=kind,
            value=value,
            status_code=status_code,
            status=status,
        )

    def test_message(self):
        err = self._make(message='the message')
        assert err.message == 'the message'
        assert str(err) == 'the message'

    def test_kind(self):
        err = self._make(kind='snap-not-found')
        assert err.kind == 'snap-not-found'

    def test_value(self):
        err = self._make(value='myvalue')
        assert err.value == 'myvalue'

    def test_private_status(self):
        err = self._make(status_code=400, status='Bad Request')
        assert err._status_code == 400
        assert err._status == 'Bad Request'

    def test_none_status_code(self):
        err = self._make(status_code=None, status=None)
        assert err._status_code is None
        assert err._status is None

    def test_repr(self):
        err = self._make(message='msg', kind='k', value='v', status_code=400, status='Bad Request')
        r = repr(err)
        assert 'SnapError' in r
        assert 'msg' in r
        assert "'k'" in r
        assert "'v'" in r
        assert '400' in r
        assert 'Bad Request' in r

    def test_subclass_repr(self):
        err = SnapNotFoundError(
            'snap not found',
            kind='snap-not-installed',
            value='',
            status_code=404,
            status='Not Found',
        )
        assert 'SnapNotFoundError' in repr(err)

    def test_snap_api_error_is_subclass_of_snap_error(self):
        assert issubclass(SnapAPIError, SnapError)

    def test_snap_bad_response_error_is_subclass(self):
        assert issubclass(SnapBadResponseError, SnapError)
        assert not issubclass(SnapBadResponseError, SnapAPIError)

    def test_snap_change_error_is_subclass(self):
        assert issubclass(SnapChangeError, SnapAPIError)
        assert issubclass(SnapChangeError, SnapError)

    def test_specific_errors_are_snap_api_error_subclasses(self):
        for cls in [
            SnapAlreadyInstalledError,
            SnapNotFoundError,
            SnapNeedsClassicError,
            SnapOptionNotFoundError,
            _SnapNoUpdatesAvailableError,
            _SnapInterfacesUnchangedError,
        ]:
            assert issubclass(cls, SnapAPIError), cls
            assert issubclass(cls, SnapError), cls
