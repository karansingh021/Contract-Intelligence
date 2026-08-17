import streamlit as st
from snowflake.snowpark.context import get_active_session

st.title("Sales Dashboard")

session = get_active_session()
df = session.table("sales_summary").to_pandas()

region = st.selectbox("Region", df["CUSTOMER_ID"].unique())
st.dataframe(df)
