# Copyright 2025 Canonical
# See LICENSE file for licensing details.

import ops
import ops.testing as scenario

from charmlibs.nginx import Nginx, NginxConfig


def test_nginx_config_written(
    ctx: 'scenario.Context[ops.CharmBase]', null_state: 'scenario.State'
):
    with ctx(event=scenario.CharmEvents.update_status(), state=null_state) as mgr:
        state_out = mgr.run()
        charm: ops.CharmBase = mgr.charm
        nginx = Nginx(
            container=charm.unit.get_container('nginx'),
            nginx_config=NginxConfig('foo', [], {}),
        )
        nginx.reconcile({})

    container_out = state_out.get_container('nginx')
    nginx_config = container_out.get_filesystem(ctx) / Nginx.NGINX_CONFIG[1:]
    assert nginx_config.exists()
