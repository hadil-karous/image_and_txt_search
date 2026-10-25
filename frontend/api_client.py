"""Client HTTP uniquement ; aucun accès aux images locales, vecteurs ou SQLite."""
import os
import requests


class ApiError(Exception):
    pass


class ApiClient:
    def __init__(self,base_url=None):
        self.base_url=(base_url or os.environ.get('IMAGE_SEARCH_API_URL','http://127.0.0.1:8000')).rstrip('/')
        self.session=requests.Session()

    def call(self,method,path,**kwargs):
        try:
            response=self.session.request(method,self.base_url+path,timeout=(5,120),**kwargs)
            if not response.ok:
                try:
                    detail=response.json().get('detail',response.text)
                except ValueError:
                    detail=response.text
                raise ApiError(f'API {response.status_code} : {detail}')
            return response.json()
        except requests.RequestException as exc:
            raise ApiError(f'Serveur indisponible à {self.base_url}. Lancez FastAPI. ({exc.__class__.__name__})') from exc

    def datasets(self):
        return self.call('GET','/datasets')

    def browse(self,dataset,offset=0,limit=12):
        return self.call('GET','/images',params=dict(dataset=dataset,offset=offset,limit=limit))

    def image(self,image_id):
        return self.call('GET',f'/images/{image_id}')

    def search(self,kind,body):
        return self.call('POST',f'/search/{kind}',json=body)
