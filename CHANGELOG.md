# Journal des versions

Les changements importants d’Open Quiz sont regroupés dans ce fichier.

## 0.2.0 — En développement

### Sécurité et corrections

- la limitation des signalements anonymes n'utilise plus jamais l'adresse IP :
  le budget est désormais global à l'instance (`PROBLEM_REPORT_ATTEMPTS`, 30
  par défaut) ;
- la connexion élève vérifie toujours le mot de passe, même pour un
  identifiant inconnu, afin de ne pas révéler les comptes existants par le
  temps de réponse ;
- les mots de passe élèves générés gagnent deux chiffres (10 caractères) ;
- les codes de rattrapage sont protégés contre la force brute par un quota par
  compte élève ;
- les réponses envoyées simultanément ne peuvent plus créer de doublons ni
  provoquer d'erreur 500 (écriture atomique) ;
- la fin d'un rattrapage termine aussi les sessions en pause et la reprise
  tolère les durées de pause héritées ;
- l'historique élève couvre toutes les classes du compte ;
- le cookie de session est supprimé avec les mêmes attributs qu'à sa création ;
- audit des créations, modifications et suppressions de comptes élèves ;
- Dependabot activé pour GitHub Actions, Docker, uv et npm.

### Ajouts

- comptes élèves avec identifiant, mot de passe et tableau de bord dédié ;
- routes séparées `/student/*` et `/teacher/*` ;
- gestion indépendante des élèves et des classes ;
- examens créés séparément et banques d’entraînement affectées par classe ;
- entraînements relançables librement avec correction immédiate ;
- score potentiel et historique de progression des entraînements ;
- sessions de rattrapage limitées à des examens déjà passés par la classe ;
- tirage individuel des questions au lancement pour chaque élève ;
- ordre aléatoire propre à chaque élève ;
- quantités explicites de questions par difficulté, limitées par les banques ;
- barème défini sur chaque proposition de réponse ;
- import JSON atomique de plusieurs classes et de leurs comptes élèves, avec
  aperçu et exemple téléchargeable ;
- quantité de questions configurable pour chaque banque d’entraînement d’une
  classe ;
- impression A4 de sujets d’examen nominatifs avec randomisation déterministe.

### Interface

- les questions d’une banque sont triées par difficulté par défaut, repliables
  avec animation et conservent la position de liste après édition ;
- la progression d’un quiz affiche uniquement `Question X sur Z` ;
- la navigation entre questions défile horizontalement à gauche du bouton de
  validation, qui reste aligné à droite ;
- les énoncés et réponses rédactionnelles utilisent toute la largeur disponible ;
- les contrôles non rédactionnels n’affichent plus de curseur de saisie ;
- l’écran de passage d’un entraînement n’affiche plus d’icône de mode ;
- les imports de classes et de banques utilisent des boutons de sélection de
  fichier cohérents et accessibles.

### Modifications incompatibles

- l’entrée en examen nécessite désormais un compte élève authentifié ;
- les anciens élèves sans compte sont supprimés lors de la migration ;
- les pourcentages de difficulté sont remplacés par des quantités ;
- les points sont désormais définis sur les propositions des banques de questions ;
- l’ancien écran public permettant de rejoindre un quiz est remplacé par la
  connexion élève.

## 0.1.0 — 2026-08-02

- première préversion publiée ;
- gestion des enseignants, classes, banques de questions et sessions ;
- correction automatique et manuelle, traduction locale et export CSV ;
- déploiement autonome avec Docker Compose, Caddy et SQLite.
