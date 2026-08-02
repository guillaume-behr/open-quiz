# Journal des versions

Les changements importants d’Open Quiz sont regroupés dans ce fichier.

## 0.2.0 — En développement

### Ajouts

- comptes élèves avec identifiant, mot de passe et tableau de bord dédié ;
- routes séparées `/student/*` et `/teacher/*` ;
- gestion indépendante des élèves et des classes ;
- quiz d’examen et d’entraînement créés dans des onglets distincts ;
- entraînements relançables librement avec correction immédiate ;
- tirage commun ou individuel des questions au lancement d’un examen ;
- ordre aléatoire propre à chaque élève, y compris avec un tirage commun ;
- quantités explicites de questions par difficulté, limitées par les banques ;
- barème défini par difficulté dans le quiz et réparti entre les questions.

### Modifications incompatibles

- l’entrée en examen nécessite désormais un compte élève authentifié ;
- les anciens élèves sans compte sont supprimés lors de la migration ;
- les pourcentages de difficulté sont remplacés par des quantités ;
- les points ne sont plus définis sur les propositions des banques de questions ;
- l’ancien écran public permettant de rejoindre un quiz est remplacé par la
  connexion élève.

## 0.1.0 — 2026-08-02

- première préversion publiée ;
- gestion des enseignants, classes, banques de questions et sessions ;
- correction automatique et manuelle, traduction locale et export CSV ;
- déploiement autonome avec Docker Compose, Caddy et SQLite.
