"""Explicitly designated Supabase test project: backup and rollback-only trial.

Never commits native SQL, edits hosted migration history, resets a project,
changes application flags on disk, calls Toast, or copies managed Auth/Vault.
Synthetic API calls share one repeatable-read transaction and one connection;
this verifies engine compatibility, not concurrent requests or deployment.
"""
import argparse
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import traceback
from urllib.parse import unquote, urlparse
from uuid import uuid4
from unittest.mock import patch

import asyncpg
from dotenv import dotenv_values
import deployment_readiness as readiness
from managed_development import project_identity, DevelopmentTargetError
import schema_reconciliation as reconciliation


def designated_target(config, expected):
    identity = project_identity(config.get('DATABASE_URL') or '')
    if not re.fullmatch(r'[a-z0-9]{20}', expected) or identity['projectRef'] != expected:
        raise DevelopmentTargetError('Explicit designated test project must match the saved connection')
    if str(config.get('USE_PG', '')).lower() != 'true':
        raise DevelopmentTargetError('Existing backend must select PostgreSQL')
    if any(str(config.get(name + '_ENABLED', 'false')).lower() != 'false' for name in readiness.FEATURES):
        raise DevelopmentTargetError('Existing native features must remain held')
    return identity


def migration_body(raw):
    """Lex top-level statements; remove only the reviewed outer transaction.

    String literals, quoted identifiers, dollar bodies and nested comments do
    not introduce transaction boundaries. Refuse unexpected top-level control.
    Preserve every byte between the outer BEGIN and COMMIT after UTF-8 decoding.
    """
    text = raw.decode('utf-8-sig'); parts = []; code = []; start = 0; i = 0; first_code = None
    while i < len(text):
        if text.startswith('--', i):
            end = text.find('\n', i); i = len(text) if end < 0 else end + 1; code.append(' '); continue
        if text.startswith('/*', i):
            depth = 1; i += 2
            while i < len(text) and depth:
                if text.startswith('/*', i): depth += 1; i += 2
                elif text.startswith('*/', i): depth -= 1; i += 2
                else: i += 1
            if depth: raise ValueError('Unclosed SQL comment')
            code.append(' '); continue
        if text[i] in "'\"":
            quote = text[i]; escaped = quote == "'" and i > 0 and text[i-1] in 'Ee' and (i < 2 or not (text[i-2].isalnum() or text[i-2] == '_'))
            i += 1
            while i < len(text):
                if escaped and text[i] == '\\': i += 2; continue
                if text[i] == quote:
                    if i+1 < len(text) and text[i+1] == quote: i += 2; continue
                    i += 1; break
                i += 1
            else: raise ValueError('Unclosed SQL literal')
            code.append(' _ '); continue
        dollar = re.match(r'\$(?:[A-Za-z_][A-Za-z_0-9]*)?\$', text[i:]) if text[i] == '$' else None
        if dollar:
            tag = dollar.group(); end = text.find(tag, i+len(tag))
            if end < 0: raise ValueError('Unclosed SQL dollar body')
            i = end+len(tag); code.append(' _ '); continue
        if text[i] == ';':
            normalized = ''.join(code).strip()
            if normalized: parts.append((start, i+1, normalized, first_code))
            start = i+1; code = []; first_code = None
        else:
            if first_code is None and not text[i].isspace(): first_code = i
            code.append(text[i])
        i += 1
    if ''.join(code).strip(): raise ValueError('SQL statement missing terminator')
    if len(parts) < 3 or parts[0][2].upper() != 'BEGIN' or parts[-1][2].upper() != 'COMMIT':
        raise ValueError('Reviewed migration must have exactly one outer transaction')
    for _, _, statement, _ in parts[1:-1]:
        if re.match(r'(?i)^(BEGIN|START|COMMIT|END|ROLLBACK|ABORT|SAVEPOINT|RELEASE|PREPARE\s+TRANSACTION|SET\s+(?:SESSION\s+CHARACTERISTICS|TRANSACTION))\b', statement):
            raise ValueError('Unexpected transaction control in migration body')
    return text[parts[0][1]:parts[-1][3]]


class TrialPool:
    """Sequential single-connection API adapter; real nested savepoints retained."""
    def __init__(self, conn): self.conn = conn; self.busy = False
    @asynccontextmanager
    async def acquire(self):
        if self.busy: raise RuntimeError('Rollback trial does not support concurrent pool use')
        if not self.conn.is_in_transaction(): raise RuntimeError('Trial transaction was lost')
        self.busy = True
        try: yield self.conn
        finally: self.busy = False


def private_backup(dsn, pg_dump, directory):
    """Full application schemas/data/ACLs only; retained privately outside checkout."""
    directory = Path(directory).resolve(); executable = Path(pg_dump)
    private_root = (Path(os.environ.get('LOCALAPPDATA', '')) / 'JayMaxTests').resolve()
    if not os.environ.get('LOCALAPPDATA') or not directory.is_relative_to(private_root):
        raise ValueError('Hosted application backup must stay in the private local JayMaxTests directory')
    if not executable.is_file() or not (executable.parent / 'pg_restore.exe').is_file():
        raise ValueError('Trusted pg_dump and pg_restore required')
    directory.mkdir(parents=True, exist_ok=False)
    uri = urlparse(dsn); env = os.environ.copy()
    for key in ('PGSERVICE','PGSERVICEFILE','PGPASSFILE','PGOPTIONS'): env.pop(key, None)
    env.update(PGPASSWORD=unquote(uri.password or ''), PGSSLMODE='require', PGCONNECT_TIMEOUT='20',
               PGOPTIONS='-c default_transaction_read_only=on -c statement_timeout=60000')
    filename = directory / 'application.dump'
    command = [str(executable), '--host', uri.hostname, '--port', str(uri.port or 5432),
               '--username', unquote(uri.username), '--dbname', unquote(uri.path.lstrip('/')),
               '--format=custom', '--file', str(filename), '--no-password']
    command += ['--schema='+schema for schema in reconciliation.SCHEMAS]
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    result = subprocess.run(command, env=env, capture_output=True, timeout=120, creationflags=flags)
    if result.returncode: raise RuntimeError('Private application backup failed; driver output withheld')
    listing = subprocess.run([str(executable.parent / 'pg_restore.exe'), '--list', str(filename)],
                             capture_output=True, timeout=30, creationflags=flags)
    if listing.returncode or not filename.stat().st_size:
        raise RuntimeError('Private application backup archive could not be read')
    (directory / 'archive-list.txt').write_bytes(listing.stdout)
    manifest = {'format': 'jaymax-private-hosted-application-backup-v1',
                'bytes': filename.stat().st_size, 'sha256': hashlib.sha256(filename.read_bytes()).hexdigest(),
                'schemas': list(reconciliation.SCHEMAS), 'containsApplicationRows': True,
                'archiveReadable': True, 'restoreVerified': False,
                'managedAuthStorageVaultCronAndProjectConfigurationIncluded': False}
    (directory / 'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
    return manifest


async def row_fingerprints(conn):
    """Counts and whole-table hashes; never include original record values."""
    result = {}
    async with conn.transaction(isolation='repeatable_read',readonly=True):
        await conn.execute("SET LOCAL statement_timeout='20s'")
        tables = await conn.fetch("SELECT n.nspname,c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=ANY($1::text[]) AND c.relkind IN ('r','p') ORDER BY 1,2",list(reconciliation.SCHEMAS))
        for table in tables:
            name = '.'.join('"'+value.replace('"','""')+'"' for value in table.values())
            row = await conn.fetchrow("SELECT count(*) AS rows,encode(sha256(convert_to(coalesce(string_agg(h,'' ORDER BY h),''),'UTF8')),'hex') AS sha256 FROM (SELECT encode(sha256(convert_to(to_jsonb(t)::text,'UTF8')),'hex') AS h FROM "+name+" t) x")
            result[table['nspname']+'.'+table['relname']] = dict(row)
    return result


async def verify_baseline_triggers(conn):
    """Only the reviewed timestamp helper is permitted on existing app tables.

    Refuse unreviewed triggers before trial DDL, including deferred external
    effects. No disabling triggers, notification hooks or scheduled jobs.
    """
    triggers = await conn.fetch("SELECT p.prosrc,l.lanname,p.prosecdef FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_proc p ON p.oid=t.tgfoid JOIN pg_language l ON l.oid=p.prolang WHERE n.nspname=ANY($1::text[]) AND NOT t.tgisinternal",list(reconciliation.SCHEMAS))
    expected = 'beginnew.updated_at=now();returnnew;end'
    for trigger in triggers:
        if trigger['lanname'] != 'plpgsql' or trigger['prosecdef'] or re.sub(r'\s+','',trigger['prosrc']).lower().rstrip(';') != expected:
            raise ValueError('Existing application trigger requires side-effect review before rollback trial')
    return len(triggers)


async def client_query_denied(conn, role):
    if role not in ('anon','authenticated'): raise ValueError('Only reviewed ordinary client roles allowed')
    async with conn.transaction():
        # A failure to impersonate a role must not masquerade as a denied SELECT.
        await conn.execute('SET LOCAL ROLE '+role)
        if await conn.fetchval('SELECT current_user') != role: raise AssertionError('Client role was not selected')
        try:
            async with conn.transaction():
                await conn.fetchval('SELECT count(*) FROM purchasing.actual_purchase_facts')
        except asyncpg.InsufficientPrivilegeError:
            await conn.execute('RESET ROLE')
            return True
        raise AssertionError('Ordinary client role can query private purchase facts')


async def synthetic_workflow(conn):
    """Invented purchase/count/prep/container chain at a unique temporary location."""
    from decimal import Decimal
    from fastapi import FastAPI, HTTPException
    import httpx
    import db_pg
    import purchase_api as purchases
    import actual_inventory_api as actual
    # Only the sample generator is reused; no disposable-db setup/teardown runs.
    import csv, io
    from purchase_parser import FIELD_MAP
    await db_pg._init_connection(conn)
    ident = uuid4().hex; store = 'hosted_trial_'+ident; item = 'trial_food_'+ident
    await conn.execute('INSERT INTO public.stores(id,name) VALUES($1,$2)', store, 'Synthetic hosted rollback test')
    await conn.execute("INSERT INTO public.items(code,name,base_unit) VALUES($1,'Synthetic raw food','lb')", item)
    await conn.execute("INSERT INTO public.store_items(store_id,item_code,count_unit,base_per_count_unit,sales_tracked,control_number) VALUES($1,$2,'case',20,false,$2)",store,item)
    pool = TrialPool(conn); app = FastAPI()
    def check(location):
        if location != store: raise HTTPException(404, 'Only synthetic trial location allowed')
    def actor(request, location, write):
        if request.headers.get('authorization') != 'Bearer synthetic-hosted-trial': raise HTTPException(401)
        return 'synthetic-hosted-trial'
    app.include_router(purchases.create_router(lambda:pool,check,actor))
    app.include_router(actual.create_router(lambda:pool,check,actor))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://trial',
                                 headers={'Authorization':'Bearer synthetic-hosted-trial'}) as client:
        async def request(method,path,body=None,key=None,expected=200,**kwargs):
            if body is not None: kwargs['json'] = body
            if method != 'GET': kwargs['headers'] = {'Idempotency-Key': key or str(uuid4())}
            response = await client.request(method,path,**kwargs)
            if response.status_code != expected: raise AssertionError('Synthetic API status '+str(response.status_code)+'; expected '+str(expected)+' at '+path.split(store)[-1])
            return response
        p = '/api/pg/purchases/'+store; a = '/api/pg/actual-inventory/'+store
        scope = (await request('POST',a+'/scope',dict(scope_kind='purchased_items_only',valuation_method='explicit_count_values',
            note='Invented purchased-food scope',items=[dict(item_code=item,base_unit='lb',location_notes='All temporary storage')]))).json()
        async def count(day,qty,value):
            return (await request('POST',a+'/counts',dict(scope_id=scope['header']['id'],count_date=day,timing='before_receipts',
                note='Invented physical count',lines=[dict(item_code=item,counted_quantity=qty,counted_unit='case',
                base_units_per_counted_unit='20',inventory_value=value,confirmed=True,note='Explicit count value')]))).json()
        opening = await count('2026-10-01','2','60'); closing = await count('2026-10-08','1.5','45')
        captured = []
        for vendor,amount in (('PFG','40.00'),('US Foods','0.00')):
            specs = [s for s in FIELD_MAP if s['vendor']==vendor]
            headers = [s['header'] for s in specs]+['FutureField']; raw = []
            values = dict(document_number='SYNTHETIC-'+ident+'-'+vendor,document_type_raw='Invoice',
                customer_number='00123',vendor_branch_reference='SYNTHETIC-BRANCH',account_number='00008',
                extended_amount_source=amount,subtotal_source=amount,total_source=str(Decimal(amount)+3),
                fees_source='1',tax_source='2',net_after_adjustment_source=amount,net_before_adjustment_source=amount,
                vendor_sku_snapshot='0001',description_snapshot='Invented raw food',shipped_quantity_source='2',ordered_quantity_source='2',pack_description_raw='4 / 5 LB')
            for s in specs: raw.append(values.get(s['target'].split('.')[-1], '0' if s['type']=='numeric' else '2026-10-01' if s['type']=='date' else ''))
            raw.append('unmapped, retained "exactly"\r\nsecond line')
            out = io.StringIO(newline=''); w = csv.writer(out); w.writerow(headers); w.writerow(raw); source = out.getvalue().encode()
            file = (await request('POST',p+'/files',files={'file':('synthetic.csv',source,'text/csv')})).json()
            if (await request('GET',p+'/files/'+file['id']+'/source')).content != source: raise AssertionError('Raw source bytes changed')
            rows = (await request('GET',p+'/files/'+file['id']+'/rows')).json()
            if rows['headers'] != headers or rows['rows'][0]['raw_values'] != raw: raise AssertionError('Unmapped/raw fields changed')
            captured.append(file)
        doc = captured[0]['documents'][0]
        if Decimal(doc['header']['fees_source']) != 1 or Decimal(doc['header']['tax_source']) != 2:
            raise AssertionError('Separate fee/tax source amounts were lost')
        mapping = dict(confirmed_currency='USD',received_date='2026-10-04',lines=[dict(line_id=line['id'],classification='food',movement_kind='receipt',
            item_code=item,base_unit='lb',received_quantity='2',received_unit='case',base_units_per_received_unit='20',verified=True,note='Invented verified mapping') for line in doc['lines']])
        path = p+'/documents/'+doc['id']+'/post'; key = str(uuid4())
        await request('POST',path,mapping|{'received_date':None},expected=422)
        posted = (await request('POST',path,mapping,key=key)).json()
        replay = (await request('POST',path,mapping,key=key)).json()
        if replay['batchId'] != posted['batchId']: raise AssertionError('Purchase replay duplicated a batch')
        await request('POST',path,mapping|{'received_date':'2026-10-05'},key=key,expected=409)
        fact = await conn.fetchrow('SELECT base_quantity,inventory_cost_amount,inventory_record_date FROM purchasing.actual_purchase_facts WHERE store_id=$1',store)
        if (fact['base_quantity'],fact['inventory_cost_amount'],str(fact['inventory_record_date'])) != (Decimal(40),Decimal(40),'2026-10-04'): raise AssertionError('Received-date purchase cost changed')
        async def report(): return (await request('GET',a+'/report',params={'opening':opening['header']['id'],'closing':closing['header']['id']})).json()
        baseline = await report()
        if baseline['actualFoodCost'] != '55.00' or baseline['netPurchaseCost'] != '40.00': raise AssertionError('Track 1 explicit valuation failed')
        setup = (await request('GET',p+'/unit-setup')).json(); source = next(i for i in setup['items'] if i['code']==item)['countSource']
        await request('POST',p+'/unit-profiles',dict(item_code=item,profile_kind='count',vendor_item_id=None,base_unit='lb',
            base_units_per_source_unit='20',expected_source_hash=source['hash'],verified=True,note='Measured physical case conversion'))
        product = (await request('POST',p+'/prep-products',dict(name='Invented prepared food',base_unit='lb',note='Measured usable food',verified=True))).json()['product']
        profile = (await request('POST',p+'/prep-unit-profiles',dict(product_version_id=product['id'],source_unit='lb',factor='1',note='Measured base unit',verified=True))).json()['profile']
        recipe_body = dict(product_version_id=product['id'],output_profile_id=profile['id'],entered_yield='48',method='Measured trim',note='Invented recipe',
            lines=[dict(source_kind='raw',raw_item_code=item,quantity='60',source_unit='lb',factor='1',evidence='Gross measured input; trim included')])
        plan = (await request('POST',p+'/prep-recipes/preview',recipe_body)).json()
        recipe = (await request('POST',p+'/prep-recipes',dict(recipe=recipe_body,expected_review_hash=plan['reviewHash'],reviewed=True))).json()['recipe']
        def stamp(clock): return dict(performed_at='2026-10-08T'+clock+':00-04:00',business_date='2026-10-08',timezone_name='America/New_York',calendar_date_confirmed=True,note='Invented measured prep activity')
        async def prep_count(clock,quantity):
            body = stamp(clock)|dict(complete_scope_confirmed=True,lines=[dict(product_version_id=product['id'],profile_id=profile['id'],quantity=quantity,evidence='Invented scale observation')])
            preview = (await request('POST',p+'/prep-observations/count/preview',body)).json()
            return (await request('POST',p+'/prep-observations/count',dict(body=body,expected_review_hash=preview['reviewHash'],reviewed=True))).json()['event']
        prep_open = await prep_count('09:00','1')
        lines = await conn.fetch('SELECT id FROM prep_inventory.recipe_lines WHERE recipe_version_id=$1 ORDER BY line_number', __import__('uuid').UUID(recipe['id']))
        body = stamp('10:00')|dict(recipe_version_id=recipe['id'],planned_batches='1',output_quantity='48',single_output_confirmed=True,
            inputs=[dict(recipe_line_id=str(l['id']),quantity='60',source_unit='lb',factor='1',measurement_basis='measured',evidence='Gross input weighed',included_loss_quantity='12',loss_evidence='Trim inside gross input') for l in lines])
        preview = (await request('POST',p+'/prep-batches/preview',body)).json(); batch_key = str(uuid4())
        payload = dict(batch=body,expected_review_hash=preview['reviewHash'],reviewed=True)
        batch = (await request('POST',p+'/prep-batches',payload,key=batch_key)).json()['event']
        if (await request('POST',p+'/prep-batches',payload,key=batch_key)).json()['event']['id'] != batch['id']: raise AssertionError('Prep replay duplicated batch')
        async def container(body):
            preview = (await request('POST',p+'/prep-containers/preview',body)).json()
            return (await request('POST',p+'/prep-containers/commands',dict(body=body,expected_review_hash=preview['reviewHash'],reviewed=True))).json()
        definition = (await container(dict(action='definition',name='Invented prep pan',capacity_unit='l',usable_capacity='2',evidence='Measured usable vessel')))['result']
        fill_profile = (await container(dict(action='profile',definition_id=definition['id'],product_version_id=product['id'],unit_profile_id=profile['id'],usable_quantity='2',product_fill_measured=True,evidence='Measured food fill')))['result']
        fill = (await container(stamp('10:15')|dict(action='fill',profile_id=fill_profile['id'],source_batch_id=batch['id'],label='Invented pan',quantity='2',contents_measured=True)))['result']
        await container(stamp('10:20')|dict(action='send',fill_id=fill['id'],quantity='1'))
        await container(stamp('10:25')|dict(action='waste',fill_id=fill['id'],quantity='.25',compartment='service',category='service_discard',contents_measured=True))
        await request('POST',p+'/prep-batches/'+batch['id']+'/change-preview',dict(kind='void',reason='Dependency must be resolved'),expected=409)
        prep_close = await prep_count('12:00','48.4')
        period_body = dict(opening_count_id=prep_open['id'],closing_count_id=prep_close['id'],opening_cutoff='after_all',closing_cutoff='before_all',cutoffs_confirmed=True)
        period = (await request('POST',p+'/prep-periods/preview',period_body)).json()['report']; row = period['prepared'][0]
        if [Decimal(row[k]) for k in ('openingQuantity','recordedProduction','closingQuantity','recordedWaste','observedDepletion','serviceUseOrUnrecordedLoss')] != [Decimal(v) for v in ('1','48','48.4','.25','.6','.35')]: raise AssertionError('Prep/waste count reconciliation failed')
        if period['coverage']['finalVarianceAvailable'] or period['cost']['amount'] is not None: raise AssertionError('Incomplete sales coverage became final accounting')
        await conn.execute("UPDATE public.store_state SET sales_period=$2 WHERE store_id=$1",store,{'dishSales':{'invented_sales':999},'synthetic':True})
        if await report() != baseline: raise AssertionError('Prep/waste/sales changed Track 1')
        tested_roles = []
        for role in ('anon','authenticated'):
            if not await conn.fetchval('SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=$1)',role): continue
            if await client_query_denied(conn,role): tested_roles.append(role)
        return {'status':'passed','temporaryStore':store,'rawVendorFormatsVerified':['PFG','US Foods'],
                'rawBytesUnknownColumnsAndMultilinePreserved':True,'receivedDate':'2026-10-04',
                'actualFoodCost':'55.00','foodPurchaseCost':'40.00','taxAndFeeSourceAmountsRetainedSeparately':True,
                'prepProduction':'48','prepWaste':'.25','prepObservedDepletion':'.6','prepUnexplainedDepletion':'.35',
                'exactRetryAndChangedRequestHeld':True,'prepContainerDependencyHeld':True,
                'track1UnchangedAfterPrepWasteAndSalesContext':True,'salesCoverageRemainsIncomplete':True,
                'ordinaryClientPurchaseQueryDenied':tested_roles}


async def trial(config, identity, backup_manifest, output, emit=None):
    if emit is None: emit = lambda value: print(value,flush=True)
    conn = await asyncpg.connect(config['DATABASE_URL'],timeout=20,ssl='require',statement_cache_size=0)
    report = {'format':'jaymax-designated-hosted-rollback-trial-v1','projectRef':identity['projectRef'],
              'capturedAt':datetime.now(timezone.utc).isoformat(),'backup':backup_manifest,
              'migrationPlan':readiness.migration_plan(),'sqlCommitted':False,'applicationFlagsChanged':False,
              'hostedMigrationHistoryEdited':False,'operationalReleaseApproved':False,'completedMigrations':[]}
    transaction = None
    try:
        report['stage'] = 'baseline_review'; emit('Capturing current hosted baseline before trial')
        before = await reconciliation.capture(conn)
        if any(r['nspname'] in readiness.PRIVATE for r in before['catalog']['schemas']):
            raise ValueError('Rollback fresh-install trial refuses partially installed native schemas')
        if await conn.fetchval('SELECT current_user') != 'postgres': raise ValueError('Expected designated managed database role')
        report['reviewedTimestampOnlyBaselineTriggers'] = await verify_baseline_triggers(conn)
        report['rowFingerprintsBefore'] = await row_fingerprints(conn)
        transaction = conn.transaction(isolation='repeatable_read'); await transaction.start()
        await conn.execute("SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='30s'; SET LOCAL idle_in_transaction_session_timeout='120s'")
        await conn.execute('SELECT pg_advisory_xact_lock(781340621)')
        report['stage'] = 'native_migrations'
        for entry in report['migrationPlan']['migrations']:
            raw = (readiness.ROOT/'migrations'/entry['file']).read_bytes()
            if hashlib.sha256(raw).hexdigest() != entry['sha256']: raise ValueError('Migration bytes changed since reviewed plan')
            await conn.execute(migration_body(raw))
            if not conn.is_in_transaction(): raise RuntimeError('Migration escaped rollback trial')
            report['completedMigrations'].append(entry['file']); emit('Trial migration '+str(len(report['completedMigrations']))+'/29 complete')
        report['stage'] = 'native_preflight'; emit('Checking hosted native catalog and permissions inside rollback trial')
        check = await readiness.inspect(conn); report['trialReadiness'] = check
        if check['status'] != 'passed': raise ValueError('Hosted native catalog/ACL preflight held')
        await conn.execute('SET LOCAL search_path=public,pg_catalog')
        settings = {'USE_PG':'true', **{name+'_ENABLED':'true' for name in readiness.FEATURES}}
        report['stage'] = 'synthetic_workflow'; emit('Running invented purchase, count, prep and waste workflow')
        with patch.dict(os.environ,settings): report['syntheticWorkflow'] = await synthetic_workflow(conn)
        if not conn.is_in_transaction(): raise RuntimeError('Synthetic workflow escaped rollback trial')
        await transaction.rollback(); transaction = None
        report['stage'] = 'rollback_verification'; emit('Trial rolled back; verifying original catalog, rows and permissions')
        # Reset the private jsonb codec: catalog tools expect PostgreSQL text.
        await conn.reset_type_codec('jsonb',schema='pg_catalog')
        after = await reconciliation.capture(conn)
        report['rowFingerprintsAfter'] = await row_fingerprints(conn)
        report['existingApplicationRowsAfterRollbackMatch'] = report['rowFingerprintsAfter'] == report['rowFingerprintsBefore']
        report['catalogAfterRollbackMatches'] = after['catalog'] == before['catalog']
        report['migrationHistoryAfterRollbackMatches'] = after['migrationHistory'] == before['migrationHistory']
        report['clientAccessAfterRollbackMatches'] = after['clientAccess'] == before['clientAccess']
        sid = report['syntheticWorkflow']['temporaryStore']
        report['syntheticLocationAbsentAfterRollback'] = not await conn.fetchval('SELECT EXISTS(SELECT 1 FROM public.stores WHERE id=$1)',sid)
        report['nativeSchemasAbsentAfterRollback'] = not await conn.fetchval('SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname=ANY($1::text[]))',list(readiness.PRIVATE))
        if not all(report[k] for k in ('catalogAfterRollbackMatches','migrationHistoryAfterRollbackMatches','clientAccessAfterRollbackMatches','syntheticLocationAbsentAfterRollback','nativeSchemasAbsentAfterRollback','existingApplicationRowsAfterRollbackMatch')):
            raise AssertionError('Hosted rollback verification failed')
        report['status'] = 'passed_hosted_rollback_trial'
        report['stage'] = 'complete'
    except Exception as exc:
        report.update(status='held',errorType=type(exc).__name__,
            errorFrames=[{'file':Path(f.filename).name,'function':f.name,'line':f.lineno} for f in traceback.extract_tb(exc.__traceback__)])
        # No driver errors, API bodies, source rows or credentials in evidence.
    finally:
        if transaction is not None:
            try: await transaction.rollback(); report['failedTrialRollbackCompleted'] = True
            except Exception: report['failedTrialRollbackCompleted'] = False
        await conn.close()
    report['limits'] = ['All 29 native migrations and invented workflow facts were rolled back; this is not a durable hosted installation.',
        'Single connection with nested savepoints; no concurrency, separate-transaction retry, ordinary-role runtime or browser deployment proof.',
        'Private application backup is readable but not a managed-project restore proof; Auth/Storage/Vault/cron/project settings were not backed up.',
        'Existing scheduled jobs were not called, disabled or cloned. External state and independent concurrent changes are outside rollback verification.',
        'Future Toast ingestion and sales-to-recipe analytics are not exercised; existing sales context remains explanatory only.']
    Path(output).write_text(json.dumps(report,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend-env',required=True); parser.add_argument('--designated-test-project',required=True)
    parser.add_argument('--pg-dump',required=True); parser.add_argument('--private-backup-directory',required=True)
    parser.add_argument('--output',required=True); args = parser.parse_args()
    try:
        config = dotenv_values(args.backend_env); identity = designated_target(config,args.designated_test_project)
        # Reject invalid transaction boundaries before connecting or backing up.
        for filename in readiness.MIGRATIONS: migration_body((readiness.ROOT/'migrations'/filename).read_bytes())
        manifest = private_backup(config['DATABASE_URL'],args.pg_dump,args.private_backup_directory)
        print('Fresh private application backup preserved; archive is readable',flush=True)
        report = asyncio.run(trial(config,identity,manifest,args.output))
    except Exception as exc:
        report = {'status':'held','errorType':type(exc).__name__,'sqlCommitted':False,'operationalReleaseApproved':False,
                  'errorFrames':[{'file':Path(f.filename).name,'function':f.name,'line':f.lineno} for f in traceback.extract_tb(exc.__traceback__)]}
        Path(args.output).write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('status','errorType','sqlCommitted','completedMigrations','syntheticWorkflow','catalogAfterRollbackMatches') if k in report}))
    return 0 if report['status']=='passed_hosted_rollback_trial' else 2


if __name__ == '__main__': raise SystemExit(main())
