# charmlibs.otlp

The `otlp` library.

To install, add `charmlibs-otlp` to your Python dependencies. Then in your Python code, import as:

```py
from charmlibs import otlp
```

To add endpoints that the provider supports, use the additive `add_endpoint` method:
```py
otlp_provider = OtlpProvider(charm)
otlp_provider.add_endpoint("grpc", f"{resolved_url}:4317", ["logs", "metrics"])
otlp_provider.add_endpoint("http", f"{resolved_url}:4318", ["traces"])
```

To publish those endpoints to the relation databag, call the `publish` method:
```py
otlp_provider.publish()
```

To get the alert rules from the consumer, access the `rules` attribute:
```
loki_rules = otlp_provider.rules("logql").alert_rules
prometheus_rules = otlp_provider.rules("promql").record_rules
```

To define the sender's support for protocols and telemetries:
```py
otlp_consumer = OtlpConsumer(
    charm,
    protocols=["grpc", "http"],
    telemetries=["logs", "metrics"],
)
```

Toggle the forwarding of rules with `forward_rules` and if you need to forward more than just the charm's bundled rules, define the `_rules_path` arguments accordingly:

```py
otlp_consumer = OtlpConsumer(
    # snip ...
    forward_rules = True,
    loki_alert_rules_path="./loki_alert_rules",
    loki_record_rules_path="./loki_record_rules",
    prom_alert_rules_path="./prometheus_alert_rules",
    prom_record_rules_path="./prometheus_record_rules",
)
```

To publish all rules to the relation databag:
```py
otlp_consumer.publish()
```

To get the OTLP endpoints from the provider:
```py
otlp_endpoints = otlp_consumer.endpoints()
```

See the [reference documentation](https://documentation.ubuntu.com/charmlibs/reference/charmlibs/otlp) for more.