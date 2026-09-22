import logging

from django.apps import AppConfig


class ApiConfig(AppConfig):
    name = "api"

    def ready(self):
        from . import signals

        # Python warnings otherwise go straight to stderr, past the LOGGING
        # handlers, and never reach LOG_FILE. Django stopped doing this itself.
        logging.captureWarnings(True)
