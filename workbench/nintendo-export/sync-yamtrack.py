#!/usr/bin/env python3
"""Refresh Nintendo playtime and import only user-confirmed games; no scheduler."""
import argparse,datetime,fcntl,json,os,sqlite3,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
PRIVATE=ROOT/'private'
DOCKER='/opt/homebrew/bin/docker'
def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--dry-run',action='store_true')
    ap.add_argument('--from-export',type=Path,help='Use an existing JSON instead of fetching fresh data')
    args=ap.parse_args()
    PRIVATE.mkdir(mode=0o700,exist_ok=True)
    with (PRIVATE/'sync.lock').open('a') as lock:
        os.chmod(lock.name,0o600)
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise RuntimeError('Another Nintendo sync is running')
        subprocess.run([DOCKER,'exec','yamtrack','true'],check=True,capture_output=True)
        if args.from_export:source=args.from_export.resolve()
        else:
            before=set(PRIVATE.glob('*-play-history.json'))
            subprocess.run([str(ROOT/'bin/nintendo-export'),'export'],cwd=ROOT,check=True,capture_output=True,timeout=90)
            new=set(PRIVATE.glob('*-play-history.json'))-before
            if len(new)!=1:raise RuntimeError('Expected one fresh export; refusing stale data')
            source=new.pop()
        doc=json.loads(source.read_text())
        approved=json.loads((ROOT/'approved-games.json').read_text())
        mapping={x['key']:x for x in approved['games']}
        titles=[];unknown=[];seen=set()
        for x in doc['history']['playHistories']:
            key=(x.get('platform') or x.get('deviceType'))+':'+x['titleId']
            if key in seen:raise ValueError('Duplicate Nintendo platform/title ID')
            seen.add(key)
            if key not in mapping:unknown.append({'key':key,'title':x['titleName']});continue
            minutes=x['totalPlayedMinutes']
            if type(minutes) is not int or minutes<0:raise ValueError('Invalid playtime')
            titles.append({'key':key,'media_id':mapping[key]['media_id'],'title':x['titleName'],'minutes':minutes,'image':x['imageUrl']})
        if not titles:raise ValueError('No approved games in export')
        backup=None
        if not args.dry_run:
            stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
            backup=PRIVATE/('before-yamtrack-'+stamp+'.sqlite3')
            fd=os.open(backup,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.close(fd)
            with sqlite3.connect(ROOT.parent/'yamtrack/db/db.sqlite3') as src,sqlite3.connect(backup) as dst:src.backup(dst)
        payload={'username':approved['username'],'titles':titles,'unknown':unknown,'dry_run':args.dry_run}
        code=(ROOT/'yamtrack_import.py').read_text()
        result=subprocess.run([DOCKER,'exec','-i','yamtrack','python','manage.py','shell','-c',code],input=json.dumps(payload),text=True,capture_output=True,timeout=90)
        if result.returncode:
            # Input contains no credentials, but do not emit arbitrary Django logs.
            raise RuntimeError('Yamtrack transaction failed; changes rolled back. Backup: '+str(backup))
        line=next((s for s in result.stdout.splitlines() if s.startswith('SYNC_RESULT=')),None)
        if line is None:raise RuntimeError('Missing verification result; inspect live state before retrying')
        report=json.loads(line.split('=',1)[1]);report.update({'source':source.name,'backup':str(backup) if backup else None,'completed_at':datetime.datetime.now(datetime.timezone.utc).isoformat()})
        out=PRIVATE/('last-dry-run.json' if args.dry_run else 'last-sync.json')
        fd=os.open(out,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
        with os.fdopen(fd,'w') as f:json.dump(report,f,ensure_ascii=False,indent=2)
        print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':
    try:main()
    except (RuntimeError,ValueError,KeyError,OSError,subprocess.SubprocessError) as e:
        print('Nintendo sync stopped: '+str(e),file=sys.stderr);sys.exit(1)
