"""Single-process recipe queue worker; never runs inside Waitress."""

import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from meals.generation import claim_next_task, process_task, provider_configuration, GenerationUnavailable


class Command(BaseCommand):
    help = "Run one local recipe generation worker; --once handles at most one task."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **options):
        try:
            provider_configuration()
        except GenerationUnavailable as exc:
            self.stdout.write(f"worker_not_started={exc.code}")
            return
        while True:
            close_old_connections()
            task_id = claim_next_task()
            if task_id is not None:
                process_task(task_id)
                self.stdout.write("task_processed")
            elif options["once"]:
                self.stdout.write("queue_empty")
            if options["once"]:
                return
            time.sleep(2)
