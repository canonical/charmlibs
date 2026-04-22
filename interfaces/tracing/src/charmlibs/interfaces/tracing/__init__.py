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

"""The charmlibs.interfaces.tracing package.

## Requirer Library Usage

Charms seeking to push traces to Tempo, must do so using the `TracingEndpointRequirer`
object from this charm library. For the simplest use cases, using the `TracingEndpointRequirer`
object only requires instantiating it, typically in the constructor of your charm. The
`TracingEndpointRequirer` constructor requires the name of the relation over which a tracing
endpoint is exposed by the Tempo charm, and a list of protocols it intends to send traces with.
This relation must use the `tracing` interface.
The `TracingEndpointRequirer` object may be instantiated as follows


```py
from charmlibs.interfaces.tracing import TracingEndpointRequirer

def __init__(self, *args):
    super().__init__(*args)
    # ...
    self.tracing = TracingEndpointRequirer(self,
        protocols=['otlp_grpc', 'otlp_http', 'jaeger_http_thrift']
    )
    # ...
```

Note that the first argument (`self`) to `TracingEndpointRequirer` is always a reference to the
parent charm.

Alternatively to providing the list of requested protocols at init time, the charm can do it at
any point in time by calling the
`TracingEndpointRequirer.request_protocols(*protocol:str, relation:Relation | None)` method.
Using this method also allows you to use per-relation protocols.

Units of requirer charms obtain the tempo endpoint to which they will push their traces by calling
`TracingEndpointRequirer.get_endpoint(protocol: str)`, where `protocol` is, for example:
- `otlp_grpc`
- `otlp_http`
- `zipkin`
- `tempo`

If the `protocol` is not in the list of protocols that the charm requested at endpoint set-up time,
the library will raise an error.

We recommend that you scale up your tracing provider and relate it to an ingress so that your
tracing requests go through the ingress and get load balanced across all units. Otherwise, if the
provider's leader goes down, your tracing goes down.

## Provider Library Usage

The `TracingEndpointProvider` object may be used by charms to manage relations with their
trace sources. For this purposes a Tempo-like charm needs to do two things

Instantiate the `TracingEndpointProvider` object by providing it a
reference to the parent (Tempo) charm and optionally the name of the relation that the Tempo charm
uses to interact with its trace sources. This relation must conform to the `tracing` interface
and it is strongly recommended that this relation be named `tracing` which is its
default value.

For example a Tempo charm may instantiate the `TracingEndpointProvider` in its constructor as
follows

```py
from charmlibs.interfaces.tracing import TracingEndpointProvider

def __init__(self, *args):
    super().__init__(*args)
    # ...
    self.tracing = TracingEndpointProvider(self)
    # ...
```
"""

from ._tracing import (
    AmbiguousRelationUsageError,
    BrokenEvent,
    DataAccessPermissionError,
    DatabagModel,
    DataValidationError,
    EndpointChangedEvent,
    EndpointRemovedEvent,
    NotReadyError,
    ProtocolNotRequestedError,
    ProtocolType,
    RawReceiver,
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
    "AmbiguousRelationUsageError",
    "BrokenEvent",
    "DataAccessPermissionError",
    "DataValidationError",
    "DatabagModel",
    "EndpointChangedEvent",
    "EndpointRemovedEvent",
    "NotReadyError",
    "ProtocolNotRequestedError",
    "ProtocolType",
    "RawReceiver",
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
