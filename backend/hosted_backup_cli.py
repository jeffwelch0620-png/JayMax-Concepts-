"""Manual encrypted export/isolated restore; no scheduler or active-app changes."""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from uuid import uuid4
from dotenv import dotenv_values
import hosted_backup as backup
from readonly_snapshot import error_details
from maintenance_connection import MaintenanceConnectionError


def held_result(error):
    result = {'status': 'held', **error_details(error), 'operationalReleaseApproved': False}
    diagnostics = backup.safe_export_diagnostics(getattr(error, 'backupDiagnostics', None))
    if diagnostics is not None:
        result['backupDiagnostics'] = diagnostics
    artifacts = backup.safe_export_artifacts(getattr(error, 'backupArtifacts', None))
    if artifacts is not None:
        result['backupArtifacts'] = artifacts
    if isinstance(error, (backup.BackupError, MaintenanceConnectionError)):
        result['reason'] = str(error)
    return result


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    export = commands.add_parser('export')
    export.add_argument('--owner-config', required=True, help='Private dotenv file; never pass a URL/password as an argument')
    export.add_argument('--maintenance-direct-ipv6', action='store_true',
        help='Opt-in operator path using separate MAINTENANCE_DATABASE_URL; never reads the app URL')
    export.add_argument('--timeout-seconds', type=int, default=backup.EXPORT_TIMEOUT_SECONDS,
        help='Overall export budget, 1–600 seconds; reserve additional time for cleanup and service recovery')
    restore = commands.add_parser('verify-restore')
    restore.add_argument('--connection-env', required=True, help='Name of environment variable containing a disposable loopback DSN')
    restore.add_argument('--backup', required=True)
    restore.add_argument('--key-file', required=True)
    for command in (export, restore):
        command.add_argument('--expected-project', required=True)
        command.add_argument('--pg-bin', required=True)
    args = parser.parse_args()
    binaries = Path(args.pg_bin)
    root = Path(os.environ['LOCALAPPDATA']) / 'JayMaxBuild'
    label = 'backup-' + uuid4().hex
    if args.action == 'export':
        if args.maintenance_direct_ipv6:
            from maintenance_connection import config_url
            sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools/ops'))
            from hosted_additive_index import private_file
            private_file(args.owner_config)
        config = dotenv_values(args.owner_config, **({'interpolate': False} if args.maintenance_direct_ipv6 else {}))
        url = config_url(config) if args.maintenance_direct_ipv6 else config.get('DATABASE_URL', '')
        repo = Path(__file__).resolve().parents[1]
        migrations = {path.relative_to(repo).as_posix(): backup.digest(path.read_bytes()) for directory in
            (repo / 'migrations', repo / 'supabase/migrations') for path in directory.glob('*.sql')}
        options = {'maintenance_direct_ipv6': True} if args.maintenance_direct_ipv6 else {}
        result = await backup.export_backup(url, args.expected_project,
            binaries / 'pg_dump.exe', binaries / 'pg_restore.exe', root / 'backups' / label,
            root / 'credentials' / label, migrations, timeout_seconds=args.timeout_seconds,
            progress=lambda event: print(json.dumps(event), file=sys.stderr, flush=True), **options)
    else:
        dsn = os.environ.get(args.connection_env)
        if not dsn:
            raise backup.BackupError('Restore connection variable missing')
        result = await backup.verify_restore(dsn, args.backup, args.key_file, args.expected_project,
            binaries / 'pg_restore.exe', root / 'backups' / label)
    print(json.dumps(result, indent=2))


def run():
    try:
        asyncio.run(main())
    except KeyboardInterrupt as interrupted:
        # asyncio.run translates its cancelled task into KeyboardInterrupt. Keep
        # the worker's safe artifact/cleanup evidence when that context exists.
        cancelled = interrupted.__context__
        error = cancelled if isinstance(cancelled, asyncio.CancelledError) else backup.BackupError('Backup operation cancelled by operator')
        print(json.dumps(held_result(error)))
        return 130
    except Exception as exc:
        # Even unexpected driver/subprocess errors must not reveal credentials/rows.
        print(json.dumps(held_result(exc)))
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(run())
