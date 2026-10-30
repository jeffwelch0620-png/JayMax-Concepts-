"""M3 store transfers: out of one store and into the other once, at the sender's latest cost."""
import os
import unittest
from decimal import Decimal as D
from uuid import uuid4

import asyncpg
from pydantic import ValidationError

import store_transfers as transfers


class TransferModelTests(unittest.TestCase):
    def test_send_and_receive_inputs(self):
        transfers.SendIn(to_store_id='rudds', item_code='test_food', sent_base_quantity='10', kind='lend', sent_date='2026-10-05', note='Out of flour')
        for bad in (dict(sent_base_quantity='0'), dict(sent_base_quantity='NaN'), dict(kind='sale'), dict(note=' '), dict(price='1')):
            with self.assertRaises(ValidationError):
                transfers.SendIn(**(dict(to_store_id='rudds', item_code='test_food', sent_base_quantity='10', kind='lend', sent_date='2026-10-05', note='x') | bad))
        transfers.StepIn(action='receive', received_base_quantity='8', record_date='2026-10-06', note='2 lb torn bag')
        transfers.StepIn(action='cancel', note='Not needed')
        for bad in (dict(action='receive', note='x'), dict(action='receive', received_base_quantity='1', note='x'),
                    dict(action='receive', received_base_quantity='-1', record_date='2026-10-06', note='x')):
            with self.assertRaises(ValidationError): transfers.StepIn(**bad)

    def test_cost_is_rounded_to_the_cent(self):
        self.assertEqual(transfers.cents(D('8'), D('40.00'), D('40')), D('8.00'))
        self.assertEqual(transfers.cents(D('1'), D('10.00'), D('3')), D('3.33'))
        self.assertEqual(transfers.cents(D('1'), D('5.00'), D('8')), D('0.63'))  # 0.625 rounds half up


import test_actual_inventory as actual

MIGRATION = 'migrations/20261031_store_transfers.sql'


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'), 'Disposable PostgreSQL required')
class StoreTransferDatabaseTests(actual.ActualInventoryTests):
    # Reuse the food-cost fixture without re-running its own tests here.
    for _name in [n for n in dir(actual.ActualInventoryTests) if n.startswith('test_')]:
        locals()[_name] = None
    del _name

    async def asyncSetUp(self):
        await super().asyncSetUp()
        async with self.pool.acquire() as c:
            await c.execute((actual.native.ROOT / MIGRATION).read_text(encoding='utf-8'))
            await c.execute('''INSERT INTO store_items SELECT (jsonb_populate_record(NULL::store_items, to_jsonb(s) || '{"store_id":"rudds"}')).*
                FROM store_items s WHERE store_id='berts' AND item_code='test_food' ON CONFLICT DO NOTHING''')

    def send_body(self, **changes):
        return dict(to_store_id='rudds', item_code='test_food', sent_base_quantity='10', kind='lend', sent_date='2026-10-05', note='Rudd\'s ran out') | changes

    async def send(self, store='berts', **changes):
        async with self.pool.acquire() as c:  # Rudd's counts the item in the same unit as Bert's
            await c.execute('''INSERT INTO purchasing.item_bases(store_id,item_code,base_unit) SELECT 'rudds',item_code,base_unit FROM purchasing.item_bases
                WHERE store_id='berts' AND item_code='test_food' ON CONFLICT DO NOTHING''')
        body = self.send_body(**changes)
        p = await self.client.post(f'/api/pg/actual-inventory/{store}/transfers/preview', json=body)
        if p.status_code != 200: return p
        return await self.client.post(f'/api/pg/actual-inventory/{store}/transfers', json={'transfer': body, 'expected_review_hash': p.json()['reviewHash'], 'reviewed': True},
                                      headers={'Idempotency-Key': str(uuid4())})

    async def step(self, store, transfer, **body):
        return await self.client.post(f"/api/pg/actual-inventory/{store}/transfers/{transfer['id']}/steps", json=body, headers={'Idempotency-Key': str(uuid4())})

    async def test_transfer_moves_cost_once_between_store_periods(self):
        _, a, b = await self.pair()
        self.assertEqual((await self.purchase())[0].status_code, 200)  # 40 lb for $40.00 on 2026-10-04
        sent = await self.send(); self.assertEqual(sent.status_code, 200, sent.text)
        t = sent.json()['transfer']
        self.assertEqual((t['status'], D(t['cost_amount']), D(t['cost_base_quantity'])), ('sent', D('40.00'), D('40')))
        # Sent but not received changes neither store's food cost.
        self.assertNotIn('transferLines', (await self.report(a, b)).json())
        got = await self.step('rudds', t, action='receive', received_base_quantity='8', record_date='2026-10-06', note='2 lb torn bag')
        self.assertEqual(got.status_code, 200, got.text)
        t = got.json()['transfer']
        self.assertEqual((t['status'], D(t['transfer_cost_amount']), D(t['short_base_quantity'])), ('received', D('8.00'), D('2')))
        # Bert's: 8 lb and $8.00 leave its period (the 2 lb lost stay in Bert's usage).
        report = (await self.report(a, b)).json(); self.assertEqual(report['status'], 'complete', report)
        row = report['rows'][0]
        self.assertEqual((D(row['netTransferQuantity']), D(row['netTransferCost']), D(row['actualUsage']), D(row['actualFoodCost'])), (D(-8), D('-8.00'), D(42), D('47.00')))
        self.assertEqual(D(report['netTransferCost']), D('-8.00')); self.assertEqual(D(report['netPurchaseCost']), D('40.00'))
        # Rudd's: the same 8 lb and $8.00 come in; nothing is a purchase or a sale.
        async with self.pool.acquire() as c:
            moved = await c.fetch("SELECT store_id, base_quantity, cost_amount FROM actual_inventory.transfer_movements ORDER BY store_id")
            self.assertEqual([(r['store_id'], r['base_quantity'], r['cost_amount']) for r in moved], [('berts', D(-8), D('-8.00')), ('rudds', D(8), D('8.00'))])
            self.assertEqual(await c.fetchval("SELECT count(*) FROM purchasing.current_purchase_facts WHERE store_id='rudds'"), 0)
        listed = (await self.client.get('/api/pg/actual-inventory/rudds/transfers', params={'since': '2026-10-01'})).json()
        self.assertEqual([x['status'] for x in listed['transfers']], ['received'])

    async def test_only_the_right_store_signs_and_closed_periods_are_held(self):
        _, a, b = await self.pair()
        self.assertEqual((await self.purchase())[0].status_code, 200)
        # A store with no purchase cost for the item cannot price a transfer.
        none = await self.send(store='rudds', to_store_id='berts'); self.assertEqual(none.status_code, 409); self.assertIn('no purchase cost', none.text)
        t = (await self.send()).json()['transfer']
        self.assertEqual((await self.step('berts', t, action='receive', received_base_quantity='8', record_date='2026-10-06', note='x')).status_code, 403)
        self.assertEqual((await self.step('rudds', t, action='cancel', note='x')).status_code, 403)
        self.assertEqual((await self.step('rudds', t, action='receive', received_base_quantity='11', record_date='2026-10-06', note='x')).status_code, 422)
        self.assertEqual((await self.step('rudds', t, action='receive', received_base_quantity='8', record_date='2026-10-04', note='x')).status_code, 422)
        # Close Bert's period: a receipt dated inside it is held; after it, accepted.
        self.assertEqual((await self.close((await self.report(a, b)).json())).status_code, 200)
        self.assertEqual((await self.step('rudds', t, action='receive', received_base_quantity='8', record_date='2026-10-06', note='x')).status_code, 409)
        ok = await self.step('rudds', t, action='receive', received_base_quantity='10', record_date='2026-10-09', note='All arrived')
        self.assertEqual(ok.status_code, 200, ok.text)
        self.assertEqual((await self.step('berts', t, action='cancel', note='Too late')).status_code, 409)
        # A cancelled transfer moves nothing.
        c = (await self.send(sent_date='2026-10-09')).json()['transfer']
        self.assertEqual((await self.step('berts', c, action='cancel', note='Not needed')).status_code, 200)
        async with self.pool.acquire() as conn:
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM actual_inventory.transfer_movements WHERE transfer_id=$1', c['id']), 0)

    async def test_database_refuses_a_forged_cost(self):
        await self.pair()
        self.assertEqual((await self.purchase())[0].status_code, 200)
        t = (await self.send()).json()['transfer']
        async with self.pool.acquire() as c:
            with self.assertRaisesRegex(asyncpg.PostgresError, 'latest purchase cost'):
                await c.execute('''INSERT INTO actual_inventory.store_transfers(from_store_id,to_store_id,item_code,base_unit,sent_base_quantity,kind,sent_date,
                    cost_mapping_id,cost_base_quantity,cost_amount,cost_record_date,note,actor,request_key,request_fingerprint)
                    VALUES('berts','rudds','test_food',$1,1,'lend','2026-10-05',$2,$3,1.00,'2026-10-04','Forged','tester',$4,$5)''',
                    t['base_unit'], t['cost_mapping_id'], D(t['cost_base_quantity']), uuid4(), b'\x00' * 32)
            with self.assertRaisesRegex(asyncpg.PostgresError, 'Only the receiving store'):
                await c.execute('''INSERT INTO actual_inventory.store_transfer_events(transfer_id,action,store_id,received_base_quantity,record_date,transfer_cost_amount,
                    note,actor,request_key,request_fingerprint) VALUES($1,'receive','berts',1,'2026-10-06',0,'Forged','tester',$2,$3)''', t['id'], uuid4(), b'\x00' * 32)
