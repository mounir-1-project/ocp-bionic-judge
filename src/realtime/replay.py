"""
Simulateur de flux DCS — rejeu accelere des donnees reelles du E7301.

Pourquoi un rejeu plutot qu'un generateur synthetique
----------------------------------------------------------------------------
Simuler des donnees serait plus simple, et sans valeur : on ne prouverait que
la capacite du systeme a retrouver des anomalies qu'on y a soi-meme placees.
Le rejeu fait defiler les 10 180 heures REELLES de l'export DCS a vitesse
choisie. Le systeme rencontre donc les vraies pannes capteur, les vrais
arrets, les vraies excursions de temperature — dans l'ordre ou elles se sont
produites, sans connaitre la suite.

Le simulateur ne voit jamais le futur : a l'instant t, seule la fenetre
[debut, t] est transmise a la detection. C'est cette contrainte qui rend la
demonstration honnete.

Author: Mounir Sanbouli — Stage OCP, Programme Bionic
"""

from __future__ import annotations

import threading
from collections import deque
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd
from loguru import logger

from src.pipeline import Analysis, E7301Pipeline


@dataclass
class ReplayState:
    """Etat courant du rejeu, consultable par l'API et le dashboard.

    Attributes:
        running: Le rejeu est-il actif ?
        speed: Nombre d'heures de process simulees par seconde reelle.
        cursor: Horodatage courant dans les donnees.
        n_processed: Nombre d'instants traites depuis le demarrage.
        started_at: Instant de demarrage reel.
        history: Dernieres analyses produites (fenetre glissante).
        alerts: Analyses de severite WARNING ou CRITICAL.
        disagreements: Analyses rejetees par le Judge.
    """

    running: bool = False
    speed: float = 60.0
    cursor: str | None = None
    n_processed: int = 0
    started_at: str | None = None
    history: deque[Analysis] = field(default_factory=lambda: deque(maxlen=500))
    alerts: deque[Analysis] = field(default_factory=lambda: deque(maxlen=200))
    disagreements: deque[Analysis] = field(default_factory=lambda: deque(maxlen=100))

    def snapshot(self) -> dict[str, Any]:
        """Vue instantanee serialisable de l'etat du rejeu."""
        return {
            "running": self.running,
            "speed_hours_per_second": self.speed,
            "cursor": self.cursor,
            "n_processed": self.n_processed,
            "started_at": self.started_at,
            "n_alerts": len(self.alerts),
            "n_disagreements": len(self.disagreements),
        }


class DCSReplay:
    """Rejoue l'historique DCS comme s'il arrivait en direct.

    Attributes:
        pipeline: Chaine d'analyse complete.
        state: Etat courant du rejeu.
    """

    def __init__(
        self,
        pipeline: E7301Pipeline,
        speed: float = 60.0,
        start: str | None = None,
        analyze_every: int = 1,
    ) -> None:
        """Initialise le simulateur.

        Args:
            pipeline: Chaine E7301 deja construite.
            speed: Heures de process simulees par seconde reelle. 60 signifie
                   qu'une journee de process defile en 0,4 seconde.

                   L'EXEMPLE PRECEDENT DISAIT « 24 secondes », ce qui decrit
                   une vitesse de 1 h/s, soit soixante fois moins. Il
                   contredisait a la fois le libelle de l'unite, le nom du
                   champ publie par l'API (`speed_hours_per_second`) et le
                   code. Trois enonces pour un seul reglage, dont deux faux.
            start: Horodatage de depart. Par defaut, le debut des donnees.
            analyze_every: Analyser un instant sur N (allege la charge en
                           rejeu tres rapide).
        """
        if speed <= 0:
            raise ValueError("La vitesse de rejeu doit etre strictement positive")
        if analyze_every <= 0:
            raise ValueError("analyze_every doit etre strictement positif")

        self.pipeline = pipeline
        self.state = ReplayState(speed=float(speed))
        self._index = pipeline.features.index
        if start:
            self._index = self._index[self._index >= pd.Timestamp(start)]
        if self._index.empty:
            raise ValueError("Aucune donnee disponible pour le debut de rejeu demande")
        self._analyze_every = analyze_every
        self._obligatoires = self._instants_incontournables()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._subscribers: list[Callable[[Analysis], None]] = []

    def _instants_incontournables(self) -> set:
        """Instants qu'un allègement de charge n'a pas le droit de sauter.

        UNE DECIMATION AVEUGLE PEUT SAUTER LE SEUL INSTANT QUI COMPTE.

        Le rejeu n'analysait qu'un instant sur `analyze_every` — trois par
        defaut — en choisissant sur la seule position dans la serie. Sur ce
        corpus, un unique horodatage atteint la severite critique en marche
        etablie : le 2 octobre 2024 a 18 h, temperature de sortie acide a
        72,15 degC, position 6 610 dans la serie. 6 610 n'est pas multiple de
        trois. Depart au debut des donnees, cet instant n'etait donc JAMAIS
        analyse : pas de rouge sur le jumeau, pas d'alarme ouverte, pas
        d'escalade. Le seul evenement critique de quatorze mois disparaissait
        par une regle de performance.

        Le pas d'allegement est conserve — il tient la latence quand le rejeu
        defile a plusieurs centaines d'heures par seconde — mais il ne
        s'applique plus qu'aux instants ordinaires. Tout instant qui franchit
        un seuil d'alarme du referentiel est analyse, quelle que soit sa
        position. Le filtre est vectoriel et calcule une seule fois : son cout
        est celui d'une comparaison de colonnes, pas d'une analyse.
        """
        table = self.pipeline.features
        if table.empty:
            return set()
        domaine = self.pipeline.domain
        marque = pd.Series(False, index=table.index)

        def seuil(alias: str, cle: str):
            try:
                return domaine.get(alias).threshold(cle)
            except Exception:
                return None

        franchissements = [
            ("T_ACID_OUT", "alarm_high", "ge"),
            ("T_ACID_OUT", "alarm_high_high", "ge"),
            ("T_ACID_IN", "alarm_high", "ge"),
            ("T_ACID_IN", "alarm_high_high", "ge"),
            ("F_ACID", "alarm_low", "le"),
            ("F_ACID", "alarm_low_low", "le"),
        ]
        for colonne, cle, sens in franchissements:
            valeur = seuil(colonne, cle)
            if valeur is None or colonne not in table:
                continue
            serie = table[colonne]
            test = serie >= valeur if sens == "ge" else serie <= valeur
            marque |= test.fillna(False)

        for cle in ("alarm_low", "alarm_low_low"):
            valeur = seuil("C_ACID_1100", cle)
            if valeur is not None and "conc_min" in table:
                marque |= (table["conc_min"] <= valeur).fillna(False)

        # Un franchissement pendant un arret ne designe rien : la regle
        # d'etat le neutralise de toute facon en aval. On garde malgre tout
        # les regimes transitoires, ou la perte de controle s'installe.
        if "process_state" in table:
            marque &= table["process_state"].isin(["RUNNING", "TRANSIENT"])

        # On retient des HORODATAGES, pas des positions : le rejeu peut demarrer
        # au milieu de la serie, auquel cas les positions ne coincident plus.
        instants = set(table.index[marque])
        if instants:
            logger.info(
                f"Rejeu — {len(instants)} instant(s) a franchissement de seuil "
                f"seront analyses meme au pas {self._analyze_every}"
            )
        return instants

    # ── Abonnement ───────────────────────────────────────────────────────────

    def subscribe(self, callback: Callable[[Analysis], None]) -> None:
        """Enregistre un observateur appele a chaque analyse.

        Args:
            callback: Fonction recevant l'Analysis produite.
        """
        self._subscribers.append(callback)

    # ── Execution ────────────────────────────────────────────────────────────

    def _emit(self, analysis: Analysis) -> None:
        """Publie une analyse aupres de l'etat et des abonnes.

        Args:
            analysis: Analyse a publier.
        """
        with self._lock:
            self.state.cursor = analysis.detection.timestamp
            self.state.n_processed += 1
            self.state.history.append(analysis)
            if analysis.decision.severity in ("WARNING", "CRITICAL"):
                self.state.alerts.append(analysis)
            if not analysis.verdict.agreement:
                self.state.disagreements.append(analysis)

        for cb in self._subscribers:
            try:
                cb(analysis)
            except Exception as e:
                logger.warning(f"Abonne en erreur ({type(e).__name__}: {e})")

    def _loop(self) -> None:
        """Boucle de rejeu executee dans un thread dedie."""
        logger.info(f"Rejeu demarre — {len(self._index)} instants, "
                    f"vitesse {self.state.speed} h/s")

        for i, ts in enumerate(self._index):
            if self._stop.is_set():
                break
            if i % self._analyze_every == 0 or ts in self._obligatoires:
                try:
                    # Le rejeu doit conserver une latence bornee, meme si un
                    # service de redaction externe est lent ou indisponible.
                    self._emit(self.pipeline.analyze_at(ts, use_llm=False))
                except Exception as e:
                    logger.warning(f"Analyse impossible a {ts} ({type(e).__name__}: {e})")
            # LE PAS D'ALLEGEMENT NE DOIT PAS ENTRER DANS LA TEMPORISATION.
            #
            # Le delai etait `analyze_every / speed`, applique a CHAQUE entree
            # d'index, c'est-a-dire a chaque heure de process. La vitesse
            # effective valait donc `speed / analyze_every`. Avec les valeurs
            # par defaut du depot — REPLAY_SPEED=120, REPLAY_STEP=3 — le rejeu
            # defilait a 40 h/s pendant que l'API publiait
            # `speed_hours_per_second: 120`. Un facteur trois sur le seul
            # reglage que l'exploitant manipule.
            #
            # Une entree d'index vaut une heure de process : le delai est donc
            # `1 / speed`, quel que soit le nombre d'instants analyses.
            #
            # Attente interruptible : stop() doit rester immediat meme a basse
            # vitesse. La vitesse est relue a chaque tour pour que set_speed()
            # prenne effet sans redemarrer le rejeu.
            with self._lock:
                delay = 1.0 / self.state.speed
            if self._stop.wait(delay):
                break

        with self._lock:
            self.state.running = False
        logger.info(f"Rejeu termine — {self.state.n_processed} instants analyses")

    def start(self) -> None:
        """Demarre le rejeu en arriere-plan.

        Sans effet si un rejeu est deja en cours.
        """
        with self._lock:
            if self.state.running:
                logger.warning("Rejeu deja en cours")
                return
            self.state.running = True
            self.state.started_at = datetime.now().isoformat()
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._loop, daemon=True, name="dcs-replay"
            )
        self._thread.start()

    def stop(self) -> None:
        """Arrete le rejeu et attend la fin du thread."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        with self._lock:
            self.state.running = False

    def set_speed(self, speed: float) -> None:
        """Change la vitesse de rejeu a chaud.

        Args:
            speed: Nouvelle vitesse en heures de process par seconde.
        """
        value = float(speed)
        if value <= 0:
            raise ValueError("La vitesse de rejeu doit etre strictement positive")
        with self._lock:
            self.state.speed = value

    def snapshot(self) -> dict[str, Any]:
        """Retourne un etat coherent pendant que le thread travaille."""
        with self._lock:
            return self.state.snapshot()

    # ── Mode synchrone ───────────────────────────────────────────────────────

    def run_sync(self, limit: int | None = None) -> Iterator[Analysis]:
        """Rejoue sans thread ni temporisation, pour les tests et les scripts.

        Args:
            limit: Nombre maximal d'instants a traiter.

        Yields:
            Analysis pour chaque instant.
        """
        # LE MODE SYNCHRONE SAUTAIT LES INSTANTS INCONTOURNABLES.
        #
        # Il decimait par simple decoupage `[::analyze_every]`, sans consulter
        # `_obligatoires`. La garantie etablie par `_instants_incontournables`
        # — aucun franchissement de seuil ne peut etre saute par une regle de
        # performance — ne valait donc que pour la boucle threadee. Or c'est ce
        # chemin-ci qu'empruntent les tests et les scripts hors ligne : la
        # propriete etait affirmee dans un chemin et verifiee dans l'autre.
        positions = set(self._index[::self._analyze_every])
        idx = self._index[
            self._index.isin(positions | self._obligatoires)
        ]
        if limit:
            idx = idx[:limit]
        for ts in idx:
            try:
                a = self.pipeline.analyze_at(ts, use_llm=False)
            except Exception as e:
                logger.warning(f"Analyse impossible a {ts} ({type(e).__name__})")
                continue
            self._emit(a)
            yield a

    # ── Restitution ──────────────────────────────────────────────────────────

    def recent(self, n: int = 50) -> list[dict[str, Any]]:
        """Dernieres analyses produites.

        Args:
            n: Nombre d'elements souhaites.

        Returns:
            Liste de dictionnaires serialisables, du plus recent au plus ancien.
        """
        with self._lock:
            items = list(self.state.history)[-n:]
        return [_compact(a) for a in reversed(items)]

    def alerts(self, n: int = 50) -> list[dict[str, Any]]:
        """Dernieres alertes (severite WARNING ou CRITICAL).

        Args:
            n: Nombre d'elements souhaites.

        Returns:
            Liste de dictionnaires serialisables.
        """
        with self._lock:
            items = list(self.state.alerts)[-n:]
        return [_compact(a) for a in reversed(items)]

    def disagreements(self, n: int = 50) -> list[dict[str, Any]]:
        """Dernieres decisions rejetees par le Judge.

        Args:
            n: Nombre d'elements souhaites.

        Returns:
            Liste de dictionnaires serialisables.
        """
        with self._lock:
            items = list(self.state.disagreements)[-n:]
        return [_compact(a, full=True) for a in reversed(items)]


def _compact(a: Analysis, full: bool = False) -> dict[str, Any]:
    """Reduit une Analysis a une forme legere pour le transport reseau.

    Args:
        a: Analyse a compacter.
        full: Inclure le detail des controles du Judge.

    Returns:
        Dictionnaire serialisable.
    """
    out: dict[str, Any] = {
        "timestamp": a.detection.timestamp,
        "process_state": a.detection.process_state,
        "severity": a.decision.severity,
        "anomaly_score": a.detection.anomaly_score,
        "amdec_modes": a.decision.amdec_modes,
        "diagnosis": a.decision.diagnosis,
        "action": a.decision.recommended_action.description,
        "urgency": a.decision.recommended_action.urgency,
        "confidence": a.decision.confidence,
        "judge_score": a.verdict.global_score,
        "judge_agreement": a.verdict.agreement,
        "judge_issues": a.verdict.flagged_issues,
        "judge_feedback": a.verdict.feedback,
        "measurements": a.detection.measurements,
        "findings": [
            {"code": f.code, "severity": f.severity, "source": f.source,
             "amdec_mode": f.amdec_mode, "message": f.message}
            for f in a.detection.findings
        ],
    }
    if full:
        out["checks"] = [c.model_dump() for c in a.verdict.checks]
        out["attributions"] = a.detection.attributions
    return out


if __name__ == "__main__":
    pipe = E7301Pipeline(use_llm=False)
    replay = DCSReplay(pipe, speed=1e9, start="2024-10-20", analyze_every=6)
    n_alert = 0
    for a in replay.run_sync(limit=60):
        if a.decision.severity in ("WARNING", "CRITICAL"):
            n_alert += 1
            print(a.summary_line())
    print(f"\n{replay.state.n_processed} instants rejoues, {n_alert} alertes, "
          f"{len(replay.state.disagreements)} desaccords du Judge")
