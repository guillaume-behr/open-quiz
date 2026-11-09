# Politique de sécurité

La sécurité des comptes et des données scolaires est une priorité d’Open Quiz.
Merci de signaler les vulnérabilités de manière privée afin de laisser le temps
d’analyser et de corriger le problème avant sa divulgation.

## 📌 Versions prises en charge

Open Quiz est encore en préversion et seule la branche par défaut est maintenue.

| Version                        | Correctifs de sécurité |
| ------------------------------ | ---------------------- |
| Dernier état de `master`       | oui                    |
| Versions et commits antérieurs | non                    |

Les changements incompatibles et les actions requises à la mise à jour sont
décrits dans le [journal des modifications](CHANGELOG.md) et dans le
[guide de déploiement](docs/deployment.md#-mettre-à-jour-open-quiz).

## 🚨 Signaler une vulnérabilité

Utilisez le
[formulaire privé de vulnérabilité GitHub](https://github.com/guillaume-behr/open-quiz/security/advisories/new).
N’ouvrez pas d’issue ou de pull request publique et n’incluez aucune donnée
réelle d’élève, information d’authentification ou clé secrète.

Si le formulaire privé est indisponible, ne publiez aucun détail technique.
Demandez d’abord aux mainteneurs, sans information sensible, de vous indiquer
un canal privé depuis le dépôt GitHub.

Incluez si possible :

- le composant, la version ou le commit concerné ;
- les préconditions et étapes de reproduction minimales ;
- l’impact observé ou probable ;
- une preuve de concept sans donnée réelle et sans action destructive ;
- une proposition de correction, si vous en avez une ;
- vos préférences de crédit lors de la publication.

Les mainteneurs accuseront réception dès que possible, vérifieront le rapport,
partageront l’état d’avancement dans l’advisory et coordonneront la divulgation.
Si vous n’avez reçu aucun retour après sept jours, relancez dans le même canal
privé.

## 🇬🇧 Reporting a vulnerability in English

Reports in English are welcome. Use the
[private GitHub vulnerability form](https://github.com/guillaume-behr/open-quiz/security/advisories/new);
do not open a public issue or pull request, and include no real student data,
credentials or secret keys. Only the latest state of `master` receives
security fixes. Please include the affected component or commit, minimal
reproduction steps, the impact, and a non-destructive proof of concept. If
you get no answer within seven days, follow up in the same private channel.

## 🎯 Périmètre

Sont notamment dans le périmètre :

- l’API, l’interface et les conteneurs fournis par ce dépôt ;
- les contournements d’authentification ou d’autorisation ;
- l’accès croisé aux données d’un autre enseignant ou élève ;
- l’exposition de secrets, jetons, mots de passe ou réponses privées ;
- les injections, corruptions de données et failles de téléversement ;
- une dépendance vulnérable lorsqu’un scénario exploitable affecte Open Quiz.

Ne sont pas considérés comme une vulnérabilité du projet :

- l’absence de protection physique ou système de la machine hôte ;
- une instance déployée sans HTTPS ou avec des secrets d’exemple ;
- l’indisponibilité de l’API expérimentale `Translator` d’un navigateur ;
- les alertes de surveillance manquantes ou falsifiées par un élève ;
- les attaques par déni de service nécessitant de perturber une instance réelle ;
- les failles d’un service tiers sans impact démontré sur Open Quiz.

## 🤝 Recherche de bonne foi

Pour limiter les risques :

- utilisez votre propre instance et des comptes de test ;
- accédez uniquement aux données nécessaires à la démonstration ;
- n’exfiltrez, ne modifiez et ne supprimez aucune donnée réelle ;
- n’effectuez ni ingénierie sociale, ni hameçonnage, ni déni de service ;
- n’installez aucune persistance et ne contournez pas les limites au-delà du
  minimum nécessaire ;
- laissez aux mainteneurs un délai raisonnable avant toute publication.

Les recherches qui respectent ces règles seront traitées comme des démarches de
bonne foi. La divulgation publique sera coordonnée après la disponibilité d’un
correctif ou d’une mesure de réduction du risque.

## 🧱 Frontières de confiance

Les alertes de surveillance d’un quiz proviennent du navigateur de l’élève.
Elles sont informatives, non exhaustives et non résistantes à la falsification.
Elles ne constituent pas une preuve d’intégrité et ne doivent pas déclencher
seules une sanction ou une décision automatique.

Les extraits Python s’exécutent localement dans un Web Worker. Après le
chargement de Pyodide, les API réseau, de stockage et de création d’autres
Workers sont remplacées, sur l’objet global comme sur ses prototypes. Cette
liste d’interdictions limite les capacités du code, mais ne transforme pas le
navigateur en frontière de sécurité équivalente à une isolation système : un
navigateur peut exposer demain une API qu’elle ne nomme pas. Les deux
protections qui ne dépendent pas d’elle sont la politique CSP, qui ne laisse le
Worker joindre que l’origine de l’instance, et la preuve de renouvellement
décrite ci-dessous, sans laquelle une requête émise par le Worker n’ouvre
aucune session.

Les sessions privilégiées exigent une preuve de renouvellement conservée dans
la fenêtre principale et inaccessible au Worker Python. Les autorisations et la
notation restent appliquées par le backend.

Un navigateur qui a validé la double authentification n’en redemande pas le
code avant minuit, heure de l’appareil, et 24 heures au plus : le mot de passe
reste exigé. Ce cookie HttpOnly n’ouvre aucune session seul ; le voler sans le
mot de passe ne donne rien. Sur un poste partagé, une simple déconnexion le
conserve : effacez les données de l’appareil depuis `/cookie-settings`, ou
désactivez la fonction avec `TWO_FACTOR_BROWSER_TRUST=false`.

Les tentatives de connexion sont comptées par identifiant, jamais par adresse
IP : n’importe qui peut donc épuiser celles d’un compte dont il connaît
l’identifiant. Un navigateur qui a validé la double authentification du compte
le jour même dispose de son propre compteur et reste utilisable ; sans lui, le
compte attend la fin de la fenêtre. Pour un élève, l’enseignant débloque le
compte en l’enregistrant de nouveau. Borner ce qu’une même adresse peut envoyer
relève du reverse proxy (voir le
[guide de déploiement](docs/deployment.md#-publier-lapplication-en-https)).

Les identifiants élèves sont uniques pour toute l’instance, puisqu’ils servent
à se connecter : un enseignant qui en crée ou en importe un déjà pris apprend
qu’il existe, sans rien savoir de son propriétaire.

Les mots de passe élèves sont volontairement réversibles : l’enseignant doit
pouvoir réimprimer une carte d’identifiants sans réinitialiser le compte. Ils
sont donc stockés deux fois, sous forme de condensat Argon2 pour la
vérification et sous forme chiffrée par `STUDENT_CREDENTIAL_ENCRYPTION_KEY`
pour la consultation. Ce choix a une conséquence à assumer : le chiffrement
protège une base seule — une sauvegarde égarée, un export de table — mais pas
un hôte compromis, car dans le déploiement Compose par défaut la clé et
`DATABASE_URL` résident dans le même fichier `.env`, sur la même machine. Qui
lit la base peut donc, en pratique, lire aussi la clé.

Ces mots de passe sont aussi lisibles par l’enseignant connecté, sans nouvelle
saisie du code de double authentification : un jeton d’accès enseignant volé
suffit, pendant sa durée de vie (`ACCESS_TOKEN_MINUTES`), à les obtenir tous.
Chaque consultation et chaque export sont journalisés
(`students.credentials_viewed`, `students.credentials_exported`).

Deux conséquences en découlent. Les élèves réutilisant fréquemment leurs mots
de passe ailleurs, la portée d’une compromission dépasse cette application :
traitez ces identifiants comme des données personnelles à part entière.
Si les sauvegardes constituent le risque principal du déploiement, fournir
`STUDENT_CREDENTIAL_ENCRYPTION_KEY` par variable d’environnement injectée au
démarrage, plutôt que par un fichier voisin des données, rétablit l’essentiel
du bénéfice attendu.

Les comptes enseignants et administrateurs ne sont pas concernés : leurs mots
de passe ne sont stockés que sous forme de condensat et ne sont jamais
consultables.

## 🔥 Réagir à un secret compromis

Révoquez ou remplacez d’abord le secret dans le système actif. Nettoyer
l’historique Git ne suffit pas à rendre un secret sûr.

1. retirez immédiatement le secret de l’environnement exposé ;
2. changez `JWT_SECRET` pour révoquer toutes les sessions ;
3. changez `ADMIN_PASSWORD` si le compte administrateur peut être concerné ;
4. ne changez `TOTP_ENCRYPTION_KEY` qu’en acceptant de réinscrire tous les
   comptes TOTP ;
5. ne changez `STUDENT_CREDENTIAL_ENCRYPTION_KEY` qu’en acceptant de
   réinitialiser les mots de passe élèves pour les rendre à nouveau
   consultables ;
6. redémarrez ou recréez le backend pour charger les nouvelles valeurs ;
7. examinez les événements d’audit, les accès à la base et les sauvegardes ;
8. retirez enfin le secret de l’historique accessible et des caches associés.

Le [guide d’exploitation](docs/deployment.md#-gérer-les-secrets-et-les-accès)
détaille les effets de chaque rotation.
