import logging

from django.apps import AppConfig
from django.conf import settings
from django.db.utils import ProgrammingError

LOGGER = logging.getLogger(__name__)


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "aap_eda.core"

    def ready(self):
        try:
            settings.RQ_QUEUES = self.get_rq_queues()
        except ProgrammingError as exc:
            if '"core_rq_queue" does not exist' not in str(exc):
                raise
            LOGGER.warning(
                "Error when trying to configure RQ_QUEUES. "
                "This is expected when running commands if "
                "multiqueue migration is not yet applied.",
            )

    def get_rq_queues(self):
        """Construct the RQ_QUEUES dictionary based on the settings.

        If there is no multinode enabled, the default and activation queues
        are used. Otherwise, constructs the queues based on the
        WORKERS_RULEBOOK_QUEUES list.
        """
        from .models import RQQueue

        queues = {}

        # Configures the default queue
        if settings.RQ_UNIX_SOCKET_PATH:
            queues["default"] = {
                "UNIX_SOCKET_PATH": settings.RQ_UNIX_SOCKET_PATH,
                "DEFAULT_TIMEOUT": settings.DEFAULT_QUEUE_TIMEOUT,
            }
        else:
            queues["default"] = {
                "HOST": settings.RQ_HOST,
                "PORT": settings.RQ_PORT,
                "DEFAULT_TIMEOUT": settings.DEFAULT_QUEUE_TIMEOUT,
            }

        # Configures the activation queue for single node mode
        configured_queues = RQQueue.objects.all()
        if len(configured_queues) == 1:
            if settings.RQ_UNIX_SOCKET_PATH:
                queues["activation"] = {
                    "UNIX_SOCKET_PATH": settings.RQ_UNIX_SOCKET_PATH,
                    "DEFAULT_TIMEOUT": settings.DEFAULT_QUEUE_TIMEOUT,
                }
            else:
                queues["activation"] = {
                    "HOST": settings.RQ_HOST,
                    "PORT": settings.RQ_PORT,
                    "DEFAULT_TIMEOUT": settings.DEFAULT_QUEUE_TIMEOUT,
                }
        # Configures the activation queue for multinode mode
        else:
            for queue in configured_queues:
                queues[queue.name] = {
                    "HOST": settings.RQ_HOST,
                    "PORT": settings.RQ_PORT,
                    "DEFAULT_TIMEOUT": settings.DEFAULT_QUEUE_TIMEOUT,
                }

        for queue in queues.values():
            queue["DB"] = settings.RQ_DB

        return queues
