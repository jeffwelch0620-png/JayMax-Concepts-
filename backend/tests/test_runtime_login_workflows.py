"""Ordinary restricted LOGIN workflows in unique loopback databases only.

Reuse selected behavioral assertions without collecting their inherited suites.
Fixture construction and explicit owner-control comparisons remain administrative;
the application runtime pool authenticates directly, never by SET ROLE.
"""
import os
import re
import secrets
from contextlib import AsyncExitStack
from urllib.parse import urlsplit

import asyncpg
import db_pg
import runtime_permissions as candidate
import test_runtime_permission_workflows as native
import test_runtime_manager_workflows as manager
import test_runtime_task_cutover as tasks
import test_runtime_shared_state as shared
import test_runtime_planning_ai as planning


class OrdinaryLoginMixin:
    async def prepare_runtime(self):
        # Complete the existing loopback guards, exact SQL and grants first.
        self.runtime_password = None
        await super().prepare_runtime()
        self.runtime_password = secrets.token_hex(32)
        await self.admin.execute(
            'ALTER ROLE ' + self.runtime_role + " LOGIN PASSWORD '" +
            self.runtime_password + "' CONNECTION LIMIT 12")
        old_pool = self.pool
        import server
        server_bound = server.db_pg._pool is old_pool
        await old_pool.close()
        source = os.environ['NATIVE_PURCHASE_TEST_DSN'].rsplit('/', 1)[0] + '/' + self.db
        self.pool = await self.runtime_pool(source)
        if server_bound:
            server.db_pg._pool = self.pool
        async with self.pool.acquire() as conn:
            report = await candidate.inspect(conn, self.runtime_role)
            self.assertEqual(report['status'], 'passed_local_candidate', report['issues'])
            self.assertFalse(report['operationalReleaseApproved'])

    async def authenticated(self, conn):
        identity = await conn.fetchrow('SELECT current_user AS current_role, session_user AS login_role')
        self.assertEqual(identity['current_role'], self.runtime_role)
        self.assertEqual(identity['login_role'], self.runtime_role)
        flags = await conn.fetchrow('SELECT rolsuper,rolbypassrls,rolcreatedb,rolcreaterole,rolreplication FROM pg_roles WHERE rolname=current_user')
        self.assertFalse(any(flags.values()))

    async def runtime_pool(self, dsn):
        if self.runtime_password is None:
            return await super().runtime_pool(dsn)
        parsed = urlsplit(dsn)
        if parsed.hostname != '127.0.0.1' or not re.fullmatch(r'/native_purchase_test_[a-f0-9]{32}', parsed.path):
            raise ValueError('Ordinary LOGIN fixture requires a unique loopback database')
        # Credentials are separate kwargs, never an emitted URL or environment file.
        return await asyncpg.create_pool(
            dsn, user=self.runtime_role, password=self.runtime_password,
            min_size=1, max_size=5, statement_cache_size=0,
            init=db_pg._init_connection, setup=self.authenticated)

    async def asyncTearDown(self):
        try:
            source = os.environ['NATIVE_PURCHASE_TEST_DSN'].rsplit('/', 1)[0] + '/' + self.db
            fresh = await self.runtime_pool(source)
            try:
                async with AsyncExitStack() as stack:
                    clients = [await stack.enter_async_context(fresh.acquire()) for _ in range(5)]
                    for conn in clients:
                        await self.authenticated(conn)
                        self.assertEqual(await conn.fetchval("SELECT '{\"retained\":true}'::jsonb"), {'retained': True})
            finally:
                await fresh.close()
        finally:
            try:
                await super().asyncTearDown()
            finally:
                self.runtime_password = None


def login_case(name, parent, methods):
    # Shadow inherited tests so the receipt contains exactly the selected cases.
    attributes = {key: None for key in dir(parent) if key.startswith('test_')}
    attributes['__module__'] = __name__
    for method in methods:
        attributes['test_login_' + method.removeprefix('test_')] = getattr(parent, method)
    return type(name, (OrdinaryLoginMixin, parent), attributes)


LoginPhysicalTests = login_case('LoginPhysicalTests', native.RuntimePhysicalTests, [
    'test_runtime_physical_history_corrections_closures_and_original_key_replay'])
LoginOrderTests = login_case('LoginOrderTests', native.RuntimeOrderTests, [
    'test_runtime_order_independence_receiving_and_food_cost'])
LoginPriceTests = login_case('LoginPriceTests', native.RuntimePriceTests, [
    'test_runtime_posting_and_reviewed_price_adoption_remain_separate'])
LoginContactTests = login_case('LoginContactTests', native.RuntimeContactTests, [
    'test_runtime_contact_parallel_retry_stale_edit_and_exact_replay'])
LoginWasteTests = login_case('LoginWasteTests', native.RuntimeWasteTests, [
    'test_runtime_container_waste_correction_and_track1_separation'])
LoginAnalyticsTests = login_case('LoginAnalyticsTests', native.RuntimeAnalyticsTests, [
    'test_runtime_analytics_saved_periods_and_suffix_reopen'])
LoginMenuTests = login_case('LoginMenuTests', manager.ManagerMenuTests, [
    'test_manager_runtime_menu_definition_delete_preserves_accounting',
    'test_manager_runtime_menu_seven_retained_reference_types',
    'test_manager_runtime_menu_dependency_changes_and_atomic_rollback',
    'test_manager_runtime_menu_parallel_edits_and_role_store_boundaries',
    'test_manager_runtime_menu_late_delete_failure_rolls_back_prior_upsert'])
LoginCatalogTests = login_case('LoginCatalogTests', manager.ManagerCatalogTests, [
    'test_manager_runtime_catalog_store_price_provenance_and_retirement'])
LoginRosterTests = login_case('LoginRosterTests', manager.ManagerRosterTests, [
    'test_manager_runtime_roster_assignment_delete_race_cannot_orphan',
    'test_manager_runtime_roster_lifecycle_history_and_boundaries'])
LoginTaskTests = login_case('LoginTaskTests', tasks.RuntimeTaskCutoverTests, [
    'test_task_cutover_owner_connection_cannot_restart_old_queue',
    'test_task_cutover_candidate_reads_labeled_store_scoped_archives',
    'test_task_cutover_prep_insert_denied_update_guard_and_share_lock_retained'])
LoginSharedTests = login_case('LoginSharedTests', shared.SharedStateTests, [
    'test_shared_state_candidate_loads_labeled_history_without_accounting_drift',
    'test_shared_state_owner_and_candidate_cannot_replace_history_or_bump_revision',
    'test_shared_state_area_and_sales_drafts_are_scoped_versioned_and_independent'])
LoginPlanningTests = login_case('LoginPlanningTests', planning.PlanningAITests, [
    'test_planning_ai_reproduction_forecast_read',
    'test_planning_ai_reproduction_history_read',
    'test_planning_ai_reproduction_owner_forecast_requires_review',
    'test_planning_ai_versions_decimal_validation_and_scopes',
    'test_planning_ai_concurrent_existing_missing_and_accounting_isolation'])


class LoginBoundaryTests(login_case('BoundaryFixture', planning.PlanningAITests, [])):
    async def test_login_inventory_role_excludes_account_notification_and_owner_access(self):
        source = os.environ['NATIVE_PURCHASE_TEST_DSN'].rsplit('/', 1)[0] + '/' + self.db
        with self.assertRaises(asyncpg.InvalidPasswordError):
            await asyncpg.connect(source, user=self.runtime_role, password='invented-wrong-password')
        async with self.pool.acquire() as conn:
            for table in ('public.app_users', 'public.push_subscriptions'):
                for verb in ('SELECT', 'INSERT', 'UPDATE', 'DELETE'):
                    self.assertFalse(await conn.fetchval('SELECT has_table_privilege(current_user,$1,$2)', table, verb))
            with self.assertRaises(asyncpg.InsufficientPrivilegeError):
                await conn.execute('SET ROLE purchase_implementation_test')
            await self.authenticated(conn)
