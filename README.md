# BC Connect

BC Connect est une plateforme communautaire étudiante destinée à
l'Institut Universitaire de Technologie Fotso Victor (IUT-FV) de Bandjoun,
rattaché à l'Université de Dschang.

L'objectif est de faciliter les connexions entre étudiants de toutes les
filières : entraide, affinités, vie de campus et rencontres. L'application
reprend les principes fonctionnels de SJDA-v3, adaptés à l'identité et au
contexte de l'IUT-FV.

> **État actuel :** le dépôt démarre de zéro. Une première landing page
> BC Connect est présente dans `bc_connect/`. Le backend, l'authentification,
> la validation KYI, la découverte et la modération sont encore à construire.

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

Le premier squelette Reflex présent dans `bc_connect/` sert de maquette
visuelle initiale. Il sera progressivement remplacé ou intégré au frontend
PWA cible lorsque le backend sera mis en place.

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

### Modération

- tableau de bord administrateur ;
- demandes KYI en attente ;
- signalements ;
- bannissement et rétablissement ;
- promotion ou retrait du rôle modérateur ;
- journal d'activité ;
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

La commande cible, une fois le backend installé, sera :

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn backend.main:app --reload --port 8000
```

Puis ouvrir <http://localhost:8000>.

Pendant le développement frontend, penser à mettre à jour le numéro de
cache dans `frontend/sw.js` après toute modification de `index.html`,
`app.js` ou `style.css`.

## 9. Mise en production

HTTPS est obligatoire. Une mise en ligne Render, Railway ou un VPS Docker
est adaptée à l'échelle initiale.

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

## 11. Historique de la documentation

Cette documentation est adaptée du `DevKit.txt` de SJDA-v3 et sert de
contrat de conception pour BC Connect. Toute nouvelle fonctionnalité doit
préserver les invariants de sécurité et de confidentialité ci-dessus.
