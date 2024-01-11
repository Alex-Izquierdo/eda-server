#  Copyright 2022-2023 Red Hat, Inc.
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

from datetime import datetime

# from aap_eda.api.serializers.activation import is_activation_valid
from aap_eda.core.enums import ACTIVATION_STATUS_MESSAGE_MAP, ActivationStatus

__all__ = ["RulebookProcessParent"]


class RulebookProcessParent:
    """Model Mixin for Rulebook Process Parent.

    It provides common logic for models that are going
    to be used as a parent for rulebook processes.
    """

    @property
    def status(self) -> ActivationStatus:
        """Returns the status of the activation from its latest process."""
        # if is_activation_valid(self):
        #     return ActivationStatus.ERROR
        if self.latest_instance and self.latest_instance.status:
            return ActivationStatus(self.latest_instance.status)
        return ActivationStatus.PENDING

    @property
    def status_message(self) -> str:
        """Returns the status message from its latest process."""
        if self.latest_instance and self.latest_instance.status_message:
            return self.latest_instance.status_message
        return ACTIVATION_STATUS_MESSAGE_MAP[self.status]

    @property
    def status_updated_at(self) -> datetime:
        """Returns the status updated at from its latest process."""
        if self.latest_instance and self.latest_instance.status_updated_at:
            return self.latest_instance.status_updated_at
        return self.created_at
