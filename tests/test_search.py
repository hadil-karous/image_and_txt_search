import numpy as np
import pytest
from src.database import connect
from src.text_search import text_search
from src.visual_search import SearchEngine
from src.vp_tree import VPTree


def test_text_and_special_characters(prepared):
    with connect(prepared.catalog_path) as db:
        assert len(text_search(db,'mirflickr_25k','sky water'))==3
        assert not text_search(db,'mirflickr_25k','sky forest')
        assert not text_search(db,'mirflickr_25k','" * : ()')
        assert len(text_search(db,'mirflickr_25k','"sky"'))==3
        assert not text_search(db,'objects','sky')


def test_order_filter_fusion_and_fallback(prepared):
    engine=SearchEngine(prepared)
    args=dict(dataset='mirflickr_25k',query_id=1,methods=['hsv'],k=10)
    result=engine.search(**args,method='indexed')
    assert result['method_used']=='exhaustive' and 'Index absent' in result['message']
    assert 1 not in [i for i,d in result['matches']]
    assert result['matches']==sorted(result['matches'],key=lambda x:(x[1],x[0]))
    store=engine.stores[('mirflickr_25k','hsv')]
    engine.trees[('mirflickr_25k','hsv')]=VPTree(store.vectors,store.ids)
    assert engine.search(**args,method='indexed')['matches']==result['matches']
    filtered=engine.search(**args,candidates={1,2,3},method='indexed')
    assert {i for i,d in filtered['matches']}=={2,3}
    assert engine.search(**args,candidates=set())['matches']==[]
    first=engine.search('mirflickr_25k',1,['hsv','lbp'],[1,2])
    second=engine.search('mirflickr_25k',1,['hsv','lbp'],[10,20])
    np.testing.assert_allclose([d for i,d in first['matches']],[d for i,d in second['matches']])
    extreme=engine.search('mirflickr_25k',1,['hsv','lbp'],[1e308,1e308])
    ordinary=engine.search('mirflickr_25k',1,['hsv','lbp'],[1,1])
    assert extreme['matches']==ordinary['matches']
    with pytest.raises(ValueError):
        engine.search('mirflickr_25k',1,['hsv'],[float('nan')])
    with pytest.raises(ValueError):
        engine.search('objects',1,['hsv'])
