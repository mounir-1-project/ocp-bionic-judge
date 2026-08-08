"""
Registre des techniciens et routage des alertes critiques.

L'adresse saisie a l'ouverture de session devient le DESTINATAIRE des alertes
critiques. Une identite qui declenche l'envoi d'un courriel d'intervention doit
donc etre authentifiee individuellement : un mot de passe partage ne permettrait
ni de savoir qui a ouvert la session, ni de revoquer un depart.

Ces tests verrouillent trois proprietes :
  - chaque technicien a son propre mot de passe, jamais stocke en clair ;
  - un mot de passe faux ou une adresse inconnue sont refuses ;
  - l'adresse de session devient destinataire, et cesse de l'etre a la
    deconnexion.
"""

from __future__ import annotations

import json
import os
import threading
import time

import pytest

from src.security.auth import (
    ATTEMPT_WINDOW_SECONDS,
    MAX_ATTEMPTS,
    AuthManager,
    TooManyAttemptsError,
    hash_password,
    verify_password,
)
from src.security.auth import MIN_PASSWORD_LENGTH
from src.security.registry import OperatorRegistry

PASSWORD = "motdepasse-industriel-2026"
OTHER = "un-autre-mot-de-passe"


@pytest.fixture
def registry(tmp_path):
    return OperatorRegistry(tmp_path / "operators.json")


# ── Registre ──────────────────────────────────────────────────────────────────

def test_registre_vide_au_depart(registry):
    """Sans technicien enregistre, l'acces protege ne peut pas s'activer."""
    assert registry.is_configured is False
    assert len(registry) == 0
    assert registry.emails() == set()


def test_enregistrement_d_un_technicien(registry):
    operator = registry.add(
        "tech@ocpgroup.ma", PASSWORD, role="maintenance", name="Mounir"
    )
    assert operator.email == "tech@ocpgroup.ma"
    assert operator.role == "maintenance"
    assert registry.is_configured is True
    assert registry.roles() == {"tech@ocpgroup.ma": "maintenance"}


def test_le_mot_de_passe_n_est_jamais_stocke_en_clair(registry, tmp_path):
    """LE TEST LE PLUS IMPORTANT DE CE MODULE."""
    registry.add("tech@ocpgroup.ma", PASSWORD)
    contenu = (tmp_path / "operators.json").read_text(encoding="utf-8")

    assert PASSWORD not in contenu
    assert "pbkdf2_sha256$" in contenu

    stored = json.loads(contenu)["operators"][0]["password_hash"]
    assert verify_password(PASSWORD, stored) is True
    assert verify_password(OTHER, stored) is False


def test_chaque_technicien_a_une_empreinte_distincte(registry):
    """Deux techniciens avec le MEME mot de passe doivent avoir des sels differents."""
    registry.add("a@ocpgroup.ma", PASSWORD)
    registry.add("b@ocpgroup.ma", PASSWORD)
    hashes = registry.password_hashes()
    assert hashes["a@ocpgroup.ma"] != hashes["b@ocpgroup.ma"]


def test_mot_de_passe_trop_court_refuse(registry):
    """Le refus doit citer la longueur exigée, et la citer correctement.

    CE CONTROLE VERROUILLAIT LA FAUTE. Il exigeait `match="12 caracteres"`,
    c'est-à-dire l'orthographe SANS ACCENT du message. Accentuer « caractères »
    — ce que la règle du dépôt impose à tout texte affiché — le faisait échouer.
    C'est exactement S6-4 : un test qui n'accepte la lecture que si elle est
    mal écrite.

    La règle du dépôt s'applique des deux côtés : le texte COMPARÉ est dépouillé
    par `sans_accents`, le texte AFFICHÉ reste accentué. Et la longueur n'est
    plus écrite ici non plus — elle vient de la constante.
    """
    from src.formatting import sans_accents
    from src.security.auth import MIN_PASSWORD_LENGTH

    with pytest.raises(ValueError) as refus:
        registry.add("tech@ocpgroup.ma", "court")
    message = str(refus.value)
    assert f"{MIN_PASSWORD_LENGTH} caracteres" in sans_accents(message)
    assert "caractères" in message, "le message affiché doit rester accentué"
    assert registry.is_configured is False


def test_adresse_invalide_refusee(registry):
    with pytest.raises(ValueError, match="Adresse invalide"):
        registry.add("pas-une-adresse", PASSWORD)


def test_role_inconnu_refuse(registry):
    with pytest.raises(ValueError, match="Role inconnu"):
        registry.add("tech@ocpgroup.ma", PASSWORD, role="chef-supreme")


def test_doublon_refuse(registry):
    registry.add("tech@ocpgroup.ma", PASSWORD)
    with pytest.raises(ValueError, match="deja enregistre"):
        registry.add("TECH@ocpgroup.ma", OTHER)


def test_changement_de_mot_de_passe(registry):
    registry.add("tech@ocpgroup.ma", PASSWORD)
    ancien = registry.get("tech@ocpgroup.ma").password_hash
    registry.set_password("tech@ocpgroup.ma", OTHER)
    nouveau = registry.get("tech@ocpgroup.ma").password_hash

    assert nouveau != ancien
    assert verify_password(OTHER, nouveau) is True
    assert verify_password(PASSWORD, nouveau) is False


def test_retrait_d_un_technicien(registry):
    registry.add("tech@ocpgroup.ma", PASSWORD)
    registry.remove("tech@ocpgroup.ma")
    assert registry.is_configured is False
    with pytest.raises(KeyError):
        registry.remove("tech@ocpgroup.ma")


def test_persistance_sur_disque(tmp_path):
    """Le registre doit survivre au redemarrage du service."""
    path = tmp_path / "operators.json"
    OperatorRegistry(path).add("tech@ocpgroup.ma", PASSWORD, role="operator")

    relu = OperatorRegistry(path)
    assert relu.is_configured is True
    assert relu.roles()["tech@ocpgroup.ma"] == "operator"


def test_destinataires_d_alerte_selectionnables(registry):
    """Un role de lecture seule peut legitimement ne pas etre reveille la nuit."""
    registry.add("astreinte@ocpgroup.ma", PASSWORD, role="maintenance")
    registry.add("lecture@ocpgroup.ma", OTHER, role="reader", alert_recipient=False)
    assert registry.alert_recipients() == {"astreinte@ocpgroup.ma"}


def test_longueur_minimale_publiee():
    """La CLI et le registre doivent partager la meme exigence."""
    assert MIN_PASSWORD_LENGTH >= 12


def _ecrire_registre(path, operators):
    """Ecrit un registre a la main, comme le ferait un administrateur."""
    path.write_text(
        json.dumps({"schema_version": 1, "operators": operators}, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def test_le_chargement_refuse_un_role_inconnu(tmp_path):
    """UNE HABILITATION NE DOIT PAS SE DEGRADER EN SILENCE.

    `add()` refusait deja les roles inconnus, `load()` les acceptait. Une
    entree editee a la main avec `"admin"` au lieu de `"administrator"` etait
    chargee sans un mot, puis ecartee par le filtre `VALID_ROLES` d'AuthManager
    et remplacee par `reader`. Le technicien perdait ses droits sans qu'aucune
    trace ne dise pourquoi.
    """
    path = _ecrire_registre(tmp_path / "ops.json", [{
        "email": "chef@ocpgroup.ma", "role": "admin",
        "password_hash": hash_password(PASSWORD),
    }])
    with pytest.raises(ValueError, match="role inconnu"):
        OperatorRegistry(path)


def test_le_chargement_refuse_une_empreinte_absente(tmp_path):
    """UNE EMPREINTE VIDE RENDAIT LE COMPTE OUVRABLE AVEC LE SECRET PARTAGE.

    L'adresse restait dans l'allowlist, mais `AuthManager` retire les
    empreintes vides de `user_hashes` : l'authentification retombait sur
    `AUTH_PASSWORD_HASH`. Le compte devenait donc ouvrable avec le mot de passe
    d'equipe — exactement ce que le registre par technicien existe pour
    supprimer.
    """
    path = _ecrire_registre(tmp_path / "ops.json", [{
        "email": "tech@ocpgroup.ma", "role": "maintenance", "password_hash": "",
    }])
    with pytest.raises(ValueError, match="empreinte"):
        OperatorRegistry(path)


def test_le_chargement_refuse_une_adresse_malformee(tmp_path):
    """Une adresse ignoree en silence laisse croire le technicien enregistre."""
    path = _ecrire_registre(tmp_path / "ops.json", [{
        "email": "pas-une-adresse", "role": "reader",
        "password_hash": hash_password(PASSWORD),
    }])
    with pytest.raises(ValueError, match="adresse invalide"):
        OperatorRegistry(path)


def test_le_registre_n_est_lisible_que_par_son_proprietaire(tmp_path):
    """Les droits sont poses AVANT publication, pas apres.

    Ils l'etaient sur la cible, apres `replace()`. Entre l'ecriture du fichier
    temporaire et le renommage, un fichier contenant toutes les empreintes
    existait avec les droits par defaut du processus.
    """
    if not hasattr(os, "getuid"):  # pragma: no cover - Windows
        pytest.skip("droits POSIX indisponibles")
    path = tmp_path / "ops.json"
    OperatorRegistry(path).add("tech@ocpgroup.ma", PASSWORD, role="maintenance")
    assert path.stat().st_mode & 0o077 == 0, "le registre est lisible par des tiers"
    assert not (tmp_path / "ops.tmp").exists(), "fichier temporaire non publie"


# ── Authentification par technicien ───────────────────────────────────────────

@pytest.fixture
def manager(registry):
    registry.add("tech@ocpgroup.ma", PASSWORD, role="maintenance")
    registry.add("chef@ocpgroup.ma", OTHER, role="administrator")
    return AuthManager(
        user_hashes=registry.password_hashes(),
        user_roles=registry.roles(),
    )


def test_connexion_avec_le_bon_mot_de_passe(manager):
    result = manager.authenticate("tech@ocpgroup.ma", PASSWORD, "poste-1")
    assert result is not None
    _, session = result
    assert session.email == "tech@ocpgroup.ma"
    assert session.role == "maintenance"
    assert session.csrf_token


def test_le_mot_de_passe_d_un_autre_technicien_ne_marche_pas(manager):
    """LE TEST QUI JUSTIFIE LE REGISTRE.

    Avec l'ancien mot de passe partage, ce cas reussissait : n'importe quelle
    adresse de l'allowlist ouvrait une session avec le secret d'equipe.
    """
    assert manager.authenticate("tech@ocpgroup.ma", OTHER, "poste-1") is None


def test_mot_de_passe_vide_refuse(manager):
    assert manager.authenticate("tech@ocpgroup.ma", "", "poste-1") is None


def test_adresse_inconnue_refusee(manager):
    assert manager.authenticate("intrus@ailleurs.com", PASSWORD, "poste-1") is None


def test_les_roles_viennent_du_registre(manager):
    _, session = manager.authenticate("chef@ocpgroup.ma", OTHER, "poste-2")
    assert session.role == "administrator"


def test_limitation_des_tentatives(manager):
    """Cinq echecs depuis le meme poste bloquent la fenetre."""
    from src.security.auth import TooManyAttemptsError

    for _ in range(5):
        manager.authenticate("tech@ocpgroup.ma", "faux-mot-de-passe", "poste-3")
    with pytest.raises(TooManyAttemptsError):
        manager.authenticate("tech@ocpgroup.ma", PASSWORD, "poste-3")


def test_journal_d_audit_nomme_le_technicien(manager):
    """Un secret partage rendait ce journal inutilisable."""
    manager.authenticate("tech@ocpgroup.ma", PASSWORD, "poste-4")
    manager.authenticate("chef@ocpgroup.ma", "faux", "poste-5")
    events = manager.audit_events()

    reussite = [e for e in events if e["event"] == "LOGIN_SUCCEEDED"]
    echec = [e for e in events if e["event"] == "LOGIN_FAILED"]
    assert reussite[-1]["email"] == "tech@ocpgroup.ma"
    assert echec[-1]["email"] == "chef@ocpgroup.ma"
    assert not any("password" in str(e).lower() for e in events)


def test_mode_partage_historique_reste_supporte():
    """Les deploiements existants ne doivent pas casser."""
    manager = AuthManager(
        password_hash=hash_password(PASSWORD),
        allowed_emails={"tech@ocpgroup.ma"},
        user_roles={"tech@ocpgroup.ma": "operator"},
    )
    assert manager.authenticate("tech@ocpgroup.ma", PASSWORD, "poste-6") is not None
    assert manager.authenticate("tech@ocpgroup.ma", OTHER, "poste-7") is None


def test_la_limite_de_tentatives_tient_sous_concurrence(manager):
    """LA LIMITE NE COMPTAIT QUE LES ECHECS DEJA CONSTATES.

    L'ancien ordonnancement lisait le compteur dans un premier bloc verrouille,
    executait la derivation PBKDF2 hors verrou, puis incrementait dans un
    second bloc. Toutes les tentatives lancees en parallele lisaient donc la
    meme valeur : vingt requetes simultanees produisaient vingt derivations
    completes et zero refus. Il suffisait de ne pas attendre la reponse
    precedente pour que la limite de cinq essais n'arrete rien.

    La tentative est desormais comptee AVANT la verification.
    """
    passees, refusees = [], []
    verrou = threading.Lock()

    def essayer() -> None:
        try:
            manager.authenticate("tech@ocpgroup.ma", "mauvais mot de passe", "poste-x")
            with verrou:
                passees.append(1)
        except TooManyAttemptsError:
            with verrou:
                refusees.append(1)

    fils = [threading.Thread(target=essayer) for _ in range(20)]
    for fil in fils:
        fil.start()
    for fil in fils:
        fil.join()

    assert len(passees) <= MAX_ATTEMPTS, (
        f"{len(passees)} derivations pour une limite de {MAX_ATTEMPTS} : "
        "la limitation est contournable en parallelisant les requetes"
    )
    assert refusees, "aucune tentative n'a ete refusee"


def test_les_compteurs_et_sessions_perimes_sont_liberes(registry):
    """DEUX STRUCTURES CROISSAIENT SANS LIMITE SUR ENTREE EXTERIEURE.

    `_attempts` est indexe par adresse cliente et n'etait vide que par une
    connexion REUSSIE : un balayage d'adresses y laissait une file par adresse,
    definitivement. `_sessions` n'etait purge que si le porteur revenait
    presenter son propre jeton expire — une session abandonnee en fin de quart
    ne l'etait jamais.
    """
    registry.add("tech@ocpgroup.ma", PASSWORD, role="maintenance")
    manager = AuthManager(
        user_hashes=registry.password_hashes(),
        user_roles=registry.roles(),
        idle_timeout_s=0.01,
        absolute_timeout_s=0.01,
    )
    for index in range(40):
        manager.authenticate("inconnu@ocpgroup.ma", "faux", f"10.0.0.{index}")
    assert manager.authenticate("tech@ocpgroup.ma", PASSWORD, "poste-legitime")
    assert len(manager._attempts) >= 40
    assert len(manager._sessions) == 1

    manager._purger(time.time() + 10 * ATTEMPT_WINDOW_SECONDS)
    assert manager._attempts == {}, "compteurs de tentatives non liberes"
    assert manager._sessions == {}, "sessions perimees non liberees"
