from django.core.management.base import BaseCommand
from aap_eda.core.models import RQQueue


class Command(BaseCommand):
    help = "Lists all queues in the RQQueue table"

    def handle(self, *args, **options):
        if RQQueue.objects.count() == 0:
            self.stdout.write("No queues found")
            return
        self.stdout.write("NAME STATE")
        for queue in RQQueue.objects.all():
            self.stdout.write(f"{queue.name} {queue.state}")
