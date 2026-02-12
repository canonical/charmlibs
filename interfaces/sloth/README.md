# charmlibs.interfaces.sloth

Sloth integration library for Juju charms, providing SLO (Service Level Objective) management with the Sloth operator for generating Prometheus recording and alerting rules.

To install, add `charmlibs-interfaces-sloth` to your Python dependencies. Then in your Python code, import as:

```py
from charmlibs.interfaces.sloth import SlothProvider, SlothRequirer
```

## Features

- **Provider/Requirer pattern**: Enables charms to share SLO specifications with Sloth
- **Raw YAML interface**: Provider passes raw YAML strings; validation happens on requirer side
- **Automatic topology injection**: Optionally inject Juju topology labels into Prometheus queries
- **Multi-service support**: Provide SLO specs for multiple services in a single YAML document

## Usage

### Provider Side

```python
from charmlibs.interfaces.sloth import SlothProvider

class MyCharm(ops.CharmBase):
    def __init__(self, *args):
        super().__init__(*args)
        self.sloth_provider = SlothProvider(self)

    def _provide_slos(self):
        slo_config = '''
        version: prometheus/v1
        service: my-service
        slos:
          - name: requests-availability
            objective: 99.9
            sli:
              events:
                error_query: 'sum(rate(http_requests_total{status=~"5.."}[{{.window}}]))'
                total_query: 'sum(rate(http_requests_total[{{.window}}]))'
        '''
        self.sloth_provider.provide_slos(slo_config)
```

### Requirer Side

```python
from charmlibs.interfaces.sloth import SlothRequirer

class SlothCharm(ops.CharmBase):
    def __init__(self, *args):
        super().__init__(*args)
        self.sloth_requirer = SlothRequirer(self)

    def _on_config_changed(self, event):
        # Get validated SLO specs from all related charms
        slos = self.sloth_requirer.get_slos()
        # Process SLOs and generate rules
```

## Documentation

For complete documentation, see the [charmlibs documentation](https://documentation.ubuntu.com/charmlibs/reference/charmlibs/interfaces/sloth).

## Contributing

See [CONTRIBUTING.md](https://github.com/canonical/charmlibs/blob/main/CONTRIBUTING.md) in the repository root.
