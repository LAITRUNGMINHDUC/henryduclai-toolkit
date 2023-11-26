import streamlit as st 
import pandas as pd 
import numpy as np 
import traceback
import time
from stqdm import stqdm
stqdm.pandas()
import io

st.set_page_config(
    page_title="D&A Vietnam - HR CV Scanning Tool",
    page_icon="🎇🍾🎂",
)

# Define Global variables 
in_memory_fp = None

###########################################################
def calculate_candidate_score(keywords_file, answers_file):
    global in_memory_fp
    try:
        df_keywords_dict = pd.read_excel(keywords_file, sheet_name=None)
        df_answers = pd.read_excel(answers_file)
        
        ### Very quick data validation ### 
        for sheet_name in df_keywords_dict.keys():
            if sheet_name not in df_answers.columns:
                st.error("Keywords Sheet name must match with column name of Candidate data")
                st.stop()
            else:
                df_answers[sheet_name] = df_answers[sheet_name].astype(str)
                df_answers[sheet_name] = df_answers[sheet_name].str.lower()
        
        df_answers = df_answers.to_dict('records')
        ### 
        for sheet_name in df_keywords_dict.keys():
            df_keyword = df_keywords_dict[sheet_name] ### Schema: Keyword | Score
            df_keyword['Keyword'] = df_keyword['Keyword'].str.lower()
            df_keyword['Length'] = df_keyword['Keyword'].str.len()
            df_keyword = df_keyword.sort_values(by='Length', ascending=False)
            df_keyword = df_keyword.to_dict('records')

            for record in stqdm(df_answers, f"Run for {sheet_name}"):
                time.sleep(0.01)

                answer_str = record[sheet_name]
                matched_keywords = []
                matched_score = 0

                for keyword in df_keyword:
                    if keyword['Keyword'] in answer_str:
                        matched_score = matched_score + keyword['Score']
                        matched_keywords.append(keyword['Keyword'])
                        answer_str = answer_str.replace(keyword['Keyword'], "---")
                
                record[f'{sheet_name} Score'] = matched_score
                record[f'{sheet_name} Keywords'] = ', '.join(matched_keywords)
        
        df_answers = pd.DataFrame(df_answers)
        df_answers['Full Score'] = 0
        for sheet_name in df_keywords_dict.keys():
            df_answers['Full Score'] = df_answers['Full Score'] + df_answers[f'{sheet_name} Score']
        df_answers = df_answers.sort_values(by='Full Score', ascending=False)

        # Write file to Stream and trigger Download Button
        in_memory_fp = io.BytesIO()
        df_answers.to_excel(in_memory_fp, index=False)
        in_memory_fp.seek(0, 0)

        st.write(df_answers)


    except Exception as ex:
        st.error(str(ex))
        st.error(traceback.format_exc())

def main_app():
    st.header("D&A Vietnam - HR CV Scanning Tool")
    
    with st.form("Please provide 2 required datasets", clear_on_submit=False):
        keywords_file = st.file_uploader("Keywords Dataset file")
        answers_file = st.file_uploader("Candidate Answers file")
        submitted = st.form_submit_button("Submit")
        if submitted and keywords_file is not None and answers_file is not None:
            st.success("Datasets received")
            calculate_candidate_score(keywords_file, answers_file)
        else:
            st.error("You must submit required datasets")
    
    if in_memory_fp != None:
        if st.download_button('Download Result file', 
                            file_name=f"RESULT D&A HR TOOL - {time.time()}.xlsx", 
                            data=in_memory_fp):
            st.success("Thanks for downloading...")

if __name__ == "__main__":
    main_app()