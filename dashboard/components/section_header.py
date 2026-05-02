import streamlit as st


def section_label(text: str) -> None:
    st.markdown(
        f'<div style="font-size:0.68rem;color:#2A4A6A;letter-spacing:0.18em;'
        f'text-transform:uppercase;margin:20px 0 12px 0;">{text}</div>',
        unsafe_allow_html=True,
    )
