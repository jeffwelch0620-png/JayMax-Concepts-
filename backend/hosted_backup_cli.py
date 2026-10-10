"""Manual encrypted export/isolated restore; no scheduler or active-app changes."""
import argparse
import asyncio
import json
import os
from pathlib import Path
from uuid import uuid4
from dotenv import dotenv_values
import hosted_backup as backup


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    export = commands.add_parser('export')
    export.add_argument('--owner-config', required=True, help='Private dotenv file; never pass a URL/password as an argument')
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
        config = dotenv_values(args.owner_config)
        repo = Path(__file__).resolve().parents[1]
        migrations = {str(path.relative_to(repo)): backup.digest(path.read_bytes()) for directory in
            (repo / 'migrations', repo / 'supabase/migrations') for path in directory.glob('*.sql')}
        result = await backup.export_backup(config.get('DATABASE_URL', ''), args.expected_project,
            binaries / 'pg_dump.exe', binaries / 'pg_restore.exe', root / 'backups' / label,
            root / 'credentials' / label, migrations)
    else:
        dsn = os.environ.get(args.connection_env)
        if not dsn:
            raise backup.BackupError('Restore connection variable missing')
        result = await backup.verify_restore(dsn, args.backup, args.key_file, args.expected_project,
            binaries / 'pg_restore.exe', root / 'backups' / label)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as exc:
        # Even unexpected driver/subprocess errors must not reveal credentials/rows.
        result = {'status': 'held', 'errorType': type(exc).__name__, 'operationalReleaseApproved': False}
        if isinstance(exc, backup.BackupError):
            result['reason'] = str(exc)
        print(json.dumps(result))
        raise SystemExit(2)
