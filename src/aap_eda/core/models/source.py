#  Copyright 2022 Red Hat, Inc.
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

import uuid

from django.db import models

from aap_eda.core.models.activation import Activation

__all__ = ["Source"]


class Source(Activation):
    class Meta:
        db_table = "core_source"

    uuid = models.UUIDField(default=uuid.uuid4)
    type = models.TextField(null=False)
    args = models.JSONField(null=True, default=None)
    listener_args = models.JSONField(null=True, default=None)
