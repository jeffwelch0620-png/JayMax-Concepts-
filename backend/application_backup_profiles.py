"""Explicit application backup profiles; no configuration, imports with IO or discovery."""
from dataclasses import dataclass
import hashlib
import json
import math
import re
from types import MappingProxyType


class Held(ValueError):
    """Fixed categories only. Never include SQL, paths, driver text or credentials."""


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                      allow_nan=False).encode('utf-8')


def digest(value):
    return hashlib.sha256(value).hexdigest()


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise Held('duplicate_json_key')
            result[key] = value
        return result
    def constant(_):
        raise Held('nonfinite_json')
    def floating(value):
        result=float(value)
        if not math.isfinite(result):
            raise Held('nonfinite_json')
        return result
    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant,parse_float=floating)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise Held('invalid_json') from None


def sha256(value):
    if not isinstance(value, str) or not re.fullmatch('[a-f0-9]{64}', value):
        raise Held('invalid_digest')
    return value


@dataclass(frozen=True)
class Profile:
    name: str
    schemas: tuple
    format: str

    @property
    def sha256(self):
        return digest(canonical(dict(profile=self.name, schemas=list(self.schemas), format=self.format)))


LEGACY6 = Profile('legacy6', ('public', 'purchasing', 'actual_inventory', 'prep_inventory',
                            'integrations', 'supabase_migrations'), 'jaymax-encrypted-application-backup-v1')
RECEIVING7 = Profile('receiving7', LEGACY6.schemas + ('operations',),
                     'jaymax-encrypted-application-backup-v2')
PROFILES = MappingProxyType({p.name: p for p in (LEGACY6, RECEIVING7)})
MAX_ARCHIVE = 64 * 1024 * 1024
MAX_ENVELOPE = 192 * 1024 * 1024
ROW_ALGORITHM = 'sha256-sorted-sha256-canonical-jsonb-utf8-v1'


def profile(name):
    if not isinstance(name, str) or name not in PROFILES:
        raise Held('explicit_supported_profile_required')
    return PROFILES[name]


def checked_profile(value):
    if not isinstance(value, Profile) or value != profile(value.name):
        raise Held('unreviewed_profile')
    return profile(value.name)


def scope(found, selected, managed):
    selected = checked_profile(selected)
    found = set(found)
    if set(selected.schemas) - found or found - set(selected.schemas) - set(managed):
        raise Held('missing_or_unclassified_schema')
    return selected
