"""Staff-facing projections keep audit identities in the private retained journal."""
AUDIT_IDENTITY_KEYS = frozenset({'submitted_by', 'recorded_by', 'issued_by',
    'reviewed_by', 'confirmed_by', 'created_by', 'actor', 'email'})


def staff_view(value):
    # Do not change stored facts, server review hashes, request fingerprints or
    # manager responses. Apply the same projection to nested receipts and previews.
    if isinstance(value, dict):
        return {key: staff_view(item) for key, item in value.items() if key not in AUDIT_IDENTITY_KEYS}
    if isinstance(value, list):
        return [staff_view(item) for item in value]
    return value
