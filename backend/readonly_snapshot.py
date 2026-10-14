"""Read-only snapshots preserve the original error if rollback also fails."""
from contextlib import asynccontextmanager


@asynccontextmanager
async def readonly_snapshot(conn):
    tx = conn.transaction(isolation='repeatable_read', readonly=True)
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
