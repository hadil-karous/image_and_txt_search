"""Interface française : toutes les données passent par FastAPI."""
import streamlit as st
from frontend.api_client import ApiClient, ApiError

st.set_page_config(page_title='Prisme · Recherche d’images',page_icon='◈',layout='wide')
st.markdown('''<style>
.stApp {background:#f6f7f3} h1,h2,h3 {color:#153e35}
[data-testid="stSidebar"] {background:#e9eee7}
div[data-testid="stMetric"] {background:white;padding:12px;border-radius:12px}
.eyebrow {color:#3c806a;font-size:12px;letter-spacing:3px;font-weight:700}
</style><div class="eyebrow">LIASA / EXPLORATION VISUELLE</div>''',unsafe_allow_html=True)
st.title('Prisme')
st.write('Des mots, des couleurs, des textures. Explorez une collection d’images et suivez leurs ressemblances.')


@st.cache_resource
def client():
    return ApiClient()


api=client()
try:
    bases=api.datasets()
except ApiError as exc:
    st.error(str(exc))
    st.code('.\\.venv\\Scripts\\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000',language='powershell')
    st.stop()

available=[b for b in bases if b['available']]
if not available:
    st.info('Aucune base importée. Exécutez le script d’import avant de parcourir la collection.')
    st.stop()

with st.sidebar:
    st.header('Votre recherche')
    dataset=st.selectbox('Base d’images',[b['name'] for b in available],format_func=lambda n:n.replace('_',' ').upper())
    base=next(b for b in available if b['name']==dataset)
    options=[d['name'] for d in base['descriptors'] if d['available']]
    labels={'hsv':'HSV','lbp':'LBP','hog':'HOG',
        'mpeg7_edgehistogram':'MPEG-7 · Edge Histogram',
        'mpeg7_homogeneoustexture':'MPEG-7 · Homogeneous Texture'}
    methods=st.multiselect('Descripteurs',options,default=options[:1],format_func=lambda n:labels.get(n,n),key=f'descriptors_{dataset}')
    weights=[st.slider(f'Poids {name.upper()}',0.0,3.0,1.0,0.1,key=f'w_{dataset}_{name}') for name in methods]
    indexed=len(methods)==1 and next(d['index_available'] for d in base['descriptors'] if d['name']==methods[0])
    mode=st.selectbox('Méthode',['exhaustive','indexed'] if indexed else ['exhaustive'],
        format_func=lambda m:'VP-Tree exact' if m=='indexed' else 'Exhaustive',key=f'mode_{dataset}_{indexed}')
    if len(methods)>1:
        st.caption('Fusion : classement exhaustif avec des poids normalisés.')
    elif not indexed:
        st.caption('Index indisponible pour cette sélection.')
    k=st.slider('Nombre de résultats',1,60,12)
    keywords=st.text_input('Mots-clés (tous requis)',placeholder='sky water',disabled=not base['annotated_images'])
    if not base['annotated_images']:
        st.info('Aucune annotation disponible pour cette base.')
    else:
        st.caption('Tags utilisateur, souvent en anglais. Les tags ne constituent pas une vérité terrain exhaustive.')
    missing=[b['name'] for b in bases if not b['available']]
    if missing:
        st.caption('Bases non fournies : '+', '.join(missing))
    mpeg7=[d for d in base['descriptors'] if d.get('family')=='mpeg7' and d['available']]
    if mpeg7:
        for descriptor in mpeg7:
            st.caption(f"{labels[descriptor['name']]} : {descriptor['count']:,} images · {descriptor['dimension']} dimensions".replace(',',' '))
        st.caption('MPEG-7 : correspondances vérifiées par contenu. Valeurs fournies conservées ; L2 appliquée pour la recherche.')
        if any(d['count']<base['image_count'] for d in mpeg7):
            st.info('Couverture MPEG-7 partielle : les images sans correspondance vérifiée sont exclues.')
    else:
        st.caption('MPEG-7 indisponible : importer uniquement des correspondances vérifiées.')

query_key=f'query_{dataset}'
result_key=f'results_{dataset}'
pending_key=f'pending_{dataset}'
query_id=st.session_state.get(query_key)
common_count=min([d['count'] for d in base['descriptors'] if d['name'] in methods] or [0])
a,b,c=st.columns(3)
a.metric('Images dans le catalogue',f"{base['image_count']:,}".replace(',',' '))
b.metric('Vecteurs par descripteur sélectionné',f'{common_count:,}'.replace(',',' '))
c.metric('Images avec des tags',f"{base['annotated_images']:,}".replace(',',' '))
st.caption('La couverture commune exacte est indiquée après chaque recherche visuelle.')


def choose(image_id,search=False):
    st.session_state[query_key]=image_id
    st.session_state[pending_key]=search


def show_cards(items,prefix,search=False):
    columns=st.columns(4)
    for n,item in enumerate(items):
        with columns[n%4]:
            with st.container(border=True):
                st.image(item['url'],width=230)
                st.markdown(f"**Image {item['source_id']}**")
                if 'distance' in item:
                    st.caption(f"Distance : {item['distance']:.4f}")
                if 'text_score' in item:
                    st.caption(f"Score textuel : {item['text_score']:.6f}")
                st.caption(', '.join(item['tags'][:6]) or 'Sans tags')
                st.button('Utiliser comme image requête',key=f'{prefix}_{item["id"]}',
                    on_click=choose,args=(item['id'],search),disabled=not options)


if query_id:
    try:
        query=api.image(query_id)
        left,right=st.columns([1,3])
        with left:
            st.image(query['url'],width=230)
        with right:
            st.subheader(f"Image requête · {query['source_id']}")
            st.write(', '.join(query['tags']) or 'Sans tags')
            st.caption('L’image requête est exclue des résultats. Une distance plus faible indique une plus grande ressemblance.')
            st.button('Effacer la sélection',on_click=lambda:st.session_state.pop(query_key,None))
    except ApiError as exc:
        st.error(str(exc))

buttons=st.columns(3)
text_clicked=buttons[0].button('Rechercher les mots-clés',disabled=not keywords.strip(),use_container_width=True)
visual_clicked=buttons[1].button('Rechercher par image',disabled=not query_id or not methods or not any(weights),type='primary',use_container_width=True)
combined_clicked=buttons[2].button('Combiner texte et image',disabled=not query_id or not methods or not any(weights) or not keywords.strip(),use_container_width=True)
pending=st.session_state.pop(pending_key,False)
if text_clicked or visual_clicked or combined_clicked or pending:
    try:
        with st.spinner('Recherche dans la collection…'):
            if text_clicked:
                result=api.search('text',dict(dataset=dataset,keywords=keywords,k=k))
            else:
                kind='combined' if combined_clicked or (pending and keywords.strip()) else 'visual'
                body=dict(dataset=dataset,query_id=query_id,descriptors=methods,weights=weights,k=k,method=mode)
                if kind=='combined':
                    body['keywords']=keywords
                result=api.search(kind,body)
            st.session_state[result_key]=result
    except ApiError as exc:
        st.error(str(exc))

result=st.session_state.get(result_key)
if result is not None:
    st.subheader('Résultats')
    st.caption(f"{len(result['items'])} résultat(s) · {result['method_used']} · {result['elapsed_ms']:.1f} ms")
    if 'searchable_images' in result:
        st.caption(f"Couverture commune : {result['searchable_images']} images · candidats hors requête : {result['candidate_count']}")
    if result.get('message'):
        st.info(result['message'])
    if result['items']:
        show_cards(result['items'],'result',True)
    else:
        st.info('Aucun résultat pour cette recherche.')

st.divider()
st.subheader('Parcourir la collection')
page=st.number_input('Page',min_value=1,max_value=max(1,(base['image_count']+11)//12),step=1,key=f'page_{dataset}')
try:
    gallery=api.browse(dataset,(page-1)*12)
    show_cards(gallery['items'],'gallery')
except ApiError as exc:
    st.error(str(exc))
