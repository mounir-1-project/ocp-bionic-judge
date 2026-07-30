"""Tests de sécurité de session et du canal email complémentaire."""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from src.notifications import EmailNotifier
from src.security import AuthManager, TooManyAttemptsError, hash_password


def test_session_opaque_csrf_et_invalidation():
    password_hash = hash_password("phrase secrete industrielle 2026")
    manager = AuthManager(
        password_hash=password_hash,
        idle_timeout_s=60,
        absolute_timeout_s=120,
        allowed_emails={"tech@example.test"},
        user_roles={"tech@example.test": "maintenance"},
    )

    assert manager.authenticate("tech@example.test", "incorrect", "127.0.0.1") is None
    result = manager.authenticate(
        "tech@example.test",
        "phrase secrete industrielle 2026",
        "127.0.0.1",
    )
    assert result is not None
    token, session = result
    assert len(token) >= 32
    assert session.csrf_token
    assert session.email == "tech@example.test"
    assert session.username == "tech"
    assert session.role == "maintenance"
    assert manager.validate(token) is session

    replacement = manager.rotate(token)
    assert replacement is not None
    new_token, new_session = replacement
    assert new_token != token
    assert manager.validate(token) is None
    assert manager.validate(new_token) is new_session

    manager.destroy(new_token)
    assert manager.validate(new_token) is None
    assert [event["event"] for event in manager.audit_events()] == [
        "LOGIN_FAILED", "LOGIN_SUCCEEDED",
    ]


def test_allowlist_et_limitation_des_tentatives():
    manager = AuthManager(
        password_hash=hash_password("phrase secrete industrielle 2026"),
        allowed_emails={"autorise@example.test"},
    )
    assert manager.authenticate(
        "intrus@example.test", "phrase secrete industrielle 2026", "client-a"
    ) is None
    for _ in range(4):
        assert manager.authenticate(
            "autorise@example.test", "mauvais-secret", "client-a"
        ) is None
    with pytest.raises(TooManyAttemptsError):
        manager.authenticate(
            "autorise@example.test", "phrase secrete industrielle 2026", "client-a"
        )


def test_notification_asynchrone_et_deduplication(monkeypatch):
    sent: list[str] = []
    notifier = EmailNotifier(
        host="smtp.example.test",
        port=587,
        username=None,
        password=None,
        sender="e7301@example.test",
        recipient=None,
        starttls=True,
        cooldown_minutes=60,
        minimum_severity="WARNING",
    )
    assert notifier.enabled is False
    notifier.set_recipient("shift@example.test")
    assert notifier.enabled is True
    monkeypatch.setattr(notifier, "_send", lambda job: sent.append(job.subject))

    analysis = SimpleNamespace(
        decision=SimpleNamespace(
            severity="CRITICAL",
            amdec_modes=["FAISCEAU_BOUCHAGE"],
            timestamp="2024-10-25T21:00:00",
            diagnosis="Déficit thermique persistant",
            recommended_action=SimpleNamespace(
                description="Confirmer sur le terrain",
                urgency="IMMEDIATE",
            ),
        ),
        verdict=SimpleNamespace(global_score=9.2, agreement=True),
    )
    analysis.verdict.agreement = False
    notifier.notify(analysis)
    assert sent == []
    analysis.verdict.agreement = True
    notifier.notify(analysis)
    notifier.notify(analysis)
    limit = time.monotonic() + 1
    while not sent and time.monotonic() < limit:
        time.sleep(0.01)
    notifier.stop()

    assert sent == ["[E7301][CRITICAL] FAISCEAU_BOUCHAGE"]


def test_destinataires_concurrents_ne_secrasent_pas():
    notifier = EmailNotifier(
        host="smtp.example.test",
        port=587,
        username=None,
        password=None,
        sender="e7301@example.test",
        recipient="astreinte@example.test",
        starttls=True,
        cooldown_minutes=60,
        minimum_severity="CRITICAL",
    )
    notifier.add_recipient("quart-a@example.test")
    notifier.add_recipient("quart-b@example.test")
    assert notifier.status()["active_recipients"] == 3
    notifier.remove_recipient("quart-a@example.test")
    assert notifier.status()["active_recipients"] == 2
    notifier.remove_recipient("astreinte@example.test")
    # Le destinataire d'astreinte configuré reste toujours abonné.
    assert notifier.status()["active_recipients"] == 2
    notifier.stop()
