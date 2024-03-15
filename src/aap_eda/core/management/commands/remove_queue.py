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
from django.core.exceptions import ObjectDoesNotExist
from aap_eda.core.models import RQQueue


class Command(BaseCommand):
    help = "Remove queues in eda-server."

    def add_arguments(self, parser):
        parser.add_argument("queues", nargs="+", type=str)

    def handle(self, *args, **options):
        for queue_name in options["queues"]:
            try:
                queue = RQQueue.objects.get(name=queue_name)
                # TODO: remove queue from RQ
                # TODO: we might have an option to try clean up activations
                queue.delete()
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Successfully removed queue "{queue_name}"'
                    )
                )
            except ObjectDoesNotExist:
                self.stdout.write(
                    self.style.WARNING(f'Queue "{queue_name}" does not exist')
                )
