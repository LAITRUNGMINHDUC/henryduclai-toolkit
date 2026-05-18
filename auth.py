import json
import os

import requests
import streamlit as st

FIREBASE_API_KEY = os.environ.get("FIREBASE_API_KEY", "")


def sign_in_with_email_and_password(email: str, password: str) -> dict:
    if not FIREBASE_API_KEY:
        return {"error": {"message": "Missing FIREBASE_API_KEY environment variable."}}

    request_ref = (
        "https://www.googleapis.com/identitytoolkit/v3/relyingparty/verifyPassword?key={0}"
        .format(FIREBASE_API_KEY)
    )
    headers = {"content-type": "application/json; charset=UTF-8"}
    payload = json.dumps({"email": email, "password": password, "returnSecureToken": True})
    response = requests.post(request_ref, headers=headers, data=payload)

    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError:
        return response.json()

    return response.json()


def logout():
    st.session_state.user_info = None
    st.session_state.id_token = None
    st.experimental_rerun()


def require_auth() -> bool:
    if "user_info" not in st.session_state:
        st.session_state.user_info = None
    if "id_token" not in st.session_state:
        st.session_state.id_token = None

    if st.session_state.user_info is None:
        st.markdown("<h2 style='text-align: center;'>🔐 Đăng nhập bằng Firebase để tiếp tục</h2>", unsafe_allow_html=True)
        with st.form("AuthForm", clear_on_submit=True):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login")
            if submitted:
                auth_result = sign_in_with_email_and_password(email, password)
                if auth_result.get("idToken"):
                    st.session_state.user_info = email
                    st.session_state.id_token = auth_result.get("idToken")
                    st.success(f"Welcome {st.session_state.user_info} - You are now logged in.")
                    st.experimental_rerun()
                else:
                    error_message = auth_result.get("error", {}).get("message", "Authentication failed")
                    st.error(error_message)
        st.stop()

    return True
