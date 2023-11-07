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

import re
from dataclasses import dataclass
from unittest import mock

import pytest
from dateutil import parser
from podman.errors import ContainerError, ImageNotFound
from podman.errors.exceptions import APIError, NotFound

from aap_eda.core import models
from aap_eda.core.enums import ActivationStatus
from aap_eda.services.activation.db_log_handler import DBLogger
from aap_eda.services.activation.engine.common import (
    AnsibleRulebookCmdLine,
    ContainerRequest,
)
from aap_eda.services.activation.engine.exceptions import (
    ContainerCleanupError,
    ContainerEngineInitError,
    ContainerNotFoundError,
    ContainerStartError,
)
from aap_eda.services.activation.engine.podman import Engine
from aap_eda.services.activation.exceptions import (
    ActivationImageNotFound,
    ActivationImagePullError,
)


@dataclass
class InitData:
    activation: models.Activation
    activation_instance: models.ActivationInstance


@pytest.fixture()
def init_data():
    user = models.User.objects.create(
        username="tester",
        password="secret",
        first_name="Adam",
        last_name="Tester",
        email="adam@example.com",
    )
    activation = models.Activation.objects.create(
        name="activation",
        user=user,
    )
    activation_instance = models.ActivationInstance.objects.create(
        name="test-instance",
        log_read_at=parser.parse("2023-10-30T19:18:48.362883381Z"),
        activation=activation,
    )

    return InitData(
        activation=activation,
        activation_instance=activation_instance,
    )


def get_ansible_rulebook_cmdline(data: InitData):
    return AnsibleRulebookCmdLine(
        ws_url="ws://localhost:8000/api/eda/ws/ansible-rulebook",
        ws_ssl_verify="no",
        id=data.activation.id,
        log_level="-v",
        heartbeat=5,
    )


def get_request(data: InitData):
    return ContainerRequest(
        name="test-request",
        image_url="quay.io/ansible/ansible-rulebook:main",
        activation_instance_id=data.activation_instance.id,
        activation_id=data.activation.id,
        cmdline=get_ansible_rulebook_cmdline(data),
    )


@pytest.fixture(autouse=True)
def use_dummy_socket_url(settings):
    settings.PODMAN_SOCKET_URL = "unix://socket_url"


@pytest.fixture
def podman_engine(init_data):
    activation_id = init_data.activation.id
    with mock.patch(
        "aap_eda.services.activation.engine.podman.PodmanClient"
    ) as client_mock:
        engine = Engine(
            _activation_id=str(activation_id),
            client=client_mock,
        )

        yield engine


@pytest.mark.django_db
def test_engine_init(init_data):
    activation_id = init_data.activation.id
    with mock.patch("aap_eda.services.activation.engine.podman.PodmanClient"):
        engine = Engine(_activation_id=str(activation_id))
        engine.client.version.assert_called_once()


@pytest.mark.django_db
def test_engine_init_with_exception(init_data):
    activation_id = init_data.activation.id
    with pytest.raises(
        ContainerEngineInitError,
        match=r"http://socket_url/",
    ):
        Engine(_activation_id=str(activation_id))


@pytest.mark.django_db
def test_engine_start(init_data, podman_engine):
    engine = podman_engine
    request = get_request(init_data)
    log_handler = DBLogger(init_data.activation_instance.id)

    engine.start(request, log_handler)

    engine.client.containers.run.assert_called_once()
    assert models.ActivationInstanceLog.objects.count() == 4
    assert re.match(
        r"^Container .+ is started",
        models.ActivationInstanceLog.objects.last().log,
    )


@pytest.mark.django_db
def test_engine_start_with_none_image_url(init_data, podman_engine):
    engine = podman_engine
    log_handler = DBLogger(init_data.activation_instance.id)
    request = get_request(init_data)
    request.image_url = None

    with pytest.raises(ContainerStartError):
        engine.start(request, log_handler)


@pytest.mark.django_db
def test_engine_start_with_credential(init_data, podman_engine):
    credential = models.Credential.objects.create(
        name="credential1", username="me", secret="sec1"
    )
    engine = podman_engine
    log_handler = DBLogger(init_data.activation_instance.id)
    request = get_request(init_data)
    request.credential = credential

    engine.start(request, log_handler)

    engine.client.login.assert_called_once()
    engine.client.images.pull.assert_called_once_with(
        request.image_url,
        auth_config={
            "username": credential.username,
            "password": credential.secret,
        },
    )
    engine.client.containers.run.assert_called_once_with(
        image=request.image_url,
        command=request.cmdline.command_and_args(),
        stdout=True,
        stderr=True,
        remove=True,
        detach=True,
        name=request.name,
    )


@pytest.mark.django_db
def test_engine_start_with_login_api_exception(init_data, podman_engine):
    credential = models.Credential.objects.create(
        name="credential1", username="me", secret="sec1"
    )
    engine = podman_engine
    log_handler = DBLogger(init_data.activation_instance.id)
    request = get_request(init_data)
    request.credential = credential

    def raise_error(*args, **kwargs):
        raise APIError("Login failed")

    engine.client.login.side_effect = raise_error

    with pytest.raises(ContainerStartError, match="Login failed"):
        engine.start(request, log_handler)


@pytest.mark.django_db
def test_engine_start_with_image_not_found_exception(init_data, podman_engine):
    credential = models.Credential.objects.create(
        name="credential1", username="me", secret="sec1"
    )
    engine = podman_engine
    log_handler = DBLogger(init_data.activation_instance.id)
    request = get_request(init_data)
    request.credential = credential

    def raise_error(*args, **kwargs):
        raise ImageNotFound("Image not found")

    engine.client.images.pull.side_effect = raise_error

    with pytest.raises(
        ActivationImageNotFound, match=f"Image {request.image_url} not found"
    ):
        engine.start(request, log_handler)

    assert (
        models.ActivationInstanceLog.objects.last().log
        == f"Image {request.image_url} not found"
    )


@pytest.mark.django_db
def test_engine_start_with_image_pull_exception(init_data, podman_engine):
    credential = models.Credential.objects.create(
        name="credential1", username="me", secret="sec1"
    )
    engine = podman_engine
    log_handler = DBLogger(init_data.activation_instance.id)
    request = get_request(init_data)
    request.credential = credential

    image_mock = mock.Mock()
    image_mock.pull.return_value.id = None
    msg = (
        f"Image {request.image_url} pull failed. The image url "
        "or the credentials may be incorrect."
    )

    with mock.patch.object(engine.client, "images", image_mock):
        with pytest.raises(ActivationImagePullError, match=msg):
            engine.start(request, log_handler)

    assert models.ActivationInstanceLog.objects.last().log == msg


@pytest.mark.django_db
def test_engine_start_with_containers_run_exception(init_data, podman_engine):
    credential = models.Credential.objects.create(
        name="credential1", username="me", secret="sec1"
    )
    engine = podman_engine
    log_handler = DBLogger(init_data.activation_instance.id)
    request = get_request(init_data)
    request.credential = credential

    def raise_error(*args, **kwargs):
        raise ContainerError(
            container="container",
            exit_status=1,
            command="ansibile-rulebook",
            image="image",
        )

    engine.client.containers.run.side_effect = raise_error

    with pytest.raises(ContainerStartError, match=r"Container Start Error:"):
        engine.start(request, log_handler)

    assert re.match(
        r"^Container Start Error:",
        models.ActivationInstanceLog.objects.last().log,
    )


@pytest.mark.django_db
def test_engine_get_status(podman_engine):
    engine = podman_engine

    container_mock = mock.Mock()
    engine.client.containers.get.return_value = container_mock

    # when status in "running"
    container_mock.status = "running"
    activation_status = engine.get_status("container_id")

    assert activation_status == ActivationStatus.RUNNING

    # when status in "exited"
    container_mock.status = "exited"
    expects = [
        (0, ActivationStatus.COMPLETED),
        (1, ActivationStatus.FAILED),
    ]

    for key, value in expects:
        container_mock.attrs.get.return_value.get.return_value = key
        activation_status = engine.get_status("container_id")

        assert activation_status == value


@pytest.mark.django_db
def test_engine_get_status_with_exception(podman_engine):
    engine = podman_engine

    engine.client.containers.exists.return_value = None

    with pytest.raises(
        ContainerNotFoundError, match="Container id 100 not found"
    ):
        engine.get_status("100")


@pytest.mark.django_db
def test_engine_cleanup(init_data, podman_engine):
    engine = podman_engine
    log_handler = DBLogger(init_data.activation_instance.id)

    engine.cleanup("100", log_handler)

    assert (
        models.ActivationInstanceLog.objects.last().log
        == "Container 100 is cleaned up."
    )


@pytest.mark.django_db
def test_engine_cleanup_with_not_found_exception(init_data, podman_engine):
    engine = podman_engine
    log_handler = DBLogger(init_data.activation_instance.id)

    def raise_error(*args, **kwargs):
        raise NotFound("Not found")

    container_mock = mock.Mock()
    engine.client.containers.get.return_value = container_mock
    container_mock.stop.side_effect = raise_error

    engine.cleanup("100", log_handler)

    assert (
        models.ActivationInstanceLog.objects.last().log
        == "Container 100 not found."
    )


@pytest.mark.django_db
def test_engine_cleanup_with_api_exception(init_data, podman_engine):
    engine = podman_engine
    log_handler = DBLogger(init_data.activation_instance.id)

    def raise_error(*args, **kwargs):
        raise APIError("Not found")

    engine.client.containers.get.side_effect = raise_error

    with pytest.raises(
        ContainerCleanupError, match="Failed to cleanup container 100"
    ):
        engine.cleanup("100", log_handler)


@pytest.mark.django_db
def test_engine_update_logs(init_data, podman_engine):
    engine = podman_engine
    log_handler = DBLogger(init_data.activation_instance.id)
    init_log_read_at = init_data.activation_instance.log_read_at
    message = (
        "2023-10-31 15:28:01,318 - ansible_rulebook.engine - INFO - "
        "Calling main in ansible.eda.range"
    )

    container_mock = mock.Mock()
    engine.client.containers.get.return_value = container_mock
    container_mock.status = "running"
    container_mock.logs.return_value = [
        (
            "2023-10-31T11:28:00-04:00 2023-10-31 15:28:00,905 - "
            "ansible_rulebook.engine - INFO - load source\n".encode("utf-8")
        ),
        (
            "2023-10-31T11:28:01-04:00 2023-10-31 15:28:01,142 - "
            "ansible_rulebook.engine - INFO - load source filters\n".encode(
                "utf-8"
            )
        ),
        (
            "2023-10-31T11:28:01-04:00 2023-10-31 15:28:01,142 - "
            "ansible_rulebook.engine - INFO - "
            "loading eda.builtin.insert_meta_info\n".encode("utf-8")
        ),
        f"2023-10-31T11:28:01-04:00 {message}".encode("utf-8"),
    ]

    engine.update_logs("100", log_handler)

    assert models.ActivationInstanceLog.objects.count() == len(
        container_mock.logs.return_value
    )
    assert models.ActivationInstanceLog.objects.last().log == f"{message}"

    init_data.activation_instance.refresh_from_db()
    assert init_data.activation_instance.log_read_at > init_log_read_at


@pytest.mark.django_db
def test_engine_update_logs_with_container_not_found(init_data, podman_engine):
    engine = podman_engine
    log_handler = DBLogger(init_data.activation_instance.id)

    engine.client.containers.exists.return_value = None
    engine.update_logs("100", log_handler)

    assert (
        models.ActivationInstanceLog.objects.last().log
        == "Container 100 not found."
    )