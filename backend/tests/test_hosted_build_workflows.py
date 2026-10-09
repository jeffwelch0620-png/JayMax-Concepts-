"""Build workflow target gates reject unsafe fixtures/config before network access."""
import unittest
from unittest.mock import AsyncMock,patch
from tempfile import TemporaryDirectory
from pathlib import Path
import hosted_build_workflows as workflow

PROJECT='aaaaaaaaaaaaaaaaaaaa'
OWNER={'USE_PG':'true','DATABASE_URL':'postgresql://postgres.'+PROJECT+':invented@aws-0-us-east-1.pooler.supabase.com:5432/postgres'}
OVERLAY={'USE_PG':'true','DATABASE_URL':'postgresql://inventory.'+PROJECT+':invented@aws-0-us-east-1.pooler.supabase.com:5432/postgres',
 'AUXILIARY_DATABASE_URL':'postgresql://accounts.'+PROJECT+':invented@aws-0-us-east-1.pooler.supabase.com:5432/postgres',
 **{f+'_ENABLED':'false' for f in workflow.candidate.readiness.FEATURES}}
PROVISION={'status':'passed_retained_build_connections','projectRef':PROJECT,'roles':{'inventory':'inventory','accounts':'accounts'}}
PRIOR={'workflow':{'status':'passed','temporaryStore':'hosted_trial_'+'1'*32}}

class WorkflowGuards(unittest.TestCase):
 def test_recorded_roles_and_disk_flags_are_required(self):
  self.assertEqual(workflow.target_inputs(OWNER,OVERLAY,PROVISION,PRIOR,PROJECT),PRIOR['workflow']['temporaryStore'])
  for changed in (OVERLAY|{'DATABASE_URL':OVERLAY['DATABASE_URL'].replace('inventory.','other.')},OVERLAY|{'PREP_EXECUTION_ENABLED':'true'}):
   with self.assertRaises(ValueError):workflow.target_inputs(OWNER,changed,PROVISION,PRIOR,PROJECT)

 def test_operational_location_and_cross_project_accounts_are_rejected(self):
  with self.assertRaises(ValueError):workflow.target_inputs(OWNER,OVERLAY,PROVISION,{'workflow':{'status':'passed','temporaryStore':'berts'}},PROJECT)
  with self.assertRaises(ValueError):workflow.target_inputs(OWNER,OVERLAY|{'AUXILIARY_DATABASE_URL':OVERLAY['AUXILIARY_DATABASE_URL'].replace(PROJECT,'b'*20)},PROVISION,PRIOR,PROJECT)

class NoNetworkGuard(unittest.IsolatedAsyncioTestCase):
 async def test_invalid_overlay_never_connects(self):
  with patch.object(workflow,'dotenv_values',side_effect=[OWNER,OVERLAY|{'USE_PG':'false'}]),patch.object(
    workflow.json,'loads',side_effect=[PROVISION,PRIOR]),patch.object(Path,'read_bytes',return_value=b''),patch.object(workflow.asyncpg,'connect',AsyncMock()) as connect:
   with self.assertRaises(ValueError):await workflow.run(Path('owner'),Path('overlay'),Path('provision'),Path('prior'),PROJECT,Path('output'))
   connect.assert_not_awaited()

class JournalGuards(unittest.TestCase):
 def test_transient_file_lock_retries_but_permanent_hold_preserves_old_receipt(self):
  with TemporaryDirectory() as folder:
   path=Path(folder)/'receipt.json';path.write_text('old-marker',encoding='utf-8')
   original=Path.replace
   attempts=[]
   def once(source,target):
    attempts.append(1)
    if len(attempts)==1:raise PermissionError('invented transient lock')
    return original(source,target)
   with patch.object(Path,'replace',once),patch.object(workflow.time,'sleep'):
    workflow.save_evidence(path,{'stage':'saved'})
   self.assertEqual(workflow.json.loads(path.read_text())['stage'],'saved')
   with patch.object(Path,'replace',side_effect=PermissionError('invented persistent lock')) as replace,patch.object(workflow.time,'sleep'):
    with self.assertRaises(PermissionError):workflow.save_evidence(path,{'stage':'not-saved'})
    self.assertEqual(replace.call_count,10)
   self.assertEqual(workflow.json.loads(path.read_text())['stage'],'saved')

class ForecastResponseGuard(unittest.TestCase):
 def test_reviewed_projection_is_exact_and_nonaccounting(self):
  valid={'accounting':False,'projection':{'amount':'1234.56','accounting':False,'basis':'manual_sales_forecast'}}
  workflow.verify_forecast_response(valid)
  for changed in ({'amount':'1234.56','accounting':False}, valid|{'accounting':True},
      valid|{'projection':valid['projection']|{'amount':'1234.559'}},
      valid|{'projection':valid['projection']|{'accounting':True}}):
   with self.assertRaises(AssertionError):workflow.verify_forecast_response(changed)

class PreservationScopeGuard(unittest.IsolatedAsyncioTestCase):
 async def test_operational_state_and_mismatched_prep_result_are_rejected_before_sql(self):
  conn=AsyncMock()
  with self.assertRaises(ValueError):await workflow.state_baseline(conn,{},'berts')
  with self.assertRaises(ValueError):await workflow.prep_append_ids(conn,PRIOR['workflow']['temporaryStore'],{'status':'passed','store':'berts'})
  conn.fetch.assert_not_awaited();conn.fetchrow.assert_not_awaited();conn.fetchval.assert_not_awaited()
