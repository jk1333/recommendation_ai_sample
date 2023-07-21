import streamlit as st
import pandas as pd
from google.cloud import retail_v2

st.set_page_config(page_title='Recommendations AI test', 
                    page_icon=None, 
                    layout="wide", 
                    initial_sidebar_state="auto", 
                    menu_items=None)

st.markdown("""
<style>
div.stButton > button:first-child {
    background-color: black;
    color: white;
    height: 12em;
    width: 6em;
    border-radius:10px;
    border:3px solid #000000;
    font-size:20px;
    font-weight: bold;
    margin: auto;
    display: block;
}
div.stButton > button:hover {
	background:linear-gradient(to bottom, green 5%, #ff5a5a 100%);
	background-color: white;
}
div.stButton > button:active {
	position:relative;
	top:3px;
}
</style>""", unsafe_allow_html=True)

@st.cache_resource
def get_prediction_service():
    return retail_v2.PredictionServiceClient()

@st.cache_resource
def get_search_service():
    return retail_v2.SearchServiceClient()

@st.cache_resource
def get_userevent_service():
    return retail_v2.UserEventServiceClient()

@st.cache_resource
def init_services():
    get_prediction_service()
    get_search_service()
    get_userevent_service()
    return pd.read_csv("movies.csv")

movies_df = init_services()

col1, col2 = st.columns([2, 1])
searchtxt = col1.text_input("Search", "", key="txtsearch")
if len(searchtxt) == 0:
    searchtxt = None
userid = col2.text_input("UserId", "visitor1")

def get_movie_title(product_id):
    return movies_df[movies_df['movieId'] == int(product_id)][['title']].values[0][0]

def get_predict(model, event_type, visitor_id, num, product_id = None, validate_only = False):
    user_event = retail_v2.UserEvent()
    user_event.event_type = event_type
    user_event.visitor_id = visitor_id

    if product_id is not None:
        product_detail = retail_v2.ProductDetail()
        product = retail_v2.Product()
        product.id = product_id
        product_detail.product = product
        user_event.product_details = [product_detail]

    request = retail_v2.PredictRequest(
        placement=f"projects/sandbox-373102/locations/global/catalogs/default_catalog/servingConfigs/{model}",
        user_event=user_event,
        page_size=num,
        validate_only=validate_only,
        params = {"returnProduct": True}
    )
    # Make the request
    response = get_prediction_service().predict(request=request)
    #print(response)
    # Handle the response
    return list(map(lambda x : x.id, response.results))

def update_userevent(view, visitor_id, product_id, searchtxt):
    # Initialize request argument(s)
    user_event = retail_v2.UserEvent()
    #Views are detail-page-view, home-page-view, search
    user_event.event_type = view
    user_event.visitor_id = visitor_id

    if searchtxt is not None:
        user_event.search_query = searchtxt

    #mandatory for add-to-cart, detail-page-view, purchase-complete
    if product_id is not None:
        product_detail = retail_v2.ProductDetail()
        product = retail_v2.Product()
        product.id = product_id
        product_detail.product = product
        user_event.product_details = [product_detail]

    request = retail_v2.WriteUserEventRequest(
        parent=f"projects/sandbox-373102/locations/global/catalogs/default_catalog",
        user_event=user_event,
    )
    get_userevent_service().write_user_event(request=request)

def get_search(model, query, num, visitor_id):
    spec = retail_v2.SearchRequest.PersonalizationSpec()
    spec.mode = retail_v2.SearchRequest.PersonalizationSpec.Mode.AUTO
    request = retail_v2.SearchRequest(
        placement=f"projects/sandbox-373102/locations/global/catalogs/default_catalog/servingConfigs/{model}",
        query=query,
        page_size=num,
        visitor_id=visitor_id
    )
    response = get_search_service().search(request=request)
    return list(map(lambda x : x.id, response.results))

if 'userid' not in st.session_state:
    st.session_state['userid'] = userid
elif st.session_state['userid'] != userid:
    #clear cache and refresh
    st.session_state['userid'] = userid
    st.session_state.pop('liked_product_id', None)
    st.session_state.pop('prediction_results', None)
    st.experimental_rerun()

def get_whole_recommends(clicked_item, max_num):
    whole_recommends = {}
    view = "detail-page-view"
    recommends = get_predict("movielens-pageoptimization", view, userid, max_num, clicked_item)
    for model in recommends:
        whole_recommends[model] = get_predict(model, view, userid, max_num, clicked_item)
    return whole_recommends

view_size = 8
canvas = st.empty()
container = canvas.container()
def render_view(model, view, view_size, liked_product_id, recommends):
    #print(f"Start rendering {model}")
    recommend = None
    match model:
        case "movielens-recommendation":
            #Basic recommend
            container.write("Recommended for you from your entire history")
        case "movielens-others-you-may-like":
            #Others you may like
            container.write(f"Others you may like bacause you liked '{get_movie_title(liked_product_id)}'")
        case "movielens-similar":
            #Similar items
            container.write(f"Similar items like '{get_movie_title(liked_product_id)}'")
        case "personalized-search":
            container.write("Search results by your preferences")
    if view_size > len(recommends):
        view_size = len(recommends)
    cols = container.columns([1 for _ in range(view_size)])
    for idx, col in enumerate(cols):
        if col.button(get_movie_title(recommends[idx]), key=model+recommends[idx]):
            recommend = recommends[idx]
    return view, recommend

if 'searchtxt' not in st.session_state:
    st.session_state['searchtxt'] = searchtxt
elif st.session_state['searchtxt'] == searchtxt:
    searchtxt = None    

clicked_view = None
clicked_product_id = None
if searchtxt is not None:
    #Search rendering
    print("####Start rendering searched item")    
    recommends = get_search("personalized-search", searchtxt, view_size, userid)
    if len(recommends) > 0:
        clicked_view, clicked_product_id = render_view("personalized-search", "search", view_size, None, recommends)
        if clicked_product_id is not None:
            st.session_state['searchtxt'] = searchtxt
    else:
        st.session_state['searchtxt'] = searchtxt
        container.write(f"No search result")
elif "prediction_results" not in st.session_state:
#elif st.session_state.isinit == False:
#    st.session_state.isinit = True
    #Initial rendering, use basic recommend only
    print("##Start Initial rendering")
    container.write(f"Hello {userid}!")
    recommends = get_predict("movielens-recommendation", "home-page-view", userid, view_size)
    clicked_view, clicked_product_id = render_view("movielens-recommendation", "home-page-view", view_size, None, recommends)
    print(f"{clicked_view} / {clicked_product_id}")
else:
    #Rendering cached item which data processed from last page
    print("#####Start rendering cached item")
    data_to_render = st.session_state['prediction_results']
    for model, recommends in data_to_render.items():
        a, b = render_view(model, "detail-page-view", view_size, st.session_state['liked_product_id'], recommends)
        if b is not None:
            clicked_view, clicked_product_id = a, b

if clicked_product_id is not None:
    print("Clicked!!!")
    canvas.empty()
    st.session_state['liked_product_id'] = clicked_product_id
    st.session_state['prediction_results'] = get_whole_recommends(clicked_product_id, view_size)
    update_userevent(clicked_view, userid, clicked_product_id, searchtxt)
    st.experimental_rerun()

print("Rendering complete")