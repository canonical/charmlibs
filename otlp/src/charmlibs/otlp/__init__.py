# Copyright 2026 Canonical Ltd.
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

"""The charmlibs.otlp package.

OTLP is a general-purpose telemetry data delivery protocol defined by
[the design goals of the project]
(https://github.com/open-telemetry/opentelemetry-proto/blob/main/docs/design-goals.md)
and
[requirements](https://github.com/open-telemetry/opentelemetry-proto/blob/main/docs/requirements.md).
Currently, the charm observability ecosystem is designed around APIs
which accept pushing/pulling a single telemetry type.
These applications are adapting and serving their own OTLP endpoints in their APIs,
offering telemetry uniformity across the ecosystem.
The `charmlibs.otlp` package enables charmed workloads which serve OTLP endpoints to
publish this information in the databag,
allowing senders to push data there.
The support for protocols and telemetries is restricted by the workloads implementing this library,
which tracks what upstream supports.
The package also enables a consumer to send `alerting` and
`recording` rules for `promql` and `logql` query types to a provider.
"""

from ._otlp import (
    OtlpConsumer,
    OtlpEndpoint,
    OtlpProvider,
    OtlpProviderAppData,
)
from ._version import __version__ as __version__

__all__ = [
    # only the names listed in __all__ are imported when executing:
    # from charmlibs.otlp import *
    'OtlpConsumer',
    'OtlpEndpoint',
    'OtlpProvider',
    'OtlpProviderAppData',
]
