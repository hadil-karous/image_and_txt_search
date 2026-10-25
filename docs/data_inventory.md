# Inventaire des données

Inspection du **25 octobre 2026**, racine `C:\aim_tborbi\projet`. L’ancienne affirmation d’absence de données du 16 octobre est remplacée par cet inventaire. Référence : texte joint du cahier des charges ; aucun PDF de cours disponible.

| Base | Images observées | Annotations | MPEG-7 |
| --- | ---: | --- | --- |
| MIRFLICKR-25K | 25 000 JPEG | 25 000 fichiers de tags ; EXIF et licences | Aucun fichier |
| Objects | 0 | Aucune | Aucun |
| MIRFLICKR-1M | 0 image locale | Aucune annotation du million | Deux ZIP : Edge Histogram et Homogeneous Texture |

Les images restent dans `data/raw/mirflickr_25k/images/mirflickr25k/mirflickr/imN.jpg`. Aucun déplacement, extraction ou duplication d’image n’a été nécessaire. Les identifiants source sont les nombres `N` normalisés en chaînes, distincts des identifiants internes SQLite. La base et la convention d’identifiants sont vérifiées ensemble ; aucune association avec MIRFLICKR-1M n’est effectuée.

`annotations/meta/` contient cinq sous-dossiers de **25 000 fichiers chacun** : `tags`, `tags_raw`, `exif`, `exif_raw`, `license`. L’import utilise `tags/tagsN.txt` (un tag par ligne), `exif/exifN.txt` et `license/licenseN.txt`. Les sources brutes restent intactes. Les EXIF peuvent décrire une résolution différente du JPEG fourni ; les dimensions du catalogue sont obtenues en décodant l’image réelle.

Le sous-ensemble MIRFLICKR-25K contient **150 003 fichiers utiles**, totalisant **3 105 579 299 octets**, hors ZIP MPEG-7 conservés séparément. Les images couvrent exactement les identifiants **1 à 25 000**. L’intersection images/tags contient 25 000 identifiants ; aucun tag orphelin ni fichier de tags manquant. Les nombres de tags non vides, d’images décodables et de vecteurs sont établis séparément par l’import et l’extraction : voir les mesures du rapport et les JSON dans `benchmarks/`.

| ID source | Correspondance vérifiée | Exemples réels |
| --- | --- | --- |
| 1 | `im1.jpg` / `tags1.txt` | governorsisland, cigarette, tattoos, red |
| 2 | `im2.jpg` / `tags2.txt` | explore |
| 10 | `im10.jpg` / `tags10.txt` | hemlock, ring, blanket, brooklyn |
| 100 | `im100.jpg` / `tags100.txt` | farmer, cisauk, ricefield, d300 |
| 25000 | `im25000.jpg` / `tags25000.txt` | canoneos5d, headstand, selfportrait, family |

Ce sont des **tags utilisateur**, parfois personnels ou liés au matériel. Aucune catégorie supervisée ni annotation exhaustive de pertinence n’a été trouvée. Les tags ne servent donc pas de vérité terrain pour Precision@k ou mAP.

`descriptors/doc/` contient seulement `readme.txt`, `common_tags.txt`, `owner_ids.txt`. Les deux derniers listent des fréquences globales et des propriétaires, sans constituer un descripteur visuel par image. Les empreintes des trois fichiers et les exemples complets sont conservés dans `benchmarks/data_inspection.json`.

Le readme local indique l’usage pour la recherche, les licences individuelles dans `meta/license`, et demande de redistribuer la collection entière avec `meta/`. Citation demandée : M. J. Huiskes et M. S. Lew, « The MIR Flickr Retrieval Evaluation », ACM MIR 2008. La licence de `im1` est Attribution-NonCommercial-NoDerivs 2.0 ; ne pas généraliser cette seule licence à toute la collection. Conserver images et métadonnées ensemble lors du transfert.

Les deux ZIP MPEG-7 reçus après l’inventaire initial sont décrits ci-dessous. Leur utilisation est limitée aux identités d’images vérifiées ; elle ne remplace ni Objects ni une recherche sur un million d’images.

Reproduire : `.\.venv\Scripts\python.exe -m scripts.inspect_data`. Le décodage et les références importées sont contrôlés séparément par l’import ; ses résultats sont dans `benchmarks/import.json` et `data/catalog.sqlite3`.

## Import effectivement réalisé

L’import complet a décodé **25 000 images sans fichier illisible**, en 109,14 s. **22 872 images portent au moins un tag non vide** ; les 2 128 autres possèdent un fichier de tags vide. Le catalogue contient **69 099 tags distincts** et **223 535 associations image–tag**. Les 25 000 images sont aussi présentes dans FTS5. `PRAGMA integrity_check` renvoie `ok` et aucune violation de clé étrangère n’est relevée.

L’extraction complète a produit **25 000 vecteurs pour chaque méthode**, sans erreur : HSV (128 dimensions), LBP (10), HOG (1 764). Les trois index VP-Tree portent exactement sur ces identifiants. Les matrices, identifiants et manifestes sont sous `data/processed/vectors/mirflickr_25k/` ; les index sous `data/processed/indexes/mirflickr_25k/`. Ces signatures calculées sont distinctes de toute famille MPEG-7 fournie.

## Archives MPEG-7 reçues et import sélectif

| Archive conservée sous `raw/mirflickr_1m/descriptors/` | Octets | Descripteurs dans le ZIP | Dimension | Images associées | Membres manquants pour ces images |
| --- | ---: | ---: | ---: | ---: | ---: |
| `features_edgehistogram.zip` | 624 048 777 | 1 000 000 | 150 | 24 988 | 0 |
| `features_homogeneoustexture.zip` | 360 279 480 | 1 000 000 | 43 | 24 988 | 0 |

Les membres numériques vont de 0 à 999999, avec un nombre par ligne. `feature_names.txt` documente les 150 ou 43 composantes. Aucun membre n’a été extrait en fichier individuel. Les matrices compactes sont dans `processed/vectors/mirflickr_25k/mpeg7_edgehistogram/` et `mpeg7_homogeneoustexture/`, avec des IDs internes alignés.

La correspondance a été vérifiée sur le contenu : 24 986 associations uniques par CRC32 et taille, 14 exemples répartis et deux cas de doublons corroborés par SHA-256. Douze images échouent aussi à la comparaison des pixels décodés et restent exclues : 608, 611, 692, 705, 733, 737, 798, 924, 942, 1066, 1067 et 1123. Les noms et l’ordre ne suffisent pas à justifier une association. Voir [le protocole complet](mpeg7.md) et `benchmarks/mpeg7_mapping_verification.json`.
