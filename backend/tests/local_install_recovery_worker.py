"""Fresh OS process used only by the guarded local recovery catalog test."""
import asyncio
import json
import os
import sys
import local_install_recovery as recovery
import local_parallel_install as local


async def run():
    command, url, archive_path, pin, journal_path, journal_pin = sys.argv[1:]
    controller, receipt = await recovery.recover(url, archive_path, pin, journal_path, journal_pin)
    receipt['processPid'] = os.getpid()
    def checkpoint():
        print(json.dumps({'event': 'journal_checkpoint', 'journalHeadSha256': controller.journal.expected_head,
                          'independentArchiveSha256': pin, 'processPid': os.getpid()}), flush=True)
    checkpoint()
    if controller.held:
        print(json.dumps(receipt), flush=True); return
    if command == 'recover':
        print(json.dumps(receipt), flush=True); return
    append = controller.journal.append
    crash_step = {'crash_before_create_commit': 'create', 'crash_after_create_commit': 'create',
                  'crash_after_enable_commit': 'enable', 'crash_after_restore_commit': 'restore'}.get(command)
    def crashing_append(event, data):
        if crash_step and data.get('step') == crash_step:
            if command == 'crash_before_create_commit' and event == 'expected':
                append(event, data); checkpoint(); os._exit(91)  # Durable expectation; socket closes with transaction open.
            if command != 'crash_before_create_commit' and event == 'acknowledged':
                os._exit(92)  # Actual database COMMIT completed; acknowledgement record absent.
        append(event, data)
        checkpoint()
    controller.journal.append = crashing_append
    if command in ('crash_before_create_commit', 'crash_after_create_commit'):
        await controller.step('create')
    elif command == 'crash_after_enable_commit':
        await controller.step('overlap'); await controller.step('enable')
    elif command == 'crash_after_restore_commit':
        await controller.verify_overlap(); await controller.step('restore')
    elif command == 'unsafe_disable':
        await controller.step('disable_revoke')
    elif command == 'finish':
        await controller.verify_original_singletons(); await controller.step('disable_revoke')
    else:
        raise local.RehearsalHeld('Unknown local worker action')
    receipt['completed'] = list(controller.completed)
    receipt['journalHeadSha256'] = controller.journal.expected_head
    print(json.dumps(receipt), flush=True)


if __name__ == '__main__':
    try: asyncio.run(run())
    except Exception as error:
        print(json.dumps({'status': 'held', 'errorClass': type(error).__name__,
                          'errorCategory': str(error) if isinstance(error, local.RehearsalHeld) else None,
                          'processPid': os.getpid(), 'hostedChanges': False}), flush=True)
        sys.exit(3)
