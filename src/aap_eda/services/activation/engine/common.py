#  Copyright 2023 Red Hat, Inc.
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


from abc import ABC, abstractmethod
from datetime import datetime
from typing import Union

from pydantic import BaseModel


class LogHandler(ABC):
    @abstractmethod
    def write(self, lines: Union[list[str], str], flush: bool) -> None:
        pass

    @abstractmethod
    def get_log_read_at(self) -> datetime:
        pass

    @abstractmethod
    def set_log_read_at(self, dt: datetime):
        pass

    @abstractmethod
    def flush(self) -> None:
        pass


class AnsibleRulebookCmdLine(BaseModel):
    ws_url: str
    ws_ssl_verify: str
    heartbeat: int
    id: str
    log_level: str  # -v or -vv or None

    def command(self) -> str:
        return "ansible-rulebook"

    def get_args(self) -> list[str]:
        args = [
            "--worker",
            "--websocket-ssl-verify",
            self.ws_ssl_verify,
            "--websocket-address",
            self.ws_url,
            "--id",
            self.id,
            "--heartbeat",
            str(self.heartbeat),
        ]
        if self.log_level:
            args.append(self.log_level)

        return args

    def command_and_args(self) -> list[str]:
        args = self.get_args()
        args.insert(0, self.command())
        return args


class Credential(BaseModel):
    username: str
    secret: str


class ContainerRequest(BaseModel):
    name: str  # f"eda-{activation_instance.id}-{uuid.uuid4()}"
    image_url: str  # quay.io/ansible/ansible-rulebook:main
    cmdline: AnsibleRulebookCmdLine
    id: str
    parent_id: str
    credential: Credential = None
    ports: dict = None
    pull_policy: str = "Always"  # Defaults to Always for K8S
    mem_limit: str = None
    mounts: dict = None
    env_vars: dict = None
    extra_args: dict = None


class ContainerEngine(ABC):
    """Abstract interface to connect to the deployment backend."""

    @abstractmethod
    def __init__(self, activation_id: str):
        ...

    @abstractmethod
    def get_status(self, container_id: str) -> str:
        ...

    @abstractmethod
    def start(self, request: ContainerRequest, logger: LogHandler) -> str:
        ...

    @abstractmethod
    def stop(self, container_id: str, logger: LogHandler) -> None:
        ...

    @abstractmethod
    def update_logs(self, container_id: str, logger: LogHandler) -> None:
        ...

    @abstractmethod
    def cleanup(self, container_id: str, logger: LogHandler) -> None:
        ...
