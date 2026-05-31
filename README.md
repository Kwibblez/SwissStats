# SwissStats — Guide d'installation

\---

## Prérequis

* Python 3.10+
* PostgreSQL 14+ **avec PostGIS**
* Un compte Strava

\---

## 1\. Cloner le projet

```bash
git clone https://github.com/Kwibblez/SwissStats.git
cd SwissStats
```

\---

## 2\. Environnement Python

```bash
# Windows
python -m venv venv
venv\\Scripts\\activate

# macOS / Linux
python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt
```

### Dépendances (requirements.txt)

```
flask>=3.0
psycopg2-binary>=2.9
python-dotenv>=1.0
requests>=2.31

```

\---

## 3\. Configuration de l'API Strava

### Créer une application Strava

1. Connectez-vous sur [strava.com/settings/api](https://www.strava.com/settings/api)
2. Cliquez sur **Créer une application** et remplissez les champs :

|Champ|Valeur|
|-|-|
|Nom de l'application|SwissStats (ou un autre nom marche aussi)|
|Catégorie|Data Importer (idem)|
|Site web|`http://localhost:5000/callback`|
|Domaine du rappel|`localhost`|

3. Notez votre **Client ID** et **Client Secret**

<img src="/static/figures/imgs/strava_api_settings.jpeg" alt="description" width="500">


 L'URL de callback doit correspondre exactement à `STRAVA\_REDIRECT\_URI` dans votre `.env`.

\---

## 4\. Base de données PostgreSQL + PostGIS

### Créer la base de données et activer PostGIS

Dans **pgAdmin** ou **psql** :

```sql
CREATE DATABASE "stravaGeoInfo";
\\c stravaGeoInfo
CREATE EXTENSION IF NOT EXISTS postgis;
```

### Restaurer depuis le dump

Un dump complet est fourni dans le dossier `dump/` :

> Si vous partez d'une base vide, les tables sont créées automatiquement au premier lancement via `init\_db()`.

### Structure de la base de données

La base contient deux tables principales :

**Table `users`** — stocke les tokens OAuth Strava de chaque utilisateur.

!\[Table users](https://github.com/Kwibblez/SwissStats/blob/main/static/figures/imgs/table\_users.jpeg)

**Table `activities`** — stocke toutes les activités avec leur géométrie PostGIS.

!\[Table activities](https://github.com/Kwibblez/SwissStats/blob/main/static/figures/imgs/table\_activities.jpeg)

La géométrie des tracés GPS est stockée dans la colonne `track\_geom` de type `GEOMETRY(LINESTRING, 4326)`, indexée avec un index GIST pour les requêtes spatiales.

\---

## 5\. Variables d'environnement

```bash
cp .env.example .env
```

Contenu du `.env` :

```env
# ── Strava API ──────────────────────────────────────────────
STRAVA\_CLIENT\_ID=votre\_client\_id
STRAVA\_CLIENT\_SECRET=votre\_client\_secret
STRAVA\_REDIRECT\_URI=http://localhost:5000/callback

# ── Flask ────────────────────────────────────────────────────
FLASK\_SECRET\_KEY=une\_cle\_secrete\_longue\_et\_aleatoire

# ── PostgreSQL ───────────────────────────────────────────────
POSTGRES\_DB=stravaGeoInfo
POSTGRES\_USER=postgres
POSTGRES\_PASSWORD=votre\_mot\_de\_passe
POSTGRES\_HOST=localhost
POSTGRES\_PORT=5432
```



\---

## 6\. Lancer l'application

```bash
python app.py
```

Ouvrez [http://localhost:5000](http://localhost:5000).

\---

## 7\. Première utilisation

1. Cliquez sur **Connecter mon compte Strava**
2. Autorisez l'application
3. Cliquez sur **Sync Strava**, sélectionnez l'année et attendez
4. Vos parcours apparaissent sur la carte

\---



## Structure du projet

```
SwissStats/
├── app.py              # Application Flask + PostGIS
├── db.py               # Connexion PostgreSQL
├── strava\_api.py       # Wrapper API Strava
├── schema.sql          # Schéma PostGIS
├── requirements.txt
├── .env.example
├── dump/               # Dump de la base de données        
├── static/
│   ├── css/main.css
├   ├── figures/imgs/
│   └── js/
│       ├── map.js      # Carte Leaflet + WMS swisstopo + mesure
│       └── stats.js
└── templates/
    ├── login.html
    ├── map.html
    └── stats.html
```

\---

## Fonctionnalités

* **Carte interactive Leaflet** avec tracés GPS colorés par sport (PostGIS `ST\_AsGeoJSON`)
* **Fonds de carte** : CartoDB, Swisstopo couleur, Swisstopo gris (WMS `wms.geo.admin.ch`)
* **Outil de mesure** — mesurez distances et surfaces directement sur la carte
* **Filtres** — par année et par type de sport
* **Popup détaillé** — distance, durée, dénivelé, vitesse, FC, calories
* **Export GPX** — téléchargez le tracé de chaque activité
* **Statistiques annuelles** — résumé complet avec graphiques
* **Stats fun** — vaches, tours du lac Léman, altitude du Cervin, fondues…
* **Synchronisation** — barre de progression en temps réel

\---

## Dépannage

|Problème|Solution|
|-|-|
|`could not open extension control file postgis`|PostGIS n'est pas installé — utilisez Stack Builder|
|`UndefinedColumn: track\_geom`|Supprimez les tables et relancez `python app.py`|
|`400 Bad Request` OAuth Strava|Vérifiez que `STRAVA\_REDIRECT\_URI` correspond exactement à l'URL Strava|
|CSS non chargé|Vérifiez que `static/` est en minuscules dans git|
|`relation "users" does not exist`|Exécutez `schema.sql` dans pgAdmin|
|`NoneType is not subscriptable`|Reconnectez-vous à Strava avant de lancer la sync|



