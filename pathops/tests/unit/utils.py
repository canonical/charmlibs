# Copyright 2025 Canonical Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Mocks for use in tests."""

from __future__ import annotations

from ops import pebble


def raise_unknown_api_error(*args: object, **kwargs: object):
    raise pebble.APIError(body={}, code=9000, status='', message='')


def raise_connection_error(*args: object, **kwargs: object):
    raise pebble.ConnectionError()


def raise_not_found(*args: object, **kwargs: object):
    raise pebble.PathError(kind='not-found', message='not found')


def raise_permission_denied(*args: object, **kwargs: object):
    raise pebble.PathError(kind='permission-denied', message='')


def raise_unknown_path_error(*args: object, **kwargs: object):
    raise pebble.PathError(kind='unknown-kind', message='unknown-message')


def raise_unknown_os_error(*args: object, **kwargs: object):
    raise OSError(9000, 'unknown-kind', 'unknown-message')
