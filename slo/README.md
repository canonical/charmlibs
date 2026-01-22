# charmlibs.slo

SLO (Service Level Objective) management library for Juju charms, providing integration with the Sloth operator for generating Prometheus recording and alerting rules.

To install, add `charmlibs-slo` to your Python dependencies. Then in your Python code, import as:

```py
from charmlibs.slo import SLOProvider, SLORequirer
```

## Features

- **Provider/Requirer pattern**: Enables charms to share SLO specifications with Sloth
- **Raw YAML interface**: Provider passes raw YAML strings; validation happens on requirer side
- **Automatic topology injection**: Optionally inject Juju topology labels into Prometheus queries
- **Multi-service support**: Provide SLO specs for multiple services in a single YAML document

## Usage

### Provider Side

```python
from charmlibs.slo import SLOProvider

class MyCharm(ops.CharmBase):
    def __init__(self, *args):
        super().__init__(*args)
        self.slo_provider = SLOProvider(self)

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
        self.slo_provider.provide_slos(slo_config)
```

### Requirer Side

```python
from charmlibs.slo import SLORequirer

class SlothCharm(ops.CharmBase):
    def __init__(self, *args):
        super().__init__(*args)
        self.slo_requirer = SLORequirer(self)

    def _on_config_changed(self, event):
        # Validation happens here
        slos = self.slo_requirer.get_slos()
        # Process validated SLOs
```

See the [reference documentation](https://documentation.ubuntu.com/charmlibs/reference/charmlibs/slo) for more.
