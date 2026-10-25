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


def diagnostic_operator(channel,profile,approval,actors,input_mode):
    """Real worker, fictional inputs/exchanges and denied application sockets."""
    import asyncio
    from unittest.mock import patch
    import s1_activation as activation
    import s1_operator as operator
    loop=asyncio.new_event_loop()  # Standard Windows wakeup plumbing only.
    def deny(event,args):
        if event in ('socket.connect','socket.connect_ex','socket.getaddrinfo','socket.bind'):
            raise AssertionError('TEST ONLY application socket forbidden')
    sys.addaudithook(deny)
    fault=input_mode;order=activation.sequence(profile);seen=[]
    values=iter(['4826',actors['owner']['email'],operator.FICTIONAL_PASSWORD])
    original_receive=operator.receive;stop=[False]
    def receive(ch):
        reply=original_receive(ch)
        if fault=='window' and reply=={'start_dispatch':True}: stop[0]=True
        return reply
    original_now=activation.engine.utc_now
    def now():return activation.stamp(approval['stopChecksAt']) if stop[0] else original_now()
    async def exchange(client,step,body,session,budget):
        label=order[len(seen)];seen.append(label)
        owner=actors['owner']
        if label=='L01':
            if fault=='password':raise activation.Held('unexpected_status')
            return {'token':'TEST-ONLY-OWNER-TOKEN.0123456789','user':dict(owner)},None
        shape=activation.steps(profile)[label].shape
        values={'yes':{'ok':True,'staff':[]},'no':{'ok':False},'throttled':{'detail':'TEST ONLY'},
                'me':{'sub':owner['id'],**{k:v for k,v in owner.items() if k!='id'}},
                'users':[dict(owner)],'error':{'detail':'TEST ONLY'}}
        return values[shape],'60' if shape=='throttled' else None
    original_init=activation._ApprovedTransport.__init__
    def init(self,*args,**kw):
        if fault=='constructor':raise RuntimeError('TEST-ONLY-PRIVATE-PASSWORD-DSN')
        return original_init(self,*args,**kw)
    original_sleep=asyncio.sleep
    async def sleep(seconds):
        if fault in ('quiet','primary_cleanup'):
            raise RuntimeError('TEST-ONLY-PRIVATE-PASSWORD-DSN')
        await original_sleep(seconds)
    original_close=activation._ApprovedTransport.close
    def close(client):
        original_close(client)
        if fault in ('cleanup','primary_cleanup'):raise OSError('TEST-ONLY-PRIVATE-PASSWORD-DSN')
    try:
        with patch.object(operator,'console_input',lambda _:next(values)),patch.object(operator,'receive',receive),\
             patch.object(activation.engine,'utc_now',now),patch.object(activation._ApprovedTransport,'_exchange',exchange),\
             patch.object(activation._ApprovedTransport,'__init__',init),patch.object(activation._ApprovedTransport,'close',close),\
             patch.object(asyncio,'sleep',sleep),patch.object(asyncio.events,'new_event_loop',lambda:loop):
            operator._operator_worker(channel,profile,approval,actors,'terminal')
    finally:
        if not loop.is_closed():loop.close()


if __name__=='__main__' and len(sys.argv)==3 and sys.argv[1]=='parent-death':
    parent_death(sys.argv[2])
