"""Spawnable fictional process fixtures. No real inputs or hosted endpoints."""
import os
from pathlib import Path
import subprocess
import sys
import time

from s1_process import receive, send, supervise


def done(channel): send(channel, {'event':'done'})


def stalled(channel):
    send(channel, {'event':'waiting'})
    while True: time.sleep(.1)


def descendant(channel):
    child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'])
    send(channel,{'event':'pid','pid':child.pid})
    receive(channel)
    send(channel,{'event':'done'})


def parent_death(pid_file):
    def event(value):
        if value=={'event':'waiting'}:
            # Supervisor owns the worker object internally. Worker records its PID itself below.
            os._exit(0)
    supervise(write_pid_and_stall,(pid_file,),on_event=event,guard=lambda:None,seconds=20)


def write_pid_and_stall(channel,pid_file):
    Path(pid_file).write_text(str(os.getpid()),encoding='ascii')
    stalled(channel)


def claim(profile,approval,actors,directory,connection):
    import s1_activation as activation
    try:
        journal=activation.Journal(profile,approval,actors,directory)
        journal.finish(cleanup_confirmed=True)
        connection.send_bytes(b'won')
    except BaseException: connection.send_bytes(b'held')
    finally: connection.close()


def typed_operator(channel,profile,approval,actors,input_mode):
    """One local email typo, then valid fictional fields in the real worker."""
    import s1_operator as operator
    values=['4826','typo@example.invalid']
    for role in profile['roles']: values.extend([actors[role]['email'],operator.FICTIONAL_PASSWORD])
    entries=iter(values)
    operator.console_input=lambda _:next(entries)
    operator._operator_worker(channel,profile,approval,actors,'terminal')


def invalid_email_operator(channel,profile,approval,actors,input_mode):
    import s1_operator as operator
    entries=iter(['4826']+['typo@example.invalid']*3)
    operator.console_input=lambda _:next(entries)
    operator._operator_worker(channel,profile,approval,actors,'terminal')


def invalid_pin_operator(channel,profile,approval,actors,input_mode):
    import s1_operator as operator
    entries=iter(['bad','12','123456789'])
    operator.console_input=lambda _:next(entries)
    operator._operator_worker(channel,profile,approval,actors,'terminal')


if __name__=='__main__' and len(sys.argv)==3 and sys.argv[1]=='parent-death':
    parent_death(sys.argv[2])
