# Copyright 2025 Canonical
# See LICENSE file for licensing details.
import typing

from ops.testing import CharmEvents

from charmlibs.nginx import Nginx, NginxConfig
from charmlibs.nginx.nginx import NGINX_CONFIG

if typing.TYPE_CHECKING:
    import ops


def test_nginx_config_written(ctx: 'ops.testing.Context', null_state: 'ops.testing.State'):
    with ctx(event=CharmEvents.update_status(), state=null_state) as mgr:
        state_out = mgr.run()
        charm: ops.CharmBase = mgr.charm
        nginx = Nginx(
            container=charm.unit.get_container('nginx'), nginx_config=NginxConfig('foo', [], {})
        )
        nginx.reconcile({})

    container_out = state_out.get_container('nginx')
    nginx_config = container_out.get_filesystem(ctx) / NGINX_CONFIG[1:]
    assert nginx_config.exists()
