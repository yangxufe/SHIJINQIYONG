"""Serve Django behind the single trusted loopback Caddy proxy."""

import os

from waitress import serve

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")

from config.wsgi import application  # noqa: E402


if __name__ == "__main__":
    serve(
        application,
        host="127.0.0.1",
        port=8000,
        threads=4,
        trusted_proxy="127.0.0.1",
        trusted_proxy_count=1,
        trusted_proxy_headers={"x-forwarded-for", "x-forwarded-proto"},
        clear_untrusted_proxy_headers=True,
        max_request_body_size=220_000_000,  # Only the recipe-upload Caddy route permits a large body.
    )
