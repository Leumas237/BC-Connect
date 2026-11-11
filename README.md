# BC Connect

BC Connect est une plateforme communautaire étudiante destinée à
l'Institut Universitaire de Technologie Fotso Victor (IUT-FV) de Bandjoun,
rattaché à l'Université de Dschang.

L'objectif est de faciliter les connexions entre étudiants de toutes les
filières : entraide, affinités, vie de campus et rencontres. L'application
reprend les principes fonctionnels de SJDA-v3, adaptés à l'identité et au
contexte de l'IUT-FV.

> **État actuel :** version fonctionnelle en revue. Le socle FastAPI + SQLite +
> PWA couvre l'inscription, la validation KYI, les profils, la découverte, les
> matchs, le mur communautaire et la modération. Les tests de durcissement et
> la préparation de production restent à finaliser.

## 1. Vision du produit

BC Connect doit rester :

- **fédérateur** : toutes les filières de l'IUT-FV ont leur place ;
- **direct** : une expérience simple, pensée pour le mobile ;
- **sûr** : identité étudiante vérifiée avant l'accès à la communauté ;
- **sobre techniquement** : une architecture adaptée à quelques centaines
  ou milliers d'étudiants, sans complexité prématurée ;
- **respectueux de la vie privée** : les données sensibles et les réseaux
  sociaux ne sont visibles que dans le contexte prévu.

Les lieux et usages du campus peuvent être intégrés au ton de l'application :
les amphis, le foyer, le terrain de volley, le Club 100 et les différents
départements.

## 2. Identité visuelle

| Élément | Valeur |
| --- | --- |
| Nom | BC Connect |
| Établissement | IUT-FV de Bandjoun |
| Couleur principale | `#FF2A54` |
| Fond principal | `#0F172A` |
| Texte principal | `#FFFFFF` |
| Police des titres | Space Grotesk |
| Police du contenu | Inter |

Le ton de marque est inclusif, dynamique, étudiant et orienté vers
l'esprit d'équipe. Le logo doit évoquer la connectivité et les liens
inter-amphis sans se limiter à un symbole informatique.

## 3. Architecture cible

L'architecture cible suit les principes de `DevKit.txt` de SJDA-v3 :

```text
backend/
  main.py       # routes API, règles métier et WebSocket
  auth.py       # mots de passe, sessions et dépendances d'accès
  db.py         # schéma SQLite et connexions
  config.py     # configuration par variables d'environnement
  push.py       # notifications Web Push

frontend/
  index.html    # vues de la SPA
  app.js        # état client, navigation, découverte et appels API
  style.css     # thème BC Connect et responsive design
  sw.js         # cache hors-ligne et notifications push
  manifest.json # installation PWA
  icons/        # icônes 192x192 et 512x512

data/           # données persistantes, ignorées par Git
  bc_connect.db
  uploads/      # photos de profil
  kyi/          # cartes étudiantes, jamais publiques
  vapid_private.pem
```

La version actuelle utilise directement le frontend PWA cible. Le backend
expose déjà le socle d'authentification ; les fonctionnalités métier seront
ajoutées par lots afin de pouvoir les relire et les valider séparément.

### Principes techniques

- un seul processus FastAPI sert l'API, le WebSocket et le frontend ;
- SQLite est suffisant pour l'échelle initiale du campus ;
- le dossier `data/` constitue la sauvegarde complète de l'instance ;
- aucune donnée sensible ne doit être exposée par le serveur statique ;
- HTTPS est obligatoire en production pour la PWA, le WebSocket et le push.

## 4. Parcours étudiant prévu

1. Création d'un compte.
2. Soumission du dossier KYI : nom officiel, date de naissance, classe et
   photo de la carte étudiante.
3. Attente de validation par un administrateur.
4. Création et modification du profil.
5. Découverte des profils compatibles.
6. Actions d'intérêt ou de passage, avec quota quotidien.
7. Match réciproque.
8. Déblocage des réseaux sociaux uniquement après le match.
9. Signalement et blocage depuis un match.

Le profil doit couvrir les différents cycles de l'IUT-FV :

- DUT 1 et DUT 2 ;
- BTS 1 et BTS 2 ;
- Licence de technologie et licence professionnelle ;
- Master 1 et Master 2.

Les filières et spécialités seront centralisées dans la configuration ou
dans une table dédiée afin d'éviter de disperser des listes en dur dans
l'interface.

## 5. Fonctionnalités prévues

### Authentification et validation

- inscription et connexion par email et mot de passe ;
- sessions par jeton opaque ;
- validation KYI obligatoire avant l'accès à la découverte ;
- validation et refus par les administrateurs ;
- suppression complète d'un compte et de ses fichiers associés.

### Profils

- biographie, filière, classe et cycle ;
- centres d'intérêt ;
- intention : amis, couple ou les deux ;
- préférences de recherche ;
- âge facultatif ;
- jusqu'à six photos de profil ;
- mode invisible.

### Découverte et matchs

- cartes mobiles avec glissement tactile ;
- filtres par âge, cycle, filière et classe ;
- exclusion des profils déjà traités ;
- quota quotidien d'actions positives ;
- annulation du dernier swipe ;
- match seulement en cas d'intérêt réciproque.

BC Connect ne prévoit pas de messagerie interne dans la première version.
Après un match, les réseaux sociaux autorisés sont révélés pour permettre
aux étudiants de poursuivre l'échange sur les plateformes adaptées.

### Mon mur

- publications texte et image visibles par les membres validés ;
- réactions et commentaires ;
- suppression de ses propres publications par l'auteur ;
- onglets séparés pour le mur, le Swipe et la modération.

### Modération

- tableau de bord administrateur ;
- demandes KYI en attente ;
- signalements ;
- bannissement et classement des signalements ;
- statistiques d'usage ;
- journal d'activité exportable en CSV ;
- code d'invitation modérateur renouvelable depuis le dashboard ;
- notifications temps réel pour les événements importants.

### Notifications et PWA

- installation sur téléphone ;
- fonctionnement hors-ligne de la coquille de l'application ;
- notification d'un nouveau match ;
- notification d'une demande KYI ;
- notification d'un signalement ;
- nettoyage automatique des abonnements push expirés.

## 6. Configuration

Les variables prévues sont :

```text
BC_APP_NAME=BC Connect
BC_EMAIL_DOMAINS=
BC_MOD_CODE=
BC_ADMIN_EMAILS=
BC_DAILY_LIKES=15
BC_SPAM_STRIKES_BAN=30
BC_DATA_DIR=./data
```

`BC_EMAIL_DOMAINS` peut rester vide si l'inscription doit accepter tous les
emails, comme décidé pour la première version BC Connect. Dans ce cas, la
validation KYI et la modération deviennent les contrôles principaux
d'appartenance à la communauté.

Ne jamais committer un fichier `.env`, un mot de passe, une clé VAPID ou une
carte étudiante.

## 7. Données et sécurité

Les garanties suivantes sont non négociables :

1. Les cartes étudiantes de `data/kyi/` ne sont jamais servies comme fichiers
   statiques.
2. Les réseaux sociaux ne sont jamais renvoyés dans la découverte.
3. Le compteur « qui m'a liké » reste anonyme.
4. Un refus ou une suppression efface aussi les fichiers du compte.
5. Un utilisateur banni devient immédiatement invisible et ses sessions sont
   invalidées.
6. Les mots de passe utilisent PBKDF2-SHA256 avec comparaison en temps
   constant.
7. Tout contenu utilisateur affiché côté client passe par un échappement HTML.
8. Les actions qui dépassent le quota sont enregistrées avant de lever une
   erreur HTTP volontaire.

Le dossier `data/` doit être sauvegardé régulièrement. Il contient la base,
les photos, les dossiers KYI et les clés nécessaires aux notifications push.

## 8. Développement local

Lancer la version actuelle :

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn backend.main:app --reload --port 8000
```

Puis ouvrir <http://localhost:8000>. Le bouton « Vérifier l'API » et le
formulaire d'inscription permettent de vérifier rapidement l'installation.

Pour une base de test administrateur :

```powershell
$env:BC_ADMIN_EMAILS = "admin@example.com"
uvicorn backend.main:app --reload --port 8000
```

Le compte créé avec cette adresse est administrateur et validé
automatiquement. La validation KYI n'est pas encore implémentée dans v0.1.

Pendant le développement frontend, penser à mettre à jour le numéro de
cache dans `frontend/sw.js` après toute modification de `index.html`,
`app.js` ou `style.css`.

## 9. Bêta publique sur Render

HTTPS est obligatoire. Une mise en ligne Render, Railway ou un VPS Docker
est adaptée à l'échelle initiale.

La configuration `render.yaml` prépare un service `bc-connect-beta` avec
un disque persistant dédié monté sur `/app/data`, une base neuve et un
health check sur `/api/health`. Les variables marquées `sync: false` doivent
être renseignées dans Render avant le premier déploiement, notamment
`BC_ADMIN_EMAILS`.

Le stockage persistant doit être monté sur `/app/data` ou configuré via
`BC_DATA_DIR`. Sans volume persistant, un redéploiement supprimerait la
base, les photos, les dossiers KYI et les clés push.

Exemple conceptuel :

```powershell
docker build -t bc-connect .
docker run -d -p 8000:8000 `
  -v C:\bc-connect-data:/app/data `
  -e BC_ADMIN_EMAILS=admin@example.com `
  -e BC_MOD_CODE=<secret> `
  bc-connect
```

Avant chaque mise en production :

- vérifier les variables secrètes ;
- tester l'inscription et la validation KYI ;
- vérifier qu'un dossier KYI n'est pas accessible par URL publique ;
- vérifier les droits administrateur ;
- tester un match, un signalement et un bannissement ;
- vérifier les notifications push ;
- sauvegarder `data/` ;

Pour la bêta publique :

- utiliser une base Render neuve, sans données de développement ;
- créer un compte avec une adresse de `BC_ADMIN_EMAILS` ;
- communiquer aux testeurs l’URL bêta et un canal de retour ;
- surveiller les logs, les signalements et l'espace disque ;
- sauvegarder le disque avant toute migration ou modification de schéma.
- incrémenter le cache du service worker.

## 10. Tests manuels essentiels

La recette minimale doit couvrir :

1. inscription, connexion et déconnexion ;
2. soumission KYI avec fichier trop volumineux et fichier valide ;
3. validation et refus par un administrateur ;
4. modification du profil après validation ;
5. découverte et exclusion des profils déjà swipés ;
6. quota quotidien et suspension anti-spam ;
7. match réciproque et déblocage des réseaux sociaux ;
8. signalement, fermeture du match et blocage mutuel ;
9. suppression complète du compte ;
10. accès refusé aux cartes KYI sans session administrateur.

## 11. Périmètre de la v0.1

### Inclus

- landing page BC Connect ;
- configuration par variables d'environnement ;
- SQLite persistante dans `data/` ;
- inscription avec validation basique de l'email ;
- mot de passe PBKDF2-SHA256 ;
- session Bearer opaque ;
- connexion, récupération de compte et déconnexion ;
- interface responsive et installable comme PWA ;
- Dockerfile de lancement ;
- endpoints `/api/health`, `/api/config`, `/api/register`, `/api/login`,
  `/api/me` et `/api/logout`.
- gestion des photos de profil jusqu'à six fichiers ;
- découverte, swipes, matchs et réseaux sociaux débloqués après match ;
- signalements, bannissement et invalidation des sessions ;
- WebSocket de notification de match ;
- abonnement Web Push et envoi VAPID si les clés sont configurées ;
- export et suppression du compte ;
- politique de confidentialité accessible depuis l'application.

### Non inclus

- tests automatisés complets ;
- migrations SQLite versionnées au-delà des migrations de compatibilité ;
- génération et rotation automatisées des clés VAPID ;
- validation juridique finale et désignation formelle du responsable du
  traitement.

## 12. Protection des données au Cameroun

BC Connect traite notamment des données de compte, de profil, de photos et
de vérification KYI. La page `/static/privacy.html` présente la politique de
confidentialité de travail et les contrôles implémentés :

- acceptation explicite de la politique à l'inscription ;
- stockage des cartes étudiantes hors du répertoire statique ;
- accès KYI limité aux administrateurs ;
- export et suppression du compte ;
- absence des réseaux sociaux dans la découverte ;
- conservation des photos et du KYI dans `data/`, à sauvegarder et à purger
  selon une durée définie par l'exploitant ;
- consentement et documentation des sous-traitants avant tout transfert.

La politique s'appuie sur la loi camerounaise n°2024/017 du 23 décembre 2024
relative à la protection des données à caractère personnel et la loi
n°2010/012 du 21 décembre 2010 relative à la cybersécurité et à la
cybercriminalité. Le responsable du traitement doit compléter ses coordonnées,
fixer la durée de conservation et faire valider le dispositif par un conseil
juridique camerounais avant mise en production.

## 13. Historique de la documentation

Cette documentation est adaptée du `DevKit.txt` de SJDA-v3 et sert de
contrat de conception pour BC Connect. Toute nouvelle fonctionnalité doit
préserver les invariants de sécurité et de confidentialité ci-dessus.
