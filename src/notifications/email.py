"""Canal email pour les alertes E7301.

Envoie un email au technicien connecté lorsqu'une panne est détectée
(WARNING ou CRITICAL). Version simplifiée : envoi synchrone, sans queue.

Author: Mounir Sanbouli — Stage OCP, Programme Bionic
"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Any

from loguru import logger


class EmailNotifier:
    """Envoi email simple pour les alertes."""

    def __init__(
        self,
        host: str | None = None,
        port: int = 587,
        username: str | None = None,
        password: str | None = None,
        sender: str | None = None,
        starttls: bool = True,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.sender = sender
        self.starttls = starttls
        self._recipients: set[str] = set()
        self._sent_count = 0

    @property
    def enabled(self) -> bool:
        """Le canal est-il configuré ?"""
        return bool(self.host and self.sender)

    def add_recipient(self, email: str) -> None:
        """Ajoute un destinataire (technicien connecté)."""
        self._recipients.add(email)
        logger.info(f"Email — destinataire ajouté: {email}")

    def remove_recipient(self, email: str) -> None:
        """Retire un destinataire."""
        self._recipients.discard(email)

    def notify(self, analysis: Any) -> None:
        """Envoie une alerte email si panne détectée (appele par le replay).

        Args:
            analysis: Resultat de l'analyse (objet Analysis).
        """
        if not self.enabled or not self._recipients:
            return

        severity = getattr(analysis.decision, "severity", "NORMAL")
        if severity not in ("WARNING", "CRITICAL"):
            return

        # Construire le message
        subject = f"[E7301] Alerte {severity} — {analysis.detection.timestamp}"
        body = self._build_body(analysis)

        # Envoyer à tous les destinataires
        for recipient in self._recipients:
            try:
                self._send_email(recipient, subject, body)
                self._sent_count += 1
                logger.info(f"Email envoyé à {recipient} — {severity}")
            except Exception as e:
                logger.error(f"Échec envoi email à {recipient}: {e}")

    def _build_body(self, analysis: Any) -> str:
        """Construit le corps de l'email."""
        d = analysis.detection
        dec = analysis.decision
        v = analysis.verdict

        lines = [
            f"ALERTE E7301 — {dec.severity}",
            f"",
            f"Horodatage: {d.timestamp}",
            f"État process: {d.process_state}",
            f"Score anomalie: {d.anomaly_score:.3f}",
            f"",
            f"DIAGNOSTIC:",
            f"{dec.diagnosis}",
            f"",
            f"RAISONNEMENT:",
            f"{dec.reasoning}",
            f"",
            f"CONFIANCE: {dec.confidence:.2f}",
            f"JUDGE: {v.global_score:.2f}/10 ({'ACCORD' if v.agreement else 'DÉSACCORD'})",
            f"",
            f"ACTION RECOMMANDÉE:",
            f"{dec.recommended_action.description}",
            f"Urgence: {dec.recommended_action.urgency}",
        ]

        if dec.recommended_action.requires_shutdown:
            lines.append("⚠ ARRÊT REQUIS")

        lines.extend([
            f"",
            f"---",
            f"Système de surveillance E7301 — OCP Bionic Judge",
        ])

        return "\n".join(lines)

    def _send_email(self, recipient: str, subject: str, body: str) -> None:
        """Envoie un email via SMTP."""
        if not self.host or not self.sender:
            return

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self.sender
        msg["To"] = recipient
        msg.set_content(body)

        with smtplib.SMTP(self.host, self.port) as server:
            if self.starttls:
                server.starttls()
            if self.username and self.password:
                server.login(self.username, self.password)
            server.send_message(msg)

    def enqueue_test(self, demandeur: str | None = None) -> bool:
        """Envoie un email de test."""
        if not self.enabled:
            return False
        # Utiliser le demandeur comme destinataire s'il est fourni
        recipient = demandeur or next(iter(self._recipients), None)
        if not recipient:
            return False
        try:
            self._send_email(recipient, "[E7301] Test de notification", "Email de test fonctionnel.")
            self._sent_count += 1
            return True
        except Exception as e:
            logger.error(f"Échec email de test: {e}")
            return False

    def status(self) -> dict[str, Any]:
        """État du canal."""
        return {
            "enabled": self.enabled,
            "configured": self.enabled,
            "host": self.host,
            "sender": self.sender,
            "recipient_count": len(self._recipients),
            "recipients": list(self._recipients),
            "sent_count": self._sent_count,
        }

    def stop(self) -> None:
        """Rien a arreter."""
        pass
