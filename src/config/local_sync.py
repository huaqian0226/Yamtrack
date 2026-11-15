"""Authenticated local queue; contains no Nintendo credentials or shell execution."""
import json,uuid,datetime,os
from pathlib import Path
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.cache import never_cache
ROOT=Path(os.environ.get('WORKBENCH_SYNC_DIR','/yamtrack/local-sync'))
WORKBENCH_USER=os.environ.get('WORKBENCH_USER','')
@never_cache
@login_required
@require_http_methods(['GET','POST'])
def nintendo_sync(request):
    if not WORKBENCH_USER or request.user.username!=WORKBENCH_USER:return JsonResponse({'state':'forbidden'},status=403)
    try:status=json.loads((ROOT/'status.json').read_text())
    except (FileNotFoundError,ValueError):status={'state':'idle'}
    if status.get('state')=='running' and (datetime.datetime.now(datetime.timezone.utc)-datetime.datetime.fromisoformat(status['started_at'])).total_seconds()>300:
        status={'state':'error','message':'上次同步已中断，可以重新点击同步。'}
    if request.method=='POST':
        if status.get('state')!='running' and not list(ROOT.glob('request-*.json')):
            p=ROOT/('request-'+str(uuid.uuid4())+'.json')
            p.write_text('{}')
        return JsonResponse({'state':'running' if status.get('state')=='running' else 'queued'})
    if list(ROOT.glob('request-*.json')):return JsonResponse({'state':'queued'})
    return JsonResponse(status)


@never_cache
@login_required
@require_http_methods(['GET','POST'])
def game_library_sync(request):
    if not WORKBENCH_USER or request.user.username!=WORKBENCH_USER:return JsonResponse({'state':'forbidden'},status=403)
    import fcntl
    from celery.result import AsyncResult
    from integrations.tasks import import_steam
    def read(name):
        try:return json.loads((ROOT/name).read_text())
        except (FileNotFoundError,ValueError):return {}
    def nintendo_state():
        n=read('status.json') or {'state':'idle'}
        if list(ROOT.glob('request-*.json')):n={'state':'queued'}
        elif n.get('state')=='running' and (datetime.datetime.now(datetime.timezone.utc)-datetime.datetime.fromisoformat(n['started_at'])).total_seconds()>300:
            n={'state':'error','message':'同步已中断，请重试。'}
        return n
    def steam_state():
        meta=read('steam-task.json')
        if not meta:return {'state':'idle'}
        if not meta.get('task_id'):return {'state':'error','message':'Steam任务提交失败，请重试。'}
        result=AsyncResult(meta['task_id'])
        if result.state=='SUCCESS':
            message=str(result.result)
            return {'state':'success','message':'无变化' if message=='No media was imported.' else message,'started_at':meta['started_at']}
        if result.state in ['FAILURE','REVOKED']:return {'state':'error','message':'Steam同步失败，请检查导入历史或账户设置。'}
        if (datetime.datetime.now(datetime.timezone.utc)-datetime.datetime.fromisoformat(meta['started_at'])).total_seconds()>900:
            return {'state':'error','message':'Steam任务等待超时，请先检查导入历史再重试。'}
        return {'state':'running' if result.state=='STARTED' else 'queued'}
    with (ROOT/'submit.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        n=nintendo_state();s=steam_state()
        busy=any(x.get('state') in ['running','queued'] for x in [n,s])
        if request.method=='POST' and not busy:
            (ROOT/('request-'+str(uuid.uuid4())+'.json')).write_text('{}')
            meta={'started_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
            try:meta['task_id']=import_steam.delay(os.environ['STEAM_USER_ID'],request.user.pk,'overwrite').id
            except Exception:meta['error']=True
            tmp=ROOT/('steam-'+str(uuid.uuid4())+'.tmp');tmp.write_text(json.dumps(meta));tmp.replace(ROOT/'steam-task.json')
            n=nintendo_state();s=steam_state()
    busy=any(x.get('state') in ['running','queued'] for x in [n,s])
    return JsonResponse({'state':'running' if busy else 'idle','steam':s,'nintendo':n})


def workbench_context(request):
    return {
        'workbench_knowledge_url': os.environ.get('WORKBENCH_KNOWLEDGE_URL', 'http://127.0.0.1:3000/games/'),
        'workbench_tv_url': os.environ.get('WORKBENCH_TV_URL', ''),
        'workbench_files_url': os.environ.get('WORKBENCH_FILES_URL', 'http://127.0.0.1:5244/'),
        'workbench_sync_enabled': bool(WORKBENCH_USER) and request.user.is_authenticated and request.user.username == WORKBENCH_USER,
    }
