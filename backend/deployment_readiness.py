"""Supabase cutover preflight: file/config review and read-only catalog inspection."""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import re
from urllib.parse import urlparse
import asyncpg
from dotenv import dotenv_values

ROOT=Path(__file__).resolve().parents[1]
PRIVATE=('purchasing','actual_inventory','prep_inventory')
COLUMN_MARKERS={'public.store_items':('control_number',),'prep_inventory.batch_events':('source_kind','opening_decision_id'),
    'prep_inventory.container_moves':('compartment',),'prep_inventory.execution_events':('link_event_id','task_complete','created_xid')}
# Explicit dependency order; same-date alphabetical ordering is not a migration plan.
MIGRATIONS=(
 '20261004_native_purchase_import.sql','20261004_actual_inventory_counts.sql',
 '20261004_actual_inventory_corrections.sql','20261004_actual_inventory_scope_bridges.sql',
 '20261004_posted_invoice_corrections.sql','20261005_manual_purchase_sources.sql',
 '20261005_native_order_receiving.sql','20261005_po_receipt_reconciliation.sql',
 '20261005_staff_count_drafts.sql','20261005_prep_mapping_foundation.sql',
 '20261005_prep_batch_events.sql','20261005_prep_observations.sql',
 '20261005_prep_opening_sources.sql','20261005_prep_period_journal.sql',
 '20261006_shared_catalog.sql','20261006_supplier_price_history.sql',
 '20261006_order_commands.sql','20261006_supplier_contacts.sql',
 '20261007_prep_planning.sql','20261007_prep_day_tasks.sql','20261007_prep_execution.sql',
 '20261007_prep_progress.sql','20261007_staff_prep_counts.sql','20261007_prep_containers.sql',
 '20261007_staff_prep_tasks.sql','20261007_container_waste.sql','20261007_staff_prep_production.sql',
 '20261008_container_waste_corrections.sql','20261007_native_private_access.sql')
FEATURES={
 'PURCHASE_IMPORT':('NATIVE_PURCHASES',()),'ACTUAL_INVENTORY':('ACTUAL_INVENTORY',('PURCHASE_IMPORT',)),
 'CATALOG_MAPPING':('CATALOG_MAPPING',('ACTUAL_INVENTORY',)),
 'ORDER_WORKFLOW':('ORDER_WORKFLOW',('CATALOG_MAPPING',)), 'SUPPLIER_CONTACTS':('SUPPLIER_CONTACTS',('ORDER_WORKFLOW',)),
 'PREP_SETUP':('PREP_SETUP',('PURCHASE_IMPORT',)), 'PREP_BATCHES':('PREP_BATCHES',('PREP_SETUP',)),
 'PREP_OBSERVATIONS':('PREP_OBSERVATIONS',('PREP_BATCHES',)),
 'PREP_PLANNING':('PREP_PLANNING',('PREP_SETUP','CATALOG_MAPPING')),
 'PREP_DAY_TASKS':('PREP_DAY_TASKS',('PREP_PLANNING','PREP_OBSERVATIONS')),
 'PREP_EXECUTION':('PREP_EXECUTION',('PREP_DAY_TASKS',)),
 'STAFF_PREP_COUNTS':('STAFF_PREP_COUNTS',('PREP_OBSERVATIONS',)),
 'PREP_CONTAINERS':('PREP_CONTAINERS',('PREP_OBSERVATIONS',)),
 'STAFF_PREP_TASKS':('STAFF_PREP_TASKS',('PREP_EXECUTION',)),
 'STAFF_PREP_PRODUCTION':('STAFF_PREP_PRODUCTION',('STAFF_PREP_TASKS',))}

def configuration(backend,frontend):
    problems=[];values={};pairs=[]
    def boolean(data,key,default=None):
        value=str(data.get(key,default) or '').lower()
        if value not in ('true','false'):problems.append({'key':key,'reason':'Set an explicit true/false value'});return False
        return value=='true'
    pg=boolean(backend,'USE_PG');browser_pg=boolean(frontend,'REACT_APP_USE_PG')
    if not pg or not browser_pg:problems.append({'key':'PostgreSQL mode','reason':'Both backend and frontend must explicitly select PostgreSQL; Mongo fallback is held for this deployment'})
    for name,(browser,deps) in FEATURES.items():
        values[name]=boolean(backend,name+'_ENABLED','false')
        view=boolean(frontend,'REACT_APP_'+browser,'false')
        pairs.append({'feature':name,'backend':values[name],'frontend':view})
        if values[name]!=view:problems.append({'key':name,'reason':'Backend and built frontend feature flags differ'})
    for name,(_,deps) in FEATURES.items():
        if values[name]:
            for dependency in deps:
                if not values[dependency]:problems.append({'key':name,'reason':'Requires '+dependency})
    return {'status':'held' if problems else 'passed','problems':problems,'features':pairs,
        'allNativeFeaturesHeld':not any(values.values()),'secretValuesIncluded':False}

def migration_plan():
    entries=[]
    for name in MIGRATIONS:
        raw=(ROOT/'migrations'/name).read_bytes();text=raw.decode('utf-8-sig')
        tables=sorted(set(re.findall(r'CREATE\s+TABLE\s+([a-z_]+\.[a-z_]+)',text,re.I)))
        functions=sorted(set(re.findall(r'CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+([a-z_]+\.[a-z_]+)',text,re.I)))
        triggers=sorted(set(re.findall(r'CREATE\s+(?:CONSTRAINT\s+)?TRIGGER\s+([a-z_]+)\s+[^;]*?\s+ON\s+([a-z_]+\.[a-z_]+)\b',text,re.I|re.S)))
        entries.append({'file':name,'sha256':hashlib.sha256(raw).hexdigest(),'tables':tables,'functions':functions,'triggers':triggers})
    return {'base':'Existing reviewed application public schema; reference snapshot is not a live migration',
        'alreadyInBase':'20260930_recurring_prep_items.sql','applyAutomatically':False,'migrations':entries,
        'limit':'Catalog presence is not proof of an applied file checksum. Retain hosted migration history and review partially installed objects before any DDL.'}

async def inspect(conn,client_roles=('anon','authenticated'),stores=()):
    plan=migration_plan();issues=[];warnings=[];installed=[]
    async with conn.transaction(isolation='repeatable_read',readonly=True):
        await conn.execute("SET LOCAL statement_timeout='20s'")
        await conn.execute("SET LOCAL search_path=pg_catalog")
        role=await conn.fetchrow('SELECT current_user AS name,rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user')
        for entry in plan['migrations']:
            missing=[]
            for table in entry['tables']:
                if not await conn.fetchval('SELECT to_regclass($1) IS NOT NULL',table):missing.append(table)
            for name in entry['functions']:
                schema,fn=name.split('.')
                if not await conn.fetchval('SELECT EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname=$1 AND p.proname=$2)',schema,fn):missing.append(name+'()')
            for name,table in entry['triggers']:
                if not await conn.fetchval('SELECT EXISTS(SELECT 1 FROM pg_trigger WHERE tgrelid=to_regclass($1) AND tgname=$2)',table,name):missing.append(table+':'+name)
            installed.append({'file':entry['file'],'missingObjects':missing,'status':'missing_or_partial' if missing else 'objects_present_not_checksum_proof'})
            if missing:issues.append({'kind':'schema','file':entry['file'],'missingObjects':missing})
        for table in ('public.app_users','public.store_state','public.stores'):
            if not await conn.fetchval('SELECT to_regclass($1) IS NOT NULL',table):issues.append({'kind':'base_schema','object':table})
        for table,columns in COLUMN_MARKERS.items():
            for column in columns:
                if not await conn.fetchval('SELECT EXISTS(SELECT 1 FROM pg_attribute WHERE attrelid=to_regclass($1) AND attname=$2 AND NOT attisdropped)',table,column):
                    issues.append({'kind':'partial_schema_column','object':table+'.'+column})
        if stores and await conn.fetchval("SELECT to_regclass('public.store_state') IS NOT NULL"):
            missing=await conn.fetch('SELECT id FROM unnest($1::text[]) id WHERE NOT EXISTS(SELECT 1 FROM public.store_state s WHERE s.store_id=id)',list(stores))
            if missing:issues.append({'kind':'store_coordination','missing':[r['id'] for r in missing]})
        disabled=await conn.fetch('''SELECT n.nspname,c.relname,t.tgname FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=ANY($1::text[]) AND t.tgenabled NOT IN ('O','A')''',list(PRIVATE)+['public'])
        for r in disabled:issues.append({'kind':'disabled_trigger','object':'.'.join(r.values())})
        invalid=await conn.fetch('SELECT n.nspname,k.conname FROM pg_constraint k JOIN pg_namespace n ON n.oid=k.connamespace WHERE n.nspname=ANY($1::text[]) AND NOT k.convalidated',list(PRIVATE))
        for r in invalid:issues.append({'kind':'unvalidated_constraint','object':'.'.join(r.values())})
        # Object ACLs are checked independently of RLS and schema exposure. A future
        # USAGE grant must not make an old PUBLIC/function grant usable silently.
        schema_acl=await conn.fetch('''SELECT n.nspname,a.privilege_type FROM pg_namespace n,
            LATERAL aclexplode(coalesce(n.nspacl,acldefault('n',n.nspowner))) a
            WHERE n.nspname=ANY($1::text[]) AND a.grantee=0''',list(PRIVATE))
        for r in schema_acl:issues.append({'kind':'public_private_schema_grant','object':r['nspname'],'privilege':r['privilege_type']})
        public_acl=await conn.fetch('''SELECT 'relation' AS kind,n.nspname,c.relname AS name,a.privilege_type
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace,
            LATERAL aclexplode(coalesce(c.relacl,acldefault(CASE WHEN c.relkind='S' THEN 's'::"char" ELSE 'r'::"char" END,c.relowner))) a
            WHERE n.nspname=ANY($1::text[]) AND c.relkind IN ('r','p','v','m','S') AND a.grantee=0
            UNION ALL SELECT 'function',n.nspname,p.proname,a.privilege_type FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace,
            LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a WHERE n.nspname=ANY($1::text[]) AND a.grantee=0''',list(PRIVATE))
        for r in public_acl:issues.append({'kind':'public_private_object_grant','object':r['nspname']+'.'+r['name'],'privilege':r['privilege_type']})
        for client in client_roles:
            if not await conn.fetchval('SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=$1)',client):
                issues.append({'kind':'client_role_not_checked','role':client});continue
            for schema in PRIVATE:
                exists=await conn.fetchval('SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname=$1)',schema)
                if exists and await conn.fetchval('SELECT has_schema_privilege($1,$2,\'USAGE\')',client,schema):issues.append({'kind':'client_private_schema_access','role':client,'object':schema})
            relations=await conn.fetch('''SELECT n.nspname,c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname=ANY($1::text[]) AND c.relkind IN ('r','p','v','m')
                AND CASE WHEN c.relkind IN ('r','p','v','m') THEN has_table_privilege($2,c.oid,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') ELSE false END''',list(PRIVATE),client)
            for r in relations:issues.append({'kind':'client_private_object_access','role':client,'object':r['nspname']+'.'+r['relname']})
            sequences=await conn.fetch('''SELECT n.nspname,c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname=ANY($1::text[]) AND c.relkind='S' AND CASE WHEN c.relkind='S' THEN has_sequence_privilege($2,c.oid,'USAGE,SELECT,UPDATE') ELSE false END''',list(PRIVATE),client)
            for r in sequences:issues.append({'kind':'client_private_sequence_access','role':client,'object':r['nspname']+'.'+r['relname']})
            funcs=await conn.fetch('''SELECT n.nspname,p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
                WHERE (n.nspname=ANY($1::text[]) OR (n.nspname='public' AND p.prosecdef)) AND has_function_privilege($2,p.oid,'EXECUTE')''',list(PRIVATE),client)
            for r in funcs:issues.append({'kind':'client_function_execute','role':client,'object':r['nspname']+'.'+r['proname']})
        defaults=await conn.fetch('''SELECT pg_get_userbyid(d.defaclrole) AS creator,coalesce(n.nspname,'global') AS scope,d.defaclobjtype::text AS object_type
            FROM pg_default_acl d LEFT JOIN pg_namespace n ON n.oid=d.defaclnamespace,
            LATERAL aclexplode(d.defaclacl) a WHERE (d.defaclnamespace=0 OR n.nspname=ANY($1::text[]))
            AND (a.grantee=0 OR a.grantee IN (SELECT oid FROM pg_roles WHERE rolname=ANY($2::text[])))''',list(PRIVATE),list(client_roles))
        if defaults:warnings.append({'kind':'future_client_default_grants','entries':[dict(r) for r in defaults],
            'reason':'Later DDL can reintroduce access. Inspect again after each migration; defaults belong to their creating role.'})
        foreign=await conn.fetch('SELECT n.nspname,c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=ANY($1::text[]) AND c.relowner<>(SELECT oid FROM pg_roles WHERE rolname=current_user)',list(PRIVATE))
        if foreign and not role['rolsuper']:issues.append({'kind':'backend_owner_access_not_proven','reason':'Configured backend must own the native objects or have an explicitly reviewed role grant model'})
    return {'status':'held' if issues else 'passed','issues':issues,'warnings':warnings,'migrations':installed,'readOnly':True,
        'operationalReleaseApproved':False,'externalChecksPending':['Hosted Data API exposed schemas/configuration','Reviewed applied migration checksums','Operational backup and isolated hosted restore','Application connection recycle and browser walkthrough'],
        'limits':'Catalog/ACL checks only; no business rows, credentials, migration or restore performed.'}

async def main(args):
    backend=dict(dotenv_values(args.backend_env)) if args.backend_env else dict(os.environ)
    frontend=dict(dotenv_values(args.frontend_env)) if args.frontend_env else dict(os.environ)
    report={'target':'existing_hosted_supabase','configuration':configuration(backend,frontend),'plan':migration_plan(),
        'database':{'status':'not_checked'},'operationalReleaseApproved':False}
    if args.inspect_database:
        dsn=backend.get('DATABASE_URL') or ''
        if not connection_configured(dsn):
            report['database']={'status':'held','reason':'Configure DATABASE_URL privately before read-only inspection'}
        else:
            conn=None
            try:
                conn=await asyncpg.connect(dsn,timeout=20,statement_cache_size=0,ssl='require',server_settings={'default_transaction_read_only':'on'})
                report['database']=await inspect(conn,stores=args.store)
            except Exception as e:
                # Driver errors can contain connection material. Never echo the DSN/error text.
                report['database']={'status':'held','reason':'Read-only inspection failed','errorType':type(e).__name__}
            finally:
                if conn is not None:await conn.close()
    output=json.dumps(report,indent=2)+'\n'
    if args.output:Path(args.output).write_text(output,encoding='utf-8')
    else:print(output,end='')
    return 2 if report['configuration']['status']=='held' or (args.inspect_database and report['database']['status']!='passed') else 0

def connection_configured(dsn):
    if not dsn or '[YOUR-PASSWORD]' in dsn:return False
    try:
        parsed=urlparse(dsn)
        _=parsed.port
        return parsed.scheme in ('postgres','postgresql') and bool(parsed.hostname and parsed.username and parsed.path.strip('/'))
    except ValueError:return False

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend-env');parser.add_argument('--frontend-env');parser.add_argument('--inspect-database',action='store_true')
    parser.add_argument('--store',action='append',default=[]);parser.add_argument('--output')
    raise SystemExit(asyncio.run(main(parser.parse_args())))
