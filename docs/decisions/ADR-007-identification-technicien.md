# ADR-007 — Compte individuel par technicien

**Statut** : accepté
**Portée** : sécurité et escalade

---

## Problème

L'adresse saisie à l'ouverture de session n'est pas décorative : elle devient
le **destinataire des états critiques** retenus par le contrôleur de cohérence.

Une première implémentation reposait sur un mot de passe unique partagé par
toutes les adresses autorisées. C'est inacceptable dès lors que l'identité
déclenche l'envoi d'un courriel d'intervention :

- n'importe quel technicien pouvait ouvrir une session sous l'adresse d'un
  collègue avec le secret d'équipe ;
- le journal d'authentification ne pouvait plus dire qui s'était connecté ;
- un départ n'était pas révocable individuellement.

## Décision

Un registre local attribue à **chaque technicien son propre mot de passe**,
haché en PBKDF2-SHA256 à 600 000 itérations avec un sel distinct.

```
python scripts/manage_operators.py add | list | passwd | remove
```

L'accès protégé **s'active de lui-même** dès qu'un compte existe : aucune
variable d'environnement à positionner, donc aucun oubli possible.

## Choix de mise en œuvre

- Le mot de passe n'est **jamais** accepté en argument de ligne de commande :
  il apparaîtrait dans l'historique du terminal et la liste des processus.
  Saisie masquée, avec confirmation, douze caractères minimum.
- Une adresse inconnue déclenche quand même une dérivation PBKDF2, afin que le
  temps de réponse ne révèle pas quelles adresses sont enregistrées.
- Cinq tentatives échouées depuis un même poste bloquent la fenêtre.
- Session opaque en cookie HttpOnly, jeton CSRF distinct, expiration sur
  inactivité et expiration absolue.
- Le registre vit hors du dépôt, en droits restreints, et ne contient que des
  empreintes.

## Escalade

À l'ouverture de session, l'adresse devient destinataire ; à la déconnexion,
elle cesse de l'être. Un état critique ne déclenche un envoi que s'il est
**retenu par le contrôleur de cohérence** : une décision rejetée ne réveille
personne. Les envois sont dédoublonnés par un délai anti-répétition.

## Portée

Ce registre est un mécanisme mono-poste. En exploitation, il cède la place au
fournisseur d'identité de l'entreprise : le mode production refuse de démarrer
sans intégration OIDC.
