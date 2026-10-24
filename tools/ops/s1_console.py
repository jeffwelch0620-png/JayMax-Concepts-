"""Fictional-only operator console milestone. No HTTP or real credential lookup."""
import argparse
import getpass
import json
import os
from pathlib import Path
import sys
import warnings

from s1_process import ProcessHeld, receive, send, supervise

FICTIONAL_INPUT = 'TEST-ONLY-CONSOLE-4826'


def console_input(prompt):
    if os.name != 'nt': raise ProcessHeld('windows_console_required')
    # spawn closes stdin; restore only the existing attached operator console.
    stream = open('CONIN$', 'r')
    sys.stdin = sys.__stdin__ = stream
    try:
        if not stream.isatty(): raise ProcessHeld('private_console_required')
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            return getpass.getpass(prompt)
    finally:
        stream.close()


def fictional_console_worker(channel):
    value = console_input('FICTIONAL ONLY: type TEST-ONLY-CONSOLE-4826 (input hidden): ')
    passed = value == FICTIONAL_INPUT
    value = None
    send(channel, {'event': 'console', 'fictionalInputMatched': passed})
    if receive(channel) != {'continue': True}: return
    send(channel, {'event': 'done'})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    if args.receipt.exists(): parser.error('Use a fresh receipt path')
    result = {'format': 's1-fictional-console-v1', 'hostedRequests': 0,
              'realCredentialsRequested': False, 'status': 'held', 'fictionalInputMatched': False}
    def event(value):
        if value == {'event': 'done'}: return
        if set(value) != {'event','fictionalInputMatched'} or value['event'] != 'console' or value['fictionalInputMatched'] is not True:
            raise ProcessHeld('fictional_console_not_matched')
        result['fictionalInputMatched'] = True
        return {'continue': True}
    print('Local fictional console rehearsal. Never enter an actual password or store PIN.', flush=True)
    try:
        from read_only_probe import resources
        resources(start=True)
        result.update(supervise(fictional_console_worker, on_event=event, guard=resources, seconds=180))
    except BaseException:
        result['status'] = 'held'
    with args.receipt.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2); stream.write('\n')
    print('Fictional console rehearsal: ' + result['status'] + '. Receipt saved; no input text saved.')
    return 0 if result['status'] == 'completed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
