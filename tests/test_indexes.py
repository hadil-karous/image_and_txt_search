import numpy as np
import pytest
from src.vp_tree import VPTree, distances
from src.feature_store import FeatureStore


@pytest.mark.parametrize('dimension',[1,10,128])
def test_exact_random_and_ties(dimension):
    rng=np.random.default_rng(23)
    vectors=rng.normal(size=(200,dimension)).astype(np.float32)
    vectors[5:12]=vectors[0]
    ids=rng.permutation(np.arange(1000,1200))
    tree=VPTree(vectors,ids,leaf_size=8)
    for query in list(vectors[:20])+[rng.normal(size=dimension)]:
        ds=distances(vectors,query)
        for k in [1,10,250]:
            expected=sorted([(int(i),float(d)) for i,d in zip(ids,ds) if i!=ids[0]],key=lambda x:(x[1],x[0]))[:k]
            result,_=tree.search(query,k,exclude_id=int(ids[0]))
            assert result==expected


def test_persistence_and_stale(prepared,tmp_path):
    store=FeatureStore(prepared,'mirflickr_25k','lbp')
    tree=VPTree(store.vectors,store.ids)
    path=tmp_path/'tree.npz'
    tree.save(path,store.signature)
    loaded=VPTree.load(path,store)
    assert loaded.search(store.vectors[0])==tree.search(store.vectors[0])
    store.signature='stale'
    with pytest.raises(ValueError,match='obsolète'):
        VPTree.load(path,store)
