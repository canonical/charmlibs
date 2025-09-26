# nginx

`nginx` provides abstractions for Juju Charms to run a sidecar Nginx container and a corresponding Prometheus exporter.
The supported Nginx configuration is not meant to fully cover all Nginx features, but a minimal subset sufficient to cover our immediate use cases. 

To install, add `charmlibs-nginx` to your requirements. Then in your Python code, import as:

```py
from charmlibs import nginx
```

Check out the reference docs on the [charmlibs docsite](https://canonical-charmlibs.readthedocs-hosted.com/reference/charmlibs/nginx/).

# Getting started

To get started, you can add two sidecar containers to your charm's `charmcraft.yaml` and in `charm.py`, 
instantiate the `Nginx` and `NginxPrometheusExporter` classes in your initializer and call their `.reconcile()` methods whenever you wish to synchronize the configuration files.

```py
import ops

from charmlibs import nginx


class MyCharm(ops.CharmBase):
    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self._nginx = nginx.Nginx(
            self.unit.get_container("nginx-container"),
            nginx_config=nginx.NginxConfig(
                server_name="foo",
                upstream_configs=[
                    nginx.NginxUpstream(name="foo", port=4040, group="backend"),
                    nginx.NginxUpstream(name="bar", port=4041, group="frontend")
                ],
                server_ports_to_locations={8080: [
                    nginx.NginxLocationConfig(
                        path="/", 
                        backend="foo", 
                        backend_url="/api/v1", 
                        headers={"a": "b"},
                        modifier="=",
                        is_grpc=True, 
                        upstream_tls=True
                    ),
                ]}
            )
        )
        self._nginx_pexp = nginx.NginxPrometheusExporter(
            self.unit.get_container('nginx-pexp-container')
        )

        self.framework.observe(self.on.nginx_container_pebble_ready, self._on_reconcile)
        self.framework.observe(self.on.nginx_pexp_container_pebble_ready, self._on_reconcile)

    def _on_reconcile(self, _):
        self._nginx.reconcile(
            upstreams_to_addresses={
                "foo": {"http://example.com"},
                "bar": {"http://example.io"},
            }
        )
        self._nginx_pexp.reconcile()
```