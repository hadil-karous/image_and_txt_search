"""Validate imported MPEG-7 on the real catalogue, API and Streamlit interface."""
import json
from pathlib import Path

from streamlit.testing.v1 import AppTest

from backend.config import get_settings
from frontend.api_client import ApiClient
from src.descriptors import MPEG7_METHODS
from src.feature_store import atomic_json,file_hash
from src.visual_search import SearchEngine


def main():
    settings=get_settings()
    engine=SearchEngine(settings)
    api=ApiClient()
    base=next(b for b in api.datasets() if b['name']=='mirflickr_25k')
    assert base['mpeg7_available']
    checks={}
    for method in MPEG7_METHODS:
        store=engine.stores[('mirflickr_25k',method)]
        query_ids=store.ids[::max(1,len(store.ids)//20)][:20].tolist()
        for query_id in query_ids:
            exhaustive=engine.search('mirflickr_25k',query_id,[method],k=10)
            indexed=engine.search('mirflickr_25k',query_id,[method],k=10,method='indexed')
            assert exhaustive['matches']==indexed['matches']
            assert indexed['method_used']=='vp_tree'
        body=dict(dataset='mirflickr_25k',query_id=query_ids[0],descriptors=[method],k=10,method='indexed')
        result=api.search('visual',body)
        assert result['method_used']=='vp_tree' and len(result['items'])==10
        assert result['searchable_images']==len(store.ids)
        assert 'Couverture limitée' in result['message']
        combined=api.search('combined',dict(body,keywords='sky water'))
        assert combined['method_used']=='exhaustive' and combined['items']
        fusion=api.search('visual',dict(body,descriptors=['hsv',method],weights=[1,2]))
        assert fusion['method_used']=='exhaustive' and len(fusion['items'])==10
        checks[method]=dict(count=len(store.ids),dimension=store.vectors.shape[1],
            exact_queries=len(query_ids),api_index=True,api_combined=True,api_fusion=True)
    app=AppTest.from_file(Path(__file__).resolve().parents[1]/'frontend/app.py',default_timeout=120).run()
    assert not app.exception
    for method in MPEG7_METHODS:
        label={'mpeg7_edgehistogram':'MPEG-7 · Edge Histogram',
               'mpeg7_homogeneoustexture':'MPEG-7 · Homogeneous Texture'}[method]
        assert label in app.multiselect[0].options
        # Use the underlying value, not the human-readable formatted label.
        app.multiselect[0].set_value([method]).run()
        app.button(key='gallery_1').click().run()
        next(b for b in app.button if b.label=='Rechercher par image').click().run()
        assert not app.exception and not app.error
        assert app.session_state['results_mirflickr_25k']['searchable_images']==24988
        next(s for s in app.selectbox if s.label=='Méthode').select('indexed').run()
        next(b for b in app.button if b.label=='Rechercher par image').click().run()
        assert app.session_state['results_mirflickr_25k']['method_used']=='vp_tree'
    preservation_path=Path('benchmarks/mpeg7_preservation.json')
    preservation=json.loads(preservation_path.read_text(encoding='utf-8'))
    mismatches=[name for name,digest in preservation['before'].items() if file_hash(Path(name))!=digest]
    if mismatches:
        raise AssertionError(f'Protected sources changed: {mismatches}')
    preservation.update(all_unchanged=True,checked_files=len(preservation['before']))
    atomic_json(preservation_path,preservation)
    report=dict(status='passed',families=checks,streamlit_both_families=True,
        archives_and_existing_features_unchanged=True,protected_files=len(preservation['before']))
    atomic_json(Path('benchmarks/mpeg7_validation.json'),report)
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
