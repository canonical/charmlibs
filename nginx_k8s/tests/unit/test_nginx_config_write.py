# Copyright 2025 Canonical
# See LICENSE file for licensing details.

import ops
import ops.testing as scenario

from charmlibs.nginx_k8s import Nginx, NginxConfig


def test_nginx_config_written(
    ctx: 'scenario.Context[ops.CharmBase]', null_state: 'scenario.State'
):
    with ctx(event=scenario.CharmEvents.update_status(), state=null_state) as mgr:
        state_out = mgr.run()
        charm: ops.CharmBase = mgr.charm
        nginx = Nginx(
            container=charm.unit.get_container('nginx'),
        )
        nginx.reconcile(NginxConfig('foo', [], {}).get_config({}, False))

    container_out: scenario.Container = state_out.get_container('nginx')
    nginx_config = container_out.get_filesystem(ctx) / Nginx.NGINX_CONFIG[1:]  # type: ignore
    assert nginx_config.exists()
