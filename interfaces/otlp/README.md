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
        self.framework.observe(self.on.ingress_ready, self._publish_endpoints)
        self.framework.observe(self.on.update_status, self._access_rules)

    def _publish_endpoints(self, event):
        OtlpProvider(self).add_endpoint(
            protocol="grpc",
            endpoint="https://my-app.ingress:4317",
            telemetries=["logs", "metrics"],
        ).add_endpoint(
            protocol="http",
            endpoint="https://my-app.ingress:4318",
            telemetries=["traces"],
        ).publish()

    def _access_rules(self, event):
        OtlpProvider(self).rules("promql")
        OtlpProvider(self).rules("logql")
```

### Requirer Side

```python
from charmlibs.interfaces.otlp import OtlpRequirer

class MyOtlpSender(CharmBase):
    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.framework.observe(self.on.update_status, self._access_endpoints)
        self.framework.observe(self.on.update_status, self._publish_rules)

    def _publish_rules(self, _: ops.EventBase):
        OtlpRequirer(
            self,
            loki_rules_path="./src/loki_alert_rules",
            prometheus_rules_path="./src/prometheus_alert_rules",
        ).publish()

    def _access_endpoints(self, _: ops.EventBase):
        OtlpRequirer(
            self,
            protocols=["grpc", "http"],
            telemetries=["logs", "metrics", "traces"],
        ).endpoints
```

## Documentation

For complete documentation, see the [charmlibs documentation](https://documentation.ubuntu.com/charmlibs/reference/charmlibs/interfaces/otlp).

## Contributing

See [CONTRIBUTING.md](https://github.com/canonical/charmlibs/blob/main/CONTRIBUTING.md) in the repository root.
