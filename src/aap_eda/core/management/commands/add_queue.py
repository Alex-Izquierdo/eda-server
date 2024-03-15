#  Copyright 2024 Red Hat, Inc.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

from django.core.management.base import BaseCommand

from aap_eda.core.enums import RQQueueState
from aap_eda.core.models import RQQueue


class Command(BaseCommand):
    help = "Adds new queues to eda-server"

    def add_arguments(self, parser):
        parser.add_argument("queues", nargs="+", type=str)
        parser.add_argument(
            "--state",
            type=str,
            default=RQQueueState.AVAILABLE,
            help="State of the queue, by default is 'available'",
        )

    def handle(self, *args, **options):
        for queue_name in options["queues"]:
            RQQueue.objects.create(
                name=queue_name,
                state=options["state"],
            )
            self.stdout.write(
                self.style.SUCCESS(f'Successfully added queue "{queue_name}"'),
            )
