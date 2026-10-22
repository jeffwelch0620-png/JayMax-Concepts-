"""Prepare/verify a local operator handoff. Never execute its command templates.

Only public repository sources are read. No connection, credential configuration,
service control, approval, backup, local database or migration is created here.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re

ROOT = Path(__file__).resolve().parents[2]
FORMAT = 'jaymax-par-qualification-operator-packet-v1'
PROPOSAL = 'docs/REVIEWED_PAR_MAINTENANCE_PROPOSAL_20261022.json'
PROPOSAL_CONTENT_SHA256 = '95ecfcee657ae81266b9170f24f92e761a02dd04379a398655aa1cf8c92707e1'
CORE_PINS = 'docs/PAR_QUALIFICATION_SOURCE_PINS.json'
CORE_PINS_SHA256 = '4bf0c694812102e897c0ac23133240866e000820896b987ba8aaa0de70455d00'
MAX_BYTES = 256 * 1024
EXTRA_SOURCES = (
    '.gitattributes',
    CORE_PINS,
    'backend/hosted_backup_cli.py',
    'tools/ops/par_qualification_packet.py',
    'backend/tests/test_par_qualification_packet.py',
    'tools/run_review_tests.py',
    'docs/PAR_QUALIFICATION_EXECUTION_PACKET.md',
)


class PacketHeld(ValueError):
    """Fixed public reason, never private input or raw exception text."""


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def checked_sha(value):
    if not isinstance(value, str) or not re.fullmatch('[a-f0-9]{64}', value):
        raise PacketHeld('Exact lowercase SHA-256 required')
    return value


def source_file(root, relative):
    if (not isinstance(relative, str) or not relative or '\\' in relative
            or ':' in relative or any(p in ('', '.', '..') for p in relative.split('/'))
            or PurePosixPath(relative).is_absolute()):
        raise PacketHeld('Repository-relative source path required')
    root = Path(root).resolve(strict=True)
    candidate = root
    for part in relative.split('/'):
        candidate = candidate / part
        if candidate.is_symlink() or candidate.is_junction():
            raise PacketHeld('Source links and junctions are refused')
    if not candidate.resolve(strict=True).is_relative_to(root) or not candidate.is_file():
        raise PacketHeld('Regular in-repository source file required')
    return candidate


def json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n').encode('utf-8')


def read_json(path, expected, *, normalize_newlines=False):
    checked_sha(expected)
    # Bound the actual read; do not first materialize a user-selected large file.
    with Path(path).open('rb') as stream:
        raw = stream.read(MAX_BYTES + 1)
    compared = raw.replace(b'\r\n', b'\n') if normalize_newlines else raw
    if len(raw) > MAX_BYTES or digest(compared) != expected:
        raise PacketHeld('Artifact size or SHA-256 differs')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise PacketHeld('Duplicate JSON keys are refused')
            result[key] = value
        return result
    try:
        def constant_refused(_):
            raise PacketHeld('Nonfinite JSON is refused')
        value = json.loads(raw, object_pairs_hook=unique,
            parse_constant=constant_refused)
    except (UnicodeError, json.JSONDecodeError):
        raise PacketHeld('Valid UTF-8 JSON required') from None
    if not isinstance(value, dict):
        raise PacketHeld('JSON object required')
    return value


def commands():
    """Reference argv only. Placeholders remain intentionally unresolved."""
    return {
        'export': ['python', 'backend/hosted_backup_cli.py', 'export',
            '--owner-config', '<existing-private-maintenance-env>',
            '--expected-project', '<designated-build-project>',
            '--pg-bin', '<verified-pg17-bin>', '--maintenance-direct-ipv6',
            '--timeout-seconds', '600'],
        'restore': ['python', 'backend/hosted_backup_cli.py', 'verify-restore',
            '--connection-env', 'PAR_QUALIFICATION_RESTORE_DSN',
            '--backup', '<fresh-private-encrypted-archive>',
            '--key-file', '<fresh-separate-private-key>',
            '--expected-project', '<designated-build-project>',
            '--pg-bin', '<verified-pg17-bin>'],
        'qualify': ['python', 'tools/ops/hosted_reviewed_pars.py', 'dry-run',
            '--owner-config', '<existing-private-maintenance-env>',
            '--expected-project', '<designated-build-project>',
            '--review', '<new-private-window-and-restore-bound-review-v2>',
            '--review-sha256', '<verified-review-sha256>',
            '--output-directory', '<new-private-qualification-output>',
            '--maintenance-direct-ipv6'],
    }


def build(root=ROOT):
    root = Path(root)
    proposal_path = source_file(root, PROPOSAL)
    proposal = read_json(proposal_path, PROPOSAL_CONTENT_SHA256, normalize_newlines=True)
    pins = read_json(source_file(root, CORE_PINS), CORE_PINS_SHA256)
    # The pinned proposal contains the reviewed core manifest and all false gates.
    if (proposal.get('notExecutableInstallerPlan') is not True
            or any(proposal['executionApprovals'].values())
            or proposal['window']['active'] is not False
            or proposal['window']['startsAt'] is not None
            or proposal['window']['endsAt'] is not None
            or proposal['qualification']['executablePlanSha256'] is not None):
        raise PacketHeld('Unapproved local proposal required')
    core = proposal['installerSourceHashes']
    if (len(core) != 49 or len(proposal['migrationDependencyOrder']) != 31
            or pins.get('format') != 'jaymax-par-qualification-core-pins-v1'
            or pins.get('acceptedCommit') != proposal['acceptedCommit']
            or set(pins['coreSources']) != set(core)):
        raise PacketHeld('Reviewed source manifest differs')
    sources = {}
    for path, expected in core.items():
        checked_sha(expected)
        content_pin = pins['coreSources'][path]
        raw = source_file(root, path).read_bytes()
        mode = 'crlf_to_lf' if PurePosixPath(path).suffix in ('.py', '.json') else 'exact_bytes'
        compared = raw.replace(b'\r\n', b'\n') if mode == 'crlf_to_lf' else raw
        if (content_pin['reviewedRawSha256'] != expected or content_pin['comparison'] != mode
                or digest(compared) != checked_sha(content_pin['contentSha256'])):
            raise PacketHeld('Reviewed executable or catalog source changed')
        sources[path] = digest(raw)
    for path in EXTRA_SOURCES:
        sources[path] = digest(source_file(root, path).read_bytes())
    return {
        'format': FORMAT,
        'purpose': 'source-bound supervised qualification handoff',
        'proposal': {'path': PROPOSAL, 'contentSha256': PROPOSAL_CONTENT_SHA256,
            'rawSha256': digest(proposal_path.read_bytes())},
        'comparison': 'SQL byte-exact; accepted Python/JSON LF/CRLF-only; packet binds all actual local bytes',
        'acceptedApplicationCommit': proposal['acceptedCommit'],
        'acceptedApplicationTree': proposal['acceptedTree'],
        'sourceHashes': dict(sorted(sources.items())),
        'coreSourceCount': len(core),
        'orderedMigrations': proposal['migrationDependencyOrder'],
        'executionApprovals': dict(proposal['executionApprovals']),
        'window': {'startsAt': None, 'endsAt': None, 'active': False,
            'maximumMinutes': 45, 'drainByMinute': 8, 'exportByMinute': 18,
            'restoreByMinute': 24, 'qualifyByMinute': 34, 'recoverByMinute': 45},
        'minimumResources': {'freePhysicalMiB': 1024, 'freePhysicalPercent': 15,
            'freshLocalObservationRequired': True},
        'requiredBeforeAnyHostedStep': [
            'current owner writer and no-other-writes confirmation',
            'owner available for exact API suspend/resume',
            'fresh local resource and recovery-path checks',
            'explicit new window approval and recorded Eastern/UTC deadline',
            'fresh original API/job states and exact producer bindings',
        ],
        'stageEvidenceRequired': {
            'export': ['verified API suspension', 'exact jobs 3/4 disabled',
                'two strict quiet observations at least 45 seconds apart',
                'HTTP queue, cron run and downstream sync drain',
                'sufficient remaining work and restoration budget'],
            'restore': ['fresh encrypted archive and separate key with private ACLs',
                'owned UUID-named empty loopback PostgreSQL 17 target',
                'captured original local role/database/server inventory'],
            'qualify': ['restore equality, access guards and owned cleanup',
                'fresh current target, writer and full baseline guards',
                'new v2 review bound to window, archive and restore receipt',
                'full 600-second operation plus 600-second restoration reserve'],
            'closure': ['owned hosted clients closed', 'original producers restored',
                'recovery evidence and actual window closure recorded'],
        },
        'argvTemplates': commands(),
        'unautomatedSteps': ['Render service controls', 'exact Toast job controls',
            'fresh hosted drain observation', 'owned local restore target lifecycle',
            'binding private v2 review and delivery version', 'producer restoration'],
        'notVerifiedByThisTool': ['human authorization', 'live state or writer drain',
            'resource readiness', 'backup or restore validity', 'hosted plan readiness'],
        'schemaApplyApproved': False,
        'readyForHostedExecution': False,
        'automaticExecute': False,
        'automaticRetry': False,
        'executableInstallationPlanSha256': None,
        'deliveryVersion': None,
    }


def prepare(output, root=ROOT):
    value = build(root)
    raw = json_bytes(value)
    # Exclusive creation preserves old evidence, including existing symlink targets.
    with Path(output).open('xb') as stream:
        stream.write(raw)
    return digest(raw)


def verify(packet, expected_sha256, root=ROOT):
    value = read_json(packet, expected_sha256)
    # JSON-level comparison preserves false/0 and true/1 type distinctions.
    if json_bytes(value) != json_bytes(build(root)):
        raise PacketHeld('Packet differs from the current source-bound handoff')
    return {'status': 'verified_local_operator_handoff',
        'packetSha256': expected_sha256, 'sourceFilesVerified': len(value['sourceHashes']),
        'coreSourcesVerified': value['coreSourceCount'],
        'orderedMigrations': len(value['orderedMigrations']),
        'hostedActionsPerformed': False, 'readyForHostedExecution': False,
        'schemaApplyApproved': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode', required=True)
    sub.add_parser('prepare').add_argument('--output', type=Path, required=True)
    check = sub.add_parser('verify')
    check.add_argument('--packet', type=Path, required=True)
    check.add_argument('--packet-sha256', required=True)
    args = parser.parse_args(argv)
    try:
        if args.mode == 'prepare':
            sha = prepare(args.output)
            result = {'status': 'prepared_local_operator_handoff', 'packetSha256': sha,
                'hostedActionsPerformed': False, 'readyForHostedExecution': False}
        else:
            result = verify(args.packet, args.packet_sha256)
    except (PacketHeld, OSError, ValueError, KeyError, TypeError) as error:
        result = {'status': 'held', 'errorType': type(error).__name__,
            'hostedActionsPerformed': False, 'readyForHostedExecution': False}
        print(json.dumps(result)); return 2
    print(json.dumps(result)); return 0


if __name__ == '__main__':
    raise SystemExit(main())
