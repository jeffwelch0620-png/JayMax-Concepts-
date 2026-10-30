"""Positions from the JMAX org hierarchy (Jeff 2026-10-30) and what each may do.

A login keeps its access class (`role`: owner, manager, staff, readonly), which every existing
check uses. Its `position` (a role code from the org chart) narrows or widens a few decisions:
pars, prepping above or below par, Bulk request and sign-off, staff work acceptance and wages.
A login with no position keeps exactly what its access class allowed before positions existed.
migrations/20261031_login_positions.sql holds the same codes and access classes.
"""

# code: (access class, label, level)
POSITIONS = {
    'OWN': ('owner', 'Owner', 1),
    'OPS': ('owner', 'Operations & Integration Lead', 2),
    'GM': ('manager', 'General Manager', 3),
    'KM': ('manager', 'Kitchen Manager', 4),
    'FOHM': ('manager', 'FOH Manager', 4),
    'BPM': ('manager', 'Bulk Prep Manager', 4),
    'SL-BOH': ('manager', 'BOH Shift Leader', 5),
    'SL-FOH': ('manager', 'FOH Shift Leader', 5),
    'BPC': ('staff', 'Bulk Prep Cook', 5),
    'LC-GRL': ('staff', 'Grill Cook', 6),
    'LC-PZA': ('staff', 'Pizza Cook', 6),
    'LC-APZ': ('staff', 'Assistant Pizza Cook', 6),
    'LC-EXP': ('staff', 'Expo', 6),
    'LC-SLP': ('staff', 'Salad/Pasta Cook', 6),
    'LC-FRY': ('staff', 'Fry Cook', 6),
    'LC-PRP': ('staff', 'Prep Cook', 6),
    'LC-SBA': ('staff', 'Salad Bar Attendant', 6),
    'FOH-SRV': ('staff', 'Server', 6),
    'FOH-HST': ('staff', 'Host', 6),
    'FOH-RUN': ('staff', 'Runner', 6),
    'FOH-BW': ('staff', 'Back Window / Take Out', 6),
    'DSH': ('staff', 'Dishwasher', 7),
}

# Who may do what (DECISIONS.md, 2026-10-29 and 2026-10-30).
PERMISSIONS = {
    'set_pars': {'OWN', 'OPS'},                          # establish or change pars
    'par_exception': {'OWN', 'OPS', 'GM'},               # prep above or below par for a day
    'bulk_par_exception': {'OWN', 'OPS'},                # the same on a Bulk run (Bulk reports to the Ops Lead)
    'see_wages': {'OWN', 'OPS', 'GM'},                   # others see gross labor only
    'accept_staff_work': {'OWN', 'OPS', 'GM', 'KM', 'BPM', 'SL-BOH'},  # task lists, checklists, nightly counts
    'edit_staff_work': {'OWN', 'OPS', 'GM', 'KM', 'BPM'},              # review, edit or reassign
    'bulk_fulfill': {'OWN', 'OPS', 'BPM'},               # sign off what the Bulk kitchen made and holds
    'bulk_request': {'OWN', 'OPS', 'GM', 'KM'},          # send and accept a store's Bulk requests
}

# Before positions: owners could do everything; managers could request and sign off Bulk and
# accept staff work, but not set pars or sign off par exceptions.
LEGACY = {
    'owner': set(PERMISSIONS),
    'manager': {'bulk_fulfill', 'bulk_request', 'accept_staff_work', 'edit_staff_work'},
}

DENIED = {
    'set_pars': 'Only owners and the Operations & Integration Lead can establish or change pars',
    'par_exception': 'Preparing more or less than par needs sign-off from the General Manager, the Operations & Integration Lead or an owner',
    'bulk_par_exception': 'Bulk prep above or below par needs sign-off from the Operations & Integration Lead or an owner',
    'see_wages': 'Wages are visible to the General Manager and above',
    'accept_staff_work': 'Accepting staff work needs a BOH Shift Leader or above',
    'edit_staff_work': 'Editing or reassigning staff work needs a Kitchen Manager or above',
    'bulk_fulfill': 'Only the Bulk Prep Manager, the Operations & Integration Lead or an owner signs off Bulk prep made',
    'bulk_request': "Only the store's Kitchen Manager or General Manager, the Operations & Integration Lead or an owner sends or accepts Bulk requests",
}


def role_for(position):
    """The access class a position belongs to."""
    if position not in POSITIONS: raise ValueError('Unknown position')
    return POSITIONS[position][0]


def can(user, permission):
    """Whether a signed-in user (token payload) has a permission."""
    if permission not in PERMISSIONS: raise ValueError(f'Unknown permission: {permission}')
    user = user or {}
    position = user.get('position')
    if position in POSITIONS and POSITIONS[position][0] == user.get('role'):
        return position in PERMISSIONS[permission]
    return permission in LEGACY.get(user.get('role'), set())
