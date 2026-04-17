# charmlibs.interfaces.tracing

The `tracing` interface library.

To install, add `charmlibs-interfaces-tracing` to your Python dependencies. Then in your Python code, import as:

```py
from charmlibs.interfaces import tracing
```

See the [reference documentation](https://documentation.ubuntu.com/charmlibs/reference/charmlibs/interfaces/tracing) for more.

## Requirer Library Usage

Charms seeking to push traces to Tempo, must do so using the `TracingEndpointRequirer`
object from this charm library. For the simplest use cases, using the `TracingEndpointRequirer`
object only requires instantiating it, typically in the constructor of your charm. The
`TracingEndpointRequirer` constructor requires the name of the relation over which a tracing endpoint
 is exposed by the Tempo charm, and a list of protocols it intends to send traces with.
 This relation must use the `tracing` interface.
 The `TracingEndpointRequirer` object may be instantiated as follows


```py
from charms.tempo_coordinator_k8s.v0.tracing import TracingEndpointRequirer

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

We recommend that you scale up your tracing provider and relate it to an ingress so that your tracing requests
go through the ingress and get load balanced across all units. Otherwise, if the provider's leader goes down, your tracing goes down.

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
from charms.tempo_coordinator_k8s.v0.tracing import TracingEndpointProvider

def __init__(self, *args):
    super().__init__(*args)
    # ...
    self.tracing = TracingEndpointProvider(self)
    # ...
```
