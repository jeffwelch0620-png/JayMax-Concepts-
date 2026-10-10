"""Invented metadata only: crash the actual SQLite transaction in a new OS process."""
import json
import os
import sys
import local_supervisor_checkpoint as witness


if __name__ == '__main__':
    try:
        command, path, run_id, archive_pin, previous, head = sys.argv[1:]
        def fault(phase):
            if command == 'crash_before_commit' and phase == 'before_commit': os._exit(71)
            if command == 'crash_after_commit' and phase == 'after_commit': os._exit(72)
        if command == 'read':
            result = witness.read(path, run_id=run_id, archive_pin=archive_pin)
        elif command in ('crash_before_commit', 'crash_after_commit'):
            result = witness.advance(path, run_id=run_id, archive_pin=archive_pin,
                                     expected_receipt=previous, journal_head=head, _fault=fault)
        elif command == 'journal_gap':
            # Intentionally die after journal fsync but before witness COMMIT.
            journal_path = head
            journal = witness.CheckpointedJournal(journal_path, path, run_id=run_id, archive_pin=archive_pin)
            original_advance = witness.advance
            def interrupted_advance(*args, **kwargs):
                return original_advance(*args, **kwargs, _fault=lambda phase: os._exit(73) if phase == 'before_commit' else None)
            witness.advance = interrupted_advance
            journal.append('intent', {'step': 'create', 'before': 'b' * 64})
            raise AssertionError('Expected process exit')
        else:
            raise witness.CheckpointHeld('Unknown witness trial action')
        print(json.dumps({'processPid': os.getpid(), 'checkpoint': result}), flush=True)
    except Exception as error:
        print(json.dumps({'status': 'held', 'errorClass': type(error).__name__}), flush=True)
        sys.exit(3)
