"""Certificate-verified PostgreSQL TLS; plaintext only for loopback tests."""
import os
from pathlib import Path
import ssl
from urllib.parse import parse_qsl, urlsplit

DEFAULT_CA = Path(__file__).resolve().parent / 'certs' / 'supabase-prod-ca-2021.crt'


def connection_tls(database_url):
    url = urlsplit(database_url)
    if url.scheme not in ('postgres', 'postgresql') or not url.hostname or url.fragment:
        raise ValueError('Invalid PostgreSQL endpoint')
    # DSN routing overrides could bypass the loopback boundary or same-target gate.
    if any(key.lower() in ('host', 'hostaddr', 'port', 'service', 'servicefile', 'user', 'dbname')
           for key, _ in parse_qsl(url.query)):
        raise ValueError('PostgreSQL endpoint overrides are not supported')
    if url.hostname.lower() in ('127.0.0.1', '::1', 'localhost'):
        return False
    # Use the public Supabase CA by default. Other servers/CA rotations need an
    # explicit trusted CA file; an invalid override must hold, never downgrade.
    ca = os.environ.get('DATABASE_SSL_ROOT_CERT', str(DEFAULT_CA))
    if not ca.strip():
        raise ValueError('A trusted database CA file is required')
    return ssl.create_default_context(cafile=ca)
