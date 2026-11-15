#!/usr/bin/env python3
"""launchd runner: London 08:00 daily catch-up plus Yamtrack manual queue."""
import datetime,fcntl,json,os,subprocess,sys,time,uuid
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parent
BRIDGE=ROOT/'private/bridge'
def read(name):
    try:return json.loads((BRIDGE/name).read_text())
    except (FileNotFoundError,ValueError):return {}
def write(name,data):
    temp=BRIDGE/(str(uuid.uuid4())+'.tmp')
    with temp.open('x') as f:os.chmod(temp,0o600);json.dump(data,f,ensure_ascii=False)
    temp.replace(BRIDGE/name)
def daily_due(now,state,epoch):
    return now.hour>=8 and state.get('success_day')!=now.date().isoformat() and epoch>=state.get('retry_after',0)
def main():
    with (BRIDGE/'runner.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return
        now=datetime.datetime.now(ZoneInfo('Europe/London'));day=now.date().isoformat()
        state=read('schedule.json');requests=list(BRIDGE.glob('request-*.json'))
        due=daily_due(now,state,time.time())
        if not requests and not due:return
        for f in requests:f.unlink(missing_ok=True)
        trigger='manual' if requests else 'daily'
        write('status.json',{'state':'running','trigger':trigger,'started_at':now.isoformat()})
        try:
            r=subprocess.run([sys.executable,str(ROOT/'sync-yamtrack.py')],cwd=ROOT,capture_output=True,text=True,timeout=210)
            if r.returncode:raise RuntimeError('sync failed')
            result=json.loads(r.stdout)
            summary={k:result[k] for k in ['created','updated','unchanged','total_games','completed_at']}
            summary['unknown_count']=len(result['unknown'])
            write('status.json',{'state':'success','trigger':trigger,**summary})
            if now.hour>=8:state['success_day']=day
            state['retry_after']=0
        except Exception:
            write('status.json',{'state':'error','trigger':trigger,'completed_at':datetime.datetime.now(ZoneInfo('Europe/London')).isoformat(),'message':'同步失败，请检查 OrbStack、Yamtrack 或 Nintendo 授权；定时任务稍后重试。'})
            state['retry_after']=time.time()+900
        write('schedule.json',state)
if __name__=='__main__':main()
