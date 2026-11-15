"""Run inside the pinned Yamtrack Django environment; JSON payload comes from stdin."""
import json,sys
from django.db import transaction
from django.contrib.auth import get_user_model
from django.utils import timezone
from app.models import Item,Game
from lists.models import CustomList,CustomListItem
from simple_history.utils import bulk_create_with_history,bulk_update_with_history

p=json.load(sys.stdin)
u=get_user_model().objects.get(username=p['username'])
results={'created':0,'updated':0,'unchanged':0,'list_added':0,'unknown':p['unknown'],'dry_run':p['dry_run']}
with transaction.atomic():
    owned=CustomList.objects.get(owner=u,name='已有游戏')
    targets={x['media_id'] for x in p['titles']}
    unaffected=list(Game.objects.filter(user=u).exclude(item__source='manual',item__media_id__in=targets).order_by('id').values())
    for x in p['titles']:
        item=Item.objects.filter(source='manual',media_type='game',media_id=x['media_id']).first()
        game=Game.objects.filter(user=u,item=item).get() if item and Game.objects.filter(user=u,item=item).exists() else None
        if game and x['minutes']<game.progress:
            raise ValueError('Nintendo time decreased for '+x['title']+'; no changes committed')
        if game is None:
            results['created']+=1
            if not p['dry_run']:
                if item is None:
                    item=Item(media_id=x['media_id'],source='manual',media_type='game',title=x['title'],image=x['image'])
                    item.full_clean();Item.objects.bulk_create([item])
                game=Game(user=u,item=item,progress=x['minutes'],status='Planning',notes='Nintendo Switch；用户确认拥有（2026-11-15）；时长来自 Nintendo Store 同步。游玩状态未提供，Planning 为待确认占位。 Nintendo ID: '+x['key'])
                game.full_clean();bulk_create_with_history([game],Game,default_change_reason='Nintendo initial import')
        elif game.progress!=x['minutes']:
            results['updated']+=1
            if not p['dry_run']:
                protected=(game.notes,game.score,game.status,game.start_date,game.end_date)
                game.progress=x['minutes'];game.progressed_at=timezone.now()
                bulk_update_with_history([game],Game,['progress','progressed_at'],default_change_reason='Nintendo playtime sync')
                game.refresh_from_db();assert protected==(game.notes,game.score,game.status,game.start_date,game.end_date)
        else:results['unchanged']+=1
        if not item or not CustomListItem.objects.filter(custom_list=owned,item=item).exists():
            results['list_added']+=1
            if not p['dry_run']:CustomListItem.objects.get_or_create(custom_list=owned,item=item)
    assert unaffected==list(Game.objects.filter(user=u).exclude(item__source='manual',item__media_id__in=targets).order_by('id').values())
    if not p['dry_run']:
        for x in p['titles']:
            assert Game.objects.get(user=u,item__source='manual',item__media_type='game',item__media_id=x['media_id']).progress==x['minutes']
    results['total_games']=Game.objects.filter(user=u).count()
    results['owned_list']=owned.items.count()
print('SYNC_RESULT='+json.dumps(results,ensure_ascii=False))
