"""Credential rotation gates and failure classification without operational writes."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock,patch
from urllib.parse import urlparse,unquote
import asyncpg
import rotate_build_connections as rotation

PROJECT='a'*20
OWNER={'USE_PG':'true','DATABASE_URL':'postgresql://postgres.'+PROJECT+':invented@aws-0-us-east-1.pooler.supabase.com:5432/postgres'}
ROLES={'inventory':'jaymax_build_inventory_'+'1'*12,'accounts':'jaymax_build_accounts_'+'2'*12}
OLD={'USE_PG':'true',**{f+'_ENABLED':'false' for f in rotation.candidate.readiness.FEATURES},
 **{k:'postgresql://'+ROLES[kind]+'.'+PROJECT+':'+'x'*64+'@aws-0-us-east-1.pooler.supabase.com:5432/postgres' for kind,k in rotation.KEYS.items()}}
RECEIPT={'status':'passed_retained_build_connections','projectRef':PROJECT,'roles':ROLES}
WORKFLOW={'status':'passed_retained_login_enabled_workflows','projectRef':PROJECT}
class InputGuards(unittest.TestCase):
 def test_exact_roles_endpoint_held_flags_and_workflow_required(self):
  self.assertEqual(rotation.inputs(OWNER,OLD,RECEIPT,WORKFLOW,PROJECT),ROLES)
  for overlay,receipt,workflow in ((OLD|{'PREP_EXECUTION_ENABLED':'true'},RECEIPT,WORKFLOW),(OLD|{'AUXILIARY_DATABASE_URL':OLD['DATABASE_URL']},RECEIPT,WORKFLOW),(OLD,RECEIPT,WORKFLOW|{'status':'held'})):
   with self.assertRaises(ValueError):rotation.inputs(OWNER,overlay,receipt,workflow,PROJECT)
 def test_replacement_preserves_identity_endpoint_and_flags(self):
  new=rotation.replacement_overlay(OLD,{'inventory':'i'*64,'accounts':'j'*64})
  for kind,key in rotation.KEYS.items():
   prior=urlparse(OLD[key]);current=urlparse(new[key])
   self.assertEqual((current.username,current.hostname,current.port,current.path),(prior.username,prior.hostname,prior.port,prior.path))
   self.assertNotEqual(current.password,prior.password)
  self.assertEqual({k:v for k,v in new.items() if k not in rotation.KEYS.values()},{k:v for k,v in OLD.items() if k not in rotation.KEYS.values()})
 def test_private_writer_never_overwrites_existing_secret_file(self):
  with TemporaryDirectory() as root:
   path=Path(root)/'runtime-connections.env';path.write_text('original-marker',encoding='utf-8')
   with self.assertRaises(FileExistsError):rotation.write_private(path,OLD)
   self.assertEqual(path.read_text(),'original-marker')
class AsyncGuards(unittest.IsolatedAsyncioTestCase):
 async def test_invalid_target_never_checks_private_storage_or_connects(self):
  with patch.object(rotation,'dotenv_values',side_effect=[OWNER,OLD]),patch.object(Path,'read_bytes',return_value=b''),patch.object(rotation.json,'loads',side_effect=[RECEIPT,WORKFLOW|{'status':'held'}]),patch.object(rotation.provision,'private_directory') as private,patch.object(rotation.asyncpg,'connect',AsyncMock()) as connect:
   with self.assertRaises(ValueError):await rotation.run(Path('o'),Path('p'),Path('r'),Path('w'),PROJECT,Path('d'),Path('output'))
   private.assert_not_called();connect.assert_not_awaited()
 async def test_transport_failure_is_not_authentication_denial(self):
  with patch.object(rotation,'connect',AsyncMock(side_effect=TimeoutError)):
   with self.assertRaises(TimeoutError):await rotation.denied('invented','role')
  with patch.object(rotation,'connect',AsyncMock(side_effect=asyncpg.InvalidPasswordError)):
   self.assertEqual(await rotation.denied('invented','role'),'InvalidPasswordError')
 async def test_fresh_acceptance_is_closed_and_holds(self):
  conn=AsyncMock()
  with patch.object(rotation,'connect',AsyncMock(return_value=conn)):
   with self.assertRaises(AssertionError):await rotation.denied('invented','role')
  conn.close.assert_awaited_once()

class RefreshGuards(unittest.IsolatedAsyncioTestCase):
 async def test_refresh_retries_only_password_denial_and_has_bound(self):
  conn=AsyncMock()
  with patch.object(rotation,'connect',AsyncMock(side_effect=[asyncpg.InvalidPasswordError(),conn])) as connect,patch.object(rotation.asyncio,'sleep',AsyncMock()) as sleep:
   self.assertIs(await rotation.refreshed_connection('invented','role'),conn)
   self.assertEqual(connect.await_count,2);sleep.assert_awaited_once_with(15)
  with patch.object(rotation,'connect',AsyncMock(side_effect=asyncpg.InvalidPasswordError)) as connect,patch.object(rotation.asyncio,'sleep',AsyncMock()):
   with self.assertRaises(asyncpg.InvalidPasswordError):await rotation.refreshed_connection('invented','role')
   self.assertEqual(connect.await_count,3)
  with patch.object(rotation,'connect',AsyncMock(side_effect=TimeoutError)),patch.object(rotation.asyncio,'sleep',AsyncMock()) as sleep:
   with self.assertRaises(TimeoutError):await rotation.refreshed_connection('invented','role')
   sleep.assert_not_awaited()

class DisabledLoginGuards(unittest.IsolatedAsyncioTestCase):
 async def test_internal_pooler_failure_requires_subsequent_real_authentication_denial(self):
  with patch.object(rotation,'denied',AsyncMock(side_effect=[asyncpg.InternalServerError(),'InvalidAuthorizationSpecificationError'])),patch.object(rotation.asyncio,'sleep',AsyncMock()):
   result=await rotation.disabled_denial('invented','role')
   self.assertTrue(result['transientInternalErrorRetried']);self.assertEqual(result['denialType'],'InvalidAuthorizationSpecificationError')
  with patch.object(rotation,'denied',AsyncMock(side_effect=asyncpg.InternalServerError)) as denied,patch.object(rotation.asyncio,'sleep',AsyncMock()):
   with self.assertRaises(asyncpg.InternalServerError):await rotation.disabled_denial('invented','role')
   self.assertEqual(denied.await_count,2)
