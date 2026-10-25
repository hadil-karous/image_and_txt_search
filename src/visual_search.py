"""Ressources chargées une fois ; fusion à échelle fixe, repli exact explicite."""
import math
import time

import numpy as np

from src.database import connect, image_rows
from src.descriptors import SEARCH_METHODS
from src.feature_store import FeatureStore
from src.vp_tree import VPTree, distances


class SearchEngine:
    def __init__(self,settings):
        self.settings=settings
        self.stores,self.trees,self.messages={},{},{}
        with connect(settings.catalog_path) as db:
            datasets=[r[0] for r in db.execute('SELECT name FROM datasets')]
            for dataset in datasets:
                rows=image_rows(db,dataset)
                for method in SEARCH_METHODS:
                    key=(dataset,method)
                    try:
                        store=FeatureStore(settings,dataset,method,rows=rows)
                        self.stores[key]=store
                    except (OSError,ValueError,KeyError) as exc:
                        self.messages[key]=str(exc)
                        continue
                    try:
                        self.trees[key]=VPTree.load(settings.indexes_dir/dataset/f'{method}.npz',store)
                    except (OSError,ValueError,KeyError) as exc:
                        self.messages[key]=str(exc)

    def search(self,dataset,query_id,methods,weights=None,k=12,method='exhaustive',candidates=None):
        start=time.perf_counter()
        if not methods or len(set(methods))!=len(methods) or not set(methods).issubset(SEARCH_METHODS):
            raise ValueError('Choisir des descripteurs distincts et disponibles')
        weights=weights if weights is not None else [1.0]*len(methods)
        if len(weights)!=len(methods) or any(not math.isfinite(w) or w<0 for w in weights) or not any(weights):
            raise ValueError('Poids finis et positifs ou nuls, avec une somme positive')
        if method not in ('exhaustive','indexed') or not 1<=k<=100:
            raise ValueError('Méthode ou k invalide')
        active=[(m,float(w)) for m,w in zip(methods,weights) if w>0]
        scale=max(w for _,w in active)
        total=sum(w/scale for _,w in active)
        active=[(m,(w/scale)/total) for m,w in active]
        stores=[]
        for descriptor,weight in active:
            store=self.stores.get((dataset,descriptor))
            if store is None:
                raise ValueError(f'Descripteur {descriptor} indisponible : extraire les vecteurs et redémarrer le serveur')
            if query_id not in store.positions:
                raise ValueError(f'Image requête absente de la couverture {descriptor} pour cette base')
            stores.append((descriptor,weight,store))
        common=set(stores[0][2].positions)
        for _,_,store in stores[1:]:
            common.intersection_update(store.positions)
        coverage=len(common)
        if candidates is not None:
            common.intersection_update(candidates)
        common.discard(query_id)
        notes=[]
        used='exhaustive'
        if method=='indexed':
            if candidates is not None:
                notes.append('Filtre textuel : classement exhaustif exact des candidats filtrés.')
            elif len(stores)>1:
                notes.append('Fusion : repli exhaustif, aucun VP-Tree de fusion préconstruit.')
            elif (dataset,stores[0][0]) not in self.trees:
                notes.append('Index absent ou obsolète : repli exhaustif.')
            else:
                used='vp_tree'
        if used=='vp_tree':
            name,_,store=stores[0]
            query=store.vectors[store.positions[query_id]]
            pairs,evaluated=self.trees[(dataset,name)].search(query,k,exclude_id=query_id)
            pairs=[(i,d/store.distance_scale) for i,d in pairs]
        else:
            ids=np.array(sorted(common),dtype=np.int64)
            scores=np.zeros(len(ids),dtype=np.float64)
            for _,weight,store in stores:
                query=store.vectors[store.positions[query_id]]
                # Ne matérialise pas l'ensemble de la matrice HOG pour un filtre.
                for start_row in range(0,len(ids),2048):
                    chunk=ids[start_row:start_row+2048]
                    positions=[store.positions[int(i)] for i in chunk]
                    scores[start_row:start_row+len(chunk)]+=weight*distances(store.vectors[positions],query)/store.distance_scale
            order=np.lexsort((ids,scores))[:k]
            pairs=[(int(ids[i]),float(scores[i])) for i in order]
            evaluated=len(ids)
        with connect(self.settings.catalog_path) as db:
            total_images=db.execute('SELECT COUNT(*) FROM images i JOIN datasets d ON d.id=i.dataset_id WHERE d.name=?',(dataset,)).fetchone()[0]
        if coverage<total_images:
            notes.append(f'Couverture limitée : {coverage}/{total_images} images communes aux descripteurs.')
        return dict(matches=pairs,method_used=used,elapsed_ms=(time.perf_counter()-start)*1000,
                    evaluated=evaluated,candidate_count=len(common),searchable_images=coverage,
                    message=' '.join(notes) or None)
