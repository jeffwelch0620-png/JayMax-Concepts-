"""Atomic native installation on an explicitly designated hosted build database.

Only fresh, hash-reviewed native delivery is supported. Existing historical
ledger rows are preserved; new rows record SQL actually executed in the same
transaction. No reset, history repair, operational flags or external calls.
"""
import argparse
import asyncio
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import traceback
import asyncpg
from dotenv import dotenv_values
import deployment_readiness as readiness
import hosted_test_trial as trial
import hosted_install_preservation as preservation
import managed_development as delivery
import schema_reconciliation as reconciliation


class InstallFailure(RuntimeError):
    def __init__(self, report):
        super().__init__('Native installation held; redacted evidence retained')
        self.report=report


def entries(directory):
    delivery.verify_bundle(directory)
    manifest=json.loads((Path(directory)/'manifest.json').read_text())
    return [entry|{'bodySha256':hashlib.sha256(trial.migration_body((Path(directory)/entry['deliveryFile']).read_bytes()).encode()).hexdigest()}
            for entry in manifest['migrations']]


async def ledger_shape(conn):
    rows=await conn.fetch("""SELECT a.attname,format_type(a.atttypid,a.atttypmod) AS type,
        a.attnotnull,d.oid IS NOT NULL AS has_default FROM pg_attribute a
        LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum
        WHERE a.attrelid=to_regclass('supabase_migrations.schema_migrations')
        AND a.attnum>0 AND NOT a.attisdropped""")
    columns={r['attname']:r for r in rows}
    if any(columns.get(name,{}).get('type')!=kind for name,kind in (('version','text'),('name','text'),('statements','text[]'))):
        raise ValueError('Reviewed migration ledger shape is required')
    if any(r['attname'] not in ('version','name','statements') and r['attnotnull'] and not r['has_default'] for r in rows):
        raise ValueError('Unreviewed mandatory migration ledger field')


async def verify_install(conn, prepared, old_ledger, columns, original_rows, client_roles=('anon','authenticated')):
    history=await preservation.ledger_fingerprints(conn)
    versions={entry['deliveryVersion'] for entry in prepared}
    if set(history)!=set(old_ledger)|versions or any(history.get(v)!=sha for v,sha in old_ledger.items()):
        raise AssertionError('Historical migration ledger changed or new versions are incomplete')
    installed=await conn.fetch("SELECT version,name,statements FROM supabase_migrations.schema_migrations WHERE version=ANY($1::text[]) ORDER BY version",sorted(versions))
    expected={e['deliveryVersion']:e for e in prepared}
    for row in installed:
        entry=expected[row['version']];statements=row['statements']
        if row['name']!=Path(entry['deliveryFile']).name.split('_',1)[1].removesuffix('.sql') or not statements or len(statements)!=1 or hashlib.sha256(statements[0].encode()).hexdigest()!=entry['bodySha256']:
            raise AssertionError('Applied SQL statement hash differs from reviewed native body')
    fingerprints=await preservation.fingerprints(conn,columns)
    if fingerprints!=original_rows:raise AssertionError('Original application values changed')
    check=await readiness.inspect(conn,client_roles=client_roles)
    if check['status']!='passed':raise ValueError('Installed catalog/ACL readiness is held')
    return {'historicalLedgerRowsPreserved':True,'appliedSqlBodyHashesVerified':True,
            'originalTableCount':len(fingerprints),'originalApplicationValuesPreserved':True,
            'nativeReadiness':check}


async def apply(conn, directory, expected_catalog, expected_rows, expected_ledger, client_roles=('anon','authenticated'), emit=None):
    """One transaction; commit acknowledgement loss is explicitly UNKNOWN."""
    emit=emit or (lambda message:None);prepared=entries(directory)
    report={'format':'jaymax-designated-native-install-v1','capturedAt':datetime.now(timezone.utc).isoformat(),
            'status':'held','sqlCommitted':False,'commitAttempted':False,
            'historicalMigrationRepair':False,'applicationFlagsChanged':False,
            'operationalReleaseApproved':False,'completedMigrations':[],'delivery':prepared}
    transaction=None
    try:
        transaction=conn.transaction(isolation='repeatable_read');await transaction.start()
        await conn.execute("SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='30s'; SET LOCAL idle_in_transaction_session_timeout='120s'")
        await conn.execute('SELECT pg_advisory_xact_lock(781340621)')
        await ledger_shape(conn)
        columns=await preservation.original_columns(conn)
        await preservation.lock_original_tables(conn,columns)
        await conn.execute('LOCK TABLE supabase_migrations.schema_migrations IN EXCLUSIVE MODE')
        before=await reconciliation.capture(conn)
        if before['catalog']!=expected_catalog:raise ValueError('Current catalog differs from reviewed baseline')
        if any(row['nspname'] in readiness.PRIVATE for row in before['catalog']['schemas']):
            raise ValueError('Fresh installation refuses existing or partial native schemas')
        await trial.verify_baseline_triggers(conn)
        if await preservation.fingerprints(conn,columns)!=expected_rows:raise ValueError('Original rows differ from restore-verified backup')
        current_ledger=await preservation.ledger_fingerprints(conn)
        if current_ledger!=expected_ledger:raise ValueError('Current historical migration ledger changed')
        # Retain safe metadata needed to reconcile an ambiguous COMMIT without
        # reapplying SQL, guessing applied history or exposing old statements.
        report['historicalLedgerFingerprints']=current_ledger
        report['originalRows']=expected_rows
        report['originalColumns']=[{'schema':key[0],'table':key[1],'columns':value} for key,value in sorted(columns.items())]
        if current_ledger and min(e['deliveryVersion'] for e in prepared)<=max(current_ledger):
            raise ValueError('Native delivery versions must follow actual existing history')
        for entry in prepared:
            body=trial.migration_body((Path(directory)/entry['deliveryFile']).read_bytes())
            if hashlib.sha256(body.encode()).hexdigest()!=entry['bodySha256']:raise ValueError('Native migration body changed')
            await conn.execute(body)
            if not conn.is_in_transaction():raise RuntimeError('Native migration escaped installation transaction')
            name=Path(entry['deliveryFile']).name.split('_',1)[1].removesuffix('.sql')
            await conn.execute('INSERT INTO supabase_migrations.schema_migrations(version,name,statements) VALUES($1,$2,$3::text[])',entry['deliveryVersion'],name,[body])
            report['completedMigrations'].append(entry['sourceFile']);emit('Native installation '+str(len(report['completedMigrations']))+'/29 prepared')
        report['stage']='precommit_verification';emit('Checking original values, native permissions and recorded SQL before COMMIT')
        report['verification']=await verify_install(conn,prepared,current_ledger,columns,expected_rows,client_roles)
        report['stage']='commit';emit('Native precommit verification passed; committing atomic installation')
        report['commitAttempted']=True
        await transaction.commit();transaction=None
        report.update(status='committed_requires_independent_verification',sqlCommitted=True)
        return report,columns
    except Exception as exc:
        report.update(errorType=type(exc).__name__,errorFrames=[{'file':Path(f.filename).name,'function':f.name,'line':f.lineno} for f in traceback.extract_tb(exc.__traceback__)])
        contexts=[];context=exc.__context__
        while context is not None and len(contexts)<4:
            contexts.append({'errorType':type(context).__name__,
                'frames':[{'file':Path(f.filename).name,'function':f.name,'line':f.lineno} for f in traceback.extract_tb(context.__traceback__)]})
            context=context.__context__
        report['errorContexts']=contexts
        if report['commitAttempted']:
            # Never assert rollback or retry installation after ambiguous COMMIT.
            report.update(status='commit_outcome_unknown',sqlCommitted=None)
        elif transaction is not None:
            try:await transaction.rollback();report['failedInstallRollbackCompleted']=True
            except Exception:report.update(status='rollback_outcome_unknown',sqlCommitted=None,failedInstallRollbackCompleted=False)
        raise InstallFailure(report) from None


async def main(args):
    report={'status':'held','sqlCommitted':False,'commitAttempted':False,'applicationFlagsChanged':False,
            'historicalMigrationRepair':False,'operationalReleaseApproved':False};conn=None
    try:
        config=dotenv_values(args.backend_env);identity=trial.designated_target(config,args.designated_test_project)
        proof=json.loads(Path(args.restore_proof).read_text())
        rollback=json.loads(Path(args.rollback_proof).read_text())
        baseline=json.loads(Path(args.baseline_catalog).read_text())['catalog']
        if proof.get('status')!='passed_local_application_restore' or not proof.get('localApplicationRestoreVerified'):
            raise ValueError('Verified private application restore evidence is required')
        if rollback.get('status')!='passed_hosted_rollback_trial' or rollback.get('projectRef')!=identity['projectRef']:
            raise ValueError('Matching successful hosted rollback trial required')
        if proof.get('sourceArchiveSha256')!=rollback['backup']['sha256'] or proof['restoredRowFingerprints']!=rollback['rowFingerprintsBefore']:
            raise ValueError('Restore archive and trial baseline do not agree')
        root=(Path(__import__('os').environ['LOCALAPPDATA'])/'JayMaxTests').resolve()
        archive=Path(args.private_backup).resolve()
        if not archive.is_relative_to(root) or hashlib.sha256(archive.read_bytes()).hexdigest()!=proof['sourceArchiveSha256']:
            raise ValueError('Retained private backup path/hash changed')
        current=json.loads(json.dumps(readiness.migration_plan()['migrations']))
        if current!=rollback['migrationPlan']['migrations']:raise ValueError('Native migration plan differs from hosted trial')
        entries(args.bundle)
        conn=await asyncpg.connect(config['DATABASE_URL'],ssl='require',statement_cache_size=0,timeout=20)
        if await conn.fetchval('SELECT current_user')!='postgres':raise ValueError('Expected managed owner role')
        old_ledger=await preservation.ledger_fingerprints(conn)
        if [r['version'] for r in baseline['migrationHistory']['entries']]!=sorted(old_ledger):raise ValueError('Reviewed historical versions changed')
        report,columns=await apply(conn,args.bundle,baseline['catalog'],proof['restoredRowFingerprints'],old_ledger,emit=lambda s:print(s,flush=True))
        await conn.close();conn=None
        # Entirely new connection: successful COMMIT is checked independently.
        conn=await asyncpg.connect(config['DATABASE_URL'],ssl='require',statement_cache_size=0,timeout=20,
                                   server_settings={'default_transaction_read_only':'on'})
        report['independentVerification']=await verify_install(conn,report['delivery'],old_ledger,columns,proof['restoredRowFingerprints'])
        report.update(status='passed_durable_native_install',projectRef=identity['projectRef'],privateBackupSha256=proof['sourceArchiveSha256'])
    except InstallFailure as exc:report=exc.report
    except Exception as exc:
        report.update(status='held' if not report.get('commitAttempted') else 'committed_verification_held',errorType=type(exc).__name__,
            errorFrames=[{'file':Path(f.filename).name,'function':f.name,'line':f.lineno} for f in traceback.extract_tb(exc.__traceback__)])
    finally:
        if conn:await conn.close()
    Path(args.output).write_text(json.dumps(report,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('status','sqlCommitted','errorType','completedMigrations','projectRef') if k in report}),flush=True)
    return 0 if report.get('status')=='passed_durable_native_install' else 2


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('backend-env','designated-test-project','bundle','restore-proof','rollback-proof','baseline-catalog','private-backup','output'):
        parser.add_argument('--'+name,required=True)
    args=parser.parse_args()
    if Path(args.output).exists():raise SystemExit('Choose a fresh output path; preserve previous attempts')
    raise SystemExit(asyncio.run(main(args)))
