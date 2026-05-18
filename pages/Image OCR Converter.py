import base64
import os

import streamlit as st
from auth import logout, require_auth
from openai import AzureOpenAI

AZURE_ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
AZURE_KEY = os.environ.get("AZURE_OPENAI_KEY", "")
AZURE_VERSION = os.environ.get("AZURE_OPENAI_API_VERSION", "")
DEPLOYMENT_NAME = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "")


def encode_image(image_file):
    return base64.b64encode(image_file.read()).decode("utf-8")


def get_openai_client():
    return AzureOpenAI(
        azure_endpoint=AZURE_ENDPOINT,
        api_key=AZURE_KEY,
        api_version=AZURE_VERSION,
    )


def main_app():
    st.set_page_config(page_title="Image OCR Converter", layout="wide")
    st.title("📸 Image OCR Converter")
    st.markdown(
        "Upload multiple image files and convert them to extracted text using Azure OpenAI. "
        "Use the sidebar to upload files and logout."
    )

    with st.sidebar:
        st.title("Settings")
        if st.button("Logout"):
            logout()
        st.divider()
        uploaded_files = st.file_uploader(
            "Tải lên nhiều ảnh cùng lúc",
            type=["png", "jpg", "jpeg"],
            accept_multiple_files=True,
        )

    if "messages" not in st.session_state:
        st.session_state.messages = []

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    images_to_process = []
    if uploaded_files:
        for f in uploaded_files:
            images_to_process.append({"name": f.name, "data": f})

    if images_to_process:
        st.info(f"Đang có {len(images_to_process)} ảnh chờ xử lý.")

    user_prompt = "Extract text in this image and provide output that is easy to read and understand. Focus on accuracy and clarity."

    if images_to_process and st.button("Bắt đầu xử lý OCR"):
        client = get_openai_client()
        st.session_state.messages.append({"role": "user", "content": user_prompt})

        for uploaded_file in images_to_process:
            base64_image = encode_image(uploaded_file["data"])
            with st.chat_message("user"):
                st.image(uploaded_file["data"], width=300)
                st.markdown(user_prompt)

            with st.chat_message("assistant"):
                with st.spinner("Đang đọc dữ liệu..."):
                    try:
                        response = client.chat.completions.create(
                            model=DEPLOYMENT_NAME,
                            messages=[
                                {"role": "system", "content": "You are a professional OCR assistant."},
                                {
                                    "role": "user",
                                    "content": [
                                        {"type": "text", "text": user_prompt},
                                        {
                                            "type": "image_url",
                                            "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
                                        },
                                    ],
                                },
                            ],
                            max_tokens=20000,
                        )
                        res_text = response.choices[0].message.content or ""
                        st.markdown(res_text)
                        st.session_state.messages.append({"role": "assistant", "content": res_text})
                    except Exception as e:
                        st.error(f"Lỗi: {e}")


if __name__ == "__main__":
    if require_auth():
        main_app()
