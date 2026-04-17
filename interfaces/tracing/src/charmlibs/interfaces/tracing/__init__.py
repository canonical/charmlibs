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

"""The charmlibs.interfaces.tracing package."""

from ._tracing import (
    AmbiguousRelationUsageError,
    # BUILTIN_JUJU_KEYS,
    BrokenEvent,
    # DEFAULT_RELATION_NAME,
    DataAccessPermissionError,
    DataValidationError,
    DatabagModel,
    EndpointChangedEvent,
    EndpointRemovedEvent,
    # LIBAPI,
    # LIBID,
    # LIBPATCH,
    NotReadyError,
    # PYDEPS,
    ProtocolNotRequestedError,
    ProtocolType,
    RawReceiver,
    # RELATION_INTERFACE_NAME,
    Receiver,
    ReceiverProtocol,
    RelationInterfaceMismatchError,
    RelationNotFoundError,
    RelationRoleMismatchError,
    RequestEvent,
    TracingEndpointProvider,
    TracingEndpointProviderEvents,
    TracingEndpointRequirer,
    TracingEndpointRequirerEvents,
    TracingError,
    TracingProviderAppData,
    TracingRequirerAppData,
    TransportProtocolType,
    charm_tracing_config,
    receiver_protocol_to_transport_protocol,
)
from ._version import __version__ as __version__

__all__ = [
    "__version__",
    "AmbiguousRelationUsageError",
    # "BUILTIN_JUJU_KEYS",
    "BrokenEvent",
    # "DEFAULT_RELATION_NAME",
    "DataAccessPermissionError",
    "DataValidationError",
    "DatabagModel",
    "EndpointChangedEvent",
    "EndpointRemovedEvent",
    # "LIBAPI",
    # "LIBID",
    # "LIBPATCH",
    "NotReadyError",
    # "PYDEPS",
    "ProtocolNotRequestedError",
    "ProtocolType",
    "RawReceiver",
    # "RELATION_INTERFACE_NAME",
    "Receiver",
    "ReceiverProtocol",
    "RelationInterfaceMismatchError",
    "RelationNotFoundError",
    "RelationRoleMismatchError",
    "RequestEvent",
    "TracingEndpointProvider",
    "TracingEndpointProviderEvents",
    "TracingEndpointRequirer",
    "TracingEndpointRequirerEvents",
    "TracingError",
    "TracingProviderAppData",
    "TracingRequirerAppData",
    "TransportProtocolType",
    "charm_tracing_config",
    "receiver_protocol_to_transport_protocol",
]
