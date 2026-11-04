# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""SMTP library unit tests"""

import importlib
import itertools
import json
import secrets
from ast import literal_eval

import ops
import pydantic
import pytest
from charms.smtp_integrator.v0 import smtp
from charms.smtp_integrator.v0.smtp import SmtpRequires
from ops.testing import Harness

from lib.charms.smtp_integrator.v0.smtp import parse_recipients

REQUIRER_METADATA = """
name: smtp-consumer
requires:
  smtp:
    interface: smtp
  smtp-legacy:
    interface: smtp
"""

PROVIDER_METADATA = """
name: smtp-producer
provides:
  smtp:
    interface: smtp
  smtp-legacy:
    interface: smtp
"""

RELATION_DATA = {
    "host": "example.smtp",
    "port": "25",
    "user": "example_user",
    "auth_type": "plain",
    "transport_security": "tls",
    "domain": "domain",
    "skip_ssl_verify": "False",
}

SAMPLE_LEGACY_RELATION_DATA = {
    **RELATION_DATA,
    "password": secrets.token_hex(),
}

SAMPLE_RELATION_DATA = {
    "host": "example.smtp",
    "port": "25",
    "user": "example_user",
    "auth_type": "none",
    "transport_security": "none",
    "domain": "domain",
    "skip_ssl_verify": "False",
}

MINIMAL_EMAILS = {
    "smtp_sender": "no-reply@example.com",
    "recipients": '["a@x.com", "b@y.com"]',
}

MINIMAL_EMAILS_TRIMMED_EXPECTED = ["a@x.com", "b@y.com"]


class SmtpRequirerCharm(ops.CharmBase):
    """Class for requirer charm testing."""

    def __init__(self, *args):
        """Init method for the class.

        Args:
            args: Variable list of positional arguments passed to the parent constructor.
        """
        super().__init__(*args)
        self.smtp = smtp.SmtpRequires(self)
        self.smtp_legacy = smtp.SmtpRequires(self, relation_name=smtp.LEGACY_RELATION_NAME)
        self.events = []
        self.framework.observe(self.smtp.on.smtp_data_available, self._record_event)
        self.framework.observe(self.smtp_legacy.on.smtp_data_available, self._record_event)

    def _record_event(self, event: ops.EventBase) -> None:
        """Record emitted event in the event list.

        Args:
            event: event.
        """
        self.events.append(event)


class SmtpProviderCharm(ops.CharmBase):
    """Class for provider charm testing."""

    def __init__(self, *args):
        """Init method for the class.

        Args:
            args: Variable list of positional arguments passed to the parent constructor.
        """
        super().__init__(*args)
        self.smtp = smtp.SmtpProvides(self)
        self.smtp_legacy = smtp.SmtpProvides(self, relation_name=smtp.LEGACY_RELATION_NAME)
        self.events = []
        self.framework.observe(self.on.smtp_relation_changed, self._record_event)
        self.framework.observe(self.on.smtp_legacy_relation_changed, self._record_event)

    def _record_event(self, event: ops.EventBase) -> None:
        """Record emitted event in the event list.

        Args:
            event: event.
        """
        self.events.append(event)


def test_smtp_provider_update_relation_data():
    """
    arrange: instantiate a SmtpProviderCharm object and add an smtp-legacy relation.
    act: update the relation data.
    assert: the relation data is updated.
    """
    harness = Harness(SmtpProviderCharm, meta=PROVIDER_METADATA)
    harness.begin()
    harness.set_leader(True)
    harness.add_relation("smtp-legacy", "smtp-provider")
    relation = harness.model.get_relation("smtp-legacy")
    smtp_data = smtp.SmtpRelationData(
        host="example.smtp",
        port=25,
        auth_type="plain",
        transport_security="tls",
        skip_ssl_verify=False,
    )
    harness.charm.smtp_legacy.update_relation_data(relation, smtp_data)
    data = relation.data[harness.model.app]
    assert data["host"] == smtp_data.host
    assert data["port"] == str(smtp_data.port)
    assert data["auth_type"] == smtp_data.auth_type
    assert data["transport_security"] == smtp_data.transport_security
    assert data["skip_ssl_verify"] == str(smtp_data.skip_ssl_verify)


def test_smtp_relation_data_to_relation_data():
    """
    arrange: instantiate a SmtpRelationData object.
    act: obtain the relation representation.
    assert: the relation representation is correct.
    """
    smtp_data = smtp.SmtpRelationData(
        host="example.smtp",
        port=25,
        user="example_user",
        password=secrets.token_hex(),
        password_id=secrets.token_hex(),
        auth_type="plain",
        transport_security="tls",
        domain="domain",
        skip_ssl_verify=False,
    )
    relation_data = smtp_data.to_relation_data()
    expected_relation_data = {
        "host": "example.smtp",
        "port": "25",
        "user": "example_user",
        "password_id": smtp_data.password_id,
        "auth_type": "plain",
        "transport_security": "tls",
        "domain": "domain",
        "skip_ssl_verify": "False",
    }
    assert relation_data == expected_relation_data


def test_legacy_requirer_charm_does_not_emit_event_id_when_no_data():
    """
    arrange: set up a charm with no relation data to be populated.
    act: add an smtp-legacy relation.
    assert: no events are emitted.
    """
    harness = Harness(SmtpRequirerCharm, meta=REQUIRER_METADATA)
    harness.begin()
    harness.set_leader(True)
    harness.add_relation("smtp-legacy", "smtp-provider")
    relation = harness.charm.framework.model.get_relation("smtp-legacy", 0)
    harness.charm.on.smtp_legacy_relation_changed.emit(relation)
    assert len(harness.charm.events) == 0


def test_requirer_charm_does_not_emit_event_id_when_no_data():
    """
    arrange: set up a charm with no relation data to be populated.
    act: add an smtp relation.
    assert: no SmtpDataAvailable events are emitted.
    """
    harness = Harness(SmtpRequirerCharm, meta=REQUIRER_METADATA)
    harness.begin()
    harness.set_leader(True)
    harness.add_relation("smtp", "smtp-provider")
    relation = harness.charm.framework.model.get_relation("smtp", 0)
    harness.charm.on.smtp_legacy_relation_changed.emit(relation)
    assert len(harness.charm.events) == 0


@pytest.mark.parametrize("is_leader", [True, False])
def test_legacy_requirer_charm_with_valid_relation_data_emits_event(is_leader):
    """
    arrange: set up a charm.
    act: add an smtp-legacy relation.
    assert: an SmtpDataAvailable event containing the relation data is emitted.
    """
    harness = Harness(SmtpRequirerCharm, meta=REQUIRER_METADATA)
    harness.begin()
    harness.set_leader(is_leader)
    harness.add_relation("smtp-legacy", "smtp-provider", app_data=SAMPLE_LEGACY_RELATION_DATA)

    assert len(harness.charm.events) == 1
    assert harness.charm.events[0].host == SAMPLE_LEGACY_RELATION_DATA["host"]
    assert harness.charm.events[0].port == int(SAMPLE_LEGACY_RELATION_DATA["port"])
    assert harness.charm.events[0].user == SAMPLE_LEGACY_RELATION_DATA["user"]
    assert harness.charm.events[0].password == SAMPLE_LEGACY_RELATION_DATA["password"]
    assert harness.charm.events[0].auth_type == SAMPLE_LEGACY_RELATION_DATA["auth_type"]
    assert (
        harness.charm.events[0].transport_security
        == SAMPLE_LEGACY_RELATION_DATA["transport_security"]
    )
    assert harness.charm.events[0].domain == SAMPLE_LEGACY_RELATION_DATA["domain"]
    assert harness.charm.events[0].skip_ssl_verify == literal_eval(
        SAMPLE_LEGACY_RELATION_DATA["skip_ssl_verify"]
    )

    retrieved_relation_data = harness.charm.smtp_legacy.get_relation_data()
    assert retrieved_relation_data.host == SAMPLE_LEGACY_RELATION_DATA["host"]
    assert retrieved_relation_data.port == int(SAMPLE_LEGACY_RELATION_DATA["port"])
    assert retrieved_relation_data.user == SAMPLE_LEGACY_RELATION_DATA["user"]
    assert retrieved_relation_data.password == SAMPLE_LEGACY_RELATION_DATA["password"]
    assert retrieved_relation_data.auth_type == SAMPLE_LEGACY_RELATION_DATA["auth_type"]
    assert (
        retrieved_relation_data.transport_security
        == SAMPLE_LEGACY_RELATION_DATA["transport_security"]
    )
    assert retrieved_relation_data.domain == SAMPLE_LEGACY_RELATION_DATA["domain"]
    assert retrieved_relation_data.skip_ssl_verify == literal_eval(
        SAMPLE_LEGACY_RELATION_DATA["skip_ssl_verify"]
    )


@pytest.mark.parametrize("is_leader", [True, False])
def test_requirer_charm_with_valid_relation_data_emits_event(is_leader):
    """
    arrange: set up a charm.
    act: add an smtp relation.
    assert: an SmtpDataAvailable event containing the relation data is emitted.
    """
    harness = Harness(SmtpRequirerCharm, meta=REQUIRER_METADATA)
    harness.begin()
    harness.set_leader(is_leader)

    password = secrets.token_hex()
    secret_id = harness.add_user_secret({"password": password})
    harness.grant_secret(secret_id, "smtp-consumer")
    SAMPLE_RELATION_DATA["password_id"] = secret_id
    harness.add_relation("smtp", "smtp-provider", app_data=SAMPLE_RELATION_DATA)
    relation_data = harness.charm.smtp.get_relation_data()

    assert relation_data
    assert relation_data.host == SAMPLE_RELATION_DATA["host"]
    assert relation_data.port == int(SAMPLE_RELATION_DATA["port"])
    assert relation_data.user == SAMPLE_RELATION_DATA["user"]
    assert relation_data.password_id == SAMPLE_RELATION_DATA["password_id"]
    assert relation_data.password == password
    assert relation_data.auth_type == SAMPLE_RELATION_DATA["auth_type"]
    assert relation_data.transport_security == SAMPLE_RELATION_DATA["transport_security"]
    assert relation_data.domain == SAMPLE_RELATION_DATA["domain"]
    assert relation_data.skip_ssl_verify == literal_eval(SAMPLE_RELATION_DATA["skip_ssl_verify"])


@pytest.mark.parametrize("is_leader", [True, False])
def test_requirer_charm_with_invalid_relation_data_doesnt_emit_event(is_leader):
    """
    arrange: set up a charm.
    act: add an smtp-legacy relation changed event with invalid data.
    assert: an SmtpDataAvailable event is not emitted.
    """
    relation_data = {
        "port": "25",
        "user": "example_user",
        "password": "somepassword",  # nosec
        "auth_type": "plain",
        "transport_security": "tls",
        "domain": "domain",
        "skip_ssl_verify": "False",
    }

    harness = Harness(SmtpRequirerCharm, meta=REQUIRER_METADATA)
    harness.begin()
    harness.set_leader(is_leader)
    harness.add_relation("smtp-legacy", "smtp-provider", app_data=relation_data)

    assert len(harness.charm.events) == 0


def test_requirer_charm_get_relation_data_without_relation_data():
    """
    arrange: set up a charm with smtp relation without any relation data.
    act: call get_relation_data function.
    assert: get_relation_data should return None.
    """
    harness = Harness(SmtpRequirerCharm, meta=REQUIRER_METADATA)
    harness.begin()
    harness.set_leader(True)
    harness.add_relation("smtp", "smtp-provider", app_data={})
    assert harness.charm.smtp.get_relation_data() is None


@pytest.mark.parametrize(
    "left,right,result",
    [
        *[
            list(left_and_right) + [True]
            for left_and_right in itertools.permutations(
                [
                    "secret://d41591b7-fa4d-4b2b-8ae2-d6015d5677da/d2rhncfmp25c765918hg",
                    "secret:d41591b7-fa4d-4b2b-8ae2-d6015d5677da/d2rhncfmp25c765918hg",
                    "secret://d2rhncfmp25c765918hg",
                    "secret:d2rhncfmp25c765918hg",
                    "d2rhncfmp25c765918hg",
                ],
                2,
            )
        ],
        *[
            list(left_and_right) + [False]
            for left_and_right in itertools.product(
                [
                    "secret://d41591b7-fa4d-4b2b-8ae2-d6015d5677da/d2rhncfmp25c765918hg",
                    "secret:d41591b7-fa4d-4b2b-8ae2-d6015d5677da/d2rhncfmp25c765918hg",
                    "secret://d2rhncfmp25c765918hg",
                    "secret:d2rhncfmp25c765918hg",
                    "d2rhncfmp25c765918hg",
                ],
                [
                    "secret://d41591b7-fa4d-4b2b-8ae2-d6015d5677da/d3rhncfmp25c765918hg",
                    "secret:d41591b7-fa4d-4b2b-8ae2-d6015d5677da/d3rhncfmp25c765918hg",
                    "secret://d3rhncfmp25c765918hg",
                    "secret:d3rhncfmp25c765918hg",
                    "d3rhncfmp25c765918hg",
                ],
            )
        ],
        *[
            list(left_and_right) + [False]
            for left_and_right in itertools.product(
                [
                    "secret://d41591b7-fa4d-4b2b-8ae2-d6015d5677da/d2rhncfmp25c765918hg",
                    "secret:d41591b7-fa4d-4b2b-8ae2-d6015d5677da/d2rhncfmp25c765918hg",
                ],
                [
                    "secret://d41591b7-fa4d-4b2b-8ae2-d6015d5677db/d2rhncfmp25c765918hg",
                    "secret:d41591b7-fa4d-4b2b-8ae2-d6015d5677db/d2rhncfmp25c765918hg",
                ],
            )
        ],
    ],
)
def test_secret_uri_equal(left: str, right: str, result: bool):
    """
    arrange: none.
    act: call _secret_uri_equal function with different input.
    assert: _secret_uri_equal function should return True if the two input are the same secret.
    """
    # pylint: disable=protected-access
    assert result == SmtpRequires._secret_uri_equal(left=left, right=right)
    # pylint: disable=protected-access
    assert result == SmtpRequires._secret_uri_equal(left=right, right=left)


def test_requirer_charm_receive_event_on_secret_changed():
    """
    arrange: relate the smtp-consumer charm with three provider charm.
    act: change secret content in the provider relation data.
    assert: event should raise for the relation containing the changed secret.
    """
    harness = Harness(SmtpRequirerCharm, meta=REQUIRER_METADATA)
    harness.begin()
    harness.set_leader(True)
    secret1 = harness.add_model_secret(
        "smtp-provider-one", content={"password": "".join(["secret", "1.1"])}
    )
    secret2 = harness.add_model_secret(
        "smtp-provider-two", content={"password": "".join(["secret", "2.1"])}
    )
    relation_id1 = harness.add_relation("smtp", "smtp-provider-one")
    relation_id2 = harness.add_relation("smtp", "smtp-provider-two")
    harness.grant_secret(secret_id=secret1, observer="smtp-consumer")
    harness.grant_secret(secret_id=secret2, observer="smtp-consumer")
    harness.update_relation_data(
        relation_id1,
        "smtp-provider-one",
        {
            "host": "1.example.smtp",
            "port": "25",
            "user": "example_user",
            "password_id": secret1,
            "auth_type": "plain",
            "transport_security": "tls",
            "domain": "domain",
            "skip_ssl_verify": "False",
        },
    )
    harness.update_relation_data(
        relation_id2,
        "smtp-provider-two",
        {
            "host": "2.example.smtp",
            "port": "25",
            "user": "example_user",
            "password_id": secret2,
            "auth_type": "plain",
            "transport_security": "tls",
            "domain": "domain",
            "skip_ssl_verify": "False",
        },
    )
    harness.add_relation(
        "smtp",
        "smtp-provider-three",
        app_data={
            "host": "example.smtp",
            "port": "25",
            "user": "example_user",
            "auth_type": "none",
            "transport_security": "none",
            "domain": "domain",
            "skip_ssl_verify": "False",
        },
    )
    assert len(harness.charm.events) == 3
    harness.set_secret_content(secret1, {"password": "".join(["secret", "1.2"])})
    assert len(harness.charm.events) == 4
    assert harness.charm.events[-1].relation.app.name == "smtp-provider-one"
    assert harness.charm.events[-1].relation.id == relation_id1
    harness.set_secret_content(secret2, {"password": "".join(["secret", "2.2"])})
    assert len(harness.charm.events) == 5
    assert harness.charm.events[-1].relation.app.name == "smtp-provider-two"
    assert harness.charm.events[-1].relation.id == relation_id2


def test_relation_data_accepts_sender_and_recipients_json():
    """
    arrange: valid smtp_sender and recipients JSON list.
    act: build SmtpRelationData.
    assert: data is accepted and email fields are present.
    """
    data = smtp.SmtpRelationData(
        host="example.smtp",
        port=25,
        auth_type="plain",
        transport_security="tls",
        skip_ssl_verify=False,
        smtp_sender="no-reply@example.com",
        recipients='["a@x.com", "b@y.com"]',
    )
    assert str(data.smtp_sender) == "no-reply@example.com"
    assert [str(x) for x in (data.recipients or [])] == ["a@x.com", "b@y.com"]


@pytest.mark.parametrize("bad_sender", ["not-an-email", "a@b", "a@b..com"])
def test_relation_data_rejects_invalid_sender_email(bad_sender):
    """
    arrange: invalid smtp_sender.
    act: build SmtpRelationData.
    assert: ValidationError is raised.
    """
    with pytest.raises(pydantic.ValidationError):
        smtp.SmtpRelationData(
            host="example.smtp",
            port=25,
            auth_type="plain",
            transport_security="tls",
            skip_ssl_verify=False,
            smtp_sender=bad_sender,
        )


@pytest.mark.parametrize("bad_recipient", ["not-json", "{", '"a@x.com"', "123"])
def test_relation_data_rejects_invalid_recipients_string(bad_recipient):
    """
    arrange: recipients not a valid JSON list string.
    act: build SmtpRelationData.
    assert: ValidationError is raised.
    """
    with pytest.raises(pydantic.ValidationError):
        smtp.SmtpRelationData(
            host="example.smtp",
            port=25,
            auth_type="plain",
            transport_security="tls",
            skip_ssl_verify=False,
            recipients=bad_recipient,
        )


def test_relation_data_rejects_recipients_json_that_is_not_list():
    """
    arrange: recipients JSON decodes but does not produce a list.
    act: build SmtpRelationData.
    assert: ValidationError is raised.
    """
    with pytest.raises(pydantic.ValidationError):
        smtp.SmtpRelationData(
            host="example.smtp",
            port=25,
            auth_type="plain",
            transport_security="tls",
            skip_ssl_verify=False,
            recipients='{"a": "b"}',
        )


def test_relation_data_rejects_recipients_with_invalid_email():
    """
    arrange: recipients list contains an invalid email.
    act: build SmtpRelationData.
    assert: ValidationError is raised.
    """
    with pytest.raises(pydantic.ValidationError):
        smtp.SmtpRelationData(
            host="example.smtp",
            port=25,
            auth_type="plain",
            transport_security="tls",
            skip_ssl_verify=False,
            recipients='["a@x.com", "not-an-email"]',
        )


def test_to_relation_data_publishes_sender_and_recipients():
    """
    arrange: SmtpRelationData with smtp_sender and recipients.
    act: call to_relation_data().
    assert: smtp_sender is present and recipients is JSON encoded list.
    """
    data = smtp.SmtpRelationData(
        host="example.smtp",
        port=25,
        auth_type="plain",
        transport_security="tls",
        skip_ssl_verify=False,
        smtp_sender="no-reply@example.com",
        recipients='["a@x.com", "b@y.com"]',
    )
    relation = data.to_relation_data()
    assert relation["smtp_sender"] == "no-reply@example.com"
    assert json.loads(relation["recipients"]) == ["a@x.com", "b@y.com"]


def test_to_relation_data_does_not_publish_sender_or_recipients_when_unset():
    """
    arrange: SmtpRelationData without smtp_sender/recipients.
    act: call to_relation_data().
    assert: smtp_sender and recipients keys are omitted.
    """
    data = smtp.SmtpRelationData(
        host="example.smtp",
        port=25,
        auth_type="plain",
        transport_security="tls",
        skip_ssl_verify=False,
    )
    relation = data.to_relation_data()
    assert "smtp_sender" not in relation
    assert "recipients" not in relation


def test_legacy_requirer_event_includes_sender_and_recipients_when_present():
    """
    arrange: legacy relation has smtp_sender and recipients JSON.
    act: add smtp-legacy relation with those fields.
    assert: emitted event exposes smtp_sender and recipients list.
    """
    harness = Harness(SmtpRequirerCharm, meta=REQUIRER_METADATA)
    harness.begin()
    harness.set_leader(True)

    data = {
        **SAMPLE_LEGACY_RELATION_DATA,
        "smtp_sender": "no-reply@example.com",
        "recipients": '["a@x.com", "b@y.com"]',
    }
    harness.add_relation("smtp-legacy", "smtp-provider", app_data=data)

    assert len(harness.charm.events) == 1
    event = harness.charm.events[0]
    assert event.smtp_sender == "no-reply@example.com"
    assert event.recipients == ["a@x.com", "b@y.com"]


def test_event_sender_and_recipients_are_none_when_unset():
    """
    arrange: relation data does not include smtp_sender or recipients.
    act: add smtp-legacy relation.
    assert: properties return None.
    """
    harness = Harness(SmtpRequirerCharm, meta=REQUIRER_METADATA)
    harness.begin()
    harness.set_leader(True)

    harness.add_relation("smtp-legacy", "smtp-provider", app_data=SAMPLE_LEGACY_RELATION_DATA)
    event = harness.charm.events[0]
    assert event.smtp_sender is None
    assert event.recipients == []


def test_get_relation_data_raises_secret_error_when_secret_missing(monkeypatch):
    """
    arrange: Relation data includes a password_id that does not exist.
    act: Attempt to read relation data via get_relation_data_from_relation().
    assert: SecretError is raised.
    """
    harness = Harness(SmtpRequirerCharm, meta=REQUIRER_METADATA)
    harness.begin()
    harness.set_leader(True)

    rel_id = harness.add_relation("smtp", "smtp-provider")
    relation = harness.model.get_relation("smtp", rel_id)
    assert relation and relation.app

    relation.data[relation.app].update({**RELATION_DATA, "password_id": "missing"})  # nosec B105

    def raise_model_error(*, id: str):  # pylint: disable=redefined-builtin
        """Simulate Juju raising ModelError when a secret cannot be read.

        Args:
            id: Secret ID requested.

        Raises:
            ModelError: Always.
        """
        raise ops.model.ModelError("nope")

    monkeypatch.setattr(harness.model, "get_secret", raise_model_error)

    with pytest.raises(smtp.SecretError):
        harness.charm.smtp.get_relation_data_from_relation(relation)


def test_relation_data_rejects_broken_json_list_string():
    """
    arrange: recipients field contains an invalid JSON string.
    act: build SmtpRelationData with the broken recipients value.
    assert: ValidationError is raised.
    """
    with pytest.raises(pydantic.ValidationError):
        smtp.SmtpRelationData(
            host="example.smtp",
            port=25,
            auth_type="plain",
            transport_security="tls",
            skip_ssl_verify=False,
            recipients="[",
        )


def test_parse_recipients_none_and_empty_then_returns_empty_list():
    """
    arrange: raw recipients value is None/empty/whitespace.
    act: call parse_recipients with None/empty inputs.
    assert: returns an empty list.
    """
    assert parse_recipients(None) == []
    assert parse_recipients("") == []
    assert parse_recipients("   ") == []


def test_parse_recipients_when_comma_separated_and_single_input_then_return_list():
    """
    arrange: raw recipients value is a single email or comma-separated emails.
    act: call parse_recipients with comma-separated and single inputs.
    assert: returns a list of trimmed email strings.
    """
    assert parse_recipients("a@x.com") == ["a@x.com"]
    assert parse_recipients("a@x.com,b@y.com") == ["a@x.com", "b@y.com"]
    assert parse_recipients("a@x.com, b@y.com") == ["a@x.com", "b@y.com"]


def test_parse_recipients_when_json_list_string_input_then_return_list():
    """
    arrange: raw recipients value is a JSON list string.
    act: call parse_recipients with a JSON list string input.
    assert: returns the parsed list of email strings.
    """
    assert parse_recipients('["a@x.com", "b@y.com"]') == ["a@x.com", "b@y.com"]


def test_parse_recipients_when_bracketless_json_items_string_input_then_return_list():
    """
    arrange: raw recipients value is a bracketless JSON items string.
    act: call parse_recipients with '"a@x.com", "b@y.com"'.
    assert: returns a list of email strings.
    """
    assert parse_recipients('"a@x.com", "b@y.com"') == ["a@x.com", "b@y.com"]


def test_smtp_module_imports_without_field_validator(monkeypatch):
    """
    arrange: simulate pydantic v1 where field_validator does not exist.
    act: reload smtp module.
    assert: module reload succeeds (v1 fallback path is selected).
    """

    class _FakePydantic:  # noqa: DCO060
        """Minimal pydantic stub missing field_validator

        Attributes:
            BaseModel: Minimal BaseModel placeholder.
            EmailStr: Minimal EmailStr placeholder.
        """

        BaseModel = object
        EmailStr = str

        @staticmethod
        def Field(*_args, **_kwargs):  # noqa: N802 pylint: disable=invalid-name
            """Return a placeholder Field value.

            Returns:
                None: Placeholder value for pydantic Field().
            """
            return None

        class ValidationError(Exception):
            """Minimal ValidationError placeholder."""

            def errors(self):
                """Return empty structured errors.

                Returns:
                    list: Empty list of error dicts (pydantic-like shape).
                """
                return []

        @staticmethod
        def validator(*_args, **_kwargs):
            """Return a decorator that leaves the function unchanged.

            Returns:
                callable: A decorator function.
            """

            def decorator(fn):
                """Return the original function unchanged.

                Args:
                    fn: Function to decorate.

                Returns:
                    Any: The original function.
                """
                return fn

            return decorator

        @staticmethod
        def root_validator(*_args, **_kwargs):
            """Return a decorator that leaves the function unchanged.

            Returns:
                callable: A decorator function.
            """

            def decorator(fn):
                """Return the original function unchanged.

                Args:
                    fn: Function to decorate.

                Returns:
                    Any: The original function.
                """
                return fn

            return decorator

    monkeypatch.setattr(smtp, "pydantic", _FakePydantic(), raising=False)

    # smtp.py should choose v1 validators when field_validator isn't available
    importlib.reload(smtp)

    # parse_recipients still exists after reload
    assert callable(smtp.parse_recipients)
