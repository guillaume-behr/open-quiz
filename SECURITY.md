# Politique de sécurité

## Versions prises en charge

Open Quiz est encore en préversion. Seul le dernier état de la branche par
défaut reçoit des correctifs de sécurité. Aucune ancienne version publiée n’est
actuellement maintenue.

## Signaler une vulnérabilité

N’ouvrez pas d’issue publique et n’incluez aucune donnée réelle d’élève,
information d’authentification ou clé secrète.

Utilisez le
[formulaire privé de vulnérabilité GitHub](https://github.com/guillaume-behr/open-quiz/security/advisories/new).
Incluez si possible :

- le composant et la version ou le commit concernés ;
- les préconditions et étapes de reproduction minimales ;
- l’impact observé ou probable ;
- une proposition de correction, si vous en avez une ;
- vos préférences de crédit lors de la publication.

Les mainteneurs accuseront réception dès que possible, vérifieront le rapport,
prépareront un correctif et coordonneront la divulgation. Évitez toute
exploitation au-delà de ce qui est strictement nécessaire à la démonstration.

## Frontières de confiance

Les alertes de surveillance d’un quiz proviennent du navigateur de l’élève.
Elles sont informatives, non exhaustives et non résistantes à la falsification.
Elles ne constituent pas une preuve d’intégrité et ne doivent pas déclencher
seules une sanction ou une décision automatique.

Les extraits Python s’exécutent localement dans un Worker sans API réseau après
le chargement du runtime. Les sessions authentifiées exigent également une
preuve de renouvellement conservée dans la fenêtre principale et inaccessible
au Worker.

## Secrets compromis

Si un secret de production est exposé, retirez-le immédiatement de son système
d’origine et de l’historique accessible, puis :

- changez `JWT_SECRET` pour révoquer les sessions ;
- changez le mot de passe administrateur ;
- ne changez `TOTP_ENCRYPTION_KEY` qu’en acceptant de réinscrire tous les
  comptes TOTP ;
- examinez les événements d’audit et les accès à la base.
