# Example Snowflake Native App - Streamlit
import streamlit as st
import snowflake.connector
from snowflake.snowpark import Session
import pandas as pd

st.set_page_config(page_title="Sales Analytics", page_icon="📊", layout="wide")
st.title("📊 Sales Analytics Dashboard")

# Snowflake connection
@st.cache_resource
def get_snowflake_connection():
    return snowflake.connector.connect(
        account=st.secrets["snowflake"]["account"],
        user=st.secrets["snowflake"]["user"],
        password=st.secrets["snowflake"]["password"],
        warehouse=st.secrets["snowflake"]["warehouse"],
        database=st.secrets["snowflake"]["database"],
        schema=st.secrets["snowflake"]["schema"]
    )

@st.cache_resource
def get_snowpark_session():
    return Session.builder.configs({
        "account": st.secrets["snowflake"]["account"],
        "user": st.secrets["snowflake"]["user"],
        "password": st.secrets["snowflake"]["password"],
        "warehouse": st.secrets["snowflake"]["warehouse"],
        "database": st.secrets["snowflake"]["database"],
        "schema": st.secrets["snowflake"]["schema"]
    }).create()

conn = get_snowflake_connection()
session = get_snowpark_session()

# Sidebar filters
st.sidebar.header("Filters")
year = st.sidebar.selectbox("Year", [2022, 2023, 2024])
region = st.sidebar.multiselect("Region", ["North", "South", "East", "West"], default=["North", "South"])

# Query using Snowpark
df = session.table("sales_data").filter(
    (session.col("year") == year) & 
    (session.col("region").in_(region))
).to_pandas()

# Display metrics
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Total Sales", f"${df['revenue'].sum():,.0f}")
with col2:
    st.metric("Orders", f"{df['order_count'].sum():,.0f}")
with col3:
    st.metric("Avg Order Value", f"${df['revenue'].sum() / df['order_count'].sum():,.2f}")
with col4:
    st.metric("Customers", f"{df['customer_id'].nunique():,.0f}")

# Chart
st.subheader("📈 Sales Trend")
st.line_chart(df.groupby('month')['revenue'].sum())

# Data table
st.subheader("📋 Sales by Product")
product_sales = df.groupby('product_name').agg({
    'revenue': 'sum',
    'order_count': 'sum'
}).sort_values('revenue', ascending=False)
st.dataframe(product_sales, use_container_width=True)

# Use stored procedure
if st.button("Calculate Forecast"):
    cursor = conn.cursor()
    cursor.execute("CALL calculate_sales_forecast(?, ?)", (year, ','.join(region)))
    forecast = cursor.fetchall()
    st.success(f"Forecast generated: ${forecast[0][0]:,.0f}")
    cursor.close()
