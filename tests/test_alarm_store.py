"""Cycle de vie durable des alarmes opérateur."""

from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from src.operations import AlarmStore

# LE SENTINELLE DU CONSTRUCTEUR ENTRAIT EN COLLISION AVEC UNE VALEUR REELLE.
# `lead=None` signifiait « prends `finding` », si bien qu'aucun appel ne
# pouvait produire une decision dont `lead_finding` vaut VRAIMENT `None`.
# Or c'est le cas NOMINAL en production : `detection_agent` emet
# `lead_finding=None` avec des constatations non vides (INFO, severite basse).
# Le repli de `_trigger` — nommer l'alarme d'apres `findings[0]` — est donc le
# chemin le plus frequent du systeme, et il etait hors de portee de la suite.
_DEFAUT = object()


def _analysis(
    severity="CRITICAL",
    agreement=True,
    timestamp="2024-08-01 10:00:00",
    finding="DUTY_LOW",
    mode="FAISCEAU_BOUCHAGE",
    autres=(),
    lead=_DEFAUT,
):
    """Analyse de test.

    `autres` permet de porter PLUSIEURS constatations, ce que ce constructeur
    ne savait pas faire : il en produisait toujours exactement une. Le defaut
    AL-1 — l'alarme identifiee par `findings[0]`, donc par l'ordre d'ecriture
    des regles — etait de ce fait structurellement hors de portee de la suite.

    `lead` est la constatation que l'agent a retenue comme dominante. Par
    defaut c'est `finding`, ce qui reproduit le cas nominal.
    """
    codes = ([finding] if finding else []) + list(autres)
    return SimpleNamespace(
        detection=SimpleNamespace(
            timestamp=timestamp,
            findings=[SimpleNamespace(code=c) for c in codes],
        ),
        decision=SimpleNamespace(
            severity=severity,
            amdec_modes=[mode] if severity != "NORMAL" and mode else [],
            diagnosis="Déficit thermique persistant",
            recommended_action=SimpleNamespace(description="Inspecter le faisceau"),
            lead_finding=finding if lead is _DEFAUT else lead,
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
    with pytest.raises(ValueError):
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


def test_l_alarme_porte_la_constatation_dominante_pas_la_premiere(tmp_path):
    """AL-1 — LE REGISTRE NOMMAIT L'ALARME D'APRES LE CAPTEUR, PAS LE TUBE.

    `RuleEngine.evaluate` appelle `_rule_sensor_health` EN PREMIER. Une analyse
    qui porte a la fois un `SENSOR_FAULT` et un `CONC_DROP_SEVERE` — suspicion
    de percement de tube — presentait donc `SENSOR_FAULT` en tete de
    `findings`. `_key` prenait `findings[0]` : l'alarme persistee nommait
    l'analyseur qui derive, pendant que le diagnostic affiche nommait le
    faisceau.

    L'agent tranche par `_priorite`, qui fait passer un defaut de mesure APRES
    un diagnostic equipement. Le registre consomme desormais ce choix.
    """
    store = AlarmStore(tmp_path / "alarms.db")
    store.observe(_analysis(
        finding="SENSOR_FAULT",
        autres=("CONC_DROP_SEVERE",),
        lead="CONC_DROP_SEVERE",
        mode="FAISCEAU_FUITE",
    ))
    alarme = store.list(active_only=True)[0]
    assert alarme["trigger_rule"] == "CONC_DROP_SEVERE", (
        "l'alarme est nommee d'apres la premiere constatation evaluee "
        f"({alarme['trigger_rule']}) et non d'apres la dominante"
    )
    assert "CONC_DROP_SEVERE" in alarme["alarm_key"]
    # La preuve conserve TOUTES les constatations : rien n'est perdu.
    assert set(alarme["evidence"]["finding_codes"]) == {
        "SENSOR_FAULT", "CONC_DROP_SEVERE"
    }
    store.close()


def test_une_alarme_se_resout_meme_si_une_autre_constatation_disparait(tmp_path):
    """LA CONSEQUENCE LA PLUS COUTEUSE : UNE ALARME QUI NE SE FERME JAMAIS.

    `observe` cherche `WHERE alarm_key=?` avec la cle COURANTE. Tant que la cle
    dependait de `findings[0]`, la disparition d'une constatation en tete
    changeait la cle : la ligne existante n'etait plus retrouvee, une SECONDE
    alarme naissait, et la premiere restait ACTIVE indefiniment.

    La dominante etant stable, la meme condition retrouve sa propre alarme.
    """
    store = AlarmStore(tmp_path / "alarms.db")
    store.observe(_analysis(
        finding="SENSOR_FAULT", autres=("CONC_DROP_SEVERE",),
        lead="CONC_DROP_SEVERE", mode="FAISCEAU_FUITE",
    ))
    # Heure suivante : le defaut capteur a disparu, la chute de titre persiste.
    store.observe(_analysis(
        timestamp="2024-08-01 11:00:00",
        finding="CONC_DROP_SEVERE", lead="CONC_DROP_SEVERE", mode="FAISCEAU_FUITE",
    ))
    actives = store.list(active_only=True)
    assert len(actives) == 1, (
        f"{len(actives)} alarmes pour une seule condition : la cle a change "
        "avec l'ordre des constatations"
    )
    assert actives[0]["occurrence_count"] == 2

    # Retour a la normale : l'alarme doit se resoudre.
    store.observe(_analysis(
        severity="NORMAL", timestamp="2024-08-01 12:00:00",
        finding="CONC_DROP_SEVERE", lead=None,
    ))
    assert store.list(active_only=True) == []
    store.close()


def test_un_desaccord_du_juge_ne_resout_pas_une_alarme(tmp_path):
    """Le Judge conteste une rédaction, il ne dit rien du procédé.

    AL-2 — Le test valait `sévérité alarmante ET accord du Judge`. Sa négation
    partait donc vers la résolution dans deux cas de natures opposées : la
    condition a cessé (légitime), et la condition PERSISTE mais le Judge a
    rejeté la décision (absurde).

    Mesuré : une alarme CRITICAL levée, réobservée avec la même constatation et
    `agreement=False`, passait à `RETURNED_NORMAL` — alors que le percement
    suspecté était toujours là. C'est ce que l'en-tête du module interdit.
    """
    store = AlarmStore(tmp_path / "desaccord.db")
    store.observe(_analysis(severity="CRITICAL", finding="CONC_DROP_SEVERE"))
    assert store.list()[0]["status"] == "ACTIVE"

    # La condition persiste, le Judge conteste : rien ne doit bouger.
    assert store.observe(
        _analysis(
            severity="CRITICAL", finding="CONC_DROP_SEVERE",
            agreement=False, timestamp="2024-08-01 11:00:00",
        )
    ) is None
    assert store.list()[0]["status"] == "ACTIVE", (
        "un désaccord de gouvernance a résolu une alarme dont la condition "
        "était toujours observée"
    )

    # Et la voie de résolution légitime fonctionne toujours.
    store.observe(
        _analysis(
            severity="NORMAL", finding="CONC_DROP_SEVERE",
            timestamp="2024-08-01 12:00:00",
        )
    )
    assert store.list()[0]["status"] == "RETURNED_NORMAL"
    store.close()


def test_sans_dominante_l_alarme_retombe_sur_l_ordre_des_regles(tmp_path):
    """AL-4 — LE CHEMIN LE PLUS FRÉQUENT DU SYSTÈME N'ÉTAIT PAS TESTÉ.

    AL-1 a fait consommer par le registre la constatation dominante choisie par
    l'agent. Mais `detection_agent` n'en désigne une que sur le chemin
    diagnostique : le chemin nominal émet `lead_finding=None` **avec des
    constatations non vides** (`evidence_refs=[f.code for f in
    result.findings]`). `_trigger` retombe alors sur `findings[0]`, c'est-à-dire
    sur l'ORDRE D'ÉVALUATION DES RÈGLES — le défaut exact qu'AL-1 corrige.

    Ce test ne prétend pas que ce comportement est bon. Il établit qu'il est
    **atteignable et déterministe**, ce que la suite ne pouvait pas dire : le
    sentinelle du constructeur rendait `lead_finding=None` inexprimable.

    Reste ouvert (AL-4) : faut-il que le chemin nominal désigne lui aussi une
    dominante ? Ce n'est pas une décision de test, et je ne la prends pas ici.
    """
    store = AlarmStore(tmp_path / "sans_dominante.db")
    alarme = store.observe(_analysis(
        finding="SENSOR_FAULT",
        autres=("CONC_DROP_SEVERE",),
        lead=None,                      # exprimable seulement depuis S42
        mode="FAISCEAU_FUITE",
    ))
    assert alarme is not None, "aucune alarme alors que deux constatations sont là"
    assert alarme["trigger_rule"] == "SENSOR_FAULT", (
        "sans dominante, le repli doit nommer la PREMIÈRE constatation évaluée ; "
        f"il a nommé {alarme['trigger_rule']}"
    )
    # Et la preuve reste complète : le repli choisit un nom, il ne perd rien.
    assert set(alarme["evidence"]["finding_codes"]) == {
        "SENSOR_FAULT", "CONC_DROP_SEVERE"
    }
    store.close()
