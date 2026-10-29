"""Native prep tracks shared by planning, day lists, execution, assignments, staff
production and manager notes. Salad Bar runs only at Bert's (owner decision 2026-10-29);
migrations/20261029_salad_prep_track.sql enforces the same rule in the database."""
from typing import Literal

from fastapi import HTTPException

Track = Literal['daily', 'bulk', 'salad']
SALAD_STORES = frozenset({'berts'})


def check(store, track):
    if track == 'salad' and store not in SALAD_STORES:
        raise HTTPException(422, "Salad Bar prep is only at Bert's")
    return track
