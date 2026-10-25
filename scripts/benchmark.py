"""Comparaison reproductible : mêmes requêtes et distance, tailles imbriquées."""
import argparse
import csv
import importlib.metadata
import json
import os
import platform
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from backend.config import get_settings
from src.descriptors import METHODS
from src.feature_store import FeatureStore, atomic_json
from src.vp_tree import VPTree, distances


def exhaustive(vectors,ids,query,exclude,k):
    ds=distances(vectors,query)
    valid=ids!=exclude
    selected=np.flatnonzero(valid)
    order=np.lexsort((ids[valid],ds[valid]))[:k]
    return [(int(ids[selected[j]]),float(ds[selected[j]])) for j in order],len(vectors)


def write_csv(path,rows):
    with path.open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def hardware():
    result={}
    if os.name=='nt':
        import ctypes
        import winreg
        class MemoryStatus(ctypes.Structure):
            _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong),
                ('total_physical',ctypes.c_ulonglong),('available_physical',ctypes.c_ulonglong),
                ('total_page',ctypes.c_ulonglong),('available_page',ctypes.c_ulonglong),
                ('total_virtual',ctypes.c_ulonglong),('available_virtual',ctypes.c_ulonglong),
                ('available_extended',ctypes.c_ulonglong)]
        status=MemoryStatus()
        status.length=ctypes.sizeof(status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            result['memory_total_gb']=round(status.total_physical/1024**3,2)
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r'HARDWARE\DESCRIPTION\System\CentralProcessor\0') as key:
                result['cpu_model']=winreg.QueryValueEx(key,'ProcessorNameString')[0].strip()
        except OSError:
            pass
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset',default='mirflickr_25k')
    p.add_argument('--sizes',nargs='+',type=int,default=[500,2500,25000])
    p.add_argument('--queries',type=int,default=20)
    p.add_argument('--k',type=int,default=10)
    p.add_argument('--seed',type=int,default=2026)
    p.add_argument('--output',default='benchmarks')
    args=p.parse_args()
    if min(args.sizes)<2 or args.queries<1 or args.k<1:
        p.error('Tailles >= 2, requêtes et k positifs')
    out=Path(args.output)
    out.mkdir(parents=True,exist_ok=True)
    settings=get_settings()
    stores={}
    full_load={}
    for method in METHODS:
        start=time.perf_counter()
        stores[method]=FeatureStore(settings,args.dataset,method)
        full_load[method]=time.perf_counter()-start
    common=sorted(set.intersection(*(set(s.ids.tolist()) for s in stores.values())))
    sizes=sorted(set(min(n,len(common)) for n in args.sizes))
    if not sizes or min(sizes)<2:
        raise ValueError('Couverture commune insuffisante')
    rng=np.random.default_rng(args.seed)
    query_ids=rng.choice(common[:min(sizes)],size=min(args.queries,min(sizes)),replace=False).tolist()
    environment=dict(executed_at_utc=datetime.now(timezone.utc).isoformat(),platform=platform.platform(),python=platform.python_version(),
                     processor=platform.processor(),logical_cpus=os.cpu_count(),
                     hardware=hardware(),
                     packages={n:importlib.metadata.version(n) for n in ('numpy','scipy','scikit-image','Pillow','fastapi','streamlit','pytest')})
    atomic_json(out/'environment.json',environment)
    atomic_json(out/'parameters.json',dict(**vars(args),actual_sizes=sizes,actual_queries=len(query_ids),
                query_ids=query_ids,subset='premiers identifiants internes communs, tailles imbriquées',
                metric='euclidean_float64',normalization='distance / sqrt(2) (ne change pas le classement)',
                warmup_queries=1,leaf_size=32,exhaustive_distance_block_rows=2048,
                scope='moteur seul, hors HTTP, hors chargement',
                signatures={m:s.signature for m,s in stores.items()}))
    raw=[]
    stages=[]
    summaries=[]
    with tempfile.TemporaryDirectory(prefix='image-vp-benchmark-') as directory:
        for descriptor,store in stores.items():
            for size in sizes:
                ids=np.array(common[:size],dtype=np.int64)
                vectors=np.asarray(store.vectors[[store.positions[int(i)] for i in ids]])
                positions={int(i):n for n,i in enumerate(ids)}
                started=time.perf_counter()
                tree=VPTree(vectors,ids)
                build=time.perf_counter()-started
                path=Path(directory)/'tree.npz'
                started=time.perf_counter()
                tree.save(path,'benchmark')
                save=time.perf_counter()-started
                started=time.perf_counter()
                tree=VPTree.load(path,SimpleNamespace(ids=ids,vectors=vectors,signature='benchmark'))
                load=time.perf_counter()-started
                stages.append(dict(descriptor=descriptor,size=size,feature_load_full_seconds=full_load[descriptor],
                                   build_seconds=build,save_seconds=save,index_load_seconds=load))
                warm=ids[0]
                exhaustive(vectors,ids,vectors[0],warm,args.k)
                tree.search(vectors[0],args.k,exclude_id=int(warm))
                for query_id in query_ids:
                    query=vectors[positions[query_id]]
                    results={}
                    # Alterner l'ordre pour limiter le biais d'échauffement.
                    method_order=['exhaustive','vp_tree'] if query_id%2 else ['vp_tree','exhaustive']
                    for method in method_order:
                        start=time.perf_counter()
                        if method=='exhaustive':
                            pairs,evaluated=exhaustive(vectors,ids,query,query_id,args.k)
                        else:
                            pairs,evaluated=tree.search(query,args.k,exclude_id=query_id)
                        elapsed=(time.perf_counter()-start)*1000
                        results[method]=pairs
                        raw.append(dict(descriptor=descriptor,size=size,query_id=query_id,method=method,
                                        elapsed_ms=elapsed,evaluated=evaluated,k=args.k))
                    reference,indexed=results['exhaustive'],results['vp_tree']
                    if [i for i,d in reference]!=[i for i,d in indexed] or not np.allclose([d for i,d in reference],[d for i,d in indexed],atol=1e-10):
                        raise AssertionError(f'Voisins inexacts : {descriptor}/{size}/{query_id}')
                for method in ['exhaustive','vp_tree']:
                    measured=[r for r in raw if r['descriptor']==descriptor and r['size']==size and r['method']==method]
                    times=[r['elapsed_ms'] for r in measured]
                    summaries.append(dict(descriptor=descriptor,size=size,method=method,queries=len(times),
                        median_ms=float(np.median(times)),p95_ms=float(np.percentile(times,95)),
                        mean_evaluated=float(np.mean([r['evaluated'] for r in measured])),exact_agreement=True))
                write_csv(out/'search_raw.csv',raw)
                write_csv(out/'summary.csv',summaries)
                write_csv(out/'stages.csv',stages)
                print(descriptor,size,summaries[-2:],flush=True)
    fig,axes=plt.subplots(1,3,figsize=(13,4),layout='constrained')
    for ax,descriptor in zip(axes,METHODS):
        for method,label in [('exhaustive','Exhaustif'),('vp_tree','VP-Tree')]:
            rows=[r for r in summaries if r['descriptor']==descriptor and r['method']==method]
            ax.plot([r['size'] for r in rows],[r['median_ms'] for r in rows],marker='o',label=label)
        ax.set(title=descriptor.upper(),xlabel='Nombre d’images',ylabel='Médiane (ms)',xscale='log')
        ax.grid(alpha=.2)
        ax.legend()
    fig.savefig(out/'search_times.png',dpi=160)
    plt.close(fig)
    print('Accord exact exhaustif/VP-Tree vérifié pour toutes les requêtes mesurées.')


if __name__=='__main__':
    main()
