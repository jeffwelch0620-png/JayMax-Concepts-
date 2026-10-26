"""Manual inactive-by-default v2 adapter; no URL/password args or ambient app config.

Preparing/merging this command does not authorize its execution. A fresh separately
approved exact packet digest and --execute are required, including for restore.
"""
import argparse
import asyncio
import os
from pathlib import Path
import sys
from uuid import uuid4
from dotenv import dotenv_values

from application_backup_profiles import Held, canonical, digest, strict_json
import hosted_journal_backup as journal
import journal_backup_receipts as receipts
from readonly_snapshot import error_details


def private_file(path):
    # Import only at invocation. No dotenv/network or sys.path mutation on import.
    ops = str(Path(__file__).resolve().parents[1] / 'tools' / 'ops')
    inserted = ops not in sys.path
    if inserted:
        sys.path.insert(0,ops)
    try:
        from hosted_additive_index import private_file as checked
        return checked(path)
    finally:
        if inserted:
            sys.path.remove(ops)


def private_bytes(path,limit):
    checked=private_file(path)
    if checked.stat().st_size > limit:
        raise Held('private_input_oversized')
    with checked.open('rb') as stream:
        data=stream.read(limit+1)
    if len(data)>limit:
        raise Held('private_input_oversized')
    return data


def parser():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('export','verify-restore'))
    p.add_argument('--execute',action='store_true')
    p.add_argument('--packet',required=True)
    p.add_argument('--expected-packet-sha256',required=True)
    p.add_argument('--profile',required=True,choices=('receiving7',))
    p.add_argument('--pg-bin',required=True)
    p.add_argument('--owner-config')
    p.add_argument('--backup')
    p.add_argument('--expected-encrypted-sha256')
    p.add_argument('--key-file')
    p.add_argument('--target-record',help='Private owned-target record; DSNs themselves come from named environment variables')
    return p


async def main(argv=None):
    args=parser().parse_args(argv)
    if not args.execute:
        raise Held('separate_exact_execution_approval_required')
    raw=private_bytes(args.packet,256*1024)
    p=receipts.packet(raw,args.expected_packet_sha256,args.action)
    binaries=Path(args.pg_bin)
    suffix='.exe' if os.name=='nt' else ''
    dump=binaries/('pg_dump'+suffix); restore=binaries/('pg_restore'+suffix)
    if not dump.is_file() or not restore.is_file():
        raise Held('explicit_postgresql_binaries_required')
    root=Path(os.environ['LOCALAPPDATA'])/'JayMaxBuild'
    label='backup-'+uuid4().hex
    directory=root/'backups'/label
    if args.action=='export':
        if not args.owner_config or any((args.backup,args.key_file,args.target_record,args.expected_encrypted_sha256)):
            raise Held('export_arguments_differ')
        config_path=private_file(args.owner_config)
        config=dotenv_values(config_path,interpolate=False)
        url=journal.maintenance.config_url(config)
        repo=Path(__file__).resolve().parents[1]
        migrations={path.relative_to(repo).as_posix():digest(path.read_bytes())
                    for d in (repo/'migrations',repo/'supabase/migrations') for path in sorted(d.glob('*.sql'))}
        result=await journal.export_backup(url,p['projectRef'],dump,restore,directory,
            root/'credentials'/label,migrations,execution_packet=raw,packet_sha=args.expected_packet_sha256)
    else:
        if args.owner_config or not all((args.backup,args.key_file,args.target_record,args.expected_encrypted_sha256)):
            raise Held('restore_arguments_differ')
        target_raw=private_bytes(args.target_record,16384)
        if digest(target_raw) != p['restoreTargetSha256']:
            raise Held('restore_target_record_digest_differs')
        target=strict_json(target_raw)
        if (not isinstance(target,dict) or set(target)!={'connectionEnv','controlEnv','systemIdentifier','databaseOid'}
                or any(not isinstance(target[k],str) or not __import__('re').fullmatch('[A-Z][A-Z0-9_]{0,79}',target[k])
                       for k in ('connectionEnv','controlEnv'))):
            raise Held('owned_target_record_invalid')
        url=os.environ.get(target['connectionEnv'],''); control=os.environ.get(target['controlEnv'],'')
        result=await journal.verify_restore(journal.RestoreTarget(url,control,target['systemIdentifier'],target['databaseOid']),
            private_bytes(args.backup,journal.MAX_ENVELOPE),private_bytes(args.key_file,128),restore,directory,
            expected=p['binding'],expected_encrypted_sha=args.expected_encrypted_sha256,
            policy=p['dependencyPolicy'],execution_window=p['executionWindow'])
    # Protect custody paths in a private record; never print them or a target/role.
    try:
        with (directory/'adapter.private.json').open('xb') as stream:
            stream.write(canonical(result))
    except OSError as exc:
        exc.backupArtifacts={'finalBackupPresent':args.action=='export',
                             'privateKeyRetained':args.action=='export'}
        raise
    public={k:v for k,v in result.items() if k not in ('encryptedBackup','privateKey')}
    print(canonical(public).decode('utf-8'))
    return public


def run():
    try:
        asyncio.run(main())
    except (Exception,KeyboardInterrupt) as exc:
        value=dict(status='held',**error_details(exc),operationalReleaseApproved=False)
        if isinstance(exc,Held):
            value['reason']=str(exc)
        artifacts=journal.legacy.safe_export_artifacts(getattr(exc,'backupArtifacts',None))
        if artifacts is not None:
            value['backupArtifacts']=artifacts
        print(canonical(value).decode('utf-8'))
        return 130 if isinstance(exc,KeyboardInterrupt) else 2
    return 0


if __name__=='__main__':
    raise SystemExit(run())
