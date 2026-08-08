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
    # L'EGALITE PORTAIT SUR LE JOURNAL ENTIER, APRES UNE ROTATION ET UNE
    # DESTRUCTION. Elle gelait donc l'ABSENCE de toute trace pour ces deux
    # operations : ajouter une ligne de deconnexion cassait ce test, avec un
    # message qui n'en disait pas la raison. Or `auth.py` n'a qu'un seul
    # `self._audit.append`, appele depuis `authenticate` — c'est un constat,
    # pas une intention verifiee (SEC-3, laisse ouvert).
    # L'exactitude est conservee sur ce que le test dit examiner : les deux
    # issues d'authentification, dans l'ordre.
    authentification = [
        e["event"] for e in manager.audit_events()
        if str(e["event"]).startswith("LOGIN_")
    ]
    assert authentification == ["LOGIN_FAILED", "LOGIN_SUCCEEDED"]


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


def test_envoi_sans_destinataire_ne_leve_pas(monkeypatch):
    """Un envoi sans destinataire retourne False au lieu de lever.

    CE TEST DOIT REPRODUIRE LA FENETRE, PAS L'ETAT AU REPOS. Une premiere
    version se contentait d'un notifieur sans destinataire : `enabled` valait
    alors False et la methode sortait AVANT l'indexation. Le controle passait
    au vert en reintroduisant le defaut — il ne testait rien.

    Le defaut reel est une course. `enabled` verifie la presence d'un
    destinataire sous verrou, RELACHE le verrou, et `_destinataires()[0]`
    s'execute apres. `remove_recipient` — appele par le thread HTTP a la
    fermeture d'une session — peut vider la liste entre les deux. On modelise
    exactement cet intervalle : le jeu de destinataires reste peuple, donc
    `enabled` reste vrai, mais la lecture suivante ne rend rien.
    """
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
    notifier.set_recipient("shift@example.test")
    monkeypatch.setattr(notifier, "_destinataires", list)
    assert notifier.enabled is True, "la fenetre suppose enabled encore vrai"
    assert notifier.enqueue_governance("rapport") is False
    assert notifier.enqueue_test() is False


def test_echec_smtp_est_traduit_en_cause_actionnable():
    """« SMTPAuthenticationError » seul n'apprend rien a un exploitant."""
    import smtplib

    from src.notifications.email import diagnostiquer_echec

    auth = diagnostiquer_echec(
        smtplib.SMTPAuthenticationError(535, b"5.7.8 Username and Password not accepted")
    )
    assert "16 caractères" in auth
    assert "SMTP_PASSWORD" in auth

    reseau = diagnostiquer_echec(TimeoutError("delai depasse"))
    assert "SMTP_HOST" in reseau

    # Une exception non prevue conserve au moins son nom de classe.
    assert diagnostiquer_echec(ValueError("x")) == "ValueError"


def _analyse_critique():
    return SimpleNamespace(
        decision=SimpleNamespace(
            severity="CRITICAL",
            amdec_modes=["FAISCEAU_BOUCHAGE"],
            timestamp="2024-10-25T21:00:00",
            diagnosis="Déficit thermique persistant",
            recommended_action=SimpleNamespace(
                description="Confirmer sur le terrain", urgency="IMMEDIATE",
            ),
        ),
        verdict=SimpleNamespace(global_score=9.2, agreement=True),
    )


def test_alerte_critique_sans_destinataire_laisse_une_trace(tmp_path):
    """L'alerte automatique compte surtout quand personne n'est devant l'écran.

    Le garde etait `if not self.enabled`, et `enabled` exige un destinataire
    actif. Sans session ouverte et sans ALERT_EMAIL_TO — la nuit, le week-end,
    tout arret de poste — une decision CRITICAL validee par le controleur
    repartait sans envoi, sans fichier, sans ligne de journal et sans compteur.
    """
    notifier = EmailNotifier(
        host=None, port=587, username=None, password=None,
        sender=None, recipient=None, starttls=True,
        cooldown_minutes=60, minimum_severity="CRITICAL",
        spool=tmp_path,
    )
    assert notifier.enabled is False, "aucun destinataire : le canal est bien muet"

    notifier.notify(_analyse_critique())

    etat = notifier.status()
    assert etat["undelivered_no_recipient"] == 1
    assert any(e["etat"] == "non distribue" for e in etat["journal"]), (
        "l'alerte doit rester tracable apres coup"
    )
    assert list(tmp_path.glob("*.eml")), "un fichier doit subsister apres arret"


def test_le_corps_d_alerte_est_redige_en_francais():
    """« Severite », « Equipement », « decision rejetee » : texte lu par un exploitant."""
    envoyes = []
    notifier = EmailNotifier(
        host="smtp.example.test", port=587, username=None, password=None,
        sender="e7301@example.test", recipient="astreinte@example.test",
        starttls=True, cooldown_minutes=60, minimum_severity="CRITICAL",
    )
    notifier._enqueue = lambda job: envoyes.append(job)
    notifier.notify(_analyse_critique())

    assert envoyes, "une alerte CRITICAL avec destinataire doit partir"
    corps = envoyes[0].body
    for faute in ("Severite", "Equipement", "complementaire", "operationnelles"):
        assert faute not in corps, f"« {faute} » doit porter ses accents"
    assert "Sévérité" in corps and "Équipement" in corps
    assert "9,20/10" in corps, "la note ne doit pas porter un point décimal anglais"
    assert "Aucune panne n'est confirmée" in corps


def test_la_rotation_ne_touche_pas_la_session_tenue_par_une_requete_en_vol():
    """Rotation = publication atomique, jamais mutation d'un objet partagé.

    LE DEFAUT QUE CE CONTROLE INTERDIT (SEC-2, lot S13).

    `rotate()` écrasait `csrf_token` SUR l'objet de session, sous le verrou. Le
    commentaire en tirait la conclusion que la course était fermée. Elle ne
    l'était pas : le lecteur ne prend jamais le verrou. `api/main.py` compare
    `request.headers["X-CSRF-Token"]` à `session.csrf_token` sur l'objet que
    `validate()` lui a rendu, verrou déjà relâché.

    Déroulé reproduit ici : une requête en vol obtient la session, une rotation
    survient, la requête compare enfin son en-tête. Avec la mutation en place
    elle recevait `403` sur une requête parfaitement légitime.

    C'est SEC-1 du lot S11 sur une autre structure, et la parade est la même :
    on ne modifie pas l'objet que d'autres tiennent, on en publie un nouveau.
    """
    manager = AuthManager(
        password_hash=hash_password("phrase secrete industrielle 2026"),
        allowed_emails={"tech@example.test"},
    )
    resultat = manager.authenticate(
        "tech@example.test", "phrase secrete industrielle 2026", "127.0.0.1"
    )
    assert resultat is not None
    jeton, _ = resultat

    # 1. La requête en vol obtient sa session et retient son jeton CSRF.
    en_vol = manager.validate(jeton)
    assert en_vol is not None
    csrf_presente_par_le_client = en_vol.csrf_token

    # 2. Une rotation survient entre-temps.
    rotation = manager.rotate(jeton)
    assert rotation is not None
    nouveau_jeton, renouvelee = rotation

    # 3. La requête en vol compare enfin. Elle doit passer.
    assert en_vol.csrf_token == csrf_presente_par_le_client, (
        "la rotation a muté la session qu'une requête concurrente tenait : "
        "elle recevra 403 sur une requête légitime"
    )
    assert renouvelee is not en_vol, "la rotation doit publier un objet distinct"
    assert renouvelee.csrf_token != csrf_presente_par_le_client
    assert nouveau_jeton != jeton

    # La rotation ne prolonge pas l'expiration absolue.
    assert renouvelee.created_at == en_vol.created_at
    assert renouvelee.email == en_vol.email
    assert renouvelee.role == en_vol.role

    # Et l'ancien identifiant ne vaut plus rien.
    assert manager.validate(jeton) is None
    assert manager.validate(nouveau_jeton) is renouvelee


def test_la_limitation_de_debit_consigne_le_compte_vise():
    """Le seul événement qui signale une attaque doit nommer sa cible.

    `LOGIN_RATE_LIMITED` était consigné avec une chaîne vide : le journal disait
    qu'une limite avait été atteinte, jamais contre quel compte — alors que la
    valeur était dans la portée et que les deux autres événements la consignent.
    """
    manager = AuthManager(
        password_hash=hash_password("phrase secrete industrielle 2026"),
        allowed_emails={"vise@example.test"},
    )
    for _ in range(5):
        manager.authenticate("vise@example.test", "mauvais-secret", "client-z")
    with pytest.raises(TooManyAttemptsError):
        manager.authenticate("vise@example.test", "mauvais-secret", "client-z")

    limites = [
        evenement for evenement in manager.audit_events()
        if evenement["event"] == "LOGIN_RATE_LIMITED"
    ]
    assert limites, "aucun événement de limitation consigné"
    assert limites[-1]["email"] == "vise@example.test"
    assert limites[-1]["client_key"] == "client-z"
