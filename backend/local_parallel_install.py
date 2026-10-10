"""Local-only transaction rehearsal. No hosted installer or client cutover.

Each intent and expected catalog digest is fsynced before COMMIT. A lost
acknowledgement holds mutations until a separate connection reconciles the
durable before/after pins. Password authentication and pooler capacity are
deliberately outside this disposable, trust-authenticated PostgreSQL trial.
"""
import asyncio
import copy
import hashlib
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit
import asyncpg
import parallel_install_plan as plans
import runtime_permissions as runtime
import schema_reconciliation as catalog
import hosted_install_preservation as preservation
import transition_permissions as permissions
import connection_transition as startup
import db_pg
import db_auxiliary
import auxiliary_permissions
from uuid import uuid4


class RehearsalHeld(RuntimeError):
    """Safe category only; retain the journal and inspect before retrying."""


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     default=str).encode()).hexdigest()


def local_target(url):
    uri = urlsplit(url)
    if (uri.scheme not in ('postgres', 'postgresql') or uri.hostname != '127.0.0.1'
            or not uri.port or not uri.username or uri.password is not None
            or not re.fullmatch(r'/native_purchase_test_[a-f0-9]{32}', uri.path)
            or uri.query or uri.fragment):
        raise RehearsalHeld('Unique disposable loopback database required')
    return uri.path[1:]


class Journal:
    """Exclusive, metadata-only hash chain; fsync failure stops the controller.

    This detects accidental corruption, not malicious rewriting or truncation.
    It is not a private credential store or a hosted authorization receipt.
    """
    def __init__(self, path, database):
        if not re.fullmatch(r'native_purchase_test_[a-f0-9]{32}', database):
            raise RehearsalHeld('Disposable journal identity required')
        self.path = Path(path)
        with self.path.open('xb') as stream:
            stream.flush(); os.fsync(stream.fileno())
        self.append('opened', {'database': database})

    def rows(self):
        result = []; previous = '0' * 64
        try:
            raw = self.path.read_bytes()
            if not raw.endswith(b'\n'): raise ValueError()
            for line in raw.splitlines():
                row = json.loads(line)
                checksum = row.pop('sha256')
                if (set(row) != {'sequence', 'previous', 'event', 'data'}
                        or row['sequence'] != len(result) or row['previous'] != previous
                        or digest(row) != checksum):
                    raise ValueError()
                result.append(row | {'sha256': checksum}); previous = checksum
            if not result or result[0]['event'] != 'opened':
                raise ValueError()
            return result
        except (ValueError, KeyError, TypeError):
            raise RehearsalHeld('Journal integrity held') from None

    def append(self, event, data):
        # Only fixed metadata keys, digests, generated names/OIDs and states.
        allowed = {'database', 'step', 'before', 'after', 'state', 'oids'}
        if event not in {'opened', 'intent', 'expected', 'acknowledged', 'failed', 'commit_unknown', 'reconciled'} or not set(data) <= allowed:
            raise RehearsalHeld('Journal metadata contract held')
        for key, value in data.items():
            if key in ('before', 'after') and not re.fullmatch('[a-f0-9]{64}', value):
                raise RehearsalHeld('Journal digest required')
            if key in ('step', 'state') and value not in {
                    'create', 'overlap', 'enable', 'restore', 'disable_revoke',
                    'rolled_back', 'committed', 'not_committed', 'ambiguous'}:
                raise RehearsalHeld('Journal state held')
            if key == 'database' and not re.fullmatch('native_purchase_test_[a-f0-9]{32}', value):
                raise RehearsalHeld('Journal database held')
            if key == 'oids' and (not isinstance(value, dict) or any(
                    not re.fullmatch('jaymax_build_(inventory|accounts)_[a-f0-9]{12}', name)
                    or type(oid) is not int or not 0 < oid < 2**32 for name, oid in value.items())):
                raise RehearsalHeld('Journal role identity held')
        rows = self.rows() if self.path.stat().st_size else []
        row = {'sequence': len(rows), 'previous': rows[-1]['sha256'] if rows else '0' * 64,
               'event': event, 'data': data}
        row['sha256'] = digest(row)
        with self.path.open('ab') as stream:
            stream.write((json.dumps(row, sort_keys=True) + '\n').encode())
            stream.flush(); os.fsync(stream.fileno())


async def snapshot(conn):
    """Consistent row/ledger/sequence, role, membership and scoped access pins."""
    async with conn.transaction(isolation='repeatable_read', readonly=True):
        await conn.execute("SET LOCAL statement_timeout='20s'; SET LOCAL search_path=pg_catalog")
        columns = await preservation.original_columns(conn)
        rows = await preservation.fingerprints(conn, columns)
        schema = (await catalog.capture(conn))['catalog']
        roles = [dict(row) for row in await conn.fetch('''SELECT oid,rolname,
            rolsuper,rolinherit,rolcreaterole,rolcreatedb,rolcanlogin,rolreplication,
            rolconnlimit,rolvaliduntil,rolbypassrls,rolconfig FROM pg_roles ORDER BY oid''')]
        memberships = [dict(row) for row in await conn.fetch('SELECT * FROM pg_auth_members ORDER BY roleid,member,grantor')]
        settings = [dict(row) for row in await conn.fetch('SELECT * FROM pg_db_role_setting ORDER BY setdatabase,setrole')]
        policies = [dict(row) for row in await conn.fetch('''SELECT n.nspname AS schema,c.relname AS table,
            p.polname AS name,p.polroles::oid[] AS role_oids,p.polpermissive AS permissive,
            p.polcmd::text AS command,pg_get_expr(p.polqual,p.polrelid) AS using_expr,
            pg_get_expr(p.polwithcheck,p.polrelid) AS check_expr FROM pg_policy p
            JOIN pg_class c ON c.oid=p.polrelid JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname=ANY($1::text[]) ORDER BY 1,2,3''', list(catalog.SCHEMAS))]
        # Effective ACL rows preserve grantor and grant-option, including columns,
        # types, sequences, database and all default ACLs. NULL and an explicit
        # owner-only ACL are equivalent after exact grant/revoke round trips.
        scopes = list(catalog.SCHEMAS) + ['supabase_migrations']
        access = [dict(row) for row in await conn.fetch('''WITH objects AS (
            SELECT 'schema' AS kind,n.oid AS object,0 AS sub,n.nspowner AS owner,
                coalesce(n.nspacl,acldefault('n',n.nspowner)) AS acl FROM pg_namespace n WHERE n.nspname=ANY($1::text[])
            UNION ALL SELECT 'relation',c.oid,0,c.relowner,coalesce(c.relacl,acldefault(
                CASE WHEN c.relkind='S' THEN 's'::"char" ELSE 'r'::"char" END,c.relowner))
                FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=ANY($1::text[])
            UNION ALL SELECT 'column',c.oid,a.attnum,c.relowner,coalesce(a.attacl,'{}'::aclitem[])
                FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname=ANY($1::text[]) AND a.attnum>0 AND NOT a.attisdropped
            UNION ALL SELECT 'function',p.oid,0,p.proowner,coalesce(p.proacl,acldefault('f',p.proowner))
                FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname=ANY($1::text[])
            UNION ALL SELECT 'type',t.oid,0,t.typowner,coalesce(t.typacl,acldefault('T',t.typowner))
                FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace WHERE n.nspname=ANY($1::text[])
            UNION ALL SELECT 'default',d.oid,0,d.defaclrole,d.defaclacl FROM pg_default_acl d
            UNION ALL SELECT 'database',d.oid,0,d.datdba,coalesce(d.datacl,acldefault('d',d.datdba))
                FROM pg_database d WHERE d.datname=current_database())
            SELECT o.kind,o.object,o.sub,o.owner,a.grantor,a.grantee,a.privilege_type,a.is_grantable
            FROM objects o LEFT JOIN LATERAL aclexplode(CASE WHEN cardinality(o.acl)>0 THEN o.acl END) a ON true
            ORDER BY 1,2,3,5,6,7''', scopes)]
        sequences = {}
        for row in await conn.fetch('''SELECT n.nspname,c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE c.relkind='S' AND n.nspname=ANY($1::text[]) ORDER BY 1,2''', scopes):
            name = '.'.join(plans.quoted(row[key]) for key in ('nspname', 'relname'))
            sequences[name] = dict(await conn.fetchrow('SELECT last_value,is_called FROM ' + name))
        return {'columns': {'.'.join(key): value for key, value in columns.items()},
                'rows': rows, 'ledger': await preservation.ledger_fingerprints(conn),
                'ledgerColumns': [dict(row) for row in await conn.fetch('''SELECT attname,
                    format_type(atttypid,atttypmod) AS type,attnotnull,attnum FROM pg_attribute
                    WHERE attrelid='supabase_migrations.schema_migrations'::regclass AND attnum>0 AND NOT attisdropped ORDER BY attnum''')],
                'catalog': schema, 'roles': roles, 'memberships': memberships,
                'settings': settings, 'policies': policies, 'access': access, 'sequences': sequences}


def unchanged_projection(value, replacement_names, replacement_oids):
    """Mask only intended new-role grants and TO entries; never expressions."""
    result = copy.deepcopy(value)
    result['roles'] = [row for row in result['roles'] if row['rolname'] not in replacement_names]
    result['access'] = [row for row in result['access'] if row['grantee'] not in replacement_oids]
    for row in result['policies']:
        row['role_oids'] = [oid for oid in row['role_oids'] if oid not in replacement_oids]
    # Full effective ACLs and raw policy metadata above replace their textual
    # representations; ownership and all structural definition hashes stay.
    result['catalog'].pop('policies')
    for records in result['catalog'].values():
        for row in records:
            row.pop('acl', None)
    return result


class LocalInstaller:
    """Fixed local stages; unknown commit or drift never triggers auto retry.

    Keep this controller out of hosted startup. Only its owning test may create
    the disposable database and later review/drop retained NOLOGIN roles.
    """
    def __init__(self, url, journal, baseline, plan):
        self.database = local_target(url); self.url = url; self.journal = journal
        self.baseline = copy.deepcopy(baseline); self.plan = copy.deepcopy(plan)
        self.current = copy.deepcopy(baseline); self.oids = {}; self.held = False
        self.completed = []; self.overlap_proof = None; self.singleton_proof = None
        if journal.rows()[0]['data'] != {'database': self.database}:
            raise RehearsalHeld('Journal target differs')

    @classmethod
    async def prepare(cls, url, journal, originals, replacements):
        local_target(url)
        conn = await asyncpg.connect(url, timeout=10)
        try:
            await cls.identity(conn, local_target(url))
            before = await snapshot(conn)
            if set(replacements.values()) & {row['rolname'] for row in before['roles']}:
                raise RehearsalHeld('Replacement name collision held')
            original_oids = {row['oid'] for row in before['roles'] if row['rolname'] in originals.values()}
            policies = [row for row in before['policies'] if set(row['role_oids']) & (original_oids | {0})]
            outgoing = [row for row in before['memberships'] if row['member'] in original_oids]
            pins = {'applicationRows': digest(before['rows']),
                    'track1': digest({name: value for name, value in before['rows'].items() if name.startswith('actual_inventory.')}),
                    'migrationLedger': digest(before['ledger']), 'unaffectedAccess': digest(before['access']),
                    'administrativeMemberships': digest(before['memberships'])}
            plan = plans.prepare(originals, before['roles'], policies, outgoing, replacements,
                                 preservation_pins=pins, reference='local')
            return cls(url, journal, before, plan)
        finally:
            await conn.close()

    @staticmethod
    async def identity(conn, database):
        row = await conn.fetchrow('''SELECT current_database() AS database,host(inet_server_addr()) AS address,
            session_user=current_user AS same,r.rolsuper FROM pg_roles r WHERE r.rolname=session_user''')
        if not row or dict(row) != {'database': database, 'address': '127.0.0.1', 'same': True, 'rolsuper': True}:
            raise RehearsalHeld('Disposable local owner identity held')

    def statements(self, step):
        sql = self.plan['reviewSql']
        if step == 'create': return sql['createNOLOGIN']
        if step == 'overlap': return sql['grantExactProfile'] + sql['addExactPolicyCohort']
        if step == 'enable': return ['ALTER ROLE ' + plans.quoted(name) + ' LOGIN;' for name in self.plan['proposedReplacementRoles'].values()]
        if step == 'restore': return sql['restoreOriginalPolicyCohort']
        if step == 'disable_revoke': return ['ALTER ROLE ' + plans.quoted(name) + ' NOLOGIN;' for name in self.plan['proposedReplacementRoles'].values()] + sql['revokeExactReplacementProfile']
        raise RehearsalHeld('Unreviewed local stage held')

    def preserve(self, value):
        names = set(self.plan['proposedReplacementRoles'].values())
        if digest(unchanged_projection(value, names, set(self.oids.values()))) != digest(unchanged_projection(self.baseline, names, set())):
            raise RehearsalHeld('Independent preservation baseline changed')

    def profile_urls(self, phase):
        names = self.plan['originalRoles'] if phase == 'original' else self.plan['proposedReplacementRoles']
        uri = urlsplit(self.url)
        return {kind: uri._replace(netloc=name + '@127.0.0.1:' + str(uri.port)).geturl()
                for kind, name in names.items()}

    async def verify_overlap(self):
        if self.held or self.completed != ['create', 'overlap', 'enable']:
            raise RehearsalHeld('Acknowledged enabled cohort required')
        originals = {row['rolname']: row['oid'] for row in self.baseline['roles']}
        # Creation OIDs come from this journal, original OIDs/policy digest from
        # independent preflight. The invented project labels this local trial.
        pairs = {kind: {'original': {'name': old, 'oid': originals[old]},
                        'replacement': {'name': self.plan['proposedReplacementRoles'][kind],
                                        'oid': self.oids[self.plan['proposedReplacementRoles'][kind]]}}
                 for kind, old in self.plan['originalRoles'].items()}
        raw = json.dumps({'format': 'jaymax-permission-overlap-v1', 'projectRef': 'a' * 20,
                          'phase': 'overlap', 'rolePairs': pairs,
                          'baselinePolicySha256': self.plan['originalPolicySha256'],
                          'membershipContract': []}, sort_keys=True).encode()
        context = permissions.verify_record(raw, expected_sha256=hashlib.sha256(raw).hexdigest(),
            expected_project='a' * 20, expected_pairs=pairs,
            expected_baseline_policy_sha256=self.plan['originalPolicySha256'], expected_memberships=[])
        for phase in ('replacement', 'original'):
            urls = self.profile_urls(phase)
            revision = startup.bind_revision(context, urls, client_id='local_install_rehearsal',
                                             revision_id=str(uuid4()), reference='local')
            async with await startup.prepare_pair(revision, urls):
                pass
        self.overlap_proof = digest(self.current)

    async def verify_original_singletons(self):
        if self.held or self.completed != ['create', 'overlap', 'enable', 'restore']:
            raise RehearsalHeld('Restored acknowledged singleton cohort required')
        pools = []
        try:
            for kind, module in (('inventory', db_pg), ('accounts', db_auxiliary)):
                pool = await module._try_connect(self.profile_urls('original')[kind])
                if pool is None: raise RehearsalHeld('Original default pool held')
                pools.append(pool)
                async with pool.acquire() as conn:
                    report = (await runtime.inspect(conn, self.plan['originalRoles'][kind]) if kind == 'inventory'
                              else await auxiliary_permissions.inspect(conn))
                    if (report['status'] != ('passed_local_candidate' if kind == 'inventory' else 'passed')
                            or report['policyMode'] != 'single_role' or not report['readOnly'] or report['issues']):
                        raise RehearsalHeld('Original singleton inspection held')
        finally:
            for pool in reversed(pools): await startup.close_owned(pool)
        self.singleton_proof = digest(self.current)

    async def step(self, step, *, _fault=None):
        allowed = {'create': [], 'overlap': ['create'], 'enable': ['create', 'overlap'],
                   'restore': ['create', 'overlap', 'enable'],
                   'disable_revoke': ['create', 'overlap', 'enable', 'restore']}
        if self.held or allowed.get(step) != self.completed:
            raise RehearsalHeld('Local stage sequence or unresolved commit held')
        if step == 'restore' and self.overlap_proof != digest(self.current):
            raise RehearsalHeld('Both actual overlap pairs required before restoration')
        if step == 'disable_revoke' and self.singleton_proof != digest(self.current):
            raise RehearsalHeld('Original singleton verification required before NOLOGIN')
        conn = await asyncpg.connect(self.url, timeout=10); tx = None; committing = False
        self.held = True  # Any interruption, including a journal write failure, holds.
        try:
            async with asyncio.timeout(120):
                await self.identity(conn, self.database)
                # Inspect before intent; no mutation has occurred on a drift hold.
                before = await snapshot(conn)
                if digest(before) != digest(self.current):
                    raise RehearsalHeld('Catalog drift held before mutation')
                self.journal.append('intent', {'step': step, 'before': digest(before)})
                tx = conn.transaction(isolation='repeatable_read'); await tx.start()
                await conn.execute("SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='20s'")
                await conn.execute('SELECT pg_advisory_xact_lock(186432, (SELECT oid::int FROM pg_database WHERE datname=current_database()))')
                columns = {tuple(name.split('.')): columns for name, columns in self.baseline['columns'].items()}
                await preservation.lock_original_tables(conn, columns)
                if digest(await snapshot(conn)) != digest(before):
                    raise RehearsalHeld('Concurrent baseline drift held')
                if step in ('restore', 'disable_revoke') and await conn.fetchval(
                        'SELECT count(*) FROM pg_stat_activity WHERE usename=ANY($1::text[])',
                        list(self.plan['originalRoles'].values()) + list(self.plan['proposedReplacementRoles'].values())):
                    raise RehearsalHeld('Close all owned probes; unknown sessions held')
                for index, sql in enumerate(self.statements(step)):
                    await conn.execute(sql)
                    if _fault == 'mid_statement' and index == 0:
                        raise RehearsalHeld('Invented local statement failure')
                    if _fault == 'cancel_after_statement' and index == 0:
                        raise asyncio.CancelledError()
                after = await snapshot(conn)
                if step == 'create':
                    names = self.plan['proposedReplacementRoles'].values()
                    self.oids = {row['rolname']: row['oid'] for row in after['roles'] if row['rolname'] in names}
                self.preserve(after)
                self.journal.append('expected', {'step': step, 'before': digest(before), 'after': digest(after), 'oids': self.oids})
                committing = True
                if _fault == 'lost_ack_not_committed':
                    await tx.rollback()
                    raise ConnectionError('Invented local missing acknowledgement')
                await tx.commit()
                if _fault == 'lost_ack_committed':
                    raise ConnectionError('Invented local missing acknowledgement')
                self.journal.append('acknowledged', {'step': step, 'state': 'committed'})
                self.current = after; self.completed.append(step); self.held = False
                return 'committed'
        except BaseException as error:
            if committing:
                self.journal.append('commit_unknown', {'step': step})
            else:
                if tx is not None and conn.is_in_transaction():
                    await tx.rollback()
                self.journal.append('failed', {'step': step, 'state': 'rolled_back'})
            if not isinstance(error, Exception): raise
            raise RehearsalHeld('Local operation held; fresh reconciliation required') from None
        finally:
            await conn.close()

    async def reconcile(self):
        """Fresh connection, durable pins, no mutation or automatic retry.

        A committed state advances this same in-memory controller only after
        exact reconciliation. Process-restart restoration is not implemented.
        """
        if not self.held: raise RehearsalHeld('No pending local hold')
        rows = self.journal.rows()
        intents = [row for row in rows if row['event'] == 'intent']
        if not intents: raise RehearsalHeld('No durable mutation intent; review drift manually')
        intent = intents[-1]; step = intent['data']['step']
        tail = rows[intent['sequence'] + 1:]
        expected = next((row['data'] for row in tail if row['event'] == 'expected'), None)
        conn = await asyncpg.connect(self.url, timeout=10)
        try:
            await self.identity(conn, self.database)
            fresh = await snapshot(conn); observed = digest(fresh)
            state = ('committed' if expected and observed == expected['after'] else
                     'not_committed' if observed == intent['data']['before'] else 'ambiguous')
            self.journal.append('reconciled', {'step': step, 'state': state})
            if state == 'ambiguous': return state
            if state == 'committed':
                self.oids = dict(expected['oids']); self.preserve(fresh)
                if step not in self.completed: self.completed.append(step)
            elif step == 'create':
                self.oids = {}
            self.current = fresh; self.held = False
            return state
        finally:
            await conn.close()
