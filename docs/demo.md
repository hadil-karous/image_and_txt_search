# Démonstration et transfert

## Préparation

Installer l’environnement du README. Vérifier `data/catalog.sqlite3`, les manifestes et générations NumPy sous `data/processed/vectors/mirflickr_25k/`, les trois index sous `data/processed/indexes/mirflickr_25k/`, les images et `annotations/meta/`. Lancer FastAPI puis Streamlit avec les commandes du README. `/datasets` expose les volumes et couvertures réelles. Aucune extraction n’a lieu pendant les recherches.

## Parcours reproductible

1. Ouvrir `http://127.0.0.1:8501`, choisir MIRFLICKR-25K et montrer les volumes. Les images Objects/MIRFLICKR-1M ne sont pas fournies ; deux familles MPEG-7 du million sont importées pour les identités 25K vérifiées.
2. Saisir `sky water` et « Rechercher les mots-clés ». Tous les mots sont requis. Montrer les tags d’un résultat.
3. Dans la galerie, sélectionner l’image source 1 ; choisir HSV et « Rechercher par image ». Montrer la requête, les distances croissantes et le temps.
4. Choisir « VP-Tree exact » et relancer. Le classement reste identique ; le gain de temps dépend des données.
5. Ajouter LBP puis HOG, régler les poids et relancer. La fusion utilise une échelle fixe et l’exhaustif.
6. Conserver `sky water` et l’image sélectionnée, puis « Combiner texte et image ». Le texte filtre avant le classement visuel ; l’exhaustif sur candidats est annoncé.
7. Sur un résultat, cliquer « Utiliser comme image requête » : la recherche repart avec les paramètres et les mots-clés conservés.
8. Saisir `zzzxnonexistent` : résultat vide. Changer la page de galerie pour montrer la pagination.
9. Présenter `benchmarks/search_times.png` et les médianes/p95 du rapport. Distinguer exactitude algorithmique et pertinence : les tags ne constituent pas une vérité terrain exhaustive.
10. Choisir MPEG-7 Edge Histogram, puis Homogeneous Texture. Montrer les dimensions 150/43 et la couverture 24 988/25 000 ; lancer les recherches exhaustive et indexée. Expliquer que douze identités non vérifiées sont exclues et que les ZIP originaux n’ont pas été extraits. Le parcours complet est vérifié par `python -m scripts.validate_mpeg7` avec le Python de `.venv`.

L’image 1 ne porte pas nécessairement `sky water` : une image peut classer les candidats qui portent ces tags sans les porter elle-même.

Avec l’API en marche, `.\.venv\Scripts\python.exe -m scripts.smoke_demo` vérifie ce parcours HTTP, la relance avec un résultat et l’identité des octets servis par les URLs.

## Transfert vers un PC LIASA

Arrêter les deux serveurs avec Ctrl+C. Copier le code, `requirements-lock.txt`, `docs/`, `benchmarks/` et **tout `data/`**, y compris `meta/` et les licences. Recréer `.venv`, sans le copier. Respecter les conditions du readme local et les licences individuelles lors de la redistribution.

Installer CPython Windows 3.12 et les dépendances verrouillées. Les chemins des images sont relatifs à leur base : définir `IMAGE_SEARCH_DATA_DIR` si les données sont sur un autre disque, puis lancer les serveurs. Les bibliothèques doivent correspondre aux manifestes ; les caches incompatibles sont refusés. Refaire extraction et indexation si nécessaire. Certains outils de copie modifient les dates des fichiers : un réimport peut alors provoquer une invalidation, ce qui est attendu.

La méthode recommandée est une copie serveur arrêté. Pour une copie à chaud du catalogue SQLite, employer l’API de sauvegarde SQLite plutôt qu’une copie isolée du fichier en mode WAL.

Les mesures sont celles de cette machine Windows. L’installation et les performances du PC LIASA restent à vérifier sur place. Aucun test à un million d’images ni validation Objects n’est présenté. Le rapport Markdown est le livrable obligatoire ; Docker et PDF sont facultatifs.
