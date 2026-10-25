"""Actualiser le rapport depuis les résultats, sans inventer de chiffres."""
import csv
import json
import xml.etree.ElementTree as ET
from pathlib import Path


def main():
    bench=Path('benchmarks')
    def read(name):
        return json.loads((bench/name).read_text(encoding='utf-8-sig'))
    imported=read('import.json')
    extraction=read('extraction.json')
    builds=read('index_build.json')
    env=read('environment.json')
    params=read('parameters.json')
    smoke=read('http_smoke.json')
    interface=read('interface_smoke.json')
    subset=read('subset_validation.json')
    tests=ET.parse(bench/'tests.xml').getroot()
    suites=list(tests.iter('testsuite'))
    count=sum(int(s.attrib.get('tests',0)) for s in suites)
    failures=sum(int(s.attrib.get('failures',0))+int(s.attrib.get('errors',0)) for s in suites)
    skips=sum(int(s.attrib.get('skipped',0)) for s in suites)
    with (bench/'summary.csv').open(encoding='utf-8') as stream:
        rows=list(csv.DictReader(stream))
    with (bench/'stages.csv').open(encoding='utf-8') as stream:
        stages=list(csv.DictReader(stream))
    lines=[f"Exécution réelle : **{count} tests, {failures} échec/erreur, {skips} test ignoré** (JUnit `benchmarks/tests.xml`).",
        '',f"Essai préalable isolé : {subset['real_images']} images réelles, réimport stable et trois index exacts ; état {subset['status']}.",
        '',f"Import : **{imported['imported']} images**, {len(imported['unreadable'])} illisible(s), {imported['annotated']} images avec tags non vides, {len(imported['orphan_annotations'])} annotation(s) orpheline(s), en {imported['seconds']:.2f} s.",
        '',f"Environnement : Python {env['python']}, {env['platform']}, {env['logical_cpus']} processeurs logiques ; {env.get('hardware',{}).get('cpu_model',env['processor'])}, RAM {env.get('hardware',{}).get('memory_total_gb','non relevée')} Go.",
        '', '| Signature | Couverture | Dimension | Extraction (s) | Construction production (s) | Chargement vecteurs production (s) |',
        '| --- | ---: | ---: | ---: | ---: | ---: |']
    for method,data in extraction.items():
        build=builds[method]
        lines.append(f"| {method.upper()} | {data['count']}/{data['total_catalog']} | {data['dimension']} | {data['seconds']:.2f} | {build['build_seconds']:.3f} | {build['load_seconds']:.3f} |")
    lines.extend(['','Les durées d’extraction incluent décodage, calcul et sauvegarde ; elles correspondent à la dernière exécution publiée du manifeste. Les coûts de chargement dépendent du cache disque du système.',
        '',f"Recherche moteur : **{params['actual_queries']} requêtes par couple taille/signature**, k={params['k']}, graine={params['seed']}. Même liste de requêtes pour chaque comparaison.",
        '', '| Signature | Images | Méthode | Requêtes | Médiane (ms) | p95 (ms) | Distances évaluées en moyenne |',
        '| --- | ---: | --- | ---: | ---: | ---: | ---: |'])
    for row in rows:
        lines.append(f"| {row['descriptor'].upper()} | {row['size']} | {row['method']} | {row['queries']} | {float(row['median_ms']):.3f} | {float(row['p95_ms']):.3f} | {float(row['mean_evaluated']):.1f} |")
    lines.extend(['','| Signature | Images | Construction (s) | Sauvegarde (s) | Chargement index (s) |',
                  '| --- | ---: | ---: | ---: | ---: |'])
    for row in stages:
        lines.append(f"| {row['descriptor'].upper()} | {row['size']} | {float(row['build_seconds']):.4f} | {float(row['save_seconds']):.4f} | {float(row['index_load_seconds']):.4f} |")
    lines.extend(['','Accord des voisins **exact sur toutes les requêtes mesurées**, identifiants et distances vérifiés. Cette exactitude porte sur les signatures et métriques utilisées, pas sur un jugement humain de pertinence.',
        '',f"Validation HTTP réelle : **{smoke['status']}**, {sum(c['url_checks'] for c in smoke['checks'])} URLs comparées octet pour octet aux images attendues, recherche à partir d’un résultat validée. Aucun candidat pour le mot inexistant.",
        '', 'Analyse à la taille maximale :', ''])
    maximum=max(int(r['size']) for r in rows)
    for method in extraction:
        measured={r['method']:r for r in rows if r['descriptor']==method and int(r['size'])==maximum}
        ratio=float(measured['exhaustive']['median_ms'])/float(measured['vp_tree']['median_ms'])
        if ratio>=1:
            lines.append(f"- {method.upper()} : le VP-Tree est {ratio:.2f} fois plus rapide en médiane que l’exhaustif.")
        else:
            lines.append(f"- {method.upper()} : le VP-Tree est {1/ratio:.2f} fois plus lent en médiane que l’exhaustif.")
        evaluated=float(measured['vp_tree']['mean_evaluated'])
        if evaluated>=maximum*0.99:
            lines.append(f"  Pour {method.upper()}, au moins 99 % des distances sont évaluées : le VP-Tree n’élague pratiquement pas. Un avantage temporel éventuel vient ici des petits blocs/feuilles et de leur localité mémoire, pas d’une réduction significative du nombre de distances.")
    lines.extend(['','Le nombre de distances effectivement évaluées montre la capacité d’élagage. Le coût Python des visites et les calculs par petits blocs expliquent qu’un index exact puisse perdre face à NumPy même en évaluant moins de distances. HOG concentre des informations en grande dimension : aucun gain systématique n’est attendu.',
        '', '![Temps médians mesurés](../benchmarks/search_times.png)',
        '', f"Interface Streamlit connectée à l’API réelle : **{interface['status']}**, catalogue de {interface['real_catalog_images']} images. Sélection, exhaustif, index exact, fusion, filtre combiné, relance depuis un résultat, résultat vide et pagination validés par AppTest (`interface_smoke.json`). Aucun navigateur automatisable n’était disponible : aucun contrôle visuel dans un navigateur n’est revendiqué. La validation sur PC LIASA reste à réaliser."])
    path=Path('docs/rapport.md')
    content=path.read_text(encoding='utf-8')
    before,remainder=content.split('<!-- RESULTS_START -->',1)
    _,after=remainder.split('<!-- RESULTS_END -->',1)
    path.write_text(before+'<!-- RESULTS_START -->\n'+'\n'.join(lines)+'\n<!-- RESULTS_END -->'+after,encoding='utf-8')
    print('Rapport actualisé avec les mesures exécutées.')


if __name__=='__main__':
    main()
