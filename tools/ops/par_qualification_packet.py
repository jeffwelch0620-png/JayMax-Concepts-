"""Prepare/verify a local operator handoff. Never execute its command templates.

Only public repository sources are read. No connection, credential configuration,
service control, approval, backup, local database or migration is created here.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
FORMAT = 'jaymax-par-qualification-operator-packet-v2'
PROPOSAL = 'docs/REVIEWED_PAR_MAINTENANCE_PROPOSAL_20261022.json'
PROPOSAL_CONTENT_SHA256 = '95ecfcee657ae81266b9170f24f92e761a02dd04379a398655aa1cf8c92707e1'
CORE_PINS = 'docs/PAR_QUALIFICATION_SOURCE_PINS.json'
CORE_PINS_SHA256 = '4bf0c694812102e897c0ac23133240866e000820896b987ba8aaa0de70455d00'
# Explicit candidate amendments; never rewrite the historical proposal/pins.
# These content hashes are independently reviewable source, not execution approval.
TOOLING_AMENDMENTS = {
    'backend/deployment_readiness.py': {
        'priorContentSha256': '53cd1518b490eed146a43625f816414bfb6a0bbc951cc1b062e50a7b8bd43bfb',
        'contentSha256': '2b5c1bf90ba3159ee38eaf142e0da3f988334d27ecb4db80ec69c7841f1e5458'},
    'tools/ops/apply_reviewed_par_migration.py': {
        'priorContentSha256': '5e0b8499a8694470d5ebda80e7ca3608af60b0ecab80c61ed5df058f028a7b8a',
        'contentSha256': '80a1f1fd170b905b31af849b5b56742565453a40ae549f61b11cf21040e0d307'},
}
MAX_BYTES = 256 * 1024
# Additional prior -> current links preserve the accepted PR55 amendments above.
FOLLOWUP_TOOLING_AMENDMENTS = {
    'backend/hosted_backup.py': {
        'priorContentSha256': 'e1fbae51c519d7fda7d182d68df550e38a8644b4992ab9d8c346d62ed1ab6c09',
        'contentSha256': '5dd2201b9ed6941ea569da64a14795a486f6bc9bd12643310343e55e9ab29688'},
    'backend/hosted_install_preservation.py': {
        'priorContentSha256': 'de5ba5bd6abf8e377910cef5f2f2bd43ea5a0feee1ee821da7da137740ac9745',
        'contentSha256': '19c9c7ec439440a76da2881e3586081c3b3e09f8648571b9b6f2aaa374bb87cd'},
    'tools/ops/apply_reviewed_par_migration.py': {
        'priorContentSha256': '80a1f1fd170b905b31af849b5b56742565453a40ae549f61b11cf21040e0d307',
        'contentSha256': '2b332f27bcf720616d1e4efa2b81b9ebced806a004f06a904e6d14871923c3b0'},
    'tools/ops/hosted_reviewed_pars.py': {
        'priorContentSha256': 'ce2e7d65b649cd0d37d94976e526b54e5be4f75aadde636e66699af340cae987',
        'contentSha256': '2c0bff9a64bd84c52f133101127c6a882cc22bdbd6f3443821b33eb332963baa'},
}

# Review amendment: preserve every earlier link; bind timeout diagnostics separately.
TIMEOUT_TOOLING_AMENDMENTS = {
    'backend/hosted_backup.py': {
        'priorContentSha256': '5dd2201b9ed6941ea569da64a14795a486f6bc9bd12643310343e55e9ab29688',
        'contentSha256': '891164d236c56ad9388a2c943f630d06ff7fffcc92668f54e45c2020064048f8'},
    'backend/hosted_install_preservation.py': {
        'priorContentSha256': '19c9c7ec439440a76da2881e3586081c3b3e09f8648571b9b6f2aaa374bb87cd',
        'contentSha256': '3e064e658235e8598cb86c408826ffa0400d03d1df77bd30e9a4114c299204fd'},
    'tools/ops/apply_reviewed_par_migration.py': {
        'priorContentSha256': '2b332f27bcf720616d1e4efa2b81b9ebced806a004f06a904e6d14871923c3b0',
        'contentSha256': '0a284c224a4ed9d727d0504ca2bfff1c429dc43fb5858fdfd7e3336073afee24'},
    'tools/ops/hosted_reviewed_pars.py': {
        'priorContentSha256': '2c0bff9a64bd84c52f133101127c6a882cc22bdbd6f3443821b33eb332963baa',
        'contentSha256': '4df71297ea91a573a5369aa06137825c7d896b84c9c6f9d0e493c1f5820b1e83'},
}

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
    if not (set(TOOLING_AMENDMENTS) | set(FOLLOWUP_TOOLING_AMENDMENTS) | set(TIMEOUT_TOOLING_AMENDMENTS)) <= set(core):
        raise PacketHeld('Tooling amendments must name reviewed core sources')
    for path, expected in core.items():
        checked_sha(expected)
        content_pin = pins['coreSources'][path]
        raw = source_file(root, path).read_bytes()
        mode = 'crlf_to_lf' if PurePosixPath(path).suffix in ('.py', '.json') else 'exact_bytes'
        compared = raw.replace(b'\r\n', b'\n') if mode == 'crlf_to_lf' else raw
        expected_content = content_pin['contentSha256']
        for amendments in (TOOLING_AMENDMENTS, FOLLOWUP_TOOLING_AMENDMENTS, TIMEOUT_TOOLING_AMENDMENTS):
            amendment = amendments.get(path)
            if amendment is not None:
                if (mode != 'crlf_to_lf'
                        or amendment['priorContentSha256'] != expected_content):
                    raise PacketHeld('Tooling amendment differs from the retained baseline')
                expected_content = checked_sha(amendment['contentSha256'])
        if (content_pin['reviewedRawSha256'] != expected or content_pin['comparison'] != mode
                or digest(compared) != checked_sha(expected_content)):
            raise PacketHeld('Reviewed executable or catalog source changed')
        sources[path] = digest(raw)
    for path in EXTRA_SOURCES:
        sources[path] = digest(source_file(root, path).read_bytes())
    return {
        'format': FORMAT,
        'purpose': 'source-bound supervised qualification handoff',
        'proposal': {'path': PROPOSAL, 'contentSha256': PROPOSAL_CONTENT_SHA256,
            'rawSha256': digest(proposal_path.read_bytes())},
        'comparison': 'SQL byte-exact; historical Python/JSON plus explicit candidate amendments LF/CRLF-only; packet binds all actual local bytes',
        'acceptedApplicationCommit': proposal['acceptedCommit'],
        'acceptedApplicationTree': proposal['acceptedTree'],
        'toolingAmendments': {path:dict(value) for path,value in TOOLING_AMENDMENTS.items()},
        'followupToolingAmendments': {path:dict(value) for path,value in FOLLOWUP_TOOLING_AMENDMENTS.items()},
        'timeoutToolingAmendments': {path:dict(value) for path,value in TIMEOUT_TOOLING_AMENDMENTS.items()},
        'toolingReviewStatus': 'candidate_requires_independent_review',
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
    if sys.version_info < (3, 12):
        print(json.dumps({'status': 'held', 'reason': 'Python 3.12 or newer required',
            'hostedActionsPerformed': False, 'readyForHostedExecution': False}))
        return 2
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
