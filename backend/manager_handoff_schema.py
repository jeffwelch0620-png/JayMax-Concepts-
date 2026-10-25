"""Separate receiving extension; never expands sealed Inventory installers."""
MIGRATION = '20261025_manager_handoff_notes.sql'
BROWSER_FLAG = 'REACT_APP_MANAGER_HANDOFF_NOTES'
SERVER_FLAG = 'MANAGER_HANDOFF_NOTES_ENABLED'


def configuration(backend, frontend):
    """Pure feature-local review; no private values in the result."""
    problems=[]
    server=backend.get(SERVER_FLAG,'false');browser=frontend.get(BROWSER_FLAG,'false')
    if server not in ('true','false') or browser not in ('true','false'):
        problems.append('Set explicit true/false manager handoff flags')
    if server!=browser:problems.append('Backend and browser manager handoff flags differ')
    if server=='true':
        if backend.get('USE_PG')!='true' or frontend.get('REACT_APP_USE_PG')!='true':
            problems.append('PostgreSQL is required on both sides')
        if not backend.get('AUTH_SECRET','').strip():problems.append('Personal signing configuration is required')
    return {'status':'held' if problems else 'passed','problems':problems,'featureEnabled':server=='true',
            'storageAndRoleReviewRequired':True,'applyAutomatically':False,'secretValuesIncluded':False}
