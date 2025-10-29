# Copyright 2025 Canonical
# See LICENSE file for licensing details.

"""Nginx config directives."""

import typing

if typing.TYPE_CHECKING:
    from ._config import NginxLocationConfig, NginxMapConfig, NginxTracingConfig

Directive: typing.TypeAlias = dict[str, typing.Any] | None

temp_paths = (
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
)


def sendfile(*args: str) -> Directive:
    return {'directive': 'sendfile', 'args': [*args]}


def worker_processes(*args: str) -> Directive:
    return {'directive': 'worker_processes', 'args': [*args]}


def events(*args: str) -> Directive:
    return {
        'directive': 'events',
        'args': [],
        'block': [
            {
                'directive': 'worker_connections',
                'args': [*args],
            }
        ],
    }


def worker_rlimit_nofile(*args: str) -> Directive:
    return {'directive': 'worker_rlimit_nofile', 'args': [*args]}


def error_log(*args: str) -> Directive:
    return {'directive': 'error_log', 'args': [*args]}


def pid(*args: str) -> Directive:
    return {'directive': 'pid', 'args': [*args]}


def default_type(*args: str) -> Directive:
    return {'directive': 'default_type', 'args': [*args]}


def proxy_read_timeout(*args: str) -> Directive:
    return {'directive': 'proxy_read_timeout', 'args': [*args]}


def include(*args: str) -> Directive:
    return {'directive': 'include', 'args': [*args]}


def tcp_nopush(*args: str) -> Directive:
    return {'directive': 'tcp_nopush', 'args': [*args]}


def load_module(*args: str) -> Directive:
    return {'directive': 'load_module', 'args': [*args]}


def http(*args: str, block: list[Directive]) -> Directive:
    return {'directive': 'http', 'args': [*args], 'block': block}


def _map(*args: str, block: list[Directive]) -> Directive:
    return {'directive': 'map', 'args': [*args], 'block': block}


def map_configs(variables: list['NginxMapConfig']) -> list[Directive]:
    return [
        _map(
            variable.source_variable,
            variable.target_variable,
            block=[
                {'directive': directive, 'args': args}
                for directive, args in variable.value_mappings.items()
            ],
        )
        for variable in variables
    ]


def log_format() -> Directive:
    return {
        'directive': 'log_format',
        'args': [
            'main',
            '$remote_addr - $remote_user [$time_local]  '
            '$status "$request" '
            '$body_bytes_sent "$http_referer" '
            '"$http_user_agent" "$http_x_forwarded_for"',
        ],
    }


def access_log() -> Directive:
    return {'directive': 'access_log', 'args': ['/dev/stderr']}


def resolver(
    dns_ip_address: str,
    custom_resolver: str | None = None,
) -> list[dict[str, typing.Any]]:
    # pass a custom resolver, such as kube-dns.kube-system.svc.cluster.local.
    if custom_resolver:
        return [{'directive': 'resolver', 'args': [custom_resolver]}]

    # by default, fetch the DNS resolver address from /etc/resolv.conf
    return [
        {
            'directive': 'resolver',
            'args': [dns_ip_address],
        }
    ]


def tracing(tracing_config: typing.Optional['NginxTracingConfig']) -> list[dict[str, typing.Any]]:
    if not tracing_config:
        return []
    return (
        [
            {'directive': 'otel_trace', 'args': ['on']},
            # propagate the trace context headers
            {'directive': 'otel_trace_context', 'args': ['propagate']},
            {
                'directive': 'otel_exporter',
                'args': [],
                'block': [{'directive': 'endpoint', 'args': [tracing_config.endpoint]}],
            },
            {'directive': 'otel_service_name', 'args': [tracing_config.service_name]},
            *([
                {'directive': 'otel_resource_attr', 'args': [attr_key, attr_val]}
                for attr_key, attr_val in tracing_config.resource_attributes.items()
            ]),
        ]
        if tracing_config
        else []
    )


def servers(
    ports_to_locations: dict[int, list['NginxLocationConfig']],
    backends: list[str],
    server_name: str,
    ipv6_enabled: bool,
    supported_tls_versions: list[str] | None,
    ssl_ciphers: list[str] | None,
    listen_tls: bool,
    root_path: str | None,
    tls_cert_path: str,
    tls_key_path: str,
    enable_health_check: bool,
    enable_status_page: bool,
    proxy_connect_timeout: str,
) -> list[Directive]:
    servers: list[Directive] = []
    for port, locations in ports_to_locations.items():
        server_config = _server(
            port=port,
            locations=locations,
            backends=backends,
            server_name=server_name,
            ipv6_enabled=ipv6_enabled,
            listen_tls=listen_tls,
            root_path=root_path,
            supported_tls_versions=supported_tls_versions,
            ssl_ciphers=ssl_ciphers,
            tls_cert_path=tls_cert_path,
            tls_key_path=tls_key_path,
            enable_health_check=enable_health_check,
            enable_status_page=enable_status_page,
            proxy_connect_timeout=proxy_connect_timeout,
        )

        if server_config:
            servers.append(server_config)
    return servers


def _server(
    port: int,
    locations: list['NginxLocationConfig'],
    backends: list[str],
    server_name: str,
    ipv6_enabled: bool,
    supported_tls_versions: list[str] | None,
    ssl_ciphers: list[str] | None,
    listen_tls: bool,
    root_path: str | None,
    tls_cert_path: str,
    tls_key_path: str,
    enable_health_check: bool,
    enable_status_page: bool,
    proxy_connect_timeout: str,
) -> dict[str, typing.Any]:
    auth_enabled = False
    grpc = any(loc.is_grpc for loc in locations)
    nginx_locations = _locations(
        locations=locations,
        grpc=grpc,
        backends=backends,
        listen_tls=listen_tls,
        enable_health_check=enable_health_check,
        enable_status_page=enable_status_page,
        proxy_connect_timeout=proxy_connect_timeout,
    )
    server_config = {}
    if len(nginx_locations) > 0:
        server_config = {
            'directive': 'server',
            'args': [],
            'block': [
                *_listen(port, ssl=listen_tls, http2=grpc, ipv6_enabled=ipv6_enabled),
                *_root_path(root_path),
                *_basic_auth(auth_enabled),
                {
                    'directive': 'proxy_set_header',
                    'args': ['X-Scope-OrgID', '$ensured_x_scope_orgid'],
                },
                {'directive': 'server_name', 'args': [server_name]},
                *(
                    [
                        {
                            'directive': 'ssl_certificate',
                            'args': [tls_cert_path],
                        },
                        {
                            'directive': 'ssl_certificate_key',
                            'args': [tls_key_path],
                        },
                        {
                            'directive': 'ssl_protocols',
                            'args': supported_tls_versions,
                        },
                        {
                            'directive': 'ssl_ciphers',
                            'args': ssl_ciphers,
                        },
                    ]
                    if listen_tls
                    else []
                ),
                *nginx_locations,
            ],
        }

    return server_config


def _locations(
    locations: list['NginxLocationConfig'],
    grpc: bool,
    backends: list[str],
    listen_tls: bool,
    enable_health_check: bool,
    enable_status_page: bool,
    proxy_connect_timeout: str,
) -> list[dict[str, typing.Any]]:
    nginx_locations: list[dict[str, typing.Any]] = []

    if enable_health_check:
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
    if enable_status_page:
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
        # Handle locations without backend, i.e. serving static files
        if not location.backend:
            nginx_locations.append({
                'directive': 'location',
                'args': (
                    [location.path]
                    if location.modifier == ''
                    else [location.modifier, location.path]
                ),
                'block': [
                    *_rewrite(location.rewrite),
                    # add headers if any
                    *_headers(location.headers),
                    # add extra config directives if any
                    *_extra_directives(location.extra_directives),
                ],
            })

        # Handle locations with corresponding backends
        # don't add a location block if the upstream backend doesn't exist in the config
        if location.backend in backends:
            # if upstream_tls is explicitly set for this location, use that; otherwise,
            # use the server's listen_tls setting.
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
                    *_rewrite(location.rewrite),
                    {
                        'directive': 'grpc_pass' if grpc else 'proxy_pass',
                        'args': ['$backend'],
                    },
                    # if a server is down, no need to wait for a long time to pass on the
                    # request to the next available server
                    {
                        'directive': 'proxy_connect_timeout',
                        'args': [proxy_connect_timeout],
                    },
                    # add headers if any
                    *_headers(location.headers),
                    # add extra config directives if any
                    *_extra_directives(location.extra_directives),
                ],
            })

    return nginx_locations


def _root_path(root_path: str | None = None) -> list[Directive]:
    if root_path:
        return [{'directive': 'root', 'args': [root_path]}]
    return []


def _extra_directives(
    extra: Directive,
) -> list[Directive]:
    if extra:
        return [{'directive': key, 'args': val} for key, val in extra.items()]
    return []


def _headers(headers: dict[str, str] | None) -> list[Directive]:
    if headers:
        return [
            {'directive': 'proxy_set_header', 'args': [key, val]} for key, val in headers.items()
        ]
    return []


def _rewrite(rewrite: list[str] | None) -> list[Directive]:
    if rewrite:
        return [{'directive': 'rewrite', 'args': rewrite}]
    return []


def _basic_auth(enabled: bool) -> list[Directive]:
    if enabled:
        return [
            {'directive': 'auth_basic', 'args': ['"workload"']},
            {
                'directive': 'auth_basic_user_file',
                'args': ['/etc/nginx/secrets/.htpasswd'],
            },
        ]
    return []


def _listen(port: int, ssl: bool, http2: bool, ipv6_enabled: bool) -> list[Directive]:
    directives: list[Directive] = [{'directive': 'listen', 'args': _listen_args(port, False, ssl)}]
    if ipv6_enabled:
        directives.append({
            'directive': 'listen',
            'args': _listen_args(port, True, ssl),
        })
    if http2:
        directives.append({'directive': 'http2', 'args': ['on']})
    return directives


def _listen_args(port: int, ipv6: bool, ssl: bool) -> list[str]:
    args: list[str] = []
    if ipv6:
        args.append(f'[::]:{port}')
    else:
        args.append(f'{port}')
    if ssl:
        args.append('ssl')
    return args
