# Journal des versions

Les changements importants d’Open Quiz sont regroupés dans ce fichier.

## 0.2.1 — En développement

### Sécurité et corrections

- les questions à choix multiples sans points négatifs n’accordent plus de
  points lorsqu’une proposition incorrecte est également sélectionnée ;
- un type de réponse masqué utilise désormais la même représentation générique
  côté API et interface pour les choix simples et multiples ;
- les banques utilisées par un examen actif sont temporairement retirées des
  entraînements de la classe, et les entraînements correspondants sont révoqués
  au lancement ;
- la surveillance signale aussi les copies, collages et ouvertures du menu
  contextuel, quelle que soit la longueur du contenu ;
- adoption exclusive de PostgreSQL 17 dans Docker Compose ; cette transition
  repart d’une base vide et ne fournit pas de reprise historique ;
- la limitation des signalements anonymes n'utilise plus jamais l'adresse IP :
  le budget est désormais global à l'instance (`PROBLEM_REPORT_ATTEMPTS`, 30
  par défaut en développement et 5 dans l’exemple de production) ;
- la connexion élève vérifie toujours le mot de passe, même pour un
  identifiant inconnu, afin de ne pas révéler les comptes existants par le
  temps de réponse ;
- les mots de passe élèves générés gagnent deux chiffres (10 caractères) ;
- les codes de rattrapage sont protégés contre la force brute par un quota par
  compte élève ;
- les réponses envoyées simultanément ne peuvent plus créer de doublons ni
  provoquer d'erreur 500 (écriture atomique) ;
- les exécutions Python demandées simultanément sont sérialisées afin que leurs
  sorties et erreurs ne puissent plus se mélanger ;
- les démarrages, réponses, corrections et suppressions concurrents sont
  sérialisés afin de préserver l’état des sessions et des résultats ;
- la fin d'un rattrapage termine aussi les sessions en pause et la reprise
  tolère les durées de pause héritées ;
- l'historique élève couvre toutes les classes du compte ;
- le cookie de session est supprimé avec les mêmes attributs qu'à sa création ;
- audit des créations, modifications et suppressions de comptes élèves ;
- validation renforcée des connexions HTTP et WebSocket, avec authentification
  bornée, contrôle d’origine et reconnexion progressive ;
- test réseau conteneurisé couvrant l’API, le proxy et les WebSockets ;
- Dependabot activé pour GitHub Actions, Docker, uv et npm.
- mise à jour de `pip` dans l’outillage de développement vers une version
  corrigée de `PYSEC-2026-3721`.

### Ajouts

- installation Docker guidée par `install.sh`, avec saisie du domaine,
  génération locale des secrets, création sécurisée de `.env` et lancement du
  script de mise à jour ;
- exemple Nginx simplifié avec transmission conditionnelle de la mise à niveau
  WebSocket et chaîne d’en-têtes `X-Forwarded-*` protégée contre l’usurpation ;
- comptes élèves avec identifiant, mot de passe et tableau de bord dédié ;
- routes séparées `/student/*` et `/teacher/*` ;
- gestion indépendante des élèves et des classes ;
- examens créés séparément et banques d’entraînement affectées par classe ;
- entraînements relançables librement avec correction immédiate ;
- score potentiel et historique de progression des entraînements ;
- sessions de rattrapage limitées à des examens déjà passés par la classe ;
- tirage individuel des questions au lancement pour chaque élève ;
- option permettant de partager exactement le même tirage entre tous les
  élèves d’une session ;
- ordre aléatoire propre à chaque élève ;
- quantités explicites de questions par difficulté, limitées par les banques ;
- barème défini sur chaque proposition de réponse ;
- import JSON atomique de plusieurs classes et de leurs comptes élèves, avec
  aperçu et exemple téléchargeable ;
- quantité de questions configurable pour chaque banque d’entraînement d’une
  classe ;
- impression A4 de sujets d’examen nominatifs avec randomisation déterministe ;
- mises à jour temps réel des sessions actives, rattrapages, participants et
  résultats par WebSocket authentifié ;
- publication des notes après correction complète et historique consultable
  par l’élève.

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
  fichier cohérents et accessibles ;
- les résultats indiquent les corrections en attente et les barèmes atypiques
  directement à côté du nom de l’élève ;
- une note publiée ne peut plus être modifiée ;
- les alertes de surveillance distinguent les collages importants des saisies
  ordinaires et couvrent aussi les tentatives d’impression.

### Modifications incompatibles

- l’entrée en examen nécessite désormais un compte élève authentifié ;
- les pourcentages de difficulté sont remplacés par des quantités ;
- les points sont désormais définis sur les propositions des banques de questions ;
- l’ancien écran public permettant de rejoindre un quiz est remplacé par la
  connexion élève.

### Documentation

- Docker Compose devient la méthode d’installation présentée en premier dans
  toute la documentation ; les lancements directs avec Python et Vite sont
  explicitement réservés au développement ;
- ajout d’un guide d’exploitation couvrant HTTPS, sauvegardes, restauration,
  mises à jour, secrets, conservation et dépannage ;
- mise à jour des documentations backend et frontend à partir des commandes,
  routes et contraintes réellement présentes dans le dépôt ;
- enrichissement des guides de contribution et de sécurité ainsi que des
  modèles d’issues et de pull request.

## 0.1.0 — 2026-08-02

- première préversion publiée ;
- gestion des enseignants, classes, banques de questions et sessions ;
- correction automatique et manuelle, traduction locale et export CSV ;
- déploiement autonome avec Docker Compose, Caddy et une base embarquée.
