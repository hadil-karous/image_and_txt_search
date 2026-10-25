# MPEG-7 : ZIP conservés, import sélectif et correspondance vérifiée

## Archives et formats réellement inspectés

Les fichiers sources restent intacts dans `data/raw/mirflickr_1m/descriptors/`.

| Famille | Taille du ZIP (octets) | Membres descripteurs | Dimension observée et documentée |
| --- | ---: | ---: | ---: |
| Edge Histogram | 624 048 777 | 1 000 000 | 150 |
| Homogeneous Texture | 360 279 480 | 1 000 000 | 43 |

SHA-256 des ZIP :

```text
features_edgehistogram.zip
d75ed852d8fc28f675860ee9d15793c15b8a9e7bbc50a40a7344d64c8cded90c
features_homogeneoustexture.zip
346820f09fe2f2d3b10ef5882cd1d0c45e85309f8b9b6d1c8486f59e8e663c83
```

Chaque archive contient des membres `features_<famille>/<groupe>/<id>.txt`, avec un nombre ASCII par ligne, des IDs de 0 à 999999 et un groupe égal à la division entière de l’ID par 10000. Les échantillons ont été lus directement par `ZipFile.read`. Aucun appel à `extract` ou `extractall` n’est utilisé. Les fichiers annexes macOS sont ignorés.

`feature_names.txt` décrit exactement les dimensions observées. Edge Histogram contient 80 composantes locales, 5 globales et 65 semi-globales, soit 150 valeurs. Homogeneous Texture contient 2 composantes DC/SD, 30 cases échelle/orientation, 5 agrégats d’échelle et 6 agrégats d’orientation, soit 43 valeurs. Le parseur suit ces fichiers fournis, sans supposer une dimension standard de 80 ou 62. Il rejette les dimensions incorrectes, les nombres non finis et les membres excessivement volumineux.

La [page officielle de téléchargement](https://press.liacs.nl/mirflickr/mirdownload.html) rattache les deux familles à MIRFLICKR-1M et indique que la collection commence par les images du sous-ensemble 25K. Son résumé du conditionnement des descripteurs est ancien : l’inventaire des ZIP locaux, avec un million de petits fichiers chacun, fait foi pour ce parseur.

## Vérification de l’identité des images

La déclaration officielle du sous-ensemble ne suffit pas à prouver le décalage d’identifiants. La procédure a donc comparé les images locales au contenu de l’archive officielle `images0.zip`, en utilisant un lecteur HTTP Range borné à 32 Mio. Python `zipfile` lit son répertoire central et quelques membres JPEG ; l’archive distante de **12 494 849 861 octets** n’est jamais téléchargée intégralement ni enregistrée localement.

1. Calculer la taille et le CRC32 de chaque JPEG du catalogue, indépendamment de son nom et de son rang.
2. Chercher une correspondance de contenu unique parmi les entrées d’images de la référence officielle.
3. Vérifier les octets par SHA-256 pour 14 exemples répartis, dont les limites de dossiers et les premiers/derniers IDs.
4. Traiter séparément les duplications et les divergences ; comparer les octets puis les pixels RGB décodés, sans redimensionnement ni seuil de ressemblance.

**24 986 images** ont une correspondance unique par taille/CRC32. Ces correspondances corroborent toutes `imN.jpg → image officielle N−1 → descripteur N−1`. Cette règle est un résultat des contrôles de contenu, pas leur point de départ. Les échantillons SHA-256 confirment l’identité exacte, y compris aux frontières 9999/10000 et 19999/20000.

Les images locales **6602 et 6921** sont des duplications de contenu dans la référence. Leur association au membre N−1 a été corroborée par comparaison SHA-256 exacte. La correspondance explicitement conservée couvre donc **24 988 images**. Pour les 24 986 correspondances uniques, la vérification exhaustive repose sur CRC32 et taille, complétée par les exemples SHA-256 ; elle ne constitue pas une comparaison SHA-256 distante exhaustive des 25 000 images.

Les douze images suivantes ne correspondent pas exactement à la référence, ni en octets ni en pixels RGB décodés :

```text
608, 611, 692, 705, 733, 737, 798, 924, 942, 1066, 1067, 1123
```

Elles restent **sans association MPEG-7**, même si un fichier de descripteur portant un nombre attendu existe. Aucune correspondance n’est déduite de ce nom seul. Elles restent disponibles avec HSV/LBP/HOG. La cause des divergences n’est pas attribuée sans preuve.

La dernière vérification a transféré **13 466 972 octets**, au cours de 89 requêtes Range : répertoire ZIP et exemples uniquement. Le lecteur refuse un serveur répondant 200 à une requête Range au lieu de 206, une plage incorrecte, un changement de taille distante ou un dépassement de budget. Une première passe avait laissé les exceptions non vérifiées ; la seconde les a traitées explicitement.

Le fichier `data/processed/mpeg7_mapping.json` contient les associations explicites : ID interne, ID source local, ID du descripteur, membre de référence, taille, CRC32 et SHA-256 local. Une signature lie ces preuves au catalogue. Le résumé, les exceptions et les contrôles SHA-256 sont dans `benchmarks/mpeg7_mapping_verification.json`. Les archives de descripteurs proviennent des familles publiées sur la page officielle ; leurs empreintes locales sont conservées pour identifier précisément les sources utilisées.

## Matrices et bilan réel

L’import lit uniquement les 24 988 membres associés dans chaque ZIP, ainsi que son fichier de noms de composantes. Il n’ouvre pas les 975 012 autres descripteurs. L’énumération du répertoire central d’un ZIP reste nécessaire avec `zipfile` : elle consomme de la mémoire, mais ne crée aucun fichier individuel.

| Famille | Images associées/importées | Dimensions | Descripteurs manquants parmi les associées | Vecteurs invalides | Images non associées |
| --- | ---: | ---: | ---: | ---: | ---: |
| Edge Histogram | 24 988 | 150 | 0 | 0 | 12 |
| Homogeneous Texture | 24 988 | 43 | 0 | 0 | 12 |

Les deux imports ont duré respectivement **13,46 s** et **11,02 s** sur cette machine. Ils produisent, pour chaque famille :

```text
data/processed/vectors/mirflickr_25k/mpeg7_<famille>/
  manifest.json
  <generation>/vectors.npy
  <generation>/ids.npy
```

`vectors.npy` conserve les valeurs fournies en float32, sans normalisation à la sauvegarde. `ids.npy` contient les identifiants internes int64 dans le même ordre que les lignes. Les matrices et tableaux d’IDs des deux familles totalisent environ **19,69 Mo**, hors manifestes et preuves de correspondance. Les manifestes enregistrent source, empreintes, dimension, couverture, paramètres, labels, absences et erreurs. Ils sont publiés après écriture des tableaux.

Les dossiers et vecteurs HSV/LBP/HOG ne sont jamais utilisés comme destination. Le contrôle final de **614 fichiers protégés**, dont les deux ZIP et les anciens vecteurs, lots, manifestes et index, confirme des SHA-256 inchangés : `benchmarks/mpeg7_preservation.json`.

## Recherche et interface

Les noms de méthodes sont `mpeg7_edgehistogram` et `mpeg7_homogeneoustexture`. `FeatureStore` conserve les données brutes sur disque et applique une normalisation L2 par ligne au chargement. La distance choisie par ce moteur est **euclidienne divisée par 2**, bornée et métrique, avec une échelle fixe pour la fusion. Ce choix n’est pas présenté comme la distance MPEG-7 normative ou celle des auteurs de la collection.

Les nouveaux VP-Trees sont construits uniquement pour ces méthodes. Ils portent la signature des vecteurs et identifiants correspondants. Une fusion ou un filtre textuel utilise le même repli exhaustif exact que le reste du moteur. Une image requête exclue de la couverture MPEG-7 produit une erreur explicite, sans vecteur fabriqué ni substitution automatique par HSV.

`GET /datasets` et `/descriptors` exposent la famille, dimension, nombre d’images, index et distance. Streamlit propose les deux choix seulement lorsque les caches sont valides et chargés, et signale la couverture partielle. Le catalogue n’a reçu aucune image du million et les résultats continuent de servir les JPEG MIRFLICKR-25K locaux.

## Reproduction et validations

Depuis la racine, avec les ZIP en place :

```powershell
.\.venv\Scripts\python.exe -m scripts.inspect_mpeg7
.\.venv\Scripts\python.exe -m scripts.verify_mpeg7_mapping
.\.venv\Scripts\python.exe -m scripts.import_mpeg7
.\.venv\Scripts\python.exe -m scripts.build_indexes --methods mpeg7_edgehistogram mpeg7_homogeneoustexture
```

La vérification réseau peut être omise pour refaire l’import avec le fichier de correspondance déjà validé et un catalogue inchangé. Après préparation, redémarrer FastAPI. Puis :

```powershell
.\.venv\Scripts\python.exe -m pytest -q --junitxml=benchmarks/tests.xml
.\.venv\Scripts\python.exe -m scripts.validate_mpeg7
```

Les tests vérifient l’import sélectif sans extraction, l’alignement avec une correspondance non triviale, le rejet des preuves non vérifiées/obsolètes, les membres absents ou malformés, les dimensions, les distances et l’API. La validation réelle compare exhaustif et VP-Tree pour **20 requêtes par famille**, puis exerce recherches indexées, fusion et combinaison via HTTP, et les deux familles dans Streamlit AppTest. Ce dernier n’est pas un contrôle visuel par navigateur.

Les résultats sont dans `benchmarks/mpeg7_inspection.json`, `mpeg7_import.json`, `mpeg7_validation.json` et les preuves citées plus haut. Aucun résultat de recherche portant sur un million d’images n’est revendiqué.
