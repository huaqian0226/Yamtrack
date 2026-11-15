"""WSGI config for yamtrack project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/stable/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

_django_application = get_wsgi_application()

from django.urls import path
from config import urls as _local_urls
from config.local_sync import nintendo_sync, game_library_sync
_local_urls.urlpatterns.insert(0, path("local/nintendo-sync", nintendo_sync, name="local_nintendo_sync"))
_local_urls.urlpatterns.insert(0, path("local/game-library-sync", game_library_sync, name="local_game_library_sync"))


def application(environ, start_response):
    """Keep trusted local workbench popups in the opener's browsing group."""
    def local_headers(status, headers, exc_info=None):
        local_host = environ.get("HTTP_HOST") in {"127.0.0.1:8000", "localhost:8000"}
        html = any(k.lower() == "content-type" and "text/html" in v for k, v in headers)
        if local_host and html:
            headers = [(k, v) for k, v in headers if k.lower() != "cross-origin-opener-policy"]
            headers.append(("Cross-Origin-Opener-Policy", "unsafe-none"))
        return start_response(status, headers, exc_info)
    return _django_application(environ, local_headers)
