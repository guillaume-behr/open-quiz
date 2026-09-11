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

Les changements incompatibles et les précautions de mise à jour sont décrits
dans les notes de chaque release et dans le
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
chargement de Pyodide, les API réseau et la création d’autres Workers sont
désactivées. Cette restriction limite les capacités du code, mais ne transforme
pas le navigateur en frontière de sécurité équivalente à une isolation système.

Les sessions privilégiées exigent une preuve de renouvellement conservée dans
la fenêtre principale et inaccessible au Worker Python. Les autorisations et la
notation restent appliquées par le backend.

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
