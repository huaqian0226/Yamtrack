from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from app.models import Game, Item, MediaTypes, Sources, Status
from integrations.imports import steam
from lists.models import CustomList, CustomListItem


@patch("integrations.imports.steam.services.api_request")
@patch("integrations.imports.steam.external_game")
@patch("integrations.imports.steam.services.get_media_metadata")
class ImportSteamUpdate(TestCase):
    """Test Steam overwrite behavior for existing games."""

    def setUp(self):
        """Create user and common data for the tests."""
        self.credentials = {"username": "test", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)

        self.item = Item.objects.create(
            media_id="1",
            source=Sources.IGDB.value,
            media_type=MediaTypes.GAME.value,
            title="Counter-Strike 2",
            image="http://example.com/cs2.jpg",
        )

    def _create_game(self, status=Status.PLANNING.value, progress=0):
        """Create a game with a specific status and progress."""
        return Game.objects.create(
            item=self.item,
            user=self.user,
            status=status,
            progress=progress,
        )

    def _setup_mocks(
        self,
        mock_get_metadata,
        mock_external_game,
        mock_api_request,
        playtime=1300,
    ):
        """Set up the common Steam and IGDB mocks."""
        mock_get_metadata.return_value = {
            "title": "Counter-Strike 2",
            "image": "http://example.com/cs2.jpg",
            "max_progress": None,
        }
        mock_external_game.return_value = 1

        mock_api_request.return_value = {
            "response": {
                "games": [
                    {
                        "appid": 730,
                        "name": "Counter-Strike 2",
                        "playtime_forever": playtime,
                        "playtime_2weeks": 120,
                        "rtime_last_played": 1704067200,
                    },
                ],
            },
        }

    def test_overwrite_steam_game_updates_existing(
        self,
        mock_get_metadata,
        mock_external_game,
        mock_api_request,
    ):
        """Test overwrite mode updates an existing game instead of recreating it."""
        self._setup_mocks(mock_get_metadata, mock_external_game, mock_api_request)
        game = self._create_game()

        imported_counts, _ = steam.importer(
            "76561198000000000",
            self.user,
            "overwrite",
        )

        game.refresh_from_db()
        self.assertEqual(imported_counts[MediaTypes.GAME.value], 1)
        self.assertEqual(Game.objects.filter(user=self.user).count(), 1)
        self.assertEqual(game.progress, 1300)
        self.assertEqual(game.status, Status.IN_PROGRESS.value)
        self.assertEqual(game.history.count(), 2)

    def test_overwrite_steam_game_completed_status(
        self,
        mock_get_metadata,
        mock_external_game,
        mock_api_request,
    ):
        """Test overwrite mode does not downgrade completed games."""
        self._setup_mocks(
            mock_get_metadata,
            mock_external_game,
            mock_api_request,
            playtime=1100,
        )
        game = self._create_game(status=Status.COMPLETED.value, progress=1000)

        imported_counts, _ = steam.importer(
            "76561198000000000",
            self.user,
            "overwrite",
        )

        game.refresh_from_db()
        self.assertEqual(imported_counts[MediaTypes.GAME.value], 1)
        self.assertEqual(game.progress, 1100)
        self.assertEqual(game.status, Status.COMPLETED.value)

    def test_overwrite_updates_newest_game_instance(
        self,
        mock_get_metadata,
        mock_external_game,
        mock_api_request,
    ):
        """Test overwrite mode updates the newest game instance."""
        self._setup_mocks(mock_get_metadata, mock_external_game, mock_api_request)
        older_game = self._create_game(progress=100)
        newer_game = self._create_game(progress=200)

        imported_counts, _ = steam.importer(
            "76561198000000000",
            self.user,
            "overwrite",
        )

        older_game.refresh_from_db()
        newer_game.refresh_from_db()
        self.assertEqual(imported_counts[MediaTypes.GAME.value], 1)
        self.assertEqual(older_game.progress, 100)
        self.assertEqual(older_game.status, Status.PLANNING.value)
        self.assertEqual(newer_game.progress, 1300)
        self.assertEqual(newer_game.status, Status.IN_PROGRESS.value)

    def test_new_mode_skips_existing_game(
        self,
        mock_get_metadata,
        mock_external_game,
        mock_api_request,
    ):
        """Test that new mode still skips existing games."""
        self._setup_mocks(mock_get_metadata, mock_external_game, mock_api_request)
        game = self._create_game()

        imported_counts, _ = steam.importer("76561198000000000", self.user, "new")

        game.refresh_from_db()
        self.assertEqual(imported_counts, {})
        self.assertEqual(game.progress, 0)
        self.assertEqual(game.status, Status.PLANNING.value)

    def test_new_games_join_owned_list_without_duplicates(
        self, mock_get_metadata, mock_external_game, mock_api_request,
    ):
        """New games join the total list; retries do not duplicate entries."""
        self._setup_mocks(mock_get_metadata, mock_external_game, mock_api_request)
        steam.importer("76561198000000000", self.user, "new")
        owned = CustomList.objects.get(owner=self.user, name="已有游戏")
        self.assertEqual(list(owned.items.all()), [self.item])
        steam.importer("76561198000000000", self.user, "overwrite")
        self.assertEqual(owned.items.count(), 1)
        self.assertEqual(Game.objects.filter(user=self.user).count(), 1)

    def test_unchanged_games_repair_total_list_preserving_other_lists(
        self, mock_get_metadata, mock_external_game, mock_api_request,
    ):
        """Membership repair preserves personal data and unrelated lists."""
        self._setup_mocks(mock_get_metadata, mock_external_game, mock_api_request)
        game = self._create_game(status=Status.IN_PROGRESS.value, progress=1300)
        Game.objects.filter(pk=game.pk).update(notes="Keep this note", score=8)
        friends = CustomList.objects.create(owner=self.user, name="Friends")
        CustomListItem.objects.create(custom_list=friends, item=self.item)
        candidate = Item.objects.create(media_id="999", source="igdb",
            media_type="game", title="Unowned", image="http://example.com/x.jpg")
        CustomListItem.objects.create(custom_list=friends, item=candidate)
        other = get_user_model().objects.create_user(username="other")
        other_list = CustomList.objects.create(owner=other, name="已有游戏")
        counts, _ = steam.importer("76561198000000000", self.user, "overwrite")
        self.assertEqual(counts, {})
        owned = CustomList.objects.get(owner=self.user, name="已有游戏")
        self.assertEqual(list(owned.items.all()), [self.item])
        self.assertEqual(friends.items.count(), 2)
        self.assertEqual(other_list.items.count(), 0)
        game.refresh_from_db()
        self.assertEqual((game.notes, game.score, game.progress), ("Keep this note", 8, 1300))
