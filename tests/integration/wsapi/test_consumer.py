import base64
import logging
import uuid
from datetime import datetime
from typing import Generator
from unittest import mock
from unittest.mock import patch

import pytest
import pytest_asyncio
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone
from pydantic.error_wrappers import ValidationError

from aap_eda.core import enums, models
from aap_eda.core.models.activation import ActivationStatus
from aap_eda.services.activation.activation_manager import ActivationManager
from aap_eda.wsapi.consumers import AnsibleRulebookConsumer, logger

# TODO(doston): this test module needs a whole refactor to use already
# existing fixtures over from API conftest.py instead of creating new objects
# keeping it to minimum for now to pass all failing tests

TIMEOUT = 5

DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"

TEST_EXTRA_VAR = """
---
collections:
  - community.general
  - benthomasson.eda  # 1.3.0
"""

TEST_RULESETS = """
---
- name: hello
  hosts: localhost
  gather_facts: false
  tasks:
    - debug:
        msg: hello
"""

DUMMY_UUID = "8472ff2c-6045-4418-8d4e-46f6cffc8557"
DUMMY_UUID2 = "8472ff2c-6045-4418-8d4e-46f6cfffffff"

AAP_INPUTS = {
    "host": "https://eda_controller_url",
    "username": "adam",
    "password": "secret",
    "oauth_token": "",
    "verify_ssl": False,
}


@pytest.fixture
def eda_caplog(caplog_factory):
    return caplog_factory(logger)


@pytest.fixture
@pytest.mark.django_db(transaction=True)
async def test_handle_workers_without_credentials(
    ws_communicator: WebsocketCommunicator,
    default_organization: models.Organization,
):
    rulebook_process_with_extra_var = await _prepare_db_data(
        default_organization
    )
    rulebook_process_without_extra_var = (
        await _prepare_activation_instance_without_extra_var()
    )
    rulebook_process_no_token = await _prepare_activation_instance_no_token()

    payload = {
        "type": "Worker",
        "activation_id": rulebook_process_with_extra_var,
    }
    await ws_communicator.send_json_to(payload)

    for type in [
        "ExtraVars",
        "Rulebook",
        "ControllerInfo",
        "EndOfResponse",
    ]:
        response = await ws_communicator.receive_json_from(timeout=TIMEOUT)
        assert response["type"] == type
        if type == "ControllerInfo":
            assert response["token"] == "XXX"

    payload = {
        "type": "Worker",
        "activation_id": rulebook_process_without_extra_var,
    }
    await ws_communicator.send_json_to(payload)

    for type in [
        "Rulebook",
        "ControllerInfo",
        "EndOfResponse",
    ]:
        response = await ws_communicator.receive_json_from(timeout=TIMEOUT)
        assert response["type"] == type
        if type == "ControllerInfo":
            assert response["token"] == "XXX"

    payload = {
        "type": "Worker",
        "activation_id": rulebook_process_no_token,
    }
    await ws_communicator.send_json_to(payload)

    for type in [
        "Rulebook",
        "EndOfResponse",
    ]:
        response = await ws_communicator.receive_json_from(timeout=TIMEOUT)
        assert response["type"] == type


@pytest.mark.django_db(transaction=True)
async def test_handle_workers_with_eda_system_vault_credential(
    ws_communicator: WebsocketCommunicator,
    preseed_credential_types,
    default_organization: models.Organization,
):
    credential = await _prepare_system_vault_credential_async(
        default_organization
    )
    rulebook_process_id = await _prepare_activation_instance_with_credentials(
        default_organization,
        [credential],
    )

    payload = {
        "type": "Worker",
        "activation_id": rulebook_process_id,
    }
    await ws_communicator.send_json_to(payload)

    for type in [
        "Rulebook",
        "VaultCollection",
        "EndOfResponse",
    ]:
        response = await ws_communicator.receive_json_from(timeout=TIMEOUT)
        assert response["type"] == type
        if type == "VaultCollection":
            data = response["data"]
            assert len(data) == 1
            assert data[0]["type"] == "VaultPassword"
            assert data[0]["password"] == "secret"
            assert data[0]["label"] == "adam"


@pytest.mark.django_db(transaction=True)
async def test_handle_workers_with_controller_info(
    ws_communicator: WebsocketCommunicator,
    preseed_credential_types,
    default_organization: models.Organization,
):
    rulebook_process_id = await _prepare_activation_with_controller_info(
        default_organization,
    )

    payload = {
        "type": "Worker",
        "activation_id": rulebook_process_id,
    }
    await ws_communicator.send_json_to(payload)

    for type in [
        "Rulebook",
        "ControllerInfo",
        "VaultCollection",
        "EnvVars",
        "EndOfResponse",
    ]:
        response = await ws_communicator.receive_json_from(timeout=TIMEOUT)
        assert response["type"] == type
        if type == "ControllerInfo":
            assert response["url"] == AAP_INPUTS["host"]
            assert response["username"] == AAP_INPUTS["username"]
            assert response["password"] == AAP_INPUTS["password"]
            assert (response["ssl_verify"] == "yes") is AAP_INPUTS[
                "verify_ssl"
            ]
            assert response["token"] == AAP_INPUTS["oauth_token"]
        elif type == "EnvVars":
            assert response["data"].startswith("QUFQX0hPU1ROQU1FOiBodHRwczovL")


@pytest.mark.django_db(transaction=True)
async def test_handle_workers_with_validation_errors(
    default_organization: models.Organization,
):
    communicator = WebsocketCommunicator(
        AnsibleRulebookConsumer.as_asgi(), "ws/"
    )
    connected, _ = await communicator.connect(timeout=3)
    assert connected

    rulebook_process_id = await _prepare_db_data(default_organization)

    payload = {
        "type": "Worker",
        "invalid_activation_id": rulebook_process_id,
    }

    with pytest.raises(ValidationError):
        await communicator.send_json_to(payload)
        await communicator.wait()


@pytest.mark.django_db(transaction=True)
async def test_handle_jobs(
    ws_communicator: WebsocketCommunicator,
    default_organization: models.Organization,
):
    rulebook_process_id = await _prepare_db_data(default_organization)

    assert (await get_job_instance_count()) == 0
    assert (await get_activation_instance_job_instance_count()) == 0

    payload = {
        "type": "Job",
        "job_id": "940730a1-8b6f-45f3-84c9-bde8f04390e0",
        "ansible_rulebook_id": rulebook_process_id,
        "name": "ansible.eda.hello",
        "ruleset": "ruleset",
        "rule": "rule",
        "hosts": "hosts",
        "action": "run_playbook",
    }

    await ws_communicator.send_json_to(payload)
    await ws_communicator.wait()

    assert (await get_job_instance_count()) == 1
    assert (await get_activation_instance_job_instance_count()) == 1


@pytest.mark.django_db(transaction=True)
async def test_handle_events(ws_communicator: WebsocketCommunicator):
    job_instance = await _prepare_job_instance()

    assert (await get_job_instance_event_count()) == 0
    payload = {
        "type": "AnsibleEvent",
        "event": {
            "event": "verbose",
            "job_id": job_instance.uuid,
            "counter": 1,
            "stdout": "the playbook is completed",
        },
    }
    await ws_communicator.send_json_to(payload)
    await ws_communicator.wait()

    assert (await get_job_instance_event_count()) == 1


@pytest.mark.django_db(transaction=True)
async def test_handle_actions_multiple_firing(
    ws_communicator: WebsocketCommunicator,
    default_organization: models.Organization,
):
    rulebook_process_id = await _prepare_db_data(default_organization)
    job_instance = await _prepare_job_instance()

    assert (await get_audit_rule_count()) == 0
    payload1 = create_action_payload(
        DUMMY_UUID,
        rulebook_process_id,
        job_instance.uuid,
        DUMMY_UUID,
        "2023-03-29T15:00:17.260803Z",
        _matching_events(),
    )
    payload2 = create_action_payload(
        DUMMY_UUID2,
        rulebook_process_id,
        job_instance.uuid,
        DUMMY_UUID,
        "2023-03-29T15:00:27.260803Z",
        _matching_events(),
    )
    await ws_communicator.send_json_to(payload1)
    await ws_communicator.send_json_to(payload2)
    await ws_communicator.wait()

    assert (await get_audit_rule_count()) == 2
    assert (await get_audit_action_count()) == 2
    assert (await get_audit_event_count()) == 4


@pytest.mark.django_db(transaction=True)
async def test_handle_actions_with_empty_job_uuid(
    ws_communicator: WebsocketCommunicator,
    default_organization: models.Organization,
):
    rulebook_process_id = await _prepare_db_data(default_organization)
    assert (await get_audit_rule_count()) == 0

    # job uuid is empty string
    payload = create_action_payload(
        DUMMY_UUID,
        rulebook_process_id,
        "",
        DUMMY_UUID,
        "2023-03-29T15:00:17.260803Z",
        _matching_events(),
    )
    await ws_communicator.send_json_to(payload)
    await ws_communicator.wait()

    assert (await get_audit_rule_count()) == 1
    assert (await get_audit_action_count()) == 1
    assert (await get_audit_event_count()) == 2


@pytest.mark.django_db(transaction=True)
async def test_handle_actions(
    ws_communicator: WebsocketCommunicator,
    default_organization: models.Organization,
):
    rulebook_process_id = await _prepare_db_data(default_organization)
    job_instance = await _prepare_job_instance()

    assert (await get_audit_rule_count()) == 0
    payload = create_action_payload(
        DUMMY_UUID,
        rulebook_process_id,
        job_instance.uuid,
        DUMMY_UUID,
        "2023-03-29T15:00:17.260803Z",
        _matching_events(),
    )
    await ws_communicator.send_json_to(payload)
    await ws_communicator.wait()

    assert (await get_audit_rule_count()) == 1
    assert (await get_audit_action_count()) == 1
    assert (await get_audit_event_count()) == 2

    event1, event2 = await get_audit_events()

    event1_data = payload["matching_events"]["m_1"]
    event2_data = payload["matching_events"]["m_0"]
    for event in [event1, event2]:
        if event1_data["meta"]["uuid"] == str(event.id):
            data = event1_data.copy()
        elif event2_data["meta"]["uuid"] == str(event.id):
            data = event2_data.copy()
        else:
            data = None

        assert data is not None
        meta = data.pop("meta")
        assert event.payload == data
        assert event.source_name == meta["source"]["name"]
        assert event.source_type == meta["source"]["type"]


@pytest.mark.django_db(transaction=True)
async def test_rule_status_with_multiple_failed_actions(
    ws_communicator: WebsocketCommunicator,
    default_organization: models.Organization,
):
    rulebook_process_id = await _prepare_db_data(default_organization)
    job_instance = await _prepare_job_instance()

    action1 = create_action_payload(
        DUMMY_UUID,
        rulebook_process_id,
        job_instance.uuid,
        DUMMY_UUID,
        "2023-03-29T15:00:17.260803Z",
        _matching_events(),
    )
    action2 = create_action_payload(
        DUMMY_UUID2,
        rulebook_process_id,
        job_instance.uuid,
        DUMMY_UUID,
        "2023-03-29T15:00:17.260803Z",
        _matching_events(),
        "failed",
    )
    await ws_communicator.send_json_to(action1)
    await ws_communicator.send_json_to(action2)
    await ws_communicator.wait()

    assert (await get_audit_action_count()) == 2
    assert (await get_audit_rule_count()) == 1

    rule = await get_first_audit_rule()
    assert rule.status == "failed"


@pytest.mark.django_db(transaction=True)
async def test_handle_heartbeat(
    ws_communicator: WebsocketCommunicator,
    default_organization: models.Organization,
):
    rulebook_process_id = await _prepare_db_data(default_organization)
    rulebook_process = await get_rulebook_process(rulebook_process_id)
    activation = await get_activation_by_rulebook_process(rulebook_process_id)
    assert activation.ruleset_stats == {}

    stats = [
        {
            "start": rulebook_process.started_at.strftime(DATETIME_FORMAT),
            "end": None,
            "numberOfRules": 1,
            "numberOfDisabledRules": 0,
            "rulesTriggered": 1,
            "eventsProcessed": 2000,
            "eventsMatched": 1,
            "eventsSuppressed": 1999,
            "permanentStorageSize": 0,
            "asyncResponses": 0,
            "bytesSentOnAsync": 0,
            "sessionId": 1,
            "ruleSetName": "ruleset1",
        },
        {
            "start": rulebook_process.started_at.strftime(DATETIME_FORMAT),
            "end": "2024-08-21T18:39:12.331Z",
            "numberOfRules": 10,
            "numberOfDisabledRules": 0,
            "rulesTriggered": 1,
            "eventsProcessed": 4000,
            "eventsMatched": 1,
            "eventsSuppressed": 3999,
            "permanentStorageSize": 0,
            "asyncResponses": 0,
            "bytesSentOnAsync": 0,
            "sessionId": 1,
            "ruleSetName": "ruleset2",
        },
    ]

    payloads = [
        {
            "type": "SessionStats",
            "activation_id": rulebook_process_id,
            "stats": stat,
            "reported_at": timezone.now().strftime(DATETIME_FORMAT),
        }
        for stat in stats
    ]

    for payload in payloads:
        await ws_communicator.send_json_to(payload)

    await ws_communicator.wait()

    updated_rulebook_process = await get_rulebook_process(rulebook_process_id)
    assert (
        updated_rulebook_process.updated_at.strftime(DATETIME_FORMAT)
    ) == payload["reported_at"]

    activation = await get_activation_by_rulebook_process(rulebook_process_id)
    assert activation.ruleset_stats is not None
    assert list(activation.ruleset_stats.keys()) == [
        stat["ruleSetName"] for stat in stats
    ]


@pytest.mark.django_db(transaction=True)
async def test_handle_heartbeat_running_status(
    ws_communicator: WebsocketCommunicator,
    default_organization: models.Organization,
):
    rulebook_process_id = await _prepare_db_data(
        default_organization,
        ActivationStatus.STARTING,
    )
    rulebook_process = await get_rulebook_process(rulebook_process_id)
    activation = await get_activation_by_rulebook_process(rulebook_process_id)
    assert activation.ruleset_stats == {}

    stats = [
        {
            "start": rulebook_process.started_at.strftime(DATETIME_FORMAT),
            "end": None,
            "numberOfRules": 1,
            "numberOfDisabledRules": 0,
            "rulesTriggered": 1,
            "eventsProcessed": 2000,
            "eventsMatched": 1,
            "eventsSuppressed": 1999,
            "permanentStorageSize": 0,
            "asyncResponses": 0,
            "bytesSentOnAsync": 0,
            "sessionId": 1,
            "ruleSetName": "ruleset1",
        },
    ]

    payloads = [
        {
            "type": "SessionStats",
            "activation_id": rulebook_process_id,
            "stats": stat,
            "reported_at": timezone.now().strftime(DATETIME_FORMAT),
        }
        for stat in stats
    ]

    for payload in payloads:
        await ws_communicator.send_json_to(payload)

    await ws_communicator.wait()

    activation = await monitor_activation(activation)
    assert activation.status == ActivationStatus.RUNNING


@database_sync_to_async
def monitor_activation(activation: models.Activation):
    activation.latest_instance.activation_pod_id = "test"
    activation.latest_instance.save(update_fields=["activation_pod_id"])
    ActivationManager(activation, container_engine=mock.Mock()).monitor()
    activation.refresh_from_db()
    return activation


@pytest.mark.django_db(transaction=True)
async def test_multiple_rules_for_one_event(
    ws_communicator: WebsocketCommunicator,
    default_organization: models.Organization,
):
    rulebook_process_id = await _prepare_db_data(default_organization)
    job_instance = await _prepare_job_instance()

    matching_events = _matching_events()

    action1 = create_action_payload(
        str(uuid.uuid4()),
        rulebook_process_id,
        job_instance.uuid,
        str(uuid.uuid4()),
        "2023-03-29T15:00:17.260803Z",
        matching_events,
    )
    action2 = create_action_payload(
        str(uuid.uuid4()),
        rulebook_process_id,
        job_instance.uuid,
        str(uuid.uuid4()),
        "2023-03-29T15:00:17.260803Z",
        matching_events,
    )

    await ws_communicator.send_json_to(action1)
    await ws_communicator.send_json_to(action2)
    await ws_communicator.wait()

    assert (await get_audit_action_count()) == 2
    assert (await get_audit_rule_count()) == 2
    assert (await get_audit_event_count()) == 2

    for event in await get_audit_events():
        assert await get_audit_event_action_count(event) == 2


job_url_test_data = [
    (
        "run_job_template",
        "55",
        "http://gw/api/controller",
        "http://controller.com/jobs/1/",
        "http://gw/execution/jobs/playbook/55/details/",
    ),
    (
        "run_workflow_template",
        "55",
        "http://gw/api/controller",
        "http://controller.com/jobs/workflow/55/",
        "http://gw/execution/jobs/workflow/55/details/",
    ),
    (
        "run_job_template",
        "55",
        "http://gw/api/controller/",
        "http://controller.com/jobs/1/",
        "http://gw/execution/jobs/playbook/55/details/",
    ),
    (
        "run_workflow_template",
        "55",
        "http://gw/api/controller/",
        "http://controller.com/jobs/workflow/55/",
        "http://gw/execution/jobs/workflow/55/details/",
    ),
    (
        "run_job_template",
        "55",
        "http://controller.com",
        "http://controller.com/jobs/playbook/2/",
        "http://controller.com/#/jobs/playbook/55/details/",
    ),
    (
        "run_workflow_template",
        "55",
        "http://controller.com",
        "http://controller.com/jobs/workflow/2/",
        "http://controller.com/#/jobs/workflow/55/details/",
    ),
    (
        "run_job_template",
        "55",
        "http://controller.com/",
        "http://controller.com/jobs/playbook/2/",
        "http://controller.com/#/jobs/playbook/55/details/",
    ),
    (
        "run_workflow_template",
        "55",
        "http://controller.com/",
        "http://controller.com/jobs/workflow/2/",
        "http://controller.com/#/jobs/workflow/55/details/",
    ),
    (
        "run_workflow_template",
        "",
        "http://controller.com",
        "http://controller.com/jobs/workflow/2/",
        "http://controller.com/jobs/workflow/2/",
    ),
]


@pytest.mark.parametrize(
    "action_type, controller_job_id, api_url, old_url, new_url",
    job_url_test_data,
)
@pytest.mark.django_db(transaction=True)
async def test_controller_job_url(
    ws_communicator: WebsocketCommunicator,
    preseed_credential_types,
    action_type,
    controller_job_id,
    api_url,
    old_url,
    new_url,
    default_organization: models.Organization,
):
    my_aap_inputs = {
        "host": api_url,
        "username": "adam",
        "password": "secret",
        "ssl_verify": "no",
        "oauth_token": "",
    }
    rulebook_process_id = await _prepare_activation_with_controller_info(
        default_organization, my_aap_inputs
    )
    job_instance = await _prepare_job_instance()

    assert (await get_audit_rule_count()) == 0
    payload = create_action_payload(
        DUMMY_UUID,
        rulebook_process_id,
        job_instance.uuid,
        DUMMY_UUID,
        "2023-03-29T15:00:17.260803Z",
        _matching_events(),
        "successful",
        action_type,
        old_url,
        controller_job_id,
    )
    await ws_communicator.send_json_to(payload)
    await ws_communicator.wait()

    assert (await get_audit_action_count()) == 1
    action = await get_audit_action_first()
    assert action.url == new_url


@database_sync_to_async
def get_rulebook_process(instance_id):
    return models.RulebookProcess.objects.get(pk=instance_id)


@database_sync_to_async
def get_activation_by_rulebook_process(instance_id):
    return models.RulebookProcess.objects.get(pk=instance_id).get_parent()


@database_sync_to_async
def get_audit_events():
    return (
        models.AuditEvent.objects.first(),
        models.AuditEvent.objects.last(),
    )


@database_sync_to_async
def get_audit_events_first():
    return models.AuditEvent.objects.first()


@database_sync_to_async
def get_audit_action_first():
    return models.AuditAction.objects.first()


@database_sync_to_async
def get_audit_event_count():
    return models.AuditEvent.objects.count()


@database_sync_to_async
def get_audit_action_count():
    return models.AuditAction.objects.count()


@database_sync_to_async
def get_audit_event_action_count(event):
    return event.audit_actions.count()


@database_sync_to_async
def get_first_audit_rule():
    return models.AuditRule.objects.first()


@database_sync_to_async
def get_audit_rule_count():
    return models.AuditRule.objects.count()


@database_sync_to_async
def get_job_instance_count():
    return models.JobInstance.objects.count()


@database_sync_to_async
def get_activation_instance_job_instance_count():
    return models.ActivationInstanceJobInstance.objects.count()


@database_sync_to_async
def get_job_instance_event_count():
    return models.JobInstanceEvent.objects.count()


@database_sync_to_async
def remove_credential_type(cred_type: models.CredentialType):
    cred_type.delete()


@database_sync_to_async
def _prepare_activation_instance_with_credentials(
    default_organization: models.Organization,
    credentials: list[models.EdaCredential],
    system_vault_credential: models.EdaCredential = None,
):
    project, _ = models.Project.objects.get_or_create(
        name="test-project",
        url="https://github.com/test/project",
        git_hash="92156b2b76c6adb9afbd5688550a621bcc2e5782,",
        organization=default_organization,
    )

    rulebook, _ = models.Rulebook.objects.get_or_create(
        name="test-rulebook",
        rulesets=TEST_RULESETS,
        project=project,
        organization=default_organization,
    )

    decision_environment = models.DecisionEnvironment.objects.create(
        name="de_test_name_1",
        image_url="de_test_image_url",
        description="de_test_description",
        organization=default_organization,
    )

    user = models.User.objects.create_user(
        username="luke.skywalker",
        first_name="Luke",
        last_name="Skywalker",
        email="luke.skywalker@example.com",
        password="secret",
    )
    activation, _ = models.Activation.objects.get_or_create(
        name="test-activation",
        restart_policy=enums.RestartPolicy.ALWAYS,
        rulebook=rulebook,
        project=project,
        user=user,
        decision_environment=decision_environment,
        eda_system_vault_credential=system_vault_credential,
        organization=default_organization,
    )
    activation.eda_credentials.add(*credentials)

    rulebook_process, _ = models.RulebookProcess.objects.get_or_create(
        activation=activation,
        organization=default_organization,
    )

    return rulebook_process.id


@database_sync_to_async
def _prepare_activation_with_controller_info(
    default_organization: models.Organization,
    inputs=AAP_INPUTS,
):
    project, _ = models.Project.objects.get_or_create(
        name="test-project",
        url="https://github.com/test/project",
        git_hash="92156b2b76c6adb9afbd5688550a621bcc2e5782,",
        organization=default_organization,
    )

    rulebook, _ = models.Rulebook.objects.get_or_create(
        name="test-rulebook",
        rulesets=TEST_RULESETS,
        project=project,
        organization=default_organization,
    )

    decision_environment = models.DecisionEnvironment.objects.create(
        name="de_test_name_1",
        image_url="de_test_image_url",
        description="de_test_description",
        organization=default_organization,
    )

    user = models.User.objects.create_user(
        username="luke.skywalker",
        first_name="Luke",
        last_name="Skywalker",
        email="luke.skywalker@example.com",
        password="secret",
    )
    aap_credential_type = models.CredentialType.objects.get(
        name=enums.DefaultCredentialType.AAP
    )

    credential = models.EdaCredential.objects.create(
        name="eda_credential",
        inputs=inputs,
        managed=False,
        credential_type=aap_credential_type,
        organization=default_organization,
    )

    system_credential = _prepare_system_vault_credential(default_organization)

    activation, _ = models.Activation.objects.get_or_create(
        name="test-activation",
        restart_policy=enums.RestartPolicy.ALWAYS,
        rulebook=rulebook,
        project=project,
        user=user,
        decision_environment=decision_environment,
        organization=default_organization,
        eda_system_vault_credential=system_credential,
    )
    activation.eda_credentials.add(credential)

    rulebook_process, _ = models.RulebookProcess.objects.get_or_create(
        activation=activation,
        organization=default_organization,
    )

    return rulebook_process.id


@database_sync_to_async
def _prepare_db_data(
    default_organization: models.Organization, status=ActivationStatus.RUNNING
):
    project, _ = models.Project.objects.get_or_create(
        name="test-project",
        url="https://github.com/test/project",
        git_hash="92156b2b76c6adb9afbd5688550a621bcc2e5782,",
        organization=default_organization,
    )

    rulebook, _ = models.Rulebook.objects.get_or_create(
        name="test-rulebook",
        rulesets=TEST_RULESETS,
        project=project,
        organization=default_organization,
    )

    user = models.User.objects.create_user(
        username="luke.skywalker",
        first_name="Luke",
        last_name="Skywalker",
        email="luke.skywalker@example.com",
        password="secret",
    )

    token = models.AwxToken.objects.get_or_create(
        user=user, name="token", token="XXX"
    )
    decision_environment = models.DecisionEnvironment.objects.create(
        name="de_test_name_1",
        image_url="de_test_image_url",
        description="de_test_description",
        organization=default_organization,
    )

    activation, _ = models.Activation.objects.get_or_create(
        name="test-activation",
        restart_policy=enums.RestartPolicy.ALWAYS,
        extra_var=TEST_EXTRA_VAR,
        rulebook=rulebook,
        project=project,
        user=user,
        decision_environment=decision_environment,
        awx_token=token[0],
        status=status,
        organization=default_organization,
    )

    rulebook_process, _ = models.RulebookProcess.objects.get_or_create(
        activation=activation,
        status=status,
        organization=default_organization,
    )

    return rulebook_process.id


@database_sync_to_async
def _prepare_activation_instance_without_extra_var(
    default_organization: models.Organization,
):
    project = models.Project.objects.create(
        name="test-project-no-extra_var",
        url="https://github.com/test/project",
        git_hash="92156b2b76c6adb9afbd5688550a621bcc2e5782,",
        organization=default_organization,
    )

    rulebook = models.Rulebook.objects.create(
        name="test-rulebook",
        rulesets=TEST_RULESETS,
        project=project,
        organization=default_organization,
    )

    user = models.User.objects.create_user(
        username="luke.skywalker2",
        first_name="Luke",
        last_name="Skywalker2",
        email="luke.skywalker2@example.com",
        password="secret",
    )

    token = models.AwxToken.objects.get_or_create(
        user=user, name="token", token="XXX"
    )
    decision_environment = models.DecisionEnvironment.objects.create(
        name="de_test_name_2",
        image_url="de_test_image_url",
        description="de_test_description",
        organization=default_organization,
    )

    activation = models.Activation.objects.create(
        name="test-activation-no-extra_var",
        restart_policy=enums.RestartPolicy.ALWAYS,
        rulebook=rulebook,
        project=project,
        user=user,
        decision_environment=decision_environment,
        awx_token=token[0],
        organization=default_organization,
    )

    rulebook_process = models.RulebookProcess.objects.create(
        activation=activation,
        organization=default_organization,
    )

    return rulebook_process.id


@database_sync_to_async
def _prepare_activation_instance_no_token(
    default_organization: models.Organization,
):
    project = models.Project.objects.create(
        name="test-project-no-token",
        url="https://github.com/test/project",
        git_hash="92156b2b76c6adb9afbd5688550a621bcc2e5782,",
        organization=default_organization,
    )

    rulebook = models.Rulebook.objects.create(
        name="test-rulebook",
        rulesets=TEST_RULESETS,
        project=project,
        organization=default_organization,
    )

    user = models.User.objects.create_user(
        username="obiwan.kenobi",
        first_name="ObiWan",
        last_name="Kenobi",
        email="obiwan@jedicouncil.com",
        password="secret",
    )

    decision_environment = models.DecisionEnvironment.objects.create(
        name="de_no_token",
        image_url="de_test_image_url",
        description="de_test_description",
        organization=default_organization,
    )

    activation = models.Activation.objects.create(
        name="test-activation-no-token",
        restart_policy=enums.RestartPolicy.ALWAYS,
        rulebook=rulebook,
        project=project,
        user=user,
        decision_environment=decision_environment,
        organization=default_organization,
    )

    rulebook_process = models.RulebookProcess.objects.create(
        activation=activation,
        organization=default_organization,
    )

    return rulebook_process.id


@database_sync_to_async
def _prepare_job_instance():
    job_instance, _ = models.JobInstance.objects.get_or_create(
        uuid="940730a1-8b6f-45f3-84c9-bde8f04390e0",
        action="debug",
        name="test",
        ruleset="test-ruleset",
        rule="test-rule",
        hosts="test-hosts",
    )
    return job_instance


@pytest_asyncio.fixture(scope="function")
async def ws_communicator() -> Generator[WebsocketCommunicator, None, None]:
    communicator = WebsocketCommunicator(
        AnsibleRulebookConsumer.as_asgi(), "ws/"
    )
    connected, _ = await communicator.connect()
    assert connected

    yield communicator
    await communicator.disconnect()


def create_action_payload(
    action_uuid,
    activation_instance_id,
    job_instance_uuid,
    rule_uuid,
    rule_run_at,
    matching_events,
    action_status="successful",
    action_name="run_playbook",
    action_url="https://www.example.com/",
    controller_job_id="55",
):
    return {
        "type": "Action",
        "action": action_name,
        "action_uuid": action_uuid,
        "activation_id": activation_instance_id,
        "job_id": job_instance_uuid,
        "ruleset": "ruleset",
        "rule": "rule",
        "ruleset_uuid": DUMMY_UUID,
        "rule_uuid": rule_uuid,
        "run_at": "2023-03-29T15:00:17.260803Z",
        "rule_run_at": rule_run_at,
        "matching_events": matching_events,
        "status": action_status,
        "message": "Action run successfully",
        "url": action_url,
        "controller_job_id": controller_job_id,
    }


def _matching_events():
    return {
        "m_1": _create_event(7, str(uuid.uuid4())),
        "m_0": _create_event(3, str(uuid.uuid4())),
    }


def _create_event(data, uuid):
    return {
        "meta": {
            "received_at": "2023-03-29T15:00:17.260803Z",
            "source": {
                "name": "my test source",
                "type": "ansible.eda.range",
            },
            "uuid": uuid,
        },
        "i": data,
    }


@pytest.mark.parametrize(
    (
        "credential_type_inputs",
        "credential_type_injectors",
        "credential_inputs",
        "file_contents",
    ),
    [
        (
            {
                "fields": [
                    {"id": "cert", "label": "Certificate", "type": "string"},
                    {"id": "key", "label": "Key", "type": "string"},
                    {"id": "optional", "label": "Optional", "type": "string"},
                ]
            },
            {
                "file": {
                    "template.cert_file": "[mycert]\n{{ cert }}",
                    "template.empty": "",
                    "template.optional": "{{ optional }}",
                },
            },
            {
                "cert": "This is a certificate",
                "key": "This is a key",
                "optional": "",
            },
            [
                {
                    "data": base64.b64encode(
                        "[mycert]\nThis is a certificate".encode()
                    ).decode(),
                    "template_key": "template.cert_file",
                },
            ],
        ),
        (
            {
                "fields": [
                    {"id": "fdata", "label": "File Data", "type": "string"},
                ]
            },
            {
                "file": {
                    "template.myfile": "{{ fdata }}",
                },
            },
            {"fdata": "{'x':[{'name': 'Fred'}]}"},
            [
                {
                    "data": base64.b64encode(
                        "{'x': [{'name': 'Fred'}]}".encode()
                    ).decode(),
                    "template_key": "template.myfile",
                },
            ],
        ),
        (
            {},
            {
                "file": {
                    "template.other_file": "abc",
                },
            },
            {},
            [
                {
                    "data": base64.b64encode("abc".encode()).decode(),
                    "template_key": "template.other_file",
                },
            ],
        ),
        (
            {
                "fields": [
                    {
                        "id": "keytab",
                        "label": "KeyTab",
                        "format": "binary_base64",
                        "secret": True,
                    },
                ]
            },
            {
                "file": {
                    "template.keytab_file": "{{ keytab }}",
                },
            },
            {
                "keytab": base64.b64encode(bytes([1, 2, 3, 4, 5])).decode(),
            },
            [
                {
                    "data": base64.b64encode(bytes([1, 2, 3, 4, 5])).decode(),
                    "template_key": "template.keytab_file",
                    "data_format": "binary",
                },
            ],
        ),
    ],
)
@pytest.mark.django_db(transaction=True)
async def test_handle_workers_with_file_contents(
    ws_communicator: WebsocketCommunicator,
    preseed_credential_types,
    default_organization: models.Organization,
    credential_type_inputs: dict[str, any],
    credential_type_injectors: dict[str, any],
    credential_inputs: dict[str, any],
    file_contents: list[dict[str, any]],
):
    eda_credential = await _prepare_credential(
        credential_type_inputs,
        credential_type_injectors,
        credential_inputs,
        default_organization,
    )

    rulebook_process_id = await _prepare_activation_instance_with_credentials(
        default_organization,
        [eda_credential],
    )

    payload = {
        "type": "Worker",
        "activation_id": rulebook_process_id,
    }
    await ws_communicator.send_json_to(payload)
    check_data = [("Rulebook", None)]
    for fc in file_contents:
        check_data.append(("FileContents", fc))
    check_data.append(("EndOfResponse", None))

    for type, data in check_data:
        response = await ws_communicator.receive_json_from(timeout=TIMEOUT)
        assert response["type"] == type
        if data:
            for key, value in data.items():
                assert response[key] == value


@pytest.mark.django_db(transaction=True)
async def test_handle_workers_with_env_vars(
    ws_communicator: WebsocketCommunicator,
    preseed_credential_types,
    default_organization: models.Organization,
):
    eda_credential = await _prepare_aap_credential_async(default_organization)
    system_credential = await _prepare_system_vault_credential_async(
        default_organization
    )
    rulebook_process_id = await _prepare_activation_instance_with_credentials(
        default_organization,
        [eda_credential],
        system_credential,
    )

    payload = {
        "type": "Worker",
        "activation_id": rulebook_process_id,
    }
    await ws_communicator.send_json_to(payload)

    for type in [
        "Rulebook",
        "ControllerInfo",
        "VaultCollection",
        "EnvVars",
        "EndOfResponse",
    ]:
        response = await ws_communicator.receive_json_from(timeout=TIMEOUT)
        assert response["type"] == type
        if type == "EnvVars":
            assert response["data"].startswith("QUFQX0hPU1ROQU1FOiBodHRwczovL")


@pytest.mark.django_db(transaction=True)
async def test_receive_object_not_exist(
    ws_communicator: WebsocketCommunicator,
    default_organization: models.Organization,
):
    # Use invalid activation_id to trigger ObjectDoesNotExist
    payload = {
        "type": "Job",
        "job_id": "940730a1-8b6f-45f3-84c9-bde8f04390e0",
        "ansible_rulebook_id": 100000000,
        "name": "ansible.eda.hello",
        "ruleset": "ruleset",
        "rule": "rule",
        "hosts": "hosts",
        "action": "run_playbook",
    }
    await ws_communicator.send_json_to(payload)
    await ws_communicator.wait()


@pytest.mark.django_db(transaction=True)
async def test_insert_audit_rule_invalid_activation(
    ws_communicator: WebsocketCommunicator,
    default_organization: models.Organization,
    eda_caplog,
):
    await _prepare_db_data(default_organization)

    # Test with invalid activation ID
    invalid_activation_id = 100000000
    job_uuid = "940730a1-8b6f-45f3-84c9-bde8f04390e0"

    payload = create_action_payload(
        str(uuid.uuid4()),
        invalid_activation_id,
        job_uuid,
        str(uuid.uuid4()),
        datetime.now().isoformat(),
        _matching_events(),
    )

    initial_audit_count = await get_audit_rule_count()

    with patch(
        "aap_eda.wsapi.consumers.AnsibleRulebookConsumer._set_log_tracking_id"
    ):
        await ws_communicator.send_json_to(payload)
        await ws_communicator.wait()

        # Verify no audit records created and error is logged
        assert await get_audit_rule_count() == initial_audit_count
        assert "RulebookProcess 100000000 not found" in eda_caplog.text


@pytest.mark.django_db(transaction=True)
async def test_get_activation_with_exception(
    ws_communicator: WebsocketCommunicator,
    eda_caplog,
):
    consumer = AnsibleRulebookConsumer()

    invalid_uuid = "100000000"
    with pytest.raises(ObjectDoesNotExist):
        await consumer.get_activation(invalid_uuid)

    assert "RulebookProcess 100000000 not found" in eda_caplog.text


@pytest.mark.django_db(transaction=True)
async def test_get_controller_info_from_aap_cred(
    ws_communicator: WebsocketCommunicator,
    default_organization: models.Organization,
    preseed_credential_types,
    caplog_factory,
):
    eda_caplog = caplog_factory(logger, logging.DEBUG)
    eda_credential = await _prepare_aap_credential_async(default_organization)
    rulebook_process_id = await _prepare_activation_instance_with_credentials(
        default_organization,
        [eda_credential],
    )
    activation = await get_activation_by_rulebook_process(rulebook_process_id)

    consumer = AnsibleRulebookConsumer()
    result = await consumer.get_controller_info_from_aap_cred(activation)
    assert result.url == "https://controller_url/"
    assert result.username == "adam"

    await remove_credential_type(eda_credential.credential_type)
    result = await consumer.get_controller_info_from_aap_cred(activation)
    assert result is None
    assert '"AAP" credential type not found' in eda_caplog.text


@database_sync_to_async
def _prepare_credential(
    credential_type_inputs: dict,
    credential_type_injectors: dict,
    credential_inputs: dict,
    default_organization: models.Organization,
) -> models.EdaCredential:
    credential_type = models.CredentialType.objects.create(
        name="sample_credential_type",
        inputs=credential_type_inputs,
        injectors=credential_type_injectors,
    )

    return models.EdaCredential.objects.create(
        name="sample_eda_credential",
        inputs=credential_inputs,
        managed=False,
        credential_type=credential_type,
        organization=default_organization,
    )


@database_sync_to_async
def _prepare_aap_credential_async(
    organization: models.Organization,
):
    return _prepare_aap_credential(organization)


def _prepare_aap_credential(
    organization: models.Organization,
) -> models.EdaCredential:
    aap_credential_type = models.CredentialType.objects.get(
        name=enums.DefaultCredentialType.AAP
    )

    data = "secret"
    return models.EdaCredential.objects.create(
        name="eda_aap_credential",
        inputs={
            "host": "https://controller_url/",
            "username": "adam",
            "password": data,
        },
        credential_type=aap_credential_type,
        organization=organization,
    )


@database_sync_to_async
def _prepare_system_vault_credential_async(
    organization: models.Organization,
) -> models.EdaCredential:
    return _prepare_system_vault_credential(organization)


def _prepare_system_vault_credential(
    organization: models.Organization,
) -> models.EdaCredential:
    vault_credential_type = models.CredentialType.objects.get(
        name=enums.DefaultCredentialType.VAULT
    )

    return models.EdaCredential.objects.create(
        name="eda_system_credential",
        inputs={"vault_id": "adam", "vault_password": "secret"},
        managed=False,
        credential_type=vault_credential_type,
        organization=organization,
    )
