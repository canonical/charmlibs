# charmlibs.interfaces.otlp

The `otlp` library.

OTLP integration library for Juju charms, providing OTLP endpoint information for communicating  OTLP data and associated Loki and Prometheus rules.

## Features

- **Provider/Requirer pattern**: Enables charms to share OTLP endpoint information and rules
- **Define endpoint support**: Providers and requirers define what OTLP protocols and telemetries they support.
- **Automatic topology injection**: Inject Juju topology labels into rule expressions and labels with metadata if the labels are not already labeled.

## Getting started

To install, add `charmlibs-interfaces-otlp` to your Python dependencies. Then in your Python code, import as:

```py
from charmlibs.interfaces.otlp import OtlpProvider, OtlpRequirer
```

### Provider Side

```python
from charmlibs.interfaces.otlp import OtlpProvider

class MyOtlpServer(CharmBase):
    def __init__(self, *args):
        super().__init__(*args)
        self.otlp_provider = OtlpProvider(self)
        self.framework.observe(self.on.ingress_ready, self._on_ingress_ready)

    def _on_ingress_ready(self, event):
        self.otlp_provider.add_endpoint(
                protocol="grpc",
                endpoint="https://my-app.ingress:4317",
                telemetries=["logs", "metrics"],
        )
        self.otlp_provider.add_endpoint(
                protocol="http",
                endpoint="https://my-app.ingress:4318",
                telemetries=["traces"],
        )
        # publish the registered endpoints to the relation databag
        self.otlp_provider.publish()
        # optionally, get the alerting and recording rules
        promql_rules = self.otlp_provider.rules("promql")
        logql_rules = self.otlp_provider.rules("logql")
```

### Requirer Side

```python
from charmlibs.interfaces.otlp import OtlpRequirer

class MyOtlpSender(CharmBase):
    def __init__(self, *args):
        super().__init__(*args)
        self.otlp_requirer = OtlpRequirer(
            self,
            protocols=["grpc", "http"],
            telemetries=["logs", "metrics", "traces"],
            loki_rules_path="./src/loki_alert_rules",
            prometheus_rules_path="./src/prometheus_alert_rules",
        )
        self.framework.observe(self.on.update_status, self._reconcile)

    def _reconcile(self, event):
        # publish the rules to the relation databag
        self.otlp_requirer.publish()
        # get the endpoints from the provider
        supported_endpoints = self.otlp_requirer.endpoints
```

## Documentation

For complete documentation, see the [charmlibs documentation](https://documentation.ubuntu.com/charmlibs/reference/charmlibs/interfaces/otlp).

## Contributing

See [CONTRIBUTING.md](https://github.com/canonical/charmlibs/blob/main/CONTRIBUTING.md) in the repository root.
