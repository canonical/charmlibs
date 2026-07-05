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

"""Type checking tests for install and refresh overloads.

Pyright will error if a ``# pyright: ignore`` comment is unnecessary,
so each annotated line is a genuine type error.
"""

from charmlibs.snap import install, refresh


def typecheck_install_ok(channel: str | None, revision: int | str | None) -> None:
    install('foo')
    install('foo', channel=channel)
    install('foo', channel='stable')
    install('foo', channel=None)
    install('foo', revision=revision)
    install('foo', revision=42)
    install('foo', revision=None)
    install('foo', channel='stable', revision=None)
    install('foo', channel=None, revision=42)


def typecheck_install_error() -> None:
    install('foo', channel='stable', revision=42)  # pyright: ignore[reportCallIssue, reportArgumentType]


def typecheck_refresh_ok(channel: str | None, revision: int | str | None) -> None:
    refresh('foo')
    refresh('foo', channel)
    refresh('foo', 'stable')
    refresh('foo', None)
    refresh('foo', 'stable', revision=None)
    refresh('foo', None, revision=42)
    refresh('foo', channel=channel)
    refresh('foo', channel='stable')
    refresh('foo', channel=None)
    refresh('foo', channel='stable', revision=None)
    refresh('foo', channel=None, revision=42)
    refresh('foo', revision=revision)
    refresh('foo', revision=42)
    refresh('foo', revision=None)


def typecheck_refresh_error() -> None:
    refresh('foo', 'stable', revision=42)  # pyright: ignore[reportCallIssue, reportArgumentType]
