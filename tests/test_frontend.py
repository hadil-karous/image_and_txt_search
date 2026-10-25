"""Parcours d'interface Streamlit avec API FastAPI temporaire, sans navigateur."""
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest
from backend.main import create_app
from frontend.api_client import ApiClient, ApiError
from pathlib import Path

APP_PATH=Path(__file__).resolve().parents[1]/'frontend/app.py'


def test_interface_selection_search_requery(prepared,monkeypatch):
    with TestClient(create_app(prepared)) as api:
        def call(self,method,path,**kwargs):
            response=api.request(method,path,**kwargs)
            if not response.is_success:
                raise ApiError(str(response.json()))
            return response.json()
        monkeypatch.setattr(ApiClient,'call',call)
        app=AppTest.from_file(APP_PATH,default_timeout=30).run()
        assert not app.exception
        app.button(key='gallery_1').click().run()
        assert app.session_state['query_mirflickr_25k']==1
        next(b for b in app.button if b.label=='Rechercher par image').click().run()
        assert not app.exception
        assert len(app.session_state['results_mirflickr_25k']['items'])==5
        app.button(key='result_2').click().run()
        assert app.session_state['query_mirflickr_25k']==2
        assert 2 not in [i['id'] for i in app.session_state['results_mirflickr_25k']['items']]
        app.text_input[0].set_value('sky water').run()
        next(b for b in app.button if b.label=='Combiner texte et image').click().run()
        assert {i['id'] for i in app.session_state['results_mirflickr_25k']['items']}=={1,3}
        app.text_input[0].set_value('zzzxnonexistent').run()
        next(b for b in app.button if b.label=='Rechercher les mots-clés').click().run()
        assert not app.session_state['results_mirflickr_25k']['items']
        assert not app.exception


def test_server_unavailable(monkeypatch):
    def fail(self):
        raise ApiError('Serveur indisponible')
    monkeypatch.setattr(ApiClient,'datasets',fail)
    app=AppTest.from_file(APP_PATH).run()
    assert not app.exception
    assert any('Serveur indisponible' in e.value for e in app.error)
