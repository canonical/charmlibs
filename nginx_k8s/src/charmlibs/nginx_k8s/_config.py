# Copyright 2025 Canonical
# See LICENSE file for licensing details.
"""Nginx configuration generation utils."""

import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Literal, cast

import crossplane as _crossplane  # type: ignore[reportMissingTypeStubs]

from ._tls_config import TLSConfigManager

logger = logging.getLogger(__name__)

DEFAULT_TLS_VERSIONS: Final[list[str]] = ['TLSv1', 'TLSv1.1', 'TLSv1.2', 'TLSv1.3']


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
    backend: str
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


@dataclass
class NginxUpstream:
    """Represents metadata needed to construct an Nginx `upstream` block."""

    name: str
    """Name of the upstream block."""
    port: int
    """Port number that all backend servers in this upstream listen on.

    Our coordinators assume that all servers under an upstream share the same port.
    """
    group: str | None = None
    """Group that this upstream belongs to.

    Used for mapping multiple upstreams to a single group of backends (loadbalancing between all).
    If you leave it None, this upstream will be routed to all available backends
    (loadbalancing between them).
    """


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
    2. `upstream_configs`: List of `NginxUpstream` used to generate Nginx `upstream` blocks.
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
        >>>         # Note that you can define multiple server blocks,
        >>>         # each running on a different port
        >>>         return {NGINX_PORT: self._nginx_locations}

    """

    _pid = '/tmp/nginx.pid'  # noqa

    def __init__(
        self,
        server_name: str,
        upstream_configs: list[NginxUpstream],
        server_ports_to_locations: dict[int, list[NginxLocationConfig]],
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
              `upstream` blocks.
            server_ports_to_locations: Mapping from server ports to a list of Nginx location
              configurations.
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
                ]
            })
        """
        self._server_name = server_name
        self._upstream_configs = upstream_configs
        self._server_ports_to_locations = server_ports_to_locations
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
    ) -> str:
        """Render the Nginx configuration as a string.

        Args:
            upstreams_to_addresses: A dictionary mapping each upstream name to a set of addresses
              associated with that upstream.
            listen_tls: Whether Nginx should listen for incoming traffic over TLS.
            root_path: If provided, it is used as a location where static files will be served.
        """
        full_config = self._prepare_config(upstreams_to_addresses, listen_tls, root_path)
        return _crossplane.build(full_config)  # type: ignore

    def _prepare_config(
        self,
        upstreams_to_addresses: dict[str, set[str]],
        listen_tls: bool,
        root_path: str | None = None,
    ) -> list[dict[str, Any]]:
        upstreams = self._upstreams(upstreams_to_addresses)
        # extract the upstream name
        backends = [upstream['args'][0] for upstream in upstreams]
        # build the complete configuration
        full_config = [
            {'directive': 'worker_processes', 'args': [str(self._worker_processes)]},
            {'directive': 'error_log', 'args': ['/dev/stderr', 'error']},
            {'directive': 'pid', 'args': [self._pid]},
            {
                'directive': 'worker_rlimit_nofile',
                'args': [str(self._worker_rlimit_nofile)],
            },
            {
                'directive': 'events',
                'args': [],
                'block': [
                    {
                        'directive': 'worker_connections',
                        'args': [str(self._worker_connections)],
                    }
                ],
            },
            {
                'directive': 'http',
                'args': [],
                'block': [
                    # upstreams (load balancing)
                    *upstreams,
                    # temp paths
                    {
                        'directive': 'client_body_temp_path',
                        'args': ['/tmp/client_temp'],  # noqa
                    },
                    {
                        'directive': 'proxy_temp_path',
                        'args': ['/tmp/proxy_temp_path'],  # noqa
                    },
                    {
                        'directive': 'fastcgi_temp_path',
                        'args': ['/tmp/fastcgi_temp'],  # noqa
                    },
                    {
                        'directive': 'uwsgi_temp_path',
                        'args': ['/tmp/uwsgi_temp'],  # noqa
                    },
                    {'directive': 'scgi_temp_path', 'args': ['/tmp/scgi_temp']},  # noqa
                    # logging
                    {'directive': 'default_type', 'args': ['application/octet-stream']},
                    {
                        'directive': 'log_format',
                        'args': [
                            'main',
                            '$remote_addr - $remote_user [$time_local]  '
                            '$status "$request" '
                            '$body_bytes_sent "$http_referer" '
                            '"$http_user_agent" "$http_x_forwarded_for"',
                        ],
                    },
                    *self._log_verbose(verbose=False),
                    {'directive': 'sendfile', 'args': ['on']},
                    {'directive': 'tcp_nopush', 'args': ['on']},
                    *self._resolver(),
                    # TODO: add custom http block for the user to config?
                    {
                        'directive': 'map',
                        'args': ['$http_x_scope_orgid', '$ensured_x_scope_orgid'],
                        'block': [
                            {'directive': 'default', 'args': ['$http_x_scope_orgid']},
                            {'directive': '', 'args': ['anonymous']},
                        ],
                    },
                    {
                        'directive': 'proxy_read_timeout',
                        'args': [str(self._proxy_read_timeout)],
                    },
                    # server block
                    *self._build_servers_config(backends, listen_tls, root_path),
                ],
            },
        ]
        return full_config

    def _log_verbose(self, verbose: bool = True) -> list[dict[str, Any]]:
        if verbose:
            return [{'directive': 'access_log', 'args': ['/dev/stderr', 'main']}]
        return [
            {
                'directive': 'map',
                'args': ['$status', '$loggable'],
                'block': [
                    {'directive': '~^[23]', 'args': ['0']},
                    {'directive': 'default', 'args': ['1']},
                ],
            },
            {'directive': 'access_log', 'args': ['/dev/stderr']},
        ]

    def _resolver(
        self,
        custom_resolver: str | None = None,
    ) -> list[dict[str, Any]]:
        # pass a custom resolver, such as kube-dns.kube-system.svc.cluster.local.
        if custom_resolver:
            return [{'directive': 'resolver', 'args': [custom_resolver]}]

        # by default, fetch the DNS resolver address from /etc/resolv.conf
        return [
            {
                'directive': 'resolver',
                'args': [self._dns_IP_address],
            }
        ]

    @staticmethod
    def _get_dns_ip_address() -> str:
        """Obtain DNS ip address from /etc/resolv.conf."""
        resolv = Path('/etc/resolv.conf').read_text()
        for line in resolv.splitlines():
            if line.startswith('nameserver'):
                # assume there's only one
                return line.split()[1].strip()
        raise RuntimeError('cannot find nameserver in /etc/resolv.conf')

    def _upstreams(self, upstreams_to_addresses: dict[str, set[str]]) -> list[Any]:
        nginx_upstreams: list[Any] = []

        for upstream_config in self._upstream_configs:
            if upstream_config.group is None:
                # include all available addresses
                addresses: set[str] | None = set()
                for address_set in upstreams_to_addresses.values():
                    addresses.update(address_set)
            else:
                addresses = upstreams_to_addresses.get(upstream_config.group)

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

    def _build_servers_config(
        self,
        backends: list[str],
        listen_tls: bool = False,
        root_path: str | None = None,
    ) -> list[dict[str, Any]]:
        servers: list[dict[str, Any]] = []
        for port, locations in self._server_ports_to_locations.items():
            server_config = self._build_server_config(
                port, locations, backends, listen_tls, root_path
            )
            if server_config:
                servers.append(server_config)
        return servers

    def _build_server_config(
        self,
        port: int,
        locations: list[NginxLocationConfig],
        backends: list[str],
        listen_tls: bool = False,
        root_path: str | None = None,
    ) -> dict[str, Any]:
        auth_enabled = False
        is_grpc = any(loc.is_grpc for loc in locations)
        nginx_locations = self._locations(locations, is_grpc, backends, listen_tls)
        server_config = {}
        if len(nginx_locations) > 0:
            server_config = {
                'directive': 'server',
                'args': [],
                'block': [
                    *self._listen(port, ssl=listen_tls, http2=is_grpc),
                    *self._root_path(root_path),
                    *self._basic_auth(auth_enabled),
                    {
                        'directive': 'proxy_set_header',
                        'args': ['X-Scope-OrgID', '$ensured_x_scope_orgid'],
                    },
                    {'directive': 'server_name', 'args': [self._server_name]},
                    *(
                        [
                            {
                                'directive': 'ssl_certificate',
                                'args': [TLSConfigManager.CERT_PATH],
                            },
                            {
                                'directive': 'ssl_certificate_key',
                                'args': [TLSConfigManager.KEY_PATH],
                            },
                            {
                                'directive': 'ssl_protocols',
                                'args': self._supported_tls_versions,
                            },
                            {
                                'directive': 'ssl_ciphers',
                                'args': self._ssl_ciphers,
                            },
                        ]
                        if listen_tls
                        else []
                    ),
                    *nginx_locations,
                ],
            }

        return server_config

    def _root_path(self, root_path: str | None = None) -> list[dict[str, Any] | None]:
        if root_path:
            return [{'directive': 'root', 'args': [root_path]}]
        return []

    def _locations(
        self,
        locations: list[NginxLocationConfig],
        grpc: bool,
        backends: list[str],
        listen_tls: bool,
    ) -> list[dict[str, Any]]:
        nginx_locations: list[dict[str, Any]] = []

        if self._enable_health_check:
            nginx_locations.append(
                {
                    'directive': 'location',
                    'args': ['=', '/'],
                    'block': [
                        {
                            'directive': 'return',
                            'args': ['200', "'OK'"],
                        },
                        {
                            'directive': 'auth_basic',
                            'args': ['off'],
                        },
                    ],
                },
            )
        if self._enable_status_page:
            nginx_locations.append(
                {
                    'directive': 'location',
                    'args': ['=', '/status'],
                    'block': [
                        {
                            'directive': 'stub_status',
                            'args': [],
                        },
                    ],
                },
            )

        for location in locations:
            # don't add a location block if the upstream backend doesn't exist in the config
            if location.backend in backends:
                # if upstream_tls is explicitly set for this location, use that; otherwise,
                #   use the server's listen_tls setting.
                tls = location.upstream_tls if location.upstream_tls is not None else listen_tls
                s = 's' if tls else ''
                protocol = f'grpc{s}' if grpc else f'http{s}'
                nginx_locations.append({
                    'directive': 'location',
                    'args': (
                        [location.path]
                        if location.modifier == ''
                        else [location.modifier, location.path]
                    ),
                    'block': [
                        {
                            'directive': 'set',
                            'args': [
                                '$backend',
                                f'{protocol}://{location.backend}{location.backend_url}',
                            ],
                        },
                        {
                            'directive': 'grpc_pass' if grpc else 'proxy_pass',
                            'args': ['$backend'],
                        },
                        # if a server is down, no need to wait for a long time to pass on the
                        #  request to the next available server
                        {
                            'directive': 'proxy_connect_timeout',
                            'args': [self._proxy_connect_timeout],
                        },
                        # add headers if any
                        *(
                            [
                                {
                                    'directive': 'proxy_set_header',
                                    'args': [key, val],
                                }
                                for key, val in location.headers.items()
                            ]
                            if location.headers
                            else []
                        ),
                    ],
                })

        return nginx_locations

    def _basic_auth(self, enabled: bool) -> list[dict[str, Any] | None]:
        if enabled:
            return [
                {'directive': 'auth_basic', 'args': ['"workload"']},
                {
                    'directive': 'auth_basic_user_file',
                    'args': ['/etc/nginx/secrets/.htpasswd'],
                },
            ]
        return []

    def _listen(self, port: int, ssl: bool, http2: bool) -> list[dict[str, Any]]:
        directives: list[dict[str, Any]] = []
        directives.append({'directive': 'listen', 'args': self._listen_args(port, False, ssl)})
        if self._ipv6_enabled:
            directives.append({
                'directive': 'listen',
                'args': self._listen_args(port, True, ssl),
            })
        if http2:
            directives.append({'directive': 'http2', 'args': ['on']})
        return directives

    def _listen_args(self, port: int, ipv6: bool, ssl: bool) -> list[str]:
        args: list[str] = []
        if ipv6:
            args.append(f'[::]:{port}')
        else:
            args.append(f'{port}')
        if ssl:
            args.append('ssl')
        return args
