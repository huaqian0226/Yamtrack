import io
import json
import runpy
from contextlib import redirect_stdout
from pathlib import Path
from subprocess import CompletedProcess
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from simple_history.utils import bulk_create_with_history

from app.models import Game, Item, MediaTypes, Sources, Status
from lists.models import CustomList, CustomListItem

SCRIPTS = Path(__file__).resolve().parents[4] / "workbench" / "nintendo-export"
IMPORT_SCRIPT = SCRIPTS / "yamtrack_import.py"


class ImportNintendo(TestCase):
    """Exercise the script passed to the Django shell with synthetic exports."""

    @classmethod
    def setUpTestData(cls):
        """Create the library owner and their existing list."""
        cls.user = get_user_model().objects.create_user(username="nintendo-test")
        cls.owned = CustomList.objects.create(owner=cls.user, name="已有游戏")

    def setUp(self):
        """Keep every IGDB metadata request inside the test."""
        self.metadata = self.enterContext(
            patch("app.providers.services.get_media_metadata")
        )

    def _entry(self, media_id, **fields):
        return {
            "key": f"Switch:{media_id}",
            "title": f"Switch game {media_id}",
            "image": "https://example.com/switch.jpg",
            "media_id": media_id,
            "minutes": 90,
            **fields,
        }

    def _make_game(
        self, media_id, source=Sources.IGDB, reason="Nintendo initial import"
    ):
        item = Item(
            source=source,
            media_type=MediaTypes.GAME,
            media_id=media_id,
            title="Existing title",
            image="https://example.com/existing.jpg",
        )
        Item.objects.bulk_create([item])
        game = Game(
            item=item,
            user=self.user,
            progress=45,
            status=Status.COMPLETED,
            notes="保留我的备注",
            score=8,
            start_date=timezone.now(),
            end_date=timezone.now(),
        )
        bulk_create_with_history([game], Game, default_change_reason=reason)
        return game

    def _run_import(self, *entries, dry_run=False, unknown=()):
        payload = {
            "username": self.user.username,
            "titles": entries,
            "unknown": list(unknown),
            "dry_run": dry_run,
        }
        self.output = io.StringIO()
        with (
            patch("sys.stdin", io.StringIO(json.dumps(payload))),
            redirect_stdout(self.output),
        ):
            runpy.run_path(str(IMPORT_SCRIPT))
        return json.loads(self.output.getvalue().split("SYNC_RESULT=", 1)[1])

    def test_manual_entries_default_to_manual_and_report_unknown(self):
        """Keep legacy mappings idempotent and import only approved titles."""
        manual_id = "e805648c-b60f-427c-b83e-047b96d2a3ca"
        unknown = [{"key": "Switch:unknown", "title": "Unknown game"}]
        result = self._run_import(self._entry(manual_id), unknown=unknown)
        game = Game.objects.get(user=self.user)

        self.assertEqual((result["created"], result["list_added"]), (1, 1))
        self.assertEqual(result["unknown"], unknown)
        self.assertEqual(
            (game.item.source, game.item.media_id), (Sources.MANUAL, manual_id)
        )
        self.assertEqual(game.progress, 90)
        self.assertEqual(
            game.history.first().history_change_reason, "Nintendo initial import"
        )

        result = self._run_import(self._entry(manual_id, source="manual"))

        self.assertEqual((result["unchanged"], result["list_added"]), (1, 0))
        self.assertEqual(list(self.owned.items.all()), [game.item])
        self.metadata.assert_not_called()

    def test_existing_igdb_game_updates_only_playtime(self):
        """Match by source and ID while preserving the Game and its memberships."""
        game = self._make_game("123")
        manual_twin = self._make_game("123", Sources.MANUAL)
        before = Game.objects.filter(pk=game.pk).values().get()
        other_before = Game.objects.filter(pk=manual_twin.pk).values().get()
        friends = CustomList.objects.create(owner=self.user, name="和朋友玩的游戏")
        CustomListItem.objects.create(custom_list=self.owned, item=game.item)
        CustomListItem.objects.create(custom_list=friends, item=game.item)

        result = self._run_import(self._entry("123", source="igdb"))
        after = Game.objects.filter(pk=game.pk).values().get()

        self.assertEqual((result["updated"], result["list_added"]), (1, 0))
        self.assertEqual(after["progress"], 90)
        self.assertGreater(after["progressed_at"], before["progressed_at"])
        self.assertEqual(
            after, {**before, "progress": 90, "progressed_at": after["progressed_at"]}
        )
        self.assertEqual(
            Game.objects.filter(pk=manual_twin.pk).values().get(), other_before
        )
        self.assertEqual(list(self.owned.items.all()), [game.item])
        self.assertEqual(list(friends.items.all()), [game.item])
        self.assertEqual(
            game.history.first().history_change_reason, "Nintendo playtime sync"
        )
        self.metadata.assert_not_called()

    def test_new_igdb_item_uses_igdb_title_and_image(self):
        """Prefer catalog metadata when creating a new IGDB Item."""
        self.metadata.return_value = {
            "title": "IGDB title",
            "image": "https://example.com/igdb.jpg",
        }

        result = self._run_import(self._entry("234", source="igdb"))
        game = Game.objects.get(
            user=self.user, item__source=Sources.IGDB, item__media_id="234"
        )

        self.metadata.assert_called_once_with(MediaTypes.GAME, "234", Sources.IGDB)
        self.assertEqual(
            (game.item.title, game.item.image),
            ("IGDB title", "https://example.com/igdb.jpg"),
        )
        self.assertEqual((game.progress, game.status), (90, Status.PLANNING))
        self.assertEqual(list(self.owned.items.all()), [game.item])
        self.assertEqual((result["created"], result["list_added"]), (1, 1))

    def test_failed_igdb_lookup_uses_export_metadata(self):
        """Keep importing minutes when the IGDB metadata request fails."""
        self.metadata.side_effect = RuntimeError("Synthetic provider failure")
        entry = self._entry("345", source="igdb")

        self._run_import(entry)
        item = Item.objects.get(source=Sources.IGDB, media_id="345")

        self.assertEqual((item.title, item.image), (entry["title"], entry["image"]))

    def test_overlap_rolls_back_all_prior_writes(self):
        """Reject a Steam game even when it follows valid updates and creates."""
        nintendo = self._make_game("456")
        steam = self._make_game("567", reason="Imported from Steam")

        with self.assertRaisesRegex(ValueError, "Switch game 567.*独立的 manual 条目"):
            self._run_import(
                self._entry("456", source="igdb"),
                self._entry("new-manual"),
                self._entry("567", source="igdb"),
            )

        self.assertIn("SYNC_ERROR=", self.output.getvalue())
        nintendo.refresh_from_db()
        steam.refresh_from_db()
        self.assertEqual((nintendo.progress, steam.progress), (45, 45))
        self.assertEqual(nintendo.history.count(), 1)
        self.assertEqual(Game.history.count(), 2)
        self.assertEqual(Item.objects.count(), 2)
        self.assertEqual(self.owned.items.count(), 0)

    def test_time_decrease_rolls_back_batch(self):
        """Refuse decreasing minutes for a Nintendo-managed IGDB Game."""
        game = self._make_game("678")

        with self.assertRaisesRegex(
            ValueError, "Nintendo time decreased for Switch game 678"
        ):
            self._run_import(
                self._entry("new-manual"), self._entry("678", source="igdb", minutes=44)
            )

        game.refresh_from_db()
        self.assertEqual(game.progress, 45)
        self.assertEqual(Item.objects.count(), 1)
        self.assertEqual(self.owned.items.count(), 0)
        self.assertEqual(Game.history.count(), 1)

    def test_dry_run_writes_nothing(self):
        """Preview creates, minute updates and membership without doing any of them."""
        game = self._make_game("789")

        result = self._run_import(
            self._entry("789", source="igdb"),
            self._entry("890", source="igdb"),
            dry_run=True,
        )

        game.refresh_from_db()
        self.assertEqual(result["dry_run"], True)
        self.assertEqual(
            (result["created"], result["updated"], result["list_added"]), (1, 1, 2)
        )
        self.assertEqual((result["total_games"], result["owned_list"]), (1, 0))
        self.assertEqual(game.progress, 45)
        self.assertEqual(Item.objects.count(), 1)
        self.assertEqual(Game.history.count(), 1)
        self.metadata.assert_not_called()

    def test_invalid_source_is_rejected(self):
        """Validate the shell payload independently of the host script."""
        with self.assertRaisesRegex(ValueError, "source 只允许 manual 或 igdb"):
            self._run_import(self._entry("bad-id", source="steam"))

        self.assertFalse(Item.objects.exists())


class NintendoSyncHost(SimpleTestCase):
    """Verify the host-to-container payload without Docker or private files."""

    def setUp(self):
        """Create a temporary host layout with synthetic mappings and exports."""
        self.root = Path(self.enterContext(TemporaryDirectory()))
        reports = self.root / "reports"
        self.main = runpy.run_path(str(SCRIPTS / "sync-yamtrack.py"))["main"]
        self.enterContext(
            patch.dict(self.main.__globals__, ROOT=self.root, PRIVATE=reports)
        )
        export = self.root / "export.json"
        export.write_text(
            json.dumps(
                {
                    "history": {
                        "playHistories": [
                            {
                                "platform": "Switch",
                                "titleId": name,
                                "titleName": name,
                                "totalPlayedMinutes": 90,
                                "imageUrl": "https://example.com/switch.jpg",
                            }
                            for name in ("legacy", "mapped", "unknown")
                        ],
                    },
                }
            ),
            encoding="utf-8",
        )
        self.enterContext(
            patch(
                "sys.argv",
                ["sync-yamtrack.py", "--dry-run", "--from-export", str(export)],
            )
        )
        self.run = self.enterContext(patch("subprocess.run"))
        self.mappings = [
            {"key": "Switch:legacy", "title": "Legacy", "media_id": "manual-id"},
            {
                "key": "Switch:mapped",
                "title": "Mapped",
                "media_id": "123",
                "source": "igdb",
            },
        ]

    def _write_mapping(self):
        (self.root / "approved-games.json").write_text(
            json.dumps({"username": "nintendo-test", "games": self.mappings}),
            encoding="utf-8",
        )

    def test_host_forwards_both_sources_and_shows_overlap_error(self):
        """Relay the structured overlap error and keep arbitrary logs private."""
        self._write_mapping()
        (self.root / IMPORT_SCRIPT.name).write_text("# Test script", encoding="utf-8")
        error = "mapped: 已有非 Nintendo 同步记录。整批已回滚。"
        self.run.side_effect = [
            CompletedProcess([], 0),
            CompletedProcess(
                [], 1, f"SYNC_ERROR={json.dumps(error)}\n", "Internal Django log"
            ),
        ]

        with self.assertRaisesRegex(RuntimeError, error) as raised:
            self.main()

        payload = json.loads(self.run.call_args.kwargs["input"])
        self.assertEqual(
            [(entry["source"], entry["media_id"]) for entry in payload["titles"]],
            [("manual", "manual-id"), ("igdb", "123")],
        )
        self.assertEqual(
            payload["unknown"], [{"key": "Switch:unknown", "title": "unknown"}]
        )
        self.assertNotIn("Internal Django log", str(raised.exception))

    def test_host_rejects_unapproved_source_before_loading_export(self):
        """Validate all approved records even when the export omits a game."""
        self.mappings.append(
            {"key": "Switch:absent", "title": "Absent", "source": "steam"}
        )
        self._write_mapping()

        with self.assertRaisesRegex(ValueError, "Absent.*source 只允许 manual 或 igdb"):
            self.main()

        self.run.assert_not_called()
