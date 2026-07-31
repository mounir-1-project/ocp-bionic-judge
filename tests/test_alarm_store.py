"""Cycle de vie durable des alarmes opérateur."""

from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

from src.operations import AlarmStore


def _analysis(
    severity="CRITICAL",
    agreement=True,
    timestamp="2024-08-01 10:00:00",
    finding="DUTY_LOW",
    mode="FAISCEAU_BOUCHAGE",
):
    return SimpleNamespace(
        detection=SimpleNamespace(
            timestamp=timestamp,
            findings=[SimpleNamespace(code=finding)] if finding else [],
        ),
        decision=SimpleNamespace(
            severity=severity,
            amdec_modes=[mode] if severity != "NORMAL" and mode else [],
            diagnosis="Déficit thermique persistant",
            recommended_action=SimpleNamespace(description="Inspecter le faisceau"),
        ),
        verdict=SimpleNamespace(agreement=agreement),
    )


def test_cycle_de_vie_persistant(tmp_path):
    path = tmp_path / "alarms.db"
    store = AlarmStore(path)
    store.observe(_analysis())
    active = store.list(active_only=True)
    assert len(active) == 1
    assert active[0]["status"] == "ACTIVE"
    assert active[0]["occurrence_count"] == 1
    assert active[0]["equipment_id"] == "S-PC-E7301"

    alarm = store.transition(
        active[0]["id"],
        action="acknowledge",
        operator="technicien@ocpgroup.ma",
        comment="Inspection demandée",
    )
    assert alarm["status"] == "ACKNOWLEDGED"
    assert alarm["acknowledged_by"] == "technicien@ocpgroup.ma"
    # LA COLONNE `transition` NOMME L'ACTION, PAS L'ETAT D'ARRIVEE.
    # Elle recevait auparavant `target`, si bien que le journal inscrivait
    # « ACTIVE » aussi bien pour une desinhibition que pour une reapparition :
    # l'auditeur ne pouvait plus dire POURQUOI l'etat avait change. Les
    # transitions systeme nommaient deja leur cause (APPEARED, REPEATED,
    # REACTIVATED); seules les actions imputables a une personne la perdaient.
    assert [item["transition"] for item in alarm["history"]] == [
        "APPEARED",
        "ACKNOWLEDGED_BY_OPERATOR",
    ]
    store.close()

    reopened = AlarmStore(path)
    assert reopened.list(active_only=True)[0]["comment"] == "Inspection demandée"
    reopened.observe(_analysis(severity="NORMAL", timestamp="2024-08-01 11:00:00"))
    assert reopened.list(active_only=True) == []
    assert reopened.list()[0]["status"] == "RETURNED_NORMAL"
    reopened.close()


def test_shelving_et_validation_des_transitions(tmp_path):
    store = AlarmStore(tmp_path / "alarms.db")
    store.observe(_analysis(severity="WARNING"))
    alarm_id = store.list()[0]["id"]
    assert store.transition(
        alarm_id, action="shelve", operator="poste-local", comment="Travaux en cours"
    )["status"] == "SHELVED"
    assert store.transition(
        alarm_id, action="unshelve", operator="poste-local"
    )["status"] == "ACTIVE"
    with __import__("pytest").raises(ValueError):
        store.transition(alarm_id, action="unshelve", operator="poste-local")
    store.close()


def test_deux_alarmes_independantes_et_retour_cible(tmp_path):
    store = AlarmStore(tmp_path / "alarms.db")
    store.observe(_analysis(finding="DUTY_LOW", mode="FAISCEAU_BOUCHAGE"))
    store.observe(_analysis(finding="TEMP_HIGH", mode="FAISCEAU_FUITE"))
    assert len(store.list(active_only=True)) == 2

    store.observe(
        _analysis(
            severity="NORMAL",
            timestamp="2024-08-01 11:00:00",
            finding="DUTY_LOW",
        )
    )
    active = store.list(active_only=True)
    assert len(active) == 1
    assert active[0]["trigger_rule"] == "TEMP_HIGH"
    store.close()


def test_shelved_ne_revient_pas_silencieusement_a_la_normale(tmp_path):
    store = AlarmStore(tmp_path / "alarms.db")
    alarm = store.observe(_analysis())
    store.transition(
        alarm["id"],
        action="shelve",
        operator="maintenance@ocpgroup.ma",
        comment="Inhibition autorisée pendant inspection",
    )
    store.observe(_analysis(severity="NORMAL", timestamp="2024-08-01 11:00:00"))
    assert store.get(alarm["id"])["status"] == "SHELVED"
    store.close()


def test_repetition_reactivation_cloture_et_idempotence(tmp_path):
    import pytest

    store = AlarmStore(tmp_path / "alarms.db")
    alarm = store.observe(_analysis())
    repeated = store.observe(_analysis(timestamp="2024-08-01 10:05:00"))
    assert repeated["id"] == alarm["id"]
    assert repeated["occurrence_count"] == 2

    store.observe(_analysis(severity="NORMAL", timestamp="2024-08-01 11:00:00"))
    # Une seconde observation normale est idempotente.
    store.observe(_analysis(severity="NORMAL", timestamp="2024-08-01 11:00:00"))
    assert store.get(alarm["id"])["status"] == "RETURNED_NORMAL"

    reactivated = store.observe(_analysis(timestamp="2024-08-01 12:00:00"))
    assert reactivated["status"] == "ACTIVE"
    assert reactivated["occurrence_count"] == 3
    with pytest.raises(ValueError):
        store.transition(alarm["id"], action="close", operator="maintenance")
    store.observe(_analysis(severity="NORMAL", timestamp="2024-08-01 13:00:00"))
    assert store.transition(
        alarm["id"], action="close", operator="maintenance", comment="Contrôle terminé"
    )["status"] == "CLOSED"
    store.close()


def test_analyse_normale_sans_cle_ne_resout_rien(tmp_path):
    store = AlarmStore(tmp_path / "alarms.db")
    alarm = store.observe(_analysis())
    assert store.observe(_analysis(severity="NORMAL", finding=None)) is None
    assert store.get(alarm["id"])["status"] == "ACTIVE"
    store.close()


def test_observations_concurrentes_restent_atomiques(tmp_path):
    """Une rafale identique conserve une seule alarme et toutes les occurrences."""
    store = AlarmStore(tmp_path / "alarms.db")

    def observe(index: int):
        return store.observe(
            _analysis(timestamp=f"2024-08-01 10:{index:02d}:00")
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        alarms = list(executor.map(observe, range(20)))

    assert len({alarm["id"] for alarm in alarms}) == 1
    persisted = store.list(active_only=True)
    assert len(persisted) == 1
    assert persisted[0]["occurrence_count"] == 20
    assert len(store.get(persisted[0]["id"])["history"]) == 20
    store.close()
