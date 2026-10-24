"""Actual owned Windows process/job tests; no application or hosted connections."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools/ops'))
import s1_process as processes
import s1_activation_workers as workers


def stopped(pid):
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
    kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    handle=kernel.OpenProcess(0x100000,False,pid)
    if not handle:
        assert ctypes.get_last_error()==87
        return True
    try: return kernel.WaitForSingleObject(handle,5000)==0
    finally: kernel.CloseHandle(handle)


def test_owned_process_completion_and_platform_refusal():
    if os.name!='nt':
        with pytest.raises(processes.ProcessHeld): processes.OwnedJob()
        return
    assert processes.supervise(workers.done,on_event=lambda _:None,guard=lambda:None,seconds=5)=={
        'status':'completed','ownedCleanupConfirmed':True}


def test_stalled_owned_worker_is_stopped_by_real_deadline():
    if os.name!='nt': return
    started=time.monotonic()
    with pytest.raises(processes.ProcessHeld,match='worker_deadline'):
        processes.supervise(workers.stalled,on_event=lambda _:None,guard=lambda:None,seconds=1)
    assert time.monotonic()-started<8


def test_blocked_controller_callback_does_not_block_worker_cleanup():
    if os.name!='nt': return
    release=threading.Event()
    def callback(_): release.wait(10)
    try:
        with pytest.raises(processes.ProcessHeld,match='controller_callback_unconfirmed'):
            processes.supervise(workers.stalled,on_event=callback,guard=lambda:None,seconds=1.5)
    finally: release.set()


def test_owned_descendant_is_closed_even_after_worker_returns():
    if os.name!='nt': return
    pids=[]
    def event(value):
        if value.get('event')=='pid': pids.append(value['pid']);return {'continue':True}
    result=processes.supervise(workers.descendant,on_event=event,guard=lambda:None,seconds=8)
    assert result['ownedCleanupConfirmed'] and pids and all(stopped(pid) for pid in pids)


def test_parent_exit_does_not_leave_owned_orphan(tmp_path):
    if os.name!='nt': return
    file=tmp_path/'owned-pid.txt'
    result=subprocess.run([sys.executable,str(Path(workers.__file__)),'parent-death',str(file)],
                          capture_output=True,timeout=15,creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode==0 and file.exists()
    assert stopped(int(file.read_text()))


@pytest.mark.parametrize('raw',[b'{"event":"done","event":"held"}',b'{"x":NaN}',b'[]',b'x'*5000])
def test_worker_protocol_refuses_ambiguous_nonfinite_and_oversized_data(raw):
    parent,child=processes.multiprocessing.get_context('spawn').Pipe()
    try:
        child.send_bytes(raw)
        with pytest.raises(processes.ProcessHeld,match='worker_message_invalid'): processes.receive(parent)
    finally: parent.close();child.close()


def test_guard_error_text_is_not_exposed():
    if os.name!='nt': return
    def event(_): raise ValueError('TEST ONLY private error text')
    with pytest.raises(processes.ProcessHeld,match='supervisor_held') as error:
        processes.supervise(workers.stalled,on_event=event,guard=lambda:None,seconds=5)
    assert 'private' not in str(error.value) and error.value.ownedCleanupConfirmed is True
