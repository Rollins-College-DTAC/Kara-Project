"""One call that gives every page the shared look (fonts, navy sidebar, cards, animations)."""

import streamlit as st

from dashboard.ui import CSS


def inject() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
