"""Render/check review guides from source constants; never connect or apply SQL."""
import argparse
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def guides():
    tree = ast.parse((ROOT / 'backend/deployment_readiness.py').read_text(encoding='utf-8-sig'))
    values = {node.targets[0].id: ast.literal_eval(node.value) for node in tree.body
              if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
              and node.targets[0].id in ('MIGRATIONS','FEATURES')}
    order = '# Reviewed migration apply order\n\n'
    order += ('Generated from `backend/deployment_readiness.py::MIGRATIONS`. Check with '
              '`python tools/review_contracts.py --check`. Do not sort SQL filenames.\n\n'
              'This order applies to a reviewed legacy application public schema with '
              '`20260930_recurring_prep_items.sql` already installed. The reference schema '
              'snapshot is not a migration or a fresh-database installer.\n\n'
              'For an existing hosted database, compare recorded migration history and '
              'object definitions first. Presence alone does not prove an applied checksum. '
              'Do not replay this list against partially installed objects, rename previously '
              'delivered files, or use an automatic Supabase CLI filename-order apply. '
              'A future workflow must reconcile CLI migration history explicitly. '
              'This guide does not apply SQL or change the current Supabase connection.\n\n'
              '| Step | File |\n| --- | --- |\n')
    order += ''.join(f'| {i} | [{name}]({name}) |\n' for i,name in enumerate(values['MIGRATIONS'],1))
    profile = '# Native build/test feature settings\n\n'
    profile += ('Generated from the reviewed feature map. This is a proposed testing profile, '
                'not evidence of live Render settings and not an instruction to enable features '
                'before their schema, permissions, and workflow checks pass.\n\n'
                'Keep the existing hosted Supabase connection, session pooler, and private '
                'backend credentials during build. Paid IPv4, connection/role changes, and '
                'operational release decisions are deferred. No connection secret belongs '
                'in frontend settings or this document.\n\n'
                'Both `USE_PG=true` and `REACT_APP_USE_PG=true` are required for PostgreSQL. '
                'For each reviewed feature, backend and frontend must agree; the browser '
                'settings require a frontend rebuild. `render.yaml` does not declare these '
                'native flags, so review dashboard overrides without exposing their secrets.\n\n'
                'A database with `purchasing.store_vendor_items` installed requires the '
                'PURCHASE_IMPORT, ACTUAL_INVENTORY, and CATALOG_MAPPING foundation together '
                'for catalog loading. Turning all native flags off does not restore legacy '
                'catalog compatibility after installation. The load error provides a retry '
                'and diagnosis; it does not bypass that compatibility hold.\n\n'
                'The full native testing profile below sets both columns to `true` only '
                'after each installed module is reviewed. A narrower profile must set both '
                'sides to `false` for held modules and honor all listed prerequisites.\n\n'
                '| Backend setting | Frontend build setting | Prerequisites |\n| --- | --- | --- |\n')
    profile += ''.join(f'| `{name}_ENABLED=true` | `REACT_APP_{browser}=true` | {", ".join(deps) or "None"} |\n'
                       for name,(browser,deps) in values['FEATURES'].items())
    profile += ('\nRun the existing `backend/deployment_readiness.py` configuration review '
                'with private backend and frontend settings. A matching configuration '
                'does not prove schema installation or runtime permissions; complete its '
                'read-only catalog checks separately. Authentication/PIN redesign remains '
                'deferred in build and required before operational use.\n')
    return {'migrations/APPLY_ORDER.md':order, 'docs/BUILD_TEST_FEATURE_PROFILE.md':profile}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check',action='store_true'); mode.add_argument('--write',action='store_true')
    args = parser.parse_args(); stale = []
    for name,content in guides().items():
        path = ROOT/name
        if args.write:
            path.parent.mkdir(parents=True,exist_ok=True); path.write_text(content,encoding='utf-8')
        elif not path.is_file() or path.read_text(encoding='utf-8') != content:
            stale.append(name)
    if stale: raise SystemExit('Review guides differ from source: '+', '.join(stale))
    print('Review guides written' if args.write else 'Review guides match source')


if __name__ == '__main__': main()
