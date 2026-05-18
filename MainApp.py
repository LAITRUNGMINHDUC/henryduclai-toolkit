import streamlit as st

from auth import require_auth


def main() -> None:
    st.set_page_config(page_title="Streamlit Multi-Page App", layout="wide")
    st.title("Streamlit Multi-Page App")

    st.markdown(
        "Chào mừng đến với ứng dụng Streamlit đa trang. Sử dụng thanh sidebar để điều hướng giữa các phần của ứng dụng."
    )

    st.markdown("## Các trang hiện có")
    st.markdown("- **Invoice Extraction**: Tải lên nhiều file PDF/ảnh, trích xuất dữ liệu hóa đơn, và tải xuống Excel/CSV.")
    st.markdown("- **Image OCR Converter**: Chuyển ảnh thành văn bản bằng Azure OpenAI cùng tính năng đăng nhập.")
    st.markdown("- **Google Map Route calculator**: Tải lên bảng địa chỉ Excel và tính quãng đường/duration cùng link bản đồ.")
    st.markdown("- **Truck Route Optimization**: Tối ưu lộ trình xe dựa trên Google Maps và OR-Tools.")
    st.markdown("- **Keyword Matching with Score**: Quét CV và tính điểm từ khóa với báo cáo Excel.")

    st.markdown("---")
    st.markdown("### Điều hướng nhanh")
    st.markdown(
        "Nếu bạn đang sử dụng Streamlit, mở sidebar để chuyển sang trang **Invoice Extraction**. "
        "Hoặc truy cập trực tiếp bằng liên kết:"
    )
    st.markdown(
        "[Go to Invoice Extraction](./?page=Invoice%20Extraction)"
    )

    st.info("Lưu ý: Sidebar tự động xuất hiện khi có nhiều trang trong thư mục `pages`.")


if __name__ == "__main__":
    if require_auth():
        main()
