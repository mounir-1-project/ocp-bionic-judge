"""Canal email asynchrone, complémentaire à l'alarme HMI locale."""

from __future__ import annotations

import queue
import smtplib
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from src.pipeline import Analysis


def diagnostiquer_echec(exc: Exception) -> str:
    """Traduit un échec d'envoi en cause actionnable.

    LE NOM DE CLASSE NE SUFFIT PAS. Le journal ne conservait que
    `type(exc).__name__` — l'interface affichait donc « SMTPAuthenticationError »
    à un exploitant, qui n'a aucun moyen d'en déduire quoi faire. Le cas le plus
    fréquent, et de loin, est le mot de passe Gmail ordinaire là où Google exige
    un mot de passe d'application depuis mai 2022 : la cause est connue, la
    correction est connue, et rien de tout cela n'était dit.

    Le texte du serveur n'est pas recopié tel quel : il varie selon le relais et
    peut contenir l'adresse d'authentification. Chaque cause est traduite par une
    phrase fixe, vérifiable, qui ne divulgue aucun paramètre du poste.

    Args:
        exc: Exception levée par la tentative d'envoi.

    Returns:
        Une phrase décrivant la cause et la correction attendue.
    """
    nom = type(exc).__name__
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return (
            f"{nom} : le relais a refusé l'identification. Gmail n'accepte plus "
            "le mot de passe du compte depuis mai 2022 — il faut un mot de passe "
            "d'application de 16 caractères, saisi sans espaces dans "
            "SMTP_PASSWORD."
        )
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return f"{nom} : le relais a refusé l'adresse du destinataire."
    if isinstance(exc, smtplib.SMTPSenderRefused):
        return (
            f"{nom} : le relais a refusé l'expéditeur. SMTP_FROM doit "
            "correspondre au compte authentifié par SMTP_USERNAME."
        )
    if isinstance(exc, smtplib.SMTPNotSupportedError):
        return (
            f"{nom} : le relais ne propose pas STARTTLS sur ce port. Utiliser "
            "le port 587 avec SMTP_STARTTLS=true."
        )
    if isinstance(exc, (TimeoutError, OSError)):
        return (
            f"{nom} : le relais est injoignable. Vérifier SMTP_HOST, SMTP_PORT, "
            "et qu'aucun pare-feu ne bloque la sortie sur ce port."
        )
    return nom


@dataclass
class MailJob:
    """Message prêt à être envoyé par le worker."""

    subject: str
    body: str
    recipient: str
    deduplication_key: str | None = None
    attempt: int = 0


class EmailNotifier:
    """File non bloquante avec déduplication des alertes."""

    def __init__(
        self,
        *,
        host: str | None,
        port: int,
        username: str | None,
        password: str | None,
        sender: str | None,
        recipient: str | None,
        starttls: bool,
        cooldown_minutes: float,
        minimum_severity: str,
        spool: str | Path | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.sender = sender
        self.recipient = recipient.strip().lower() if recipient else None
        self._default_recipient = self.recipient
        self._recipients: set[str] = {self.recipient} if self.recipient else set()
        # Trois threads touchent cet ensemble : HTTP (ouverture et
        # fermeture de session), rejeu (`notify`), worker (`_send`).
        self._recipients_lock = threading.RLock()
        self.starttls = starttls
        self.cooldown_seconds = cooldown_minutes * 60
        self.minimum_severity = minimum_severity
        self.transport_ready = bool(host and sender)

        # DEPOT LOCAL : UNE ESCALADE NON DELIVREE DOIT RESTER TRACABLE.
        #
        # Sans relais SMTP, la version precedente ne faisait rien du tout :
        # pas d'envoi, pas de trace, pas de moyen de verifier que la chaine
        # d'escalade fonctionne. Une supervision industrielle ne peut pas se
        # permettre ce silence — si le canal sortant tombe, il faut pouvoir
        # dire APRES COUP quelles alertes auraient du partir.
        #
        # Chaque message est donc ecrit sur disque au format RFC 822, avec un
        # etat explicite : 'envoye' quand le relais a accepte, 'depose' quand
        # il n'y a pas de relais, 'echec' quand le relais a refuse. Le journal
        # en memoire alimente l'interface; les fichiers restent apres arret.
        self.spool = Path(spool) if spool else None
        if self.spool is not None:
            try:
                self.spool.mkdir(parents=True, exist_ok=True)
            except OSError:
                self.spool = None
        self.journal_ready = self.spool is not None
        self.journal: list[dict[str, object]] = []

        self._jobs: queue.Queue[MailJob | None] = queue.Queue(maxsize=100)
        self._last_sent_by_key: dict[str, float] = {}
        self._pending_keys: set[str] = set()
        self._sent = 0
        self._spooled = 0
        # Alertes qualifiees qu'aucune adresse active ne pouvait recevoir.
        # Ce compteur rend visible un canal muet : il valait zero parce que
        # ces alertes n'etaient meme pas comptees.
        self._sans_destinataire = 0
        self._failed = 0
        self._suppressed = 0
        self._last_error: str | None = None
        self._worker: threading.Thread | None = None
        if self.transport_ready or self.journal_ready:
            self._worker = threading.Thread(
                target=self._run,
                daemon=True,
                name="e7301-email",
            )
            self._worker.start()

    @property
    def enabled(self) -> bool:
        """Un exutoire — relais ou dépôt — et un destinataire de quart."""
        with self._recipients_lock:
            actifs = bool(self._recipients)
        return bool((self.transport_ready or self.journal_ready) and actifs)

    def _tracer(self, job: MailJob, etat: str, detail: str = "") -> None:
        """Inscrit une escalade au journal, quel qu'ait été son sort."""
        entree = {
            "horodatage": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "objet": job.subject,
            "destinataire": job.recipient,
            "etat": etat,
            "detail": detail,
            "corps": job.body,
        }
        self.journal.insert(0, entree)
        del self.journal[200:]

    def _deposer(self, job: MailJob) -> None:
        """Écrit le message sur disque quand aucun relais n'est configuré."""
        if self.spool is None:
            raise RuntimeError("aucun dépôt configuré")
        message = EmailMessage()
        message["Subject"] = job.subject
        message["From"] = self.sender or "e7301@local"
        message["To"] = job.recipient
        message["Date"] = datetime.now(timezone.utc).strftime(
            "%a, %d %b %Y %H:%M:%S +0000")
        message.set_content(job.body)
        nom = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f") + ".eml"
        (self.spool / nom).write_bytes(bytes(message))

    def _destinataires(self) -> list[str]:
        """Instantane trie des destinataires, pris sous verrou.

        L'ENSEMBLE ETAIT LU ET MODIFIE PAR TROIS THREADS SANS AUCUN VERROU.
        `add_recipient` et `remove_recipient` sont appeles par le thread HTTP a
        l'ouverture et a la fermeture d'une session; `notify` le parcourt
        depuis le thread de rejeu.

        CE N'EST PAS L'ITERATION QUI CASSE — verification faite, `sorted()` sur
        un ensemble est atomique sous le GIL de CPython et ne leve jamais ici.
        Le defaut reel est la FENETRE DE COHERENCE de `remove_recipient`, qui
        retire l'adresse puis remet le destinataire par defaut en deux temps :
        entre les deux, l'ensemble est VIDE. Mesure sur 200 000 retraits, un
        observateur concurrent l'a vu vide 54 098 fois. Une alerte emise dans
        cette fenetre ne trouve aucun destinataire et disparait sans trace.

        S'y ajoute la lecture composite de `notify`, qui consulte `enabled`
        puis parcourt l'ensemble en deux acces distincts.

        Returns:
            Copie triee des destinataires.
        """
        with self._recipients_lock:
            return sorted(self._recipients)

    def set_recipient(self, recipient: str | None) -> None:
        """Remplace les destinataires (compatibilité mono-poste)."""
        with self._recipients_lock:
            self.recipient = recipient.strip().lower() if recipient else None
            self._recipients = {self.recipient} if self.recipient else set()

    def add_recipient(self, recipient: str) -> None:
        """Abonne une session technicien sans écraser les autres sessions."""
        normalized = recipient.strip().lower()
        if normalized:
            with self._recipients_lock:
                self._recipients.add(normalized)
                self.recipient = normalized

    def remove_recipient(self, recipient: str) -> None:
        """Désabonne uniquement la session qui se ferme."""
        with self._recipients_lock:
            self._recipients.discard(recipient.strip().lower())
            if self._default_recipient:
                self._recipients.add(self._default_recipient)
            self.recipient = sorted(self._recipients)[-1] if self._recipients else None

    def notify(self, analysis: Analysis) -> None:
        """Reçoit une analyse du rejeu sans jamais bloquer celui-ci."""
        severity = analysis.decision.severity
        rank = {"NORMAL": 0, "INFO": 1, "WARNING": 2, "CRITICAL": 3}
        # UNE ALERTE CRITIQUE SANS DESTINATAIRE DISPARAISSAIT SANS TRACE.
        #
        # Le garde etait `if not self.enabled` — or `enabled` exige un
        # destinataire actif. Sans session ouverte et sans `ALERT_EMAIL_TO`,
        # une decision CRITICAL validee par le controleur repartait donc en
        # silence : pas d'envoi, pas de fichier, pas de ligne de journal, pas
        # meme un increment de `_suppressed`. Rien.
        #
        # C'est l'exact contraire de ce que ce module promet en tete de
        # fichier : « si le canal sortant tombe, il faut pouvoir dire APRES
        # COUP quelles alertes auraient du partir ». Et le moment ou l'alerte
        # automatique compte le plus est precisement celui ou personne n'est
        # devant l'ecran — donc celui ou aucune session n'est ouverte.
        #
        # On ne garde plus que l'exutoire. L'absence de destinataire est
        # traitee plus bas, apres redaction du message, et laisse une trace.
        if not (self.transport_ready or self.journal_ready):
            return
        if not analysis.verdict.agreement:
            # Une décision rejetée par le contrôleur ne sort pas du poste :
            # c'est la règle. On la compte pour pouvoir la défendre.
            self._suppressed += 1
            return
        if rank.get(severity, 0) < rank.get(self.minimum_severity, 2):
            self._suppressed += 1
            return
        modes = analysis.decision.amdec_modes or ["SANS_MODE"]
        event_key = f"{severity}:{','.join(sorted(modes))}"
        now = time.time()
        subject = f"[E7301][{severity}] {', '.join(modes)}"
        # LE CORPS ETAIT ECRIT SANS ACCENTS — « Severite », « Equipement »,
        # « decision rejetee », « references operationnelles » — alors que le
        # depot impose l'inverse sur tout texte lu par un exploitant, et qu'un
        # test le verrouille. Ce message-ci echappait au corpus controle. La
        # note du controleur portait de surcroit un point decimal anglais.
        note = f"{analysis.verdict.global_score:.2f}".replace(".", ",")
        body = (
            f"Équipement : S-PC-E7301 — refroidisseur d'acide de séchage\n"
            f"Horodatage DCS : {analysis.decision.timestamp}\n"
            f"Sévérité : {severity}\n"
            f"Modes AMDEC suspectés : {', '.join(modes)}\n\n"
            f"Diagnostic : {analysis.decision.diagnosis}\n"
            f"Action recommandée : "
            f"{analysis.decision.recommended_action.description}\n"
            f"Urgence : {analysis.decision.recommended_action.urgency}\n"
            f"Contrôleur : {note}/10 — accord\n\n"
            "Aucune panne n'est confirmée : le système signale un écart de "
            "comportement,\nsa cause reste à établir sur le terrain.\n\n"
            "Ce message est un canal complémentaire. L'alarme HMI locale et "
            "les procédures\nOCP restent les références opérationnelles."
        )

        destinataires = self._destinataires()
        if not destinataires:
            # Aucune adresse active : on trace, on compte, on n'oublie pas.
            self._sans_destinataire += 1
            orphelin = MailJob(subject, body, "(aucun destinataire)", event_key)
            self._deposer(orphelin)
            self._tracer(
                orphelin,
                "non distribue",
                "aucun destinataire actif : aucune session ouverte et "
                "ALERT_EMAIL_TO non renseigné",
            )
            return

        for recipient in destinataires:
            key = f"{recipient}:{event_key}"
            if (
                key in self._pending_keys
                or now - self._last_sent_by_key.get(key, 0) < self.cooldown_seconds
            ):
                continue
            # Le cooldown n'est validé qu'après livraison SMTP réussie.
            self._pending_keys.add(key)
            self._enqueue(MailJob(subject, body, recipient, key))

    # FENETRE DE COURSE ENTRE `enabled` ET `_destinataires()[0]`.
    #
    # `enabled` verifie bien qu'un destinataire existe — verification faite,
    # ce n'etait donc pas un `IndexError` garanti. Mais il relache le verrou
    # avant de rendre la main, et ces deux methodes indexaient ENSUITE la liste
    # a `[0]`. Entre les deux, `remove_recipient` peut la vider : il est appele
    # par le thread HTTP a la fermeture d'une session.
    #
    # Le cas n'est pas theorique. C'est exactement ce qui se produit quand une
    # session expire pendant qu'un rapport part : `enabled` a repondu vrai, la
    # session tombe, l'indexation leve `IndexError` et l'envoi remonte en 500
    # sans qu'aucune trace ne dise pourquoi. Une seule lecture, et un retour
    # `False` conforme a la signature.
    def _premier_destinataire(self, souhaite: str | None = None) -> str | None:
        """Destinataire d'un envoi ponctuel, celui qui l'a demandé si possible.

        LE RAPPORT PARTAIT AU PREMIER PAR ORDRE ALPHABETIQUE. `_destinataires()`
        rend une liste TRIEE, et ces envois en prenaient l'element `[0]` — sans
        aucun rapport avec le technicien qui venait de cliquer. Avec deux
        adresses actives, « astreinte@… » passe avant « mounir@… » : le rapport
        demande par l'un arrivait chez l'autre, et l'interface annoncait un
        succes. La docstring de l'endpoint promet pourtant « envoie AU
        TECHNICIEN ».

        L'adresse demandee n'est retenue que si elle est deja destinataire
        actif : ce canal ne doit pas devenir un moyen d'expedier l'etat du poste
        vers une adresse arbitraire.
        """
        destinataires = self._destinataires()
        if souhaite:
            cible = souhaite.strip().lower()
            if cible in destinataires:
                return cible
        return destinataires[0] if destinataires else None

    def enqueue_test(self, demandeur: str | None = None) -> bool:
        """Ajoute un message de vérification de configuration."""
        destinataire = self._premier_destinataire(demandeur)
        if not self.enabled or destinataire is None:
            return False
        # NOTIF-1 — DEUX CORPS DE MESSAGE, DEUX TYPOGRAPHIES, DANS CE FICHIER.
        # Le rapport de gouvernance est intégralement accentué depuis
        # `redaction.py` ; celui-ci restait en « operationnel » et « associee ».
        # ADR-011 règle 3 annonce que le test de typographie « couvre toute
        # surface lisible » : cette chaîne n'est retournée par aucune API, elle
        # échappe donc au parcours du test. C'est pourtant le seul message que
        # le technicien reçoit quand il vérifie son propre canal.
        self._enqueue(MailJob(
            "[E7301] Test du canal de notification",
            "Le canal e-mail du poste E7301 est opérationnel.\n"
            "Aucune alerte procédé n'est associée à ce message : il ne vaut que "
            "comme vérification du relais et du destinataire.",
            destinataire,
        ))
        return True

    def enqueue_governance(self, report: str, demandeur: str | None = None) -> bool:
        """Envoie le rapport de gouvernance demandé par le technicien."""
        destinataire = self._premier_destinataire(demandeur)
        if not self.enabled or destinataire is None:
            return False
        self._enqueue(MailJob(
            "[E7301] Rapport de gouvernance du Judge",
            report,
            destinataire,
        ))
        return True

    def _enqueue(self, job: MailJob) -> None:
        try:
            self._jobs.put_nowait(job)
        except queue.Full:
            self._failed += 1
            self._last_error = "file de notification saturee"
            if job.deduplication_key:
                self._pending_keys.discard(job.deduplication_key)
            logger.warning("Notification E7301 abandonnee : file saturee")

    def _run(self) -> None:
        while True:
            job = self._jobs.get()
            if job is None:
                return
            try:
                if self.transport_ready:
                    self._send(job)
                    self._sent += 1
                    self._tracer(job, "envoye", f"relais {self.host}:{self.port}")
                else:
                    self._deposer(job)
                    self._spooled += 1
                    self._tracer(job, "depose",
                                 "aucun relais SMTP — message écrit dans le dépôt local")
                if job.deduplication_key:
                    self._last_sent_by_key[job.deduplication_key] = time.time()
                    self._pending_keys.discard(job.deduplication_key)
                self._last_error = None
            except Exception as exc:
                self._failed += 1
                self._last_error = diagnostiquer_echec(exc)
                logger.warning(
                    "Email E7301 non envoye (%s)",
                    type(exc).__name__,
                )
                if job.attempt < 2:
                    job.attempt += 1
                    self._enqueue(job)
                else:
                    self._tracer(job, "echec", self._last_error)
                    if job.deduplication_key:
                        self._pending_keys.discard(job.deduplication_key)

    def _send(self, job: MailJob) -> None:
        message = EmailMessage()
        message["Subject"] = job.subject
        message["From"] = self.sender
        message["To"] = job.recipient
        message.set_content(job.body)
        with smtplib.SMTP(self.host, self.port, timeout=10) as client:
            if self.starttls:
                client.starttls()
            if self.username:
                client.login(self.username, self.password or "")
            client.send_message(message)

    def status(self) -> dict[str, object]:
        """État public sans secret SMTP."""
        recipient = self.recipient or ""
        masked = (
            f"{recipient[:2]}***@{recipient.split('@', 1)[1]}"
            if "@" in recipient else None
        )
        # Dire POURQUOI le canal est inactif. Un simple « desactive » laisse
        # l'exploitant croire a une panne alors qu'il manque le plus souvent
        # une variable SMTP, ou simplement une session ouverte.
        if not self.transport_ready and self.journal_ready:
            reason = (
                "Aucun relais SMTP : les escalades sont écrites dans le dépôt "
                "local et tracées au journal ci-dessous. Renseigner SMTP_HOST "
                "et SMTP_FROM dans le fichier .env pour les faire partir."
            )
        elif not self.transport_ready:
            reason = (
                "Relais SMTP non configuré : renseigner SMTP_HOST et SMTP_FROM "
                "dans le fichier .env pour activer l'escalade."
            )
        elif not self._destinataires():
            # DIRE QUE L'ALERTE AUTOMATIQUE EST HORS SERVICE, PAS EN ATTENTE.
            # L'ancienne phrase decrivait un canal qui s'activerait tout seul a
            # la prochaine session. Elle laissait croire que la surveillance
            # etait couverte, alors qu'aucune alerte ne peut partir tant que
            # personne n'est connecte — c'est-a-dire la nuit, le week-end, et
            # pendant tout arret de poste.
            reason = (
                "AUCUNE ALERTE NE PEUT PARTIR. Aucun destinataire actif : "
                "l'adresse d'un technicien ne devient destinataire qu'à "
                "l'ouverture de sa session. Pour une escalade permanente, "
                "indépendante de toute session, renseigner ALERT_EMAIL_TO "
                "dans le fichier .env."
            )
        else:
            reason = ""

        return {
            "enabled": self.enabled,
            "transport_ready": self.transport_ready,
            "mode": "smtp" if self.transport_ready else (
                "depot" if self.journal_ready else "inactif"),
            "spool": str(self.spool) if self.spool else None,
            "spooled": self._spooled,
            "suppressed": self._suppressed,
            "undelivered_no_recipient": self._sans_destinataire,
            "journal": self.journal[:25],
            "reason": reason,
            "automatic": True,
            "requires_judge_agreement": True,
            "recipient": masked,
            "active_recipients": len(self._destinataires()),
            "minimum_severity": self.minimum_severity,
            "cooldown_minutes": self.cooldown_seconds / 60,
            "queued": self._jobs.qsize(),
            "sent": self._sent,
            "failed": self._failed,
            "last_error": self._last_error,
            "retry_policy": "3 tentatives maximum; cooldown après succès",
        }

    def stop(self) -> None:
        """Arrête le worker sans bloquer le service."""
        if self._worker is None:
            return
        try:
            self._jobs.put_nowait(None)
        except queue.Full:
            return
        self._worker.join(timeout=2)
