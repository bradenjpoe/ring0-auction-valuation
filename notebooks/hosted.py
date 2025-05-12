import streamlit as st
import pandas as pd
import plotly.express as px

def render_md(filename):
    path = f"notebooks/markdown/{filename}"
    with open(path, "r") as f:
        st.markdown(f.read())

# Load data
only_sold = pd.read_csv("notebooks/only_sold.csv")
sire_data = pd.read_csv("notebooks/sire_data.csv")
all_data = pd.read_csv("notebooks/all_data.csv")

# Widen layout
st.set_page_config(layout="wide")

# Markdown Introduction
st.title("Keeneland Yearling Sales Dashboard")
render_md("overview.md")

st.markdown("---")

# Yearly Sales Data Box Plot
st.header("Box Plot: Yearly Sales by Sire")
render_md("yearly_sales.md")
data_toggle = st.radio("Data: (box plot)", ["Excluding >95th Percentile", "Full"])
all_sires = sorted(only_sold["Sire"].unique())
sire_options = [s for s in all_sires]
selected_sires = st.multiselect("Select sires:", sire_options, default=None, key="options1")

df = only_sold
if data_toggle.startswith("Excluding"):
    df = df[df.Price <= df.Price.quantile(.95)]
if selected_sires:
    df = df[df["Sire"].isin(selected_sires)]

fig = px.box(
    df, x="sale_year", y="Price",
    hover_data=["Sire", "Description", "Purchaser"],
    title="Keeneland Sept Yearling Sales by Sire"
)
st.plotly_chart(fig)

st.markdown("---")

# Sire Performance Scatter Plot
st.header("Scatter Plot: Sire Performance")
render_md("sire_performance.md")
foal_min_1 = st.number_input("Foals per year ≥", value=10, step=1, key="foal1")
years_active_min_1 = int(sire_data.years_active.min())
years_active_max_1 = int(sire_data.years_active.max())
year_range_1 = st.slider("Years active range:", years_active_min_1, years_active_max_1,
                         (years_active_min_1, years_active_max_1), key="range1")
lo_1, hi_1 = year_range_1
df2 = sire_data[(sire_data.foals_per_year >= foal_min_1) & (sire_data.years_active.between(lo_1, hi_1))]

fig2 = px.scatter(
    df2.reset_index(), x="gini_coef", y="median_price",
    size="foals_per_year", color="foals_per_year",
    hover_name="Sire", color_continuous_scale="plasma",
    title="Sire scatter (interactive thresholds)"
)
st.plotly_chart(fig2)

st.markdown("---")

# Correlation Plot
st.header("Interative Data Table")
render_md("data_table.md")

# Price range
price_min = int(only_sold.Price.min())
price_max = int(only_sold.Price.max())
price_range = st.slider("Price range:", price_min, price_max,
                         (price_min, price_max),
                         key="range3")
loP, hiP = price_range

# Year range
year_min = int(only_sold.sale_year.min())
year_max = int(only_sold.sale_year.max())
year_range = st.slider("Sale Year range:", year_min, year_max,
                         (year_min, year_max),
                         key="range4")
loY, hiY = year_range

# Sires
all_sires1 = sorted(all_data["Sire"].unique())
sire_options1 = [s for s in all_sires1]
selected_sires = st.multiselect("Select sires:", sire_options1, default=None, key='options2')

# Sales Status
status = sorted(all_data["status"].unique())
status_options = [s for s in status]
selected_statuses = st.multiselect("Select sales status:", status_options, default=None, key='options3')

df3 = all_data[["Sire", "Dam", "Description",
                 "Price", "Sex", "Color", "sale_year",
                 "Session", "Hip", "Purchaser", "PropertyLine1", "status"]]
if selected_sires:
    df3 = df3[df3["Sire"].isin(selected_sires)]
if price_range: 
    df3 = df3[(df3.status=='Sold') & (df3.Price.between(loP, hiP))]
if year_range:
    df3 = df3[(df3.sale_year.between(loY, hiY))]  
if selected_statuses: 
    df3 = df3[df3["status"].isin(selected_statuses)]

st.dataframe(df3)
# corr_by_year = (
#     df3.groupby("years_active")
#       .apply(lambda g: g["gini_coef"].corr(g["median_price"]))
#       .dropna()
#       .reset_index(name="corr")
#       .sort_values("years_active")
# )

# fig3 = px.line(
#     corr_by_year, x="years_active", y="corr",
#     markers=True,
#     title="Correlation (gini coef ↔ median price) by years active"
# )
# fig3.update_layout(yaxis_title="Correlation [-1,1]", xaxis_title="Years active")
# st.plotly_chart(fig3)