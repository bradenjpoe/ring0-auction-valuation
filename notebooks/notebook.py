import pandas as pd
import plotly.express as px
import ipywidgets as w
from ipywidgets.embed import embed_minimal_html 
from ipywidgets import SelectMultiple, VBox, Output
from IPython.display import display
import plotly.express as px
import warnings 
warnings.simplefilter("ignore")

sire_data = pd.read_csv("sire_data.csv", dtype={
    "gini_coef": "float32",
    "median_price": "float32",
    "avg_price": "float32",
    "foals_per_year": "float32",
    "years_active": "int16",
})

only_sold = pd.read_csv("only_sold.csv",
                        dtype={"Price": "float32",
                               "sale_year": "int16"},
                        usecols=["Sire",
                                 "Description",
                                 "Price",
                                 "sale_year",
                                 "Purchaser"])


# ── build the two DataFrames up front ──────────────────────────
full_df     = only_sold.copy()
subset_df   = full_df[full_df.Price <= full_df.Price.quantile(.95)]

# a master list of sires (covers both data sets)
all_sires   = sorted(full_df["Sire"].unique())

# ── widgets ────────────────────────────────────────────────────
data_toggle = w.ToggleButtons(
    options=["Excluding >95th Percentile", "Full"],
    description="Data:"
)

sire_search      = w.Text(placeholder="Search sire…", layout=w.Layout(width="50%"))
sire_multiselect = w.SelectMultiple(options=all_sires, rows=8, layout=w.Layout(width="50%"))

fig_out = w.Output()

# --------------------------------------------------------------
def _filter_options(text_widget, multi_widget, full_list):
    """Live-filter the options in a SelectMultiple, keep existing selections."""
    pat  = text_widget.value.strip().lower()
    keep = multi_widget.value
    opts = [o for o in full_list if pat in o.lower()]
    multi_widget.options = opts
    # restore any choices that are still present after filtering
    multi_widget.value   = tuple(o for o in keep if o in opts)

sire_search.observe(
    lambda ch: _filter_options(sire_search, sire_multiselect, all_sires),
    names="value"
)

# --------------------------------------------------------------
def redraw(_=None):
    # 1 choose which DataFrame to plot
    df = subset_df if data_toggle.value.startswith("Excluding") else full_df

    # 2 apply the sire filter (if any)
    if sire_multiselect.value:
        df = df[df["Sire"].isin(sire_multiselect.value)]

    # 3 draw / update the figure
    with fig_out:
        fig_out.clear_output(wait=True)
        px.box(
            df, x="sale_year", y="Price",
            hover_data=["Sire", "Description", "Purchaser"],
            title="Keeneland Sept Yearling Sales by Sire"
        ).show()

# trigger redraw whenever a control changes
for widg in (data_toggle, sire_multiselect):
    widg.observe(redraw, names="value")

# initial plot
redraw()

# ── layout ────────────────────────────────────────────────────
display(
    w.VBox([
        data_toggle,
        w.HTML("<b>Sire filter</b>"),
        sire_search,
        sire_multiselect,
        fig_out
    ])
)

def plot_dynamic(circle_size="foals_per_year"):
    """
    Interactive scatter with:
      • x-axis  : gini_coef
      • y-axis  : avg_price
      • size / colour : <circle_size> column
      • filters :
            foals_per_year ≥ F
            years_active between [Ymin, Ymax]
    """
    # ── widgets ────────────────────────────────────────────────
    foal_min = w.IntText(value=10, description="Foals per year ≥", step=1)

    yr_min, yr_max = int(sire_data.years_active.min()), int(sire_data.years_active.max())
    year_range = w.IntRangeSlider(
        value=[yr_min, yr_max], min=yr_min, max=yr_max, step=1,
        description="Years active",
        continuous_update=False, layout=w.Layout(width="75%")
    )

    fig_out = w.Output()

    # ── redraw helper ─────────────────────────────────────────
    def redraw(*_):
        lo, hi = year_range.value
        df = sire_data.loc[
            (sire_data.foals_per_year >= foal_min.value) &
            (sire_data.years_active.between(lo, hi))
        ]
        with fig_out:
            fig_out.clear_output(wait=True)
            px.scatter(
                df.reset_index(),
                x="gini_coef", y="median_price",
                size=circle_size, color=circle_size,
                hover_name="Sire",
                color_continuous_scale="plasma",
                title="Sire scatter (interactive thresholds)"
            ).show()

    # update on any control change
    foal_min.observe(redraw, names="value")
    year_range.observe(redraw, names="value")

    redraw()  # initial draw

    # ── lay out the controls and figure ───────────────────────
    display(w.VBox([
        w.HBox([foal_min, year_range]),
        fig_out
    ]))

# call the function to launch the UI
plot_dynamic("foals_per_year")        # or another column name

df0 = sire_data.reset_index().copy()

# ── master lists / limits ─────────────────────────────────────────────────
yr_min, yr_max = int(df0.years_active.min()), int(df0.years_active.max())

# ── widgets ───────────────────────────────────────────────────────────────
foal_min = w.IntText(value=10, description="Foal ≥", step=1,
                     layout=w.Layout(width="150px"))

year_range = w.IntRangeSlider(
    value=[yr_min, yr_max], min=yr_min, max=yr_max, step=1,
    description="Years active", continuous_update=False,
    layout=w.Layout(width="70%")
)

plot_out = w.Output()

# ── helper: live-filter the SelectMultiple options list ───────────────────
def _filter_options(text_widget, multi_widget, full_list):
    pat = text_widget.value.strip().lower()
    keep = multi_widget.value
    opts = [o for o in full_list if pat in o.lower()]
    multi_widget.options = opts
    multi_widget.value = tuple(o for o in keep if o in opts)

sire_search.observe(
    lambda c: _filter_options(sire_search, sire_multiselect, all_sires),
    names="value"
)

# ── recompute + redraw ────────────────────────────────────────────────────
def redraw(_=None):
    lo, hi = year_range.value

    # 1 apply filters
    d = df0.loc[
        (df0.foals_per_year >= foal_min.value) &
        (df0.years_active.between(lo, hi))
    ]

    # 2 group by years_active and compute Pearson r
    corr_by_year = (
        d.groupby("years_active")
         .apply(lambda g: g["gini_coef"].corr(g["median_price"]))
         .dropna()
         .reset_index(name="corr")
         .sort_values("years_active")
    )

    # 3 draw the line plot
    with plot_out:
        plot_out.clear_output(wait=True)
        if corr_by_year.empty:
            print("No data after filters.")
            return
        fig = px.line(
            corr_by_year, x="years_active", y="corr",
            markers=True,
            title="Correlation (gini coef ↔ median price) by years active"
        )
        fig.update_layout(
            yaxis_title="Correlation [-1,1]", xaxis_title="Years active",
            yaxis=dict(range=[-1, 1])
        )
        fig.show()

# watch every control
for widg in (foal_min, year_range, sire_multiselect):
    widg.observe(redraw, names="value")

# initial draw
redraw()

ui = w.VBox([
        w.HBox([foal_min, year_range]),
        plot_out
     ])

display(ui)                 # still shows in the notebook