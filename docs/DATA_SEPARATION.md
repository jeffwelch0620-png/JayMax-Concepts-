# Demo vs Operational Data Separation

Operational records (real Bert's items, real PFG/US Foods invoices, real pricing) live in
the **live MongoDB** and are **intentionally NOT included** in this handoff — they contain
sensitive supplier pricing and business data.

Instead, this package ships a small **sanitized, fabricated demo dataset**:
`sample-data/demo_dataset.json`. Every value in it is made up.

## How the two are kept separate
1. **Separate database.** The demo loader writes to its own `DB_NAME` (default
   `berts_demo`), so it can never touch operational collections.
2. **Separate restaurant id.** Demo records use `restaurantId: "demo_diner"`, which is not
   one of the operational ids (`berts`, `rudds`, `papa_leonis`).

## Loading the demo data
```bash
cd handoff
# point at any MongoDB; use a throwaway DB name for demo
MONGO_URL="mongodb://localhost:27017" DB_NAME="berts_demo" \
  python scripts/load_demo_data.py
```
The script is idempotent (it clears only the `demo_diner`-scoped docs it manages).

## Seeing the demo restaurant in the UI (optional)
The UI reads the restaurant registry from `RESTAURANTS` in `backend/server.py`. To make the
demo restaurant selectable, add one line to that list, then restart the backend pointed at
the demo DB:
```python
RESTAURANTS = [
    ...,
    {"id": "demo_diner", "name": "Demo Diner (Sample Data)", "short": "Demo",
     "location": "Anytown", "accent": "#22C55E"},
]
```
Do this only on a demo/staging instance — never mix the demo id into an operational deployment.

## What the demo dataset covers
- 6 `items` (with vendor SKUs/prices), 6 `areas`
- 3 `dishes` with simple recipes
- 5 `purchases` (fake invoices) so PO **receipt-matching** can be demoed
- 2 `vendor_contacts`, 1 example `purchase_orders` record spanning the approval chain
- Sample `projected_sales` rows

No personal data (no real people, emails, or phone numbers) is present — supplier emails are
`orders@demovendor.example`.
