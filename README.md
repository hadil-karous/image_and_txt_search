# Prisme — recherche textuelle et visuelle d’images

Projet universitaire Python 3.12 : catalogue SQLite/FTS5, signatures HSV/LBP/HOG, recherche exhaustive et VP-Tree exact, API FastAPI et interface Streamlit en français. L’interface appelle exclusivement l’API HTTP.

Les données locales sont **MIRFLICKR-25K : 25 000 images et 25 000 fichiers de tags**. Deux archives MPEG-7 MIRFLICKR-1M sont également présentes : Edge Histogram et Homogeneous Texture, intégrées pour **24 988 images dont la correspondance a été vérifiée par contenu**. Objects et les images du million ne sont pas fournis. Couverture, tests et mesures : [rapport](docs/rapport.md), [inventaire](docs/data_inventory.md), [vérification MPEG-7](docs/mpeg7.md). Aucun résultat de recherche sur un million d’images n’est revendiqué.

## Installation PowerShell

Depuis la racine du projet :

```powershell
Set-Location C:\aim_tborbi\projet
```

`.venv` utilise CPython Windows 3.12. Le `python` global de cette machine est une version MSYS2 sans pip : utiliser les commandes explicites ci-dessous. Pour recréer l’environnement avec `uv` :

```powershell
uv python install 3.12
uv venv --python 3.12 --seed .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
```

Sur un autre PC avec le lanceur Python et CPython 3.12 :

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
```

`requirements.txt` exprime les plages compatibles ; `requirements-lock.txt` fige l’environnement validé. Recréer `.venv` sur chaque PC.

## Préparation hors ligne

Les images locales restent sous `data/raw/mirflickr_25k/images/mirflickr25k/mirflickr/`. L’import découvre les sous-dossiers sans dupliquer les images. Les tags sont dans `annotations/meta/tags/`. L’import est idempotent et conserve les identifiants existants.

```powershell
.\.venv\Scripts\python.exe -m scripts.inspect_data
.\.venv\Scripts\python.exe -m scripts.import_dataset --dataset mirflickr_25k
.\.venv\Scripts\python.exe -m scripts.extract_features --dataset mirflickr_25k --workers 4
.\.venv\Scripts\python.exe -m scripts.build_indexes --dataset mirflickr_25k
```

`--limit 100` permet un essai d’import ou d’extraction. Pour un essai isolé, définir `IMAGE_SEARCH_DATA_DIR` vers un petit échantillon avec son `meta/`. L’import complet ne supprime pas les lignes existantes. Une extraction interrompue reprend les lots compatibles avec la même commande et les mêmes paramètres. Une modification de sélection ou de paramètres crée une nouvelle génération. Les manifestes indiquent la couverture réelle.

Configuration d’un disque externe, à définir dans **chaque terminal** concerné :

```powershell
$env:IMAGE_SEARCH_DATA_DIR = 'D:\image-search-data'
.\.venv\Scripts\python.exe -c "from backend.config import get_settings; print(get_settings().data_dir)"
```

Les chemins relatifs sont résolus depuis le projet. Conserver la disposition `raw/`, `processed/` et `catalog.sqlite3`. Préparer les fichiers serveur arrêté et **redémarrer FastAPI après import, extraction ou reconstruction** : les ressources sont chargées une fois au démarrage.

## MPEG-7 sans extraction massive

Les deux ZIP originaux sont conservés dans `data/raw/mirflickr_1m/descriptors/`. Les commandes suivantes inspectent directement les ZIP, vérifient les identités d’images, importent uniquement les membres utiles et construisent leurs propres index :

```powershell
.\.venv\Scripts\python.exe -m scripts.inspect_mpeg7
.\.venv\Scripts\python.exe -m scripts.verify_mpeg7_mapping
.\.venv\Scripts\python.exe -m scripts.import_mpeg7
.\.venv\Scripts\python.exe -m scripts.build_indexes --methods mpeg7_edgehistogram mpeg7_homogeneoustexture
```

La vérification utilise des requêtes HTTP Range vers l’archive officielle des images : environ 13,5 Mo de répertoire ZIP et d’exemples, avec plafond de 32 Mio. L’archive de 12,5 Go n’est jamais téléchargée intégralement. Le fichier de correspondance déjà livré permet de refaire l’import local sans réseau.

Résultat par famille : **24 988 vecteurs**, dimensions **150** et **43**, aucun membre manquant parmi les images associées. Douze images dont le contenu diffère de la référence sont exclues. Les valeurs fournies sont stockées en float32, accompagnées d’IDs internes alignés et d’un manifeste ; aucun fichier individuel du ZIP n’est extrait. Les matrices HSV/LBP/HOG sont conservées. Redémarrer FastAPI après préparation pour charger les nouvelles ressources.

## Lancement

Terminal 1, depuis la racine :

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Terminal 2, depuis la racine :

```powershell
.\.venv\Scripts\python.exe -m streamlit run frontend/app.py --server.address 127.0.0.1 --server.port 8501 --browser.gatherUsageStats false
```

Interface : **http://127.0.0.1:8501**. Documentation API : **http://127.0.0.1:8000/docs**. Pour une autre adresse API, définir `$env:IMAGE_SEARCH_API_URL = 'http://127.0.0.1:8000'` dans le terminal Streamlit.

## Tests, CLI et benchmarks

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m scripts.search_cli --keywords 'sky water'
.\.venv\Scripts\python.exe -m scripts.search_cli --query-id 1 --descriptors hsv lbp --weights 1 1 --k 12
.\.venv\Scripts\python.exe -m scripts.benchmark --sizes 500 2500 25000 --queries 20 --k 10
```

Avec l’API en marche :

```powershell
.\.venv\Scripts\python.exe -m scripts.smoke_demo
.\.venv\Scripts\python.exe -m scripts.validate_interface
.\.venv\Scripts\python.exe -m scripts.validate_mpeg7
```

Les tests utilisent des images synthétiques temporaires. Les benchmarks et la validation HTTP utilisent les données réelles. CSV bruts, médianes, p95, construction/chargement et graphique : `benchmarks/`. Le script vérifie l’accord exact du VP-Tree avec l’exhaustif, égalités départagées par identifiant. Aucun gain de vitesse n’est présumé.

## Livrables

- [Rapport complet](docs/rapport.md), [architecture et contrats](docs/architecture.md), [démonstration et transfert](docs/demo.md).
- `src/` : import, catalogue, signatures, caches, FTS5, exhaustif et VP-Tree.
- `backend/` : configuration et API ; `frontend/` : client HTTP et interface.
- `scripts/` : commandes reproductibles ; `tests/` : validation automatisée.
- `data/catalog.sqlite3` : catalogue local ; `data/processed/` : vecteurs et index.
- `benchmarks/` : mesures et environnement.

Les données sont exclues de Git. Livrer `data/` séparément, images et métadonnées/licences ensemble. L’association aux descripteurs MIRFLICKR-1M est limitée à la correspondance documentée et vérifiée par contenu dans `data/processed/mpeg7_mapping.json`. Aucune famille supplémentaire n’est activée sur la seule ressemblance de noms de fichiers.
