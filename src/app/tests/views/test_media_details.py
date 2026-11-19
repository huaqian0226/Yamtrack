import json
from pathlib import Path
from unittest.mock import patch

from bs4 import BeautifulSoup, SoupStrainer
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from app.models import (
    Game,
    Item,
    MediaTypes,
    Movie,
    Sources,
    Status,
)


class MediaDetailsViewTests(TestCase):
    """Test the media details views."""

    def setUp(self):
        """Create a user and log in."""
        self.credentials = {"username": "test", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        self.client.login(**self.credentials)

    def assert_detail_link(self, response, label, url):
        """Check the rendered anchor pairs its label with the expected URL."""
        links = BeautifulSoup(
            response.content,
            "html.parser",
            parse_only=SoupStrainer("a", href=url),
        )
        self.assertIn(
            label, [link.get_text(strip=True) for link in links.find_all("a")]
        )

    @patch("app.providers.services.get_media_metadata")
    def test_tmdb_media_details_view(self, mock_get_metadata):
        """Keep TMDB movie and TV links in Details only."""
        for media_type, media_id, title, imdb_url in (
            (
                MediaTypes.MOVIE.value,
                "238",
                "Test Movie",
                "https://www.imdb.com/title/tt0068646/",
            ),
            (
                MediaTypes.TV.value,
                "1668",
                "Test TV Show",
                "https://www.imdb.com/title/tt0106179/",
            ),
        ):
            with self.subTest(media_type=media_type):
                mock_get_metadata.reset_mock()
                mock_get_metadata.return_value = {
                    "media_id": media_id,
                    "title": title,
                    "media_type": media_type,
                    "source": Sources.TMDB.value,
                    "image": "http://example.com/image.jpg",
                    "details": {"runtime": 30},
                    "external_links": {"IMDb": imdb_url},
                }

                response = self.client.get(
                    reverse(
                        "media_details",
                        kwargs={
                            "source": Sources.TMDB.value,
                            "media_type": media_type,
                            "media_id": media_id,
                            "title": "test-title",
                        },
                    ),
                )

                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, "app/media_details.html")
                self.assertEqual(response.context["media"]["title"], title)
                self.assertNotContains(response, 'id="game-store-links"')
                self.assert_detail_link(response, "IMDb", imdb_url)
                mock_get_metadata.assert_called_once_with(
                    media_type, media_id, Sources.TMDB.value
                )

    def assert_game_store_buttons(self, response, title, links):
        """Check that the game title is followed by the storefront anchors."""
        document = BeautifulSoup(response.content, "html.parser")
        heading = document.select_one("main h1")
        self.assertEqual(heading.get_text(strip=True), title)
        store_group = heading.find_next_sibling()
        self.assertEqual(store_group.get("id"), "game-store-links")
        buttons = store_group.find_all("a")
        self.assertEqual(
            [(button.get_text(" ", strip=True), button["href"]) for button in buttons],
            [(f"{label} ↗", url) for label, url in links.items()],
        )
        for button in buttons:
            self.assertEqual(button["target"], "_blank")
            self.assertCountEqual(button["rel"], ["noopener", "noreferrer"])

    @patch("app.providers.igdb.get_access_token", return_value="mock-token")
    @patch("app.providers.igdb.services.api_request")
    def test_game_store_links_with_and_without_tracking_record(
        self,
        mock_api_request,
        _mock_access_token,
    ):
        """Render storefront buttons for both an Item-only and a tracked game."""
        cache.delete("igdb_game_1942")
        mock_path = Path(__file__).resolve().parent.parent / "mock_data"
        with (mock_path / "metadata_game_igdb.json").open() as file:
            mock_api_request.return_value = json.load(file)

        item = Item.objects.create(
            media_id="1942",
            source=Sources.IGDB.value,
            media_type=MediaTypes.GAME.value,
            title="The Witcher 3: Wild Hunt",
            image=settings.IMG_NONE,
        )
        self.assertFalse(Game.objects.filter(item=item).exists())

        details_url = reverse(
            "media_details",
            kwargs={
                "source": item.source,
                "media_type": item.media_type,
                "media_id": item.media_id,
                "title": "the-witcher-3-wild-hunt",
            },
        )
        response = self.client.get(details_url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/media_details.html")
        self.assertIsNone(response.context["current_instance"])
        self.assert_detail_link(
            response,
            Sources.IGDB.label,
            "https://www.igdb.com/games/the-witcher-3-wild-hunt",
        )
        links = response.context["media"]["external_links"]
        self.assertEqual(
            set(links), {"Steam", "Nintendo eShop", "Epic Games Store", "GOG"}
        )
        self.assert_game_store_buttons(response, item.title, links)
        for label, url in links.items():
            self.assert_detail_link(response, label, url)
        self.assertFalse(Game.objects.filter(item=item).exists())

        game = Game.objects.create(
            item=item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )
        tracked_response = self.client.get(details_url)
        self.assertEqual(tracked_response.status_code, 200)
        self.assertEqual(tracked_response.context["current_instance"], game)
        self.assert_game_store_buttons(tracked_response, item.title, links)

    @patch("app.providers.services.get_media_metadata")
    def test_game_without_store_links(self, mock_get_metadata):
        """Keep the normal game heading when there are no storefronts."""
        mock_get_metadata.return_value = {
            "media_id": "1942",
            "title": "Test Game",
            "media_type": MediaTypes.GAME.value,
            "source": Sources.IGDB.value,
            "image": settings.IMG_NONE,
            "external_links": {},
        }

        response = self.client.get("/details/igdb/game/1942/test-game")

        self.assertNotContains(response, 'id="game-store-links"')
        document = BeautifulSoup(response.content, "html.parser")
        heading = document.select_one("main h1")
        self.assertEqual(heading.get_text(strip=True), "Test Game")

    @patch("app.providers.services.get_media_metadata")
    @patch("app.providers.tmdb.process_episodes")
    def test_season_details_view(self, mock_process_episodes, mock_get_metadata):
        """Test the season details view."""
        self.user.obfuscate_unseen_episodes = True
        self.user.save(update_fields=["obfuscate_unseen_episodes"])

        mock_get_metadata.return_value = {
            "title": "Test TV Show",
            "media_id": "1668",
            "source": Sources.TMDB.value,
            "media_type": MediaTypes.TV.value,
            "image": "http://example.com/image.jpg",
            "season/1": {
                "title": "Season 1",
                "media_id": "1668",
                "media_type": MediaTypes.SEASON.value,
                "source": Sources.TMDB.value,
                "image": "http://example.com/season.jpg",
                "episodes": [],
                "details": {"episodes": 1},
                "external_links": {
                    "TVDB": "https://www.thetvdb.com/dereferrer/series/81189",
                },
            },
        }

        mock_process_episodes.return_value = [
            {
                "media_id": "1668",
                "source": Sources.TMDB.value,
                "media_type": MediaTypes.EPISODE.value,
                "season_number": 1,
                "episode_number": 1,
                "title": "Episode 1",
                "name": "Episode 1",
                "air_date": "2023-01-01",
                "watched": False,
            },
        ]

        response = self.client.get(
            reverse(
                "season_details",
                kwargs={
                    "source": Sources.TMDB.value,
                    "media_id": "1668",
                    "title": "test-tv-show",
                    "season_number": 1,
                },
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/media_details.html")

        self.assertIn("media", response.context)
        self.assertEqual(response.context["media"]["title"], "Season 1")
        self.assertEqual(len(response.context["media"]["episodes"]), 1)
        self.assertContains(response, "line-clamp-1 blur cursor-pointer")
        self.assert_detail_link(
            response,
            "TVDB",
            "https://www.thetvdb.com/dereferrer/series/81189",
        )

        mock_get_metadata.assert_called_once_with(
            "tv_with_seasons",
            "1668",
            Sources.TMDB.value,
            [1],
        )

    @patch("app.providers.services.get_media_metadata")
    def test_media_details_refreshes_missing_item_image(self, mock_get_metadata):
        """Item.image is updated when missing and live metadata has one."""
        live_image = "http://example.com/fresh.jpg"
        mock_get_metadata.return_value = {
            "media_id": "238",
            "title": "Test Movie",
            "media_type": MediaTypes.MOVIE.value,
            "source": Sources.TMDB.value,
            "image": live_image,
            "max_progress": 1,
            "overview": "Test overview",
            "release_date": "2023-01-01",
        }

        item = Item.objects.create(
            media_id="238",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Test Movie",
            image=settings.IMG_NONE,
        )
        Movie.objects.create(
            item=item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )

        response = self.client.get(
            reverse(
                "media_details",
                kwargs={
                    "source": Sources.TMDB.value,
                    "media_type": MediaTypes.MOVIE.value,
                    "media_id": "238",
                    "title": "test-movie",
                },
            ),
        )

        self.assertEqual(response.status_code, 200)
        item.refresh_from_db()
        self.assertEqual(item.image, live_image)

    @patch("app.providers.services.get_media_metadata")
    def test_media_details_keeps_existing_item_image(self, mock_get_metadata):
        """Item.image is left alone when already set."""
        existing_image = "http://example.com/stored.jpg"
        mock_get_metadata.return_value = {
            "media_id": "238",
            "title": "Test Movie",
            "media_type": MediaTypes.MOVIE.value,
            "source": Sources.TMDB.value,
            "image": "http://example.com/fresh.jpg",
            "max_progress": 1,
            "overview": "Test overview",
            "release_date": "2023-01-01",
        }

        item = Item.objects.create(
            media_id="238",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Test Movie",
            image=existing_image,
        )
        Movie.objects.create(
            item=item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )

        response = self.client.get(
            reverse(
                "media_details",
                kwargs={
                    "source": Sources.TMDB.value,
                    "media_type": MediaTypes.MOVIE.value,
                    "media_id": "238",
                    "title": "test-movie",
                },
            ),
        )

        self.assertEqual(response.status_code, 200)
        item.refresh_from_db()
        self.assertEqual(item.image, existing_image)
