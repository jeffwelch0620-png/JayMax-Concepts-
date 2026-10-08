"""Synthetic dependency graphs, released history and read-only boundaries."""
from uuid import uuid4
from unittest.mock import patch
import os
import test_prep_batches as fixture


class PrepCorrectionReviewTests(fixture.PrepBatchTests):
    async def inspect(self, event, store='berts'):
        return await self.client.get(f"/api/pg/purchases/{store}/prep-batches/{event['id']}/correction-review")

    async def test_dependency_graph_holds_current_use_but_keeps_released_descendants_as_history(self):
        source,_ = await self.record(await self.entry())
        consumer,_ = await self.record(await self.nested(source))
        async with self.pool.acquire() as conn:
            profile=await conn.fetchval('SELECT output_profile_id FROM prep_inventory.recipe_versions WHERE id=$1',fixture.UUID(consumer['recipe_version_id']))
        product=await self.product('Invented third-level prepared output')
        output_profile=await self.profile(product)
        recipe,_=await self.promote(self.recipe(product,output_profile,entered_yield='5',lines=[dict(source_kind='prepared',
            prepared_recipe_id=consumer['recipe_version_id'],prepared_profile_id=str(profile),quantity='5',source_unit='lb',factor='1',evidence='Measured third-level input')]))
        grandchild_body=await self.entry(recipe,output_quantity='5',performed_at='2026-10-05T12:00:00-04:00')
        grandchild_body['inputs'][0].update(quantity='5',source_batch_id=consumer['id'],included_loss_quantity=None,loss_evidence=None)
        grandchild,_=await self.record(grandchild_body)
        result = await self.inspect(source); self.assertEqual(result.status_code,200,result.text)
        data = result.json()
        self.assertEqual(data['gate']['status'],'held')
        self.assertEqual({l['id'] for l in data['lots']},{source['id'],consumer['id'],grandchild['id']})
        self.assertEqual(data['coverage']['containers'],'not_installed')
        self.assertFalse(data['track1Writeback']); self.assertTrue(data['readOnly'])
        self.assertEqual(len(data['preparedInputHistory']),2)
        before = await self.inspect(source); self.assertEqual(before.json(),data)
        await self.change(grandchild,dict(kind='void',reason='Invented erroneous descendant'))
        void,_ = await self.change(consumer,dict(kind='void',reason='Invented erroneous consumer'))
        data = (await self.inspect(source)).json()
        self.assertEqual(data['gate']['status'],'eligible_for_preview')
        self.assertEqual(len(data['preparedInputHistory']),4)
        self.assertIn(void['id'],[l['id'] for l in data['lots']])
        self.assertEqual((await self.inspect(consumer)).json()['currentEventId'],void['id'])
        self.assertEqual((await self.inspect(consumer)).json()['gate']['status'],'held')

    async def test_dependency_review_uses_location_identity_and_feature_boundary(self):
        source,_ = await self.record(await self.entry())
        self.assertEqual((await self.inspect(source,'rudds')).status_code,404)
        self.assertEqual((await self.inspect({'id':str(uuid4())})).status_code,404)
        self.assertEqual((await self.client.get(f"/api/pg/purchases/berts/prep-batches/{source['id']}/correction-review",headers={'Authorization':'Bearer invalid'})).status_code,401)
        with patch.dict(os.environ,{'PREP_BATCHES_ENABLED':'false'}):
            self.assertEqual((await self.inspect(source)).status_code,503)
