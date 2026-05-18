import io
import time
import traceback

import numpy as np
import pandas as pd
import streamlit as st
from auth import logout, require_auth
from stqdm import stqdm

st.set_page_config(
    page_title="D&A Vietnam - HR CV Scanning Tool",
    page_icon="🎇🍾🎂",
)
stqdm.pandas()


def calculate_candidate_score(keywords_file, answers_file):
    try:
        df_keywords_dict = pd.read_excel(keywords_file, sheet_name=None)
        df_answers = pd.read_excel(answers_file)

        for sheet_name in df_keywords_dict.keys():
            if sheet_name not in df_answers.columns:
                st.error("Keywords Sheet name must match with column name of Candidate data")
                st.stop()
            df_answers[sheet_name] = df_answers[sheet_name].astype(str).str.lower()

        df_answers = df_answers.to_dict("records")

        for sheet_name, df_keyword in df_keywords_dict.items():
            df_keyword = df_keyword.copy()
            df_keyword["Keyword"] = df_keyword["Keyword"].astype(str).str.lower()
            df_keyword["Length"] = df_keyword["Keyword"].str.len()
            df_keyword = df_keyword.sort_values(by="Length", ascending=False)
            df_keyword = df_keyword.to_dict("records")

            for record in stqdm(df_answers, f"Run for {sheet_name}"):
                time.sleep(0.01)
                answer_str = record.get(sheet_name, "")
                matched_keywords = []
                matched_score = 0

                for keyword in df_keyword:
                    if keyword["Keyword"] in answer_str:
                        matched_score += keyword.get("Score", 0)
                        matched_keywords.append(keyword["Keyword"])
                        answer_str = answer_str.replace(keyword["Keyword"], "---")

                record[f"{sheet_name} Score"] = matched_score
                record[f"{sheet_name} Keywords"] = ", ".join(matched_keywords)

        df_answers = pd.DataFrame(df_answers)
        df_answers["Full Score"] = 0
        for sheet_name in df_keywords_dict.keys():
            df_answers["Full Score"] += df_answers[f"{sheet_name} Score"]
        df_answers = df_answers.sort_values(by="Full Score", ascending=False)

        in_memory_fp = io.BytesIO()
        df_answers.to_excel(in_memory_fp, index=False)
        in_memory_fp.seek(0)

        st.write(df_answers)
        return in_memory_fp

    except Exception as ex:
        st.error(str(ex))
        st.error(traceback.format_exc())
        return None


def main_app():
    st.header("D&A Vietnam - HR CV Scanning Tool")

    in_memory_fp = None
    with st.form("Please provide 2 required datasets", clear_on_submit=False):
        keywords_file = st.file_uploader("Keywords Dataset file", type=["xlsx"], key="keywords_file")
        answers_file = st.file_uploader("Candidate Answers file", type=["xlsx", "csv"], key="answers_file")
        submitted = st.form_submit_button("Submit")
        if submitted:
            if keywords_file is not None and answers_file is not None:
                st.success("Datasets received")
                in_memory_fp = calculate_candidate_score(keywords_file, answers_file)
            else:
                st.error("You must submit required datasets")

    if in_memory_fp is not None:
        st.download_button(
            "Download Result file",
            file_name=f"RESULT_DA_HR_TOOL_{int(time.time())}.xlsx",
            data=in_memory_fp,
        )


if __name__ == "__main__":
    with st.sidebar:
        st.title("Settings")
        if st.button("Logout"):
            logout()

    if require_auth():
        main_app()
