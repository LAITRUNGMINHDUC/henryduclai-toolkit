import io
import os

import googlemaps
import pandas as pd
import requests
import streamlit as st
from auth import logout, require_auth
# from stqdm import stqdm

st.set_page_config(page_title="Google Map Route calculator", page_icon="🗺️")
# stqdm.pandas()

GOOGLE_APIKEY = os.environ.get("GOOGLE_APIKEY", "")
MSTEAMS_URL = os.environ.get("MSTEAMS_URL", "")

client = googlemaps.Client(key=GOOGLE_APIKEY) if GOOGLE_APIKEY else None


def get_distance_estimation(from_address, to_address):
    try:
        result = client.distance_matrix(from_address, to_address)["rows"][0]["elements"][0]
        distance = result["distance"]["value"]
        duration = result["duration"]["value"]
        return pd.Series([distance, duration])
    except Exception:
        return pd.Series([-1, -1])


def get_data_file():
    with st.form("Provide the Address list", clear_on_submit=True):
        uploaded_file = st.file_uploader(
            "Provide the Address list file - Excel Template",
            type="xlsx",
        )
        submitted = st.form_submit_button("Submit")
        if submitted and uploaded_file is not None:
            return uploaded_file
    return None


def get_distance_matrix_result(uploaded_file):
    if not GOOGLE_APIKEY:
        st.error("Missing GOOGLE_APIKEY environment variable. Set it before using this page.")
        return

    if uploaded_file is not None:
        df_map = pd.read_excel(uploaded_file, sheet_name="DATA")
        output_result = df_map.apply(
            lambda x: get_distance_estimation(x["FROM_ADDRESS"], x["TO_ADDRESS"]),
            axis=1,
        )

        df_map[["DISTANCE", "DURATION"]] = output_result
        df_map["MAP_LINK"] = df_map.apply(
            lambda x: f"https://www.google.com/maps/dir/{x['FROM_ADDRESS']}/{x['TO_ADDRESS']}",
            axis=1,
        )

        in_memory_fp = io.BytesIO()
        df_map.to_excel(in_memory_fp, index=False)
        in_memory_fp.seek(0)

        st.download_button(
            "Download result file",
            file_name="RESULT_DISTANCE_REVIEW.xlsx",
            data=in_memory_fp,
        )

        if MSTEAMS_URL:
            requests.post(
                url=MSTEAMS_URL,
                json={
                    "message": f"User {st.session_state.get('user_info')} - 🗺️ Google Maps Routes Calculator - {df_map.shape[0]} requests"
                },
            )

        st.write(df_map)


def main_app():
    st.title("🗺️ Google Map Route calculator")
    st.write(
        "Upload an Excel file with a `DATA` sheet containing `FROM_ADDRESS` and `TO_ADDRESS`. "
        "The app will return distance, duration, and a Google Maps link for each route."
    )

    with st.sidebar:
        st.title("Settings")
        if st.button("Logout"):
            logout()

    template = pd.DataFrame(
        columns=["FROM_ADDRESS", "TO_ADDRESS", "DISTANCE", "DURATION", "MAP_LINK"]
    )
    in_memory_fp = io.BytesIO()
    with pd.ExcelWriter(in_memory_fp, engine="openpyxl") as writer:
        template.to_excel(writer, index=False, sheet_name="DATA")
    in_memory_fp.seek(0)

    st.download_button(
        "Download Template file (If needed)",
        file_name="GOOGLE_MAPS_ROUTE_TEMPLATE.xlsx",
        data=in_memory_fp,
    )

    uploaded_file = get_data_file()
    get_distance_matrix_result(uploaded_file)


if __name__ == "__main__":
    if require_auth():
        main_app()
