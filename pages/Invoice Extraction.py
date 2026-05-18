import io
import json
import os

import fitz
import pandas as pd
import streamlit as st
from auth import require_auth
from openai import AzureOpenAI
from PIL import Image

try:
    import pytesseract
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False


def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            return "\n".join(page.get_text("text")  # type: ignore[attr-defined]
                                   for page in doc)
    except Exception as exc:
        st.error(f"Không thể đọc PDF: {exc}")
        return ""


def extract_text_from_image_bytes(image_bytes: bytes) -> str:
    if not OCR_AVAILABLE:
        st.error("Thiếu pytesseract để trích xuất text từ ảnh. Cài đặt pytesseract + pillow.")
        return ""

    try:
        image = Image.open(io.BytesIO(image_bytes))
        return pytesseract.image_to_string(image, lang="vie+eng")
    except Exception as exc:
        st.error(f"Lỗi OCR ảnh: {exc}")
        return ""


def create_openai_client(endpoint: str, api_key: str, api_version: str) -> AzureOpenAI:
    return AzureOpenAI(
        azure_endpoint=endpoint,
        api_key=api_key,
        api_version=api_version,
    )


def structure_text_to_json(text: str, client: AzureOpenAI, deployment_name: str) -> str:
    system_message = """
Bạn là một trợ lý AI chuyên phân tích dữ liệu hóa đơn Việt Nam.
Nhiệm vụ của bạn là trích xuất thông tin từ văn bản hóa đơn (hóa đơn GTGT) và trả về dưới định dạng JSON chính xác.

Yêu cầu cấu trúc JSON trả về phải bao gồm 2 phần chính:
1. "invoice_header": Chứa các trường thông tin chung. Các trường số như MST, số hóa đơn phải là chuỗi (string). Các trường số tiền phải là số (number).
2. "invoice_items": Là một mảng (array) chứa chi tiết các mặt hàng.

Dữ liệu cần trả về có cấu trúc như sau:
{
  "invoice_header": {
    "invoice_name": "Tên hóa đơn",
    "invoice_date": "Ngày hóa đơn (dd/mm/yyyy)",
    "serial": "Ký hiệu",
    "number": "Số hóa đơn",
    "seller_name": "Tên đơn vị bán",
    "seller_tax_code": "MST người bán",
    "buyer_company_name": "Tên đơn vị mua",
    "buyer_tax_code": "MST người mua",
    "total_amount_without_vat": "Cộng tiền hàng (số)",
    "vat_rate": "Thuế suất GTGT",
    "vat_amount": "Tiền thuế GTGT (số)",
    "grand_total": "Tổng cộng tiền thanh toán (số)",
    "amount_in_word": "Số tiền viết bằng chữ"
  },
  "invoice_items": [
    {
      "stt": "STT (số)",
      "description": "Tên hàng hóa, dịch vụ",
      "unit": "Đơn vị tính",
      "quantity": "Số lượng (số)",
      "unit_price": "Đơn giá (số)",
      "amount": "Thành tiền (số)"
    }
  ]
}
Lưu ý: Bạn hãy bỏ qua các phần chữ ký số và thông tin tra cứu hóa đơn ở cuối.
"""

    response = client.chat.completions.create(
        model=deployment_name,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": f"Văn bản hóa đơn cần xử lý:\n{text}"},
        ],
        temperature=0.1,
    )

    return response.choices[0].message.content or ""


def to_excel_bytes(dataframe: pd.DataFrame) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        dataframe.to_excel(writer, index=False)
    return output.getvalue()


def main() -> None:
    st.set_page_config(page_title="Invoice Extraction", layout="wide")
    st.title("Invoice Extraction")
    st.markdown(
        "Upload multiple PDF or image files, extract invoice data with Azure OpenAI, and download results as Excel/CSV."
    )

    uploaded_files = st.file_uploader(
        "Choose multiple PDF or image files",
        type=["pdf", "png", "jpg", "jpeg"],
        accept_multiple_files=True,
    )

    if uploaded_files and st.button("Process files"):
        # if not api_key:
        #     st.error("Missing API key. Please enter it in the configuration section.")
        #     return
        azure_endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
        api_key = os.environ.get("AZURE_OPENAI_KEY", "")
        api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "")
        deployment_name = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")

        client = create_openai_client(azure_endpoint, api_key, api_version)
        header_rows = []
        item_rows = []

        for uploaded_file in uploaded_files:
            file_bytes = uploaded_file.read()
            file_name = uploaded_file.name
            st.write(f"Processing: {file_name}")

            if file_name.lower().endswith(".pdf"):
                text = extract_text_from_pdf_bytes(file_bytes)
            else:
                text = extract_text_from_image_bytes(file_bytes)

            if not text:
                st.warning(f"No text extracted from {file_name}. Skipping.")
                continue

            with st.spinner(f"Calling Azure OpenAI for {file_name}..."):
                try:
                    raw_json = structure_text_to_json(text, client, deployment_name)
                    parsed = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
                except json.JSONDecodeError as err:
                    st.error(f"Response was not valid JSON for {file_name}: {err}")
                    st.code(raw_json)
                    continue
                except Exception as exc:
                    st.error(f"Error calling Azure OpenAI for {file_name}: {exc}")
                    continue

            invoice_header = parsed.get("invoice_header", {})
            invoice_items = parsed.get("invoice_items", [])

            if invoice_header:
                invoice_header["source_file"] = file_name
                header_rows.append(invoice_header)

            if isinstance(invoice_items, list) and invoice_items:
                for item in invoice_items:
                    item_record = dict(item)
                    item_record["source_file"] = file_name
                    item_rows.append(item_record)

        if header_rows:
            header_df = pd.DataFrame(header_rows)
            st.subheader("Invoice Headers")
            st.dataframe(header_df)

            csv_bytes = header_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "Download Invoice Headers CSV",
                data=csv_bytes,
                file_name="invoice_headers.csv",
                mime="text/csv",
            )
            st.download_button(
                "Download Invoice Headers Excel",
                data=to_excel_bytes(header_df),
                file_name="invoice_headers.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        else:
            st.info("No invoice header data was extracted.")

        if item_rows:
            items_df = pd.DataFrame(item_rows)
            st.subheader("Invoice Items")
            st.dataframe(items_df)

            csv_bytes = items_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "Download Invoice Items CSV",
                data=csv_bytes,
                file_name="invoice_items.csv",
                mime="text/csv",
            )
            st.download_button(
                "Download Invoice Items Excel",
                data=to_excel_bytes(items_df),
                file_name="invoice_items.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        elif header_rows:
            st.info("Invoice headers were extracted, but no invoice items were found.")

    if not OCR_AVAILABLE:
        st.info(
            "OCR for images is not installed. Install pytesseract and pillow if you want to process images: `pip install pytesseract pillow`."
        )


if __name__ == "__main__":
    if require_auth():
        main()
