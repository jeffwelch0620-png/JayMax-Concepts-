"""Read-only snapshots preserve the original error if rollback also fails."""
from contextlib import asynccontextmanager
import re


def error_details(error):
    """Only bounded category fields; never driver messages or exception reprs."""
    def category(value):
        return value if isinstance(value, str) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,127}', value) else None
    state = getattr(error, 'sqlstate', None)
    result = {'errorType': category(type(error).__name__),
              'sqlState': state if isinstance(state, str) and re.fullmatch(r'[A-Z0-9]{5}', state) else None,
              'snapshotCleanupErrorType': category(getattr(error, 'snapshotCleanupErrorType', None))}
    for key in ('lockReleaseErrorType', 'connectionCloseErrorType', 'partialCleanupErrorType'):
        value = category(getattr(error, key, None))
        if value is not None:
            result[key] = value
    return result


@asynccontextmanager
async def preserve_cleanup_failure(cleanup, category):
    """Preserve a body failure; cleanup-only failure still prevents success."""
    if category not in ('lockReleaseErrorType', 'connectionCloseErrorType', 'partialCleanupErrorType'):
        raise ValueError('Unsupported cleanup category')
    try:
        yield
    except BaseException as original:
        try:
            await cleanup()
        except BaseException as failure:
            setattr(original, category, type(failure).__name__)
        raise
    else:
        try:
            await cleanup()
        except BaseException as failure:
            setattr(failure, category, type(failure).__name__)
            raise


@asynccontextmanager
async def readonly_snapshot(conn, *, isolation='repeatable_read'):
    # None preserves the existing default isolation of the short activity probe.
    options = {'readonly': True}
    if isolation is not None:
        options['isolation'] = isolation
    tx = conn.transaction(**options)
    await tx.start()
    try:
        yield
    except BaseException as original:
        try:
            await tx.rollback()
        except BaseException as cleanup:
            # Only a safe category: never attach driver text, SQL or credentials.
            original.snapshotCleanupErrorType = type(cleanup).__name__
        raise
    else:
        # A failed read-only COMMIT still holds the snapshot; don't claim success.
        await tx.commit()
