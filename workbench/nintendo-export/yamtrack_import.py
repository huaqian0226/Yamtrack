"""Run inside the pinned Yamtrack Django environment; JSON payload comes from stdin."""

import json
import sys
from collections import defaultdict

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from simple_history.utils import bulk_create_with_history, bulk_update_with_history

from app.models import Game, Item, MediaTypes, Sources, Status
from app.providers import services
from lists.models import CustomList, CustomListItem


class NintendoImportError(ValueError):
    """An import error whose message is safe to display to the operator."""


def item_metadata(entry):
    """Use IGDB metadata when available, with the export as a fallback."""
    title, image = entry["title"], entry["image"]
    if entry["source"] != Sources.IGDB:
        return title, image
    try:
        metadata = services.get_media_metadata(
            MediaTypes.GAME,
            entry["media_id"],
            Sources.IGDB,
        )
        return metadata.get("title") or title, metadata.get("image") or image
    except Exception:  # noqa: BLE001 - Catalog lookup failures cannot block playtime imports.
        return title, image


def create_game(entry, user, item):
    """Create a Nintendo Game and its Item if necessary."""
    if item is None:
        title, image = item_metadata(entry)
        item = Item(
            media_id=entry["media_id"],
            source=entry["source"],
            media_type=MediaTypes.GAME,
            title=title,
            image=image,
        )
        item.full_clean()
        Item.objects.bulk_create([item])
    game = Game(
        user=user,
        item=item,
        progress=entry["minutes"],
        status=Status.PLANNING,
        notes=(
            "Nintendo Switch；用户确认拥有（2026-11-15）；"  # noqa: RUF001
            "时长来自 Nintendo Store 同步。"
            "游玩状态未提供，Planning 为待确认占位。 Nintendo ID: " + entry["key"]  # noqa: RUF001
        ),
    )
    game.full_clean()
    bulk_create_with_history(
        [game], Game, default_change_reason="Nintendo initial import"
    )
    return item


def update_playtime(game, minutes):
    """Record the new minute total without triggering status changes."""
    protected_fields = ("notes", "score", "status", "start_date", "end_date")
    protected = tuple(getattr(game, field) for field in protected_fields)
    game.progress = minutes
    game.progressed_at = timezone.now()
    bulk_update_with_history(
        [game],
        Game,
        ["progress", "progressed_at"],
        default_change_reason="Nintendo playtime sync",
    )
    game.refresh_from_db()
    assert protected == tuple(getattr(game, field) for field in protected_fields)  # noqa: S101


def sync_title(entry, user, owned, dry_run):
    """Apply one mapping and return the planned Game and membership changes."""
    source = entry["source"]
    minutes = entry["minutes"]
    item = Item.objects.filter(
        source=source,
        media_type=MediaTypes.GAME,
        media_id=entry["media_id"],
    ).first()
    games = Game.objects.filter(user=user, item=item)
    if source == Sources.IGDB and any(
        not existing.history.filter(
            history_change_reason__startswith="Nintendo",
        ).exists()
        for existing in games
    ):
        msg = (
            f"{entry['title']}：该 IGDB 条目已有非 Nintendo 同步记录。"  # noqa: RUF001
            "整批已回滚。请将 Switch 记录映射到独立的 manual 条目后重试。"
        )
        raise NintendoImportError(msg)

    game = games.get() if games else None
    if game is None:
        action = "created"
        if not dry_run:
            item = create_game(entry, user, item)
    elif minutes < game.progress:
        msg = f"Nintendo time decreased for {entry['title']}; no changes committed"
        raise NintendoImportError(msg)
    elif game.progress != minutes:
        action = "updated"
        if not dry_run:
            update_playtime(game, minutes)
    else:
        action = "unchanged"

    list_added = (
        item is None
        or not CustomListItem.objects.filter(
            custom_list=owned,
            item=item,
        ).exists()
    )
    if list_added and not dry_run:
        CustomListItem.objects.get_or_create(custom_list=owned, item=item)
    return action, list_added


def import_titles(payload):
    """Apply the approved mappings and verify the result in one transaction."""
    titles = payload["titles"]
    target_ids = defaultdict(set)
    for entry in titles:
        source = entry.setdefault("source", Sources.MANUAL)
        if source not in (Sources.MANUAL, Sources.IGDB):
            msg = f"{entry['title']}：source 只允许 manual 或 igdb。"  # noqa: RUF001
            raise NintendoImportError(msg)
        target_ids[source].add(entry["media_id"])

    targets = Q()
    for source, media_ids in target_ids.items():
        targets |= Q(item__source=source, item__media_id__in=media_ids)

    user = get_user_model().objects.get(username=payload["username"])
    dry_run = payload["dry_run"]
    results = {
        "created": 0,
        "updated": 0,
        "unchanged": 0,
        "list_added": 0,
        "unknown": payload["unknown"],
        "dry_run": dry_run,
    }
    with transaction.atomic():
        owned = CustomList.objects.get(owner=user, name="已有游戏")
        user_games = Game.objects.filter(user=user)
        unaffected_games = (
            user_games.exclude(
                targets,
                item__media_type=MediaTypes.GAME,
            )
            .order_by("id")
            .values()
        )
        unaffected = list(unaffected_games)

        for entry in titles:
            action, list_added = sync_title(entry, user, owned, dry_run)
            results[action] += 1
            results["list_added"] += int(list_added)

        assert unaffected == list(unaffected_games.all())  # noqa: S101
        if not dry_run:
            for entry in titles:
                game = user_games.get(
                    item__source=entry["source"],
                    item__media_type=MediaTypes.GAME,
                    item__media_id=entry["media_id"],
                )
                assert game.progress == entry["minutes"]  # noqa: S101
        results["total_games"] = user_games.count()
        results["owned_list"] = owned.items.count()
    return results


try:
    results = import_titles(json.load(sys.stdin))
except NintendoImportError as error:
    print("SYNC_ERROR=" + json.dumps(str(error), ensure_ascii=False))  # noqa: T201
    raise
else:
    print("SYNC_RESULT=" + json.dumps(results, ensure_ascii=False))  # noqa: T201
