"""Query budgets must be independent of the number of retained history roots."""
from datetime import datetime, timezone
from decimal import Decimal
import unittest
from uuid import uuid4
import prep_containers as containers
import staff_prep_counts as counts
from purchase_api import serial


class WorkflowReadTests(unittest.IsolatedAsyncioTestCase):
    async def test_workflow_reads_container_queries_are_constant_for_one_and_300_fills(self):
        budgets=[]
        for size in (1,300):
            fills=[dict(id=uuid4(),store_id='berts',base_quantity=Decimal('10.000000000001')) for _ in range(size)]
            moves=[dict(id=uuid4(),fill_id=f['id'],revision=1,action='waste',storage_delta=Decimal('-1'),service_delta=Decimal(0),compartment='storage') for f in fills]
            pairs=[dict(fill_id=f['id'],link={'move_id':m['id'],'observation_id':uuid4()},event={'quantity':Decimal('1.000000000001')}) for f,m in zip(fills,moves)]
            for pair in pairs:pair['event']['id']=pair['link']['observation_id']
            class Connection:
                def __init__(self):self.calls=[]
                async def fetch(self,sql,*args):
                    self.calls.append(sql)
                    if 'container_fills WHERE' in sql:return fills
                    if 'm.* FROM prep_inventory.container_moves' in sql:return moves
                    if 'm.fill_id,l.*' in sql:return [dict(fill_id=p['fill_id'],**p['link']) for p in pairs]
                    if 'SELECT o.*' in sql:return [p['event'] for p in pairs]
                    raise AssertionError('Per-row history read: '+sql)
                async def fetchval(self,sql,*args):self.calls.append(sql);return True
            conn=Connection();states=await containers.fill_states(conn,'berts')
            budgets.append(len(conn.calls));self.assertEqual(len(states),size)
            for state,f,m,pair in zip(states,fills,moves,pairs):
                self.assertEqual(state,containers.contents_state(f,[m],[dict(link=pair['link'],event=pair['event'])]))
                self.assertEqual(state['storage'],'9.000000000001')
            self.assertEqual(budgets[-1],5)
        self.assertEqual(*budgets)

    async def test_workflow_reads_sheet_queries_do_not_grow_with_sheets_or_items(self):
        budgets=[]
        for size in (1,300):
            product,version,profile=uuid4(),uuid4(),uuid4()
            instant=datetime(2026,10,8,tzinfo=timezone.utc)
            item=dict(product_id=str(product),product_version_id=str(version),profile_id=str(profile),name='Measured sauce')
            sheets=[dict(id=uuid4(),store_id='berts',sheet_snapshot={'stamp':{'performed_at':instant.isoformat(),'timezone_name':'UTC'},'items':[item]}) for _ in range(size)]
            definitions=serial(dict(products=[dict(id=version)],profiles=[dict(id=profile,product_version_id=version)]))
            class Connection:
                def __init__(self):self.calls=[]
                async def fetch(self,sql,*args):
                    self.calls.append(sql)
                    if 'SELECT s.*' in sql:return sheets
                    if 'staff_submissions' in sql or 'staff_decisions' in sql:return []
                    if 'SELECT id FROM prep_inventory.products' in sql:return [{'id':product}]
                    if 'SELECT performed_at FROM prep_inventory.observations' in sql:return []
                    if 'SELECT s.id,s.performed_at' in sql:return []
                    raise AssertionError('Per-sheet scope/unit read: '+sql)
                async def fetchval(self,sql,*args):self.calls.append(sql);return 'UTC'
            conn=Connection();results=await counts.details(conn,'berts',definitions=definitions)
            budgets.append(len(conn.calls));self.assertEqual(len(results),size)
            for row,sheet in zip(results,sheets):self.assertEqual(row,counts.review_record(sheet,[],None,[]))
            self.assertEqual(budgets[-1],7)
        self.assertEqual(*budgets)
