"""Parcours Streamlit AppTest connecté à l'API réelle, sans simuler les réponses."""
from pathlib import Path
from streamlit.testing.v1 import AppTest
from frontend.api_client import ApiClient
from src.feature_store import atomic_json


def main():
    api=ApiClient()
    first=api.browse('mirflickr_25k',limit=1)['items'][0]
    app=AppTest.from_file(Path(__file__).resolve().parents[1]/'frontend/app.py',default_timeout=120).run()
    assert not app.exception
    app.button(key=f'gallery_{first["id"]}').click().run()
    assert app.session_state['query_mirflickr_25k']==first['id']
    def press(label):
        next(b for b in app.button if b.label==label).click().run()
        assert not app.exception
        assert not app.error
        return app.session_state['results_mirflickr_25k']
    exhaustive=press('Rechercher par image')
    assert exhaustive['method_used']=='exhaustive'
    next(s for s in app.selectbox if s.label=='Méthode').select('indexed').run()
    indexed=press('Rechercher par image')
    assert indexed['method_used']=='vp_tree'
    assert [i['id'] for i in indexed['items']]==[i['id'] for i in exhaustive['items']]
    app.multiselect[0].set_value(['hsv','lbp','hog']).run()
    fusion=press('Rechercher par image')
    assert fusion['method_used']=='exhaustive'
    app.text_input[0].set_value('sky water').run()
    combined=press('Combiner texte et image')
    assert combined['items']
    selected=combined['items'][0]['id']
    app.button(key=f'result_{selected}').click().run()
    assert not app.exception
    assert app.session_state['query_mirflickr_25k']==selected
    assert selected not in [i['id'] for i in app.session_state['results_mirflickr_25k']['items']]
    app.text_input[0].set_value('zzzxnonexistent').run()
    empty=press('Rechercher les mots-clés')
    assert empty['items']==[]
    app.number_input[0].set_value(2).run()
    assert not app.exception
    atomic_json(Path('benchmarks/interface_smoke.json'),dict(status='passed',api=api.base_url,
        real_catalog_images=api.browse('mirflickr_25k',limit=1)['total'],
        query_id=first['id'],exact_index_ranking=True,fusion=True,combined_count=len(combined['items']),
        requery_id=selected,empty_results=True,pagination=True,visual_browser_check=False))
    print('Interface et API réelles : sélection, exhaustif, index, fusion, combinaison, relance et pagination validés.')


if __name__=='__main__':
    main()
