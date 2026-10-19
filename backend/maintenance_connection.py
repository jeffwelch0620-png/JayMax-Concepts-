"""Opt-in direct IPv6 operator connections; never used by application pools."""
import asyncio
import ipaddress
import re
import socket
import ssl
from urllib.parse import unquote, urlsplit

import asyncpg
from db_tls import connection_tls
from readonly_snapshot import readonly_snapshot


class MaintenanceConnectionError(ValueError):
    """Fixed safe messages only; do not include credentials or driver text."""


def direct_settings(url, project):
    try:
        value = urlsplit(url)
        if (not re.fullmatch(r'[a-z0-9]{20}', project or '')
                or value.scheme not in ('postgres', 'postgresql')
                or value.hostname != 'db.' + project + '.supabase.co'
                or value.port != 5432 or value.path != '/postgres'
                or unquote(value.username or '') != 'postgres'
                or not value.password or '[YOUR-PASSWORD]' in unquote(value.password)
                or value.query or value.fragment):
            raise ValueError
    except (ValueError, TypeError):
        raise MaintenanceConnectionError('Exact designated direct maintenance endpoint required') from None
    return {'host': value.hostname, 'port': 5432, 'database': 'postgres',
            'user': 'postgres', 'password': unquote(value.password)}


def config_url(config):
    # No fallback to DATABASE_URL or environment: app configuration is separate.
    value = config.get('MAINTENANCE_DATABASE_URL', '')
    if not isinstance(value, str) or not value.strip():
        raise MaintenanceConnectionError('Separate MAINTENANCE_DATABASE_URL required')
    return value.strip()


def ipv6_address(value):
    try:
        address = ipaddress.ip_address(value)
        if not isinstance(address, ipaddress.IPv6Address) or address.ipv4_mapped:
            raise ValueError
    except (ValueError, TypeError):
        raise MaintenanceConnectionError('Direct maintenance requires native IPv6') from None
    return str(address)


async def dump_settings(url, project):
    settings = direct_settings(url, project)
    # libpq uses hostaddr for routing and the canonical host for certificate checks.
    async with asyncio.timeout(20):
        addresses = await asyncio.get_running_loop().getaddrinfo(
            settings['host'], 5432, family=socket.AF_INET6, type=socket.SOCK_STREAM)
    if not addresses:
        raise MaintenanceConnectionError('Direct maintenance IPv6 resolution unavailable')
    return settings | {'hostaddr': ipv6_address(addresses[0][4][0])}


class DirectIPv6Connection(asyncpg.Connection):
    """Capture transport evidence through asyncpg's connection_class interface."""
    __slots__ = ('maintenance_peer', 'maintenance_tls')

    def __init__(self, protocol, transport, loop, addr, config, params):
        super().__init__(protocol, transport, loop, addr, config, params)
        self.maintenance_peer = transport.get_extra_info('peername')
        self.maintenance_tls = transport.get_extra_info('ssl_object') is not None


async def connect(url, project, *, readonly=True, label='jaymax-direct-maintenance',
                  timeout=20, command_timeout=30):
    direct_settings(url, project)
    if (type(readonly) is not bool or not isinstance(label, str)
            or not re.fullmatch(r'jaymax-[a-z0-9-]{1,55}', label)):
        raise MaintenanceConnectionError('Reviewed maintenance session options required')
    context = connection_tls(url)
    if (not isinstance(context, ssl.SSLContext) or not context.check_hostname
            or context.verify_mode != ssl.CERT_REQUIRED):
        raise MaintenanceConnectionError('Certificate-verified maintenance TLS required')
    conn = None
    try:
        async with asyncio.timeout(timeout):
            conn = await asyncpg.connect(url, ssl=context, timeout=timeout,
                command_timeout=command_timeout, statement_cache_size=0,
                connection_class=DirectIPv6Connection,
                server_settings={'default_transaction_read_only': 'on' if readonly else 'off',
                                 'application_name': label})
            peer = conn.maintenance_peer
            if not isinstance(peer, tuple) or len(peer) < 2 or peer[1] != 5432 or not conn.maintenance_tls:
                raise MaintenanceConnectionError('Direct maintenance transport evidence required')
            ipv6_address(peer[0])
            async with readonly_snapshot(conn, isolation=None, rollback_timeout=5):
                row = await conn.fetchrow("""SELECT current_user AS actor,session_user AS login,
                    current_database() AS database,pg_backend_pid() AS pid,
                    current_setting('default_transaction_read_only') AS default_readonly,
                    current_setting('transaction_read_only') AS readonly,
                    current_setting('application_name') AS label""")
                if (row['actor'] != 'postgres' or row['login'] != 'postgres' or row['database'] != 'postgres'
                        or type(row['pid']) is not int or row['pid'] <= 0 or row['readonly'] != 'on'
                        or row['default_readonly'] != ('on' if readonly else 'off') or row['label'] != label):
                    raise MaintenanceConnectionError('Effective maintenance session identity/settings differ')
        return conn
    except BaseException as original:
        if conn is not None:
            try:
                await conn.close(timeout=5)
            except BaseException as cleanup:
                original.connectionCloseErrorType = type(cleanup).__name__
                try:
                    conn.terminate()  # This exact newly owned client only; never a SQL backend signal.
                except BaseException as failure:
                    original.connectionTerminateErrorType = type(failure).__name__
        raise
