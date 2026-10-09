"""Bounded NOLOGIN comparison using only a newly owned pooler test connection."""
import asyncio
import re
import asyncpg
import credential_retirement_review as review
from db_tls import connection_tls


class DrainTrialError(RuntimeError):
    """Safe category only; raw driver messages must never reach evidence."""


async def connect_role(url, role, label=None):
    settings = {'default_transaction_read_only':'on'}
    if label:
        settings['application_name'] = label
    conn = await asyncpg.connect(url,ssl=connection_tls(url),timeout=10,
        command_timeout=10,statement_cache_size=0,server_settings=settings)
    try:
        identity = dict(await conn.fetchrow('SELECT session_user AS login,current_user AS current'))
        if identity != {'login':role,'current':role}:
            raise DrainTrialError('Fresh client LOGIN identity held')
        # The observed shared pooler did not forward these startup settings.
        # Configure the owned session explicitly, then require acknowledgement.
        await conn.execute('SET default_transaction_read_only=on')
        if label:
            if await conn.fetchval("SELECT set_config('application_name',$1,false)",label) != label:
                raise DrainTrialError('Owned client label setup held')
        if await conn.fetchval('SHOW transaction_read_only') != 'on':
            raise DrainTrialError('Fresh client read-only setup held')
        return conn
    except BaseException:
        await conn.close()
        raise


async def classify(url,role):
    try:
        conn = await connect_role(url,role)
    except Exception as exc:
        result = {'accepted':False,'errorType':type(exc).__name__,
            'sqlstate':getattr(exc,'sqlstate',None),'category':'unclassified'}
        message = str(exc).strip()
        if (isinstance(exc,asyncpg.InvalidAuthorizationSpecificationError) and
                getattr(exc,'sqlstate',None)=='28000' and 'not permitted to log in' in message.lower()):
            result['category'] = 'login_not_permitted'
        elif isinstance(exc,asyncpg.InvalidPasswordError) and getattr(exc,'sqlstate',None)=='28P01':
            result['category'] = 'password_denied'
        elif isinstance(exc,asyncpg.InternalServerError) and message in (
                '(EAUTHQUERY) user not found in the database','user not found in the database (EAUTHQUERY)'):
            # Retain corroborating lookup evidence, but never count XX000 as a
            # native authentication denial or as a passing strict comparison.
            result['category'] = 'eauthquery_user_not_found'
        return result
    else:
        await conn.close()
        return {'accepted':True,'category':'fresh_client_accepted'}


async def prepare_owned(owner,client,expected,role,label):
    identity = await client.fetchrow("""SELECT pg_backend_pid() AS pid,session_user AS login,
        current_user AS current,current_setting('application_name') AS label,
        current_setting('transaction_read_only') AS read_only,
        (SELECT backend_start FROM pg_stat_activity WHERE pid=pg_backend_pid()) AS started""")
    if (identity['login']!=role or identity['current']!=role or identity['label']!=label
            or identity['read_only']!='on'):
        raise DrainTrialError('Owned pooler identity or forwarded label held')
    owner_pid = await owner.fetchval('SELECT pg_backend_pid()')
    rows = await owner.fetch(review.ACTIVITY,[role])
    row = next((value for value in rows if value['pid']==identity['pid']),None)
    review.validate_probe(row,expected,role,identity['pid'],identity['started'],label,owner_pid)
    return {'role':role,'pid':identity['pid'],'backendStart':identity['started'].isoformat(),
        'ownedReadOnlyPoolerClientVerified':True,'existingApplicationSession':False}


async def compare_role(owner,client,expected,role,label,direct_url,pooler_url,other_role,other_urls,check,emit):
    if not re.fullmatch(r'jaymax_build_(inventory|accounts)_[a-f0-9]{12}',role) or role not in expected:
        raise DrainTrialError('Exact generated build role required')
    check['ownedClient'] = await prepare_owned(owner,client,expected,role,label)
    if await owner.fetchval('SELECT oid FROM pg_roles WHERE rolname=$1',role) != expected[role]:
        raise DrainTrialError('Recorded role OID changed before disable')
    emit('owned_pooler_identity_prepared')
    attempted = False
    try:
        # Identifier is pinned to the reviewed generated role and OID above.
        # Journal before mutation so an interrupted owner can restore only it.
        check['disableAttempted'] = True
        emit('exact_role_disable_prepared')
        attempted = True
        await owner.execute('ALTER ROLE "'+role+'" NOLOGIN')
        check['ownerConfirmsNoLogin'] = await owner.fetchval('SELECT rolcanlogin FROM pg_roles WHERE oid=$1',expected[role]) is False
        emit('exact_role_nologin_confirmed')
        if not check['ownerConfirmsNoLogin']:
            raise DrainTrialError('Owner NOLOGIN acknowledgement held')
        check['direct'] = await classify(direct_url,role)
        emit('fresh_direct_classified')
        if check['direct']['category']!='login_not_permitted':
            raise DrainTrialError('Fresh direct login denial held')
        check['ownedSignalPrepared'] = True
        emit('owned_pooler_signal_prepared')
        check['signal'] = await review.signal_owned_probe(owner,client,expected,role,label)
        # Check the actual pooler-facing client, not just the terminated backend.
        for _ in range(20):
            if client.is_closed():
                break
            await asyncio.sleep(.1)
        check['poolerClientObservedClosed'] = client.is_closed()
        await client.close()
        emit('owned_pooler_signal_acknowledged')
        if not check['poolerClientObservedClosed']:
            raise DrainTrialError('Pooler client closure not observed')
        await asyncio.sleep(15)
        check['poolerAttempts'] = [await classify(pooler_url,role)]
        emit('fresh_pooler_classified')
        first = check['poolerAttempts'][0]
        if not first['accepted'] and first.get('errorType')=='InternalServerError':
            await asyncio.sleep(15)
            check['poolerAttempts'].append(await classify(pooler_url,role))
            emit('bounded_pooler_retry_classified')
        for url in other_urls:
            conn = await connect_role(url,other_role)
            await conn.close()
        check['otherRoleAvailableOnBothPaths'] = True
        emit('other_role_available')
        if any(result['accepted'] for result in check['poolerAttempts']):
            raise DrainTrialError('Fresh disabled pooler client accepted after owned drain')
        if check['poolerAttempts'][-1]['category'] not in ('login_not_permitted','password_denied'):
            raise DrainTrialError('Pooler response did not prove strict authentication denial')
        check['strictOwnedDrainComparisonPassed'] = True
    finally:
        if attempted:
            await owner.execute('ALTER ROLE "'+role+'" LOGIN')
            check['ownerConfirmsLoginRestored'] = await owner.fetchval('SELECT rolcanlogin FROM pg_roles WHERE oid=$1',expected[role]) is True
            emit('login_restored')
        await client.close()
