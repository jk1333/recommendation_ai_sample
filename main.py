import streamlit as st
import pandas as pd
from google.cloud import retail_v2
import sys
PROJECT_ID = sys.argv[1]

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
    st.session_state.recommendations = {}
    st.session_state.clicked_product_id = None
    return pd.read_csv("movies.csv")

movies_df = init_services()
view_size = 8

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
        placement=f"projects/{PROJECT_ID}/locations/global/catalogs/default_catalog/servingConfigs/{model}",
        user_event=user_event,
        page_size=num,
        validate_only=validate_only,
        params = {"returnProduct": True}
    )
    # Make the request
    response = get_prediction_service().predict(request=request)
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
        parent=f"projects/{PROJECT_ID}/locations/global/catalogs/default_catalog",
        user_event=user_event,
    )
    get_userevent_service().write_user_event(request=request)

def get_search(model, query, num, visitor_id):
    spec = retail_v2.SearchRequest.PersonalizationSpec()
    spec.mode = retail_v2.SearchRequest.PersonalizationSpec.Mode.AUTO
    request = retail_v2.SearchRequest(
        placement=f"projects/{PROJECT_ID}/locations/global/catalogs/default_catalog/servingConfigs/{model}",
        query=query,
        page_size=num,
        visitor_id=visitor_id
    )
    response = get_search_service().search(request=request)
    return list(map(lambda x : x.id, response.results))

def on_search_change():
    if len(st.session_state.search) > 0:
        st.session_state.recommendations.clear()
        st.session_state.recommendations["personalized-search"] = get_search(
            "personalized-search", st.session_state.search, view_size, st.session_state.userid)
    
def on_user_change():
    if len(st.session_state.userid) > 0:
        st.session_state.recommendations.clear()

col1, col2 = st.columns([2, 1])
col1.text_input("Search", "", key="search", on_change=on_search_change)
col2.text_input("UserId", "visitor1", key="userid", on_change=on_user_change)

def get_whole_recommends(clicked_view, clicked_item, max_num):
    whole_recommends = {}
    recommends = get_predict("movielens-pageoptimization", clicked_view, st.session_state.userid, max_num, clicked_item)
    for model in recommends:
        whole_recommends[model] = get_predict(model, clicked_view, st.session_state.userid, max_num, clicked_item)
    return whole_recommends

def on_item_click(clicked_view, clicked_product_id):
    st.session_state.clicked_product_id = clicked_product_id
    st.session_state.recommendations = get_whole_recommends(clicked_view, clicked_product_id, view_size)
    update_userevent(clicked_view, st.session_state.userid, clicked_product_id, None)

container = st.container()
def render_view(model, view, clicked_product_id, recommends):
    match model:
        case "movielens-recommendation":
            #Basic recommend
            container.write("Recommended for you from your entire history")
        case "movielens-others-you-may-like":
            #Others you may like
            container.write(f"Others you may like bacause you liked '{get_movie_title(clicked_product_id)}'")
        case "movielens-similar":
            #Similar items
            container.write(f"Similar items like '{get_movie_title(clicked_product_id)}'")
        case "personalized-search":
            container.write("Search results by your preferences")
    cols = container.columns([1 for _ in range(len(recommends))])
    for idx, col in enumerate(cols):
        col.button(get_movie_title(recommends[idx]), key=model+recommends[idx], on_click=on_item_click, args=[view, recommends[idx]])

if not st.session_state.recommendations:
    #Get initial recommends
    st.session_state.recommendations["movielens-recommendation"] = get_predict(
        "movielens-recommendation", "home-page-view", st.session_state.userid, view_size)
    
#Rendering cached items
for model, recommends in st.session_state.recommendations.items():
    #Rendering items
    render_view(model, "detail-page-view", st.session_state.clicked_product_id, recommends)