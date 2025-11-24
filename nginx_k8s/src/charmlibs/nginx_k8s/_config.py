# Copyright 2025 Canonical
# See LICENSE file for licensing details.
"""Nginx configuration generation utils."""

import logging
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Literal, cast

import crossplane as _crossplane  # type: ignore[reportMissingTypeStubs]

from . import _directives as directives
from ._tls_config import TLSConfigManager

logger = logging.getLogger(__name__)

DEFAULT_TLS_VERSIONS: Final[list[str]] = ['TLSv1', 'TLSv1.1', 'TLSv1.2', 'TLSv1.3']
RESOLV_CONF_PATH = '/etc/resolv.conf'

# Define valid Nginx `location` block modifiers.
# cfr. https://www.digitalocean.com/community/tutorials/nginx-location-directive#nginx-location-directive-syntax
_NginxLocationModifier = Literal[
    '',  # prefix match
    '=',  # exact match
    '~',  # case-sensitive regex match
    '~*',  # case-insensitive regex match
    '^~',  # prefix match that disables further regex matching
]


@dataclass
class NginxLocationConfig:
    """Represents a `location` block in a Nginx configuration file.

    For example::

        NginxLocationConfig(
            '/',
            'foo',
            backend_url="/api/v1"
            headers={'a': 'b'},
            modifier=EXACT,
            is_grpc=True,
            use_tls=True,
        )

    would result in the nginx config::

        location = / {
            set $backend grpcs://foo/api/v1;
            grpc_pass $backend;
            proxy_connect_timeout 5s;
            proxy_set_header a b;
        }
    """

    path: str
    """The location path (e.g., '/', '/api') to match incoming requests."""
    backend: str | None = None
    """The name of the upstream service to route requests to (e.g. an `upstream` block)."""
    backend_url: str = ''
    """An optional URL path to append when forwarding to the upstream (e.g., '/v1')."""
    headers: dict[str, str] = field(default_factory=lambda: cast('dict[str, str]', {}))
    """Custom headers to include in the proxied request."""
    modifier: _NginxLocationModifier = ''
    """The Nginx location modifier."""
    is_grpc: bool = False
    """Whether to use gRPC proxying (i.e. `grpc_pass` instead of `proxy_pass`)."""
    upstream_tls: bool | None = None
    """Whether to connect to the upstream over TLS (e.g., https:// or grpcs://)
    If None, it will inherit the TLS setting from the server block that the location is part of.
    """
    rewrite: list[str] | None = None
    """Custom rewrite, used i.e. to drop the subpath from the proxied request if needed.
    Example: ['^/auth(/.*)$', '$1', 'break'] to drop `/auth` from the request.
    """
    extra_directives: dict[str, Any] = field(default_factory=lambda: cast('dict[str, Any]', {}))
    """Dictionary of arbitrary location configuration keys and values.
    Example: {"proxy_ssl_verify": ["off"]}
    """


@dataclass
class NginxUpstream:
    """Represents metadata needed to construct an Nginx `upstream` block."""

    name: str
    """Name of the upstream block."""
    port: int
    """Port number that all backend servers in this upstream listen on.

    Our coordinators assume that all servers under an upstream share the same port.
    """
    address_lookup_key: str | None = None
    """Group that this upstream belongs to.

    Used for mapping multiple upstreams to a single group of backends (loadbalancing between all).
    If you leave it None, this upstream will be routed to all available backends
    (loadbalancing between them).
    """
    ignore_address_lookup_key: bool = False
    """If True, overrides `address_lookup_key` and routes to all available backend servers.

    Use this when the upstream should be generic and include any available backend.

    TODO: This class is now used outside of the context of pure coordinated-workers.
    This arg hence must be renamed to have a more generic name for eg. `ignore_address_lookup`.
    See: https://github.com/canonical/cos-coordinated-workers/issues/105
    """


@dataclass
class NginxMapConfig:
    """Represents a `map` block of the Nginx config.

    Example::

        NginxMapConfig(
            source_variable="$http_upgrade",
            target_variable="$connection_upgrade",
            value_mappings={
                "default": ["upgrade"],
                "": ["close"],
            },
        )

    will result in the following `map` block::

        map $http_upgrade $connection_upgrade {
            default upgrade;
            '' close;
        }
    """

    source_variable: str
    """Name of the variable to map from."""
    target_variable: str
    """Name of the variable to be created."""
    value_mappings: dict[str, list[str]]
    """Mapping of source values to target values."""


@dataclass
class NginxTracingConfig:
    """Configuration for OTel tracing in Nginx."""

    endpoint: str
    service_name: str
    resource_attributes: dict[str, str] = field(default_factory=lambda: {})


def _is_ipv6_enabled() -> bool:
    """Check if IPv6 is enabled on the container's network interfaces."""
    try:
        output = subprocess.run(
            ['ip', '-6', 'address', 'show'], check=True, capture_output=True, text=True
        )
    except subprocess.CalledProcessError:
        # if running the command failed for any reason, assume ipv6 is not enabled.
        return False
    return bool(output.stdout)


class NginxConfig:
    """NginxConfig.

    To generate an Nginx configuration for a charm, instantiate the `NginxConfig` class with the
      required inputs:

    1. `server_name`: The name of the server (e.g. charm fqdn), which is used to identify the
       server in Nginx configurations.
    2. `upstream_configs`: List of `NginxUpstream` used to generate Nginx `upstream` directives.
    3. `server_ports_to_locations`: Mapping from server ports to a list of `NginxLocationConfig`.

    Any charm can instantiate `NginxConfig` to generate an Nginx configuration as follows:

    Example::
        >>> # illustrative purposes only
        >>> import socket
        >>> from ops import CharmBase
        >>> from charmlibs.nginx_k8s import NginxConfig, NginxUpstream, NginxLocationConfig
        ...     #[...]
        >>> class AnyCharm(CharmBase):
        >>>     def __init__(self, *args):
        >>>         super().__init__(*args)
        ...          #[...]
        >>>         self._container = self.unit.get_container("nginx")
        >>>         self._nginx = NginxConfig(
        >>>             server_name=self.hostname,
        >>>             upstream_configs=self._nginx_upstreams(),
        >>>             server_ports_to_locations=self._server_ports_to_locations(),
        >>>         )
        ...         #[...]
        >>>         self._reconcile()
        ...     #[...]
        >>>     @property
        >>>     def hostname(self) -> str:
        >>>         return socket.getfqdn()
        ...
        >>>     @property
        >>>     def _nginx_locations(self) -> List[NginxLocationConfig]:
        >>>         return [
        >>>             NginxLocationConfig(path="/api/v1", backend="upstream1",modifier="~"),
        >>>             NginxLocationConfig(path="/status", backend="upstream2",modifier="="),
        >>>         ]
        ...
        >>>     @property
        >>>     def _upstream_addresses(self) -> Dict[str, Set[str]]:
        >>>         # a mapping from an upstream "role" to the set of addresses
        >>>         # that belong to this upstream
        >>>         return {
        >>>             "upstream1": {"address1", "address2"},
        >>>             "upstream2": {"address3", "address4"},
        >>>         }
        ...
        >>>     @property
        >>>     def _tls_available(self) -> bool:
        >>>         # return if the Nginx config should have TLS enabled
        >>>         pass
        ...
        >>>     def _reconcile(self):
        >>>         if self._container.can_connect():
        >>>             new_config: str = self._nginx.get_config(self._upstream_addresses,
        >>>               self._tls_available)
        >>>             should_restart: bool = self._has_config_changed(new_config)
        >>>             self._container.push(self.config_path, new_config, make_dirs=True)
        >>>             self._container.add_layer("nginx", self.layer, combine=True)
        >>>             self._container.autostart()
        ...
        >>>             if should_restart:
        >>>                 logger.info("new nginx config: restarting the service")
        >>>                 self.reload()
        ...
        >>>     def _nginx_upstreams(self) -> List[NginxUpstream]:
        >>>         # UPSTREAMS is a list of backend services that we want to route traffic to
        >>>         for upstream in UPSTREAMS:
        >>>             # UPSTREAMS_PORT is the port the backend services are running on
        >>>             upstreams.append(NginxUpstream(upstream, UPSTREAMS_PORT, upstream))
        >>>             return upstreams
        ...
        >>>     def _server_ports_to_locations(self) -> Dict[int, List[NginxLocationConfig]]:
        >>>         # NGINX_PORT is the port an nginx server is running on
        >>>         # Note that you can define multiple server directives,
        >>>         # each running on a different port
        >>>         return {NGINX_PORT: self._nginx_locations}

    """

    _pid = '/tmp/nginx.pid'  # noqa
    otel_module_path = '/etc/nginx/modules/ngx_otel_module.so'

    _http_x_scope_orgid_map_config = NginxMapConfig(
        source_variable='$http_x_scope_orgid',
        target_variable='$ensured_x_scope_orgid',
        value_mappings={
            'default': ['$http_x_scope_orgid'],
            '': ['anonymous'],
        },
    )
    _logging_by_status_map_config = NginxMapConfig(
        source_variable='$status',
        target_variable='$loggable',
        value_mappings={
            '~^[23]': ['0'],
            'default': ['1'],
        },
    )

    def __init__(
        self,
        server_name: str,
        upstream_configs: list[NginxUpstream],
        server_ports_to_locations: dict[int, list[NginxLocationConfig]],
        map_configs: Sequence[NginxMapConfig] | None = None,
        enable_health_check: bool = False,
        enable_status_page: bool = False,
        supported_tls_versions: list[str] | None = None,
        ssl_ciphers: list[str] | None = None,
        worker_processes: int = 5,
        worker_connections: int = 4096,
        proxy_read_timeout: int = 300,
        proxy_connect_timeout: str = '5s',
    ):
        """Constructor for a Nginx config generator object.

        Args:
            server_name: The name of the server (e.g. fqdn), which is used to identify
              the server in Nginx configurations.
            upstream_configs: List of Nginx upstream metadata configurations used to generate Nginx
              `upstream` directives.
            server_ports_to_locations: Mapping from server ports to a list of Nginx location
              configurations.
            map_configs: List of extra `map` directives to be put under the `http` directive.
            enable_health_check: If True, adds a `/` location that returns a basic 200 OK response.
            enable_status_page: If True, adds a `/status` location that enables `stub_status` for
              basic Nginx metrics.
            supported_tls_versions: list of supported tls protocol versions.
            ssl_ciphers: ssl ciphers.
            worker_processes: Number of nginx worker processes to spawn.
            worker_connections: Max number of worker connections
            proxy_read_timeout: Proxy read timeout.
            proxy_connect_timeout: Proxy connect timeout.

        Example:
            .. code-block:: python
            NginxConfig(
            server_name = "tempo-0.tempo-endpoints.model.svc.cluster.local",
            upstreams = [
                NginxUpstream(name="zipkin", port=9411, group="distributor"),
            ],
            server_ports_to_locations = {
                9411: [
                    NginxLocationConfig(
                        path="/",
                        backend="zipkin"
                    )
                ],
            map_configs=[
                NginxMapConfig(
                    source_variable="$http_upgrade",
                    target_variable="$connection_upgrade",
                    value_mappings={
                        "default": ["upgrade"],
                        "": ["close"],
                    },
                )
            ]
            })
        """
        self._server_name = server_name
        self._upstream_configs = upstream_configs
        self._server_ports_to_locations = server_ports_to_locations
        self._map_configs = [
            self._logging_by_status_map_config,
            self._http_x_scope_orgid_map_config,
            *(map_configs or ()),
        ]
        self._enable_health_check = enable_health_check
        self._enable_status_page = enable_status_page
        self._dns_IP_address = self._get_dns_ip_address()
        self._ipv6_enabled = _is_ipv6_enabled()
        self._supported_tls_versions = supported_tls_versions or DEFAULT_TLS_VERSIONS
        self._ssl_ciphers = ssl_ciphers or [
            'HIGH:!aNULL:!MD5'  # codespell:ignore anull
        ]
        self._worker_processes = worker_processes
        self._worker_connections = worker_connections
        self._proxy_read_timeout = proxy_read_timeout
        self._proxy_connect_timeout = proxy_connect_timeout

        # number of file descriptors to open for each connection: one for upstream, one for
        # downstream. Do not exceed system ulimit.
        self._worker_rlimit_nofile = worker_connections * 2

    def get_config(
        self,
        upstreams_to_addresses: dict[str, set[str]],
        listen_tls: bool,
        root_path: str | None = None,
        tracing_config: NginxTracingConfig | None = None,
    ) -> str:
        """Render the Nginx configuration as a string.

        Args:
            upstreams_to_addresses: A dictionary mapping each upstream name to a set of addresses
              associated with that upstream.
            listen_tls: Whether Nginx should listen for incoming traffic over TLS.
            root_path: If provided, it is used as a location where static files will be served.
            tracing_config: Tracing configuration.
        """
        full_config = self._prepare_config(
            upstreams_to_addresses=upstreams_to_addresses,
            listen_tls=listen_tls,
            root_path=root_path,
            tracing_config=tracing_config,
        )
        return _crossplane.build(full_config)  # type: ignore

    def _prepare_config(
        self,
        upstreams_to_addresses: dict[str, set[str]],
        listen_tls: bool,
        root_path: str | None = None,
        tracing_config: NginxTracingConfig | None = None,
    ) -> list[directives.Directive]:
        upstreams = self._upstreams(upstreams_to_addresses)
        # build the complete configuration
        full_config: list[directives.Directive] = [
            *([directives.load_module(self.otel_module_path)] if tracing_config else []),
            directives.worker_processes(str(self._worker_processes)),
            directives.error_log('/dev/stderr', 'error'),
            directives.pid(self._pid),
            directives.worker_rlimit_nofile(str(self._worker_rlimit_nofile)),
            directives.events(str(self._worker_connections)),
            directives.http(
                block=[
                    *directives.tracing(tracing_config),
                    # upstreams (load balancing)
                    *upstreams,
                    # temp paths
                    *directives.temp_paths,
                    # include mime types so nginx can map file extensions correctly.
                    # Without this, files may fall back to "application/octet-stream",
                    # and when Nginx serves static files, browsers may download them
                    # instead of rendering (e.g., JS, CSS, SVG).
                    directives.include('/etc/nginx/mime.types'),
                    # logging
                    directives.default_type('application/octet-stream'),
                    directives.log_format(),
                    *directives.map_configs(self._map_configs),
                    directives.access_log(),
                    directives.sendfile('on'),
                    directives.tcp_nopush('on'),
                    *directives.resolver(dns_ip_address=self._dns_IP_address),
                    # TODO: add custom http block for the user to config?
                    directives.proxy_read_timeout(str(self._proxy_read_timeout)),
                    # server block
                    *directives.servers(
                        ports_to_locations=self._server_ports_to_locations,
                        backends=[upstream['args'][0] for upstream in upstreams],
                        server_name=self._server_name,
                        ipv6_enabled=self._ipv6_enabled,
                        supported_tls_versions=self._supported_tls_versions,
                        ssl_ciphers=self._ssl_ciphers,
                        listen_tls=listen_tls,
                        root_path=root_path,
                        tls_cert_path=TLSConfigManager.CERT_PATH,
                        tls_key_path=TLSConfigManager.KEY_PATH,
                        enable_health_check=self._enable_health_check,
                        enable_status_page=self._enable_status_page,
                        proxy_connect_timeout=self._proxy_connect_timeout,
                    ),
                ]
            ),
        ]
        return full_config

    @staticmethod
    def _get_dns_ip_address() -> str:
        """Obtain DNS ip address from /etc/resolv.conf."""
        resolv = Path(RESOLV_CONF_PATH).read_text()
        for line in resolv.splitlines():
            if line.startswith('nameserver'):
                # assume there's only one
                return line.split()[1].strip()
        raise RuntimeError(f'cannot find nameserver in {RESOLV_CONF_PATH}')

    def _upstreams(self, upstreams_to_addresses: dict[str, set[str]]) -> list[Any]:
        nginx_upstreams: list[Any] = []

        for upstream_config in self._upstream_configs:
            if upstream_config.address_lookup_key is None:
                # include all available addresses
                addresses: set[str] | None = set()
                for address_set in upstreams_to_addresses.values():
                    addresses.update(address_set)
            else:
                addresses = upstreams_to_addresses.get(upstream_config.address_lookup_key)

            # don't add an upstream block if there are no addresses
            if addresses:
                upstream_config_name = upstream_config.name
                nginx_upstreams.append({
                    'directive': 'upstream',
                    'args': [upstream_config_name],
                    'block': [
                        # enable dynamic DNS resolution for upstream servers.
                        # since K8s pods IPs are dynamic, we need this config to allow
                        # nginx to re-resolve the DNS name without requiring a config reload.
                        # cfr. https://www.f5.com/company/blog/nginx/dns-service-discovery-nginx-plus#:~:text=second%20method
                        {
                            'directive': 'zone',
                            'args': [f'{upstream_config_name}_zone', '64k'],
                        },
                        *[
                            {
                                'directive': 'server',
                                'args': [
                                    f'{addr}:{upstream_config.port}',
                                    'resolve',
                                ],
                            }
                            for addr in addresses
                        ],
                    ],
                })

        return nginx_upstreams
