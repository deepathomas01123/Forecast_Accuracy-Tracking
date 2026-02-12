import streamlit as st
import pandas as pd
import altair as alt

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

# =========================
# PAGE CONFIG
# =========================
st.set_page_config(
    page_title="Forecast Volume Accuracy – One Week Out",
    layout="wide"
)

# =========================
# UTIL FUNCTIONS
# =========================
def compute_kpis(df):
    if df.empty or df["Actual Kg"].sum() == 0:
        return None, None, None

    weighted_accuracy = (
        (df["Forecast Accuracy"] * df["Actual Kg"]).sum()
        / df["Actual Kg"].sum()
    )

    return (
        weighted_accuracy,
        df["Abs_Disparity_Kg"].mean(),
        df["Abs_Disparity_Kg"].sum()
    )

@st.cache_data
def load_actuals_and_roster_data():
    actuals = pd.read_excel(os.path.join(DATA_DIR, "Actuals.xlsx"))
    forecast = pd.read_excel(os.path.join(DATA_DIR, "Roster_Data.xlsx"))

    actuals.columns = actuals.columns.str.strip()
    forecast.columns = forecast.columns.str.strip()
    return actuals, forecast

@st.cache_data
def load_week_out_with_season():
    df = pd.read_excel(
        os.path.join(DATA_DIR, "4-week-out packed forecast with Fiscal_Week_and_Season.xlsx")
    )
    df.columns = df.columns.str.strip()
    return df

# =========================
# TAB SELECTION IN SIDEBAR
# =========================
st.sidebar.markdown("## 📊 Select View")
selected_tab = st.sidebar.radio(
    "Choose analysis:",
    ["Accuracy Overview", "Weekly Analysis"],
    key="tab_selector"
)

# =========================
# RENDER BASED ON SELECTION
# =========================

if selected_tab == "Accuracy Overview":
    # =====================================================================
    # ACCURACY OVERVIEW
    # =====================================================================
    
    st.title("📊 Forecast Volume Accuracy – One Week Out")

    try:
        actuals, forecast = load_actuals_and_roster_data()
    except Exception as e:
        st.error(f"❌ Error loading data: {str(e)}")
        st.stop()

    # -------------------------
    # WEEKLY AGGREGATION
    # -------------------------
    actuals_weekly = (
        actuals
        .groupby(
            ["Plant", "Product Category", "Product Variety", "Location",
             "Costa Fiscal Year", "Fiscal Week No"],
            as_index=False
        )
        .agg({"Yield Kg": "sum"})
        .rename(columns={
            "Costa Fiscal Year": "Fiscal Year",
            "Fiscal Week No": "Fiscal Week"
        })
    )

    forecast_weekly = (
        forecast
        .groupby(
            ["Plant", "Product Category", "Product Variety",
             "Location", "Fiscal Year", "Fiscal Week"],
            as_index=False
        )
        .agg({"kg": "sum"})
        .rename(columns={"kg": "Forecast Kg"})
    )

    actuals_weekly["Fiscal Week"] = actuals_weekly["Fiscal Week"].astype(int)
    forecast_weekly["Fiscal Week"] = forecast_weekly["Fiscal Week"].astype(int)

    merged = pd.merge(
        actuals_weekly,
        forecast_weekly,
        on=["Plant", "Product Category", "Product Variety",
            "Location", "Fiscal Year", "Fiscal Week"],
        how="inner"
    )

    merged["Fiscal Year"] = merged["Fiscal Year"].astype(int)

    # -------------------------
    # SIDEBAR FILTERS
    # -------------------------
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🔍 Filters")

    filtered_df = merged.copy()

    # Fiscal Year
    fy_list = sorted(filtered_df["Fiscal Year"].unique())
    selected_fy = st.sidebar.multiselect(
        "Fiscal Year",
        options=["All"] + fy_list,
        default=["All"],
        key="acc_fy"
    )

    if "All" not in selected_fy:
        filtered_df = filtered_df[filtered_df["Fiscal Year"].isin(selected_fy)]

    # Fiscal Week
    fw_list = sorted(filtered_df["Fiscal Week"].unique())
    selected_fw = st.sidebar.multiselect(
        "Fiscal Week",
        options=["All"] + fw_list,
        default=["All"],
        key="acc_fw"
    )

    if "All" not in selected_fw:
        filtered_df = filtered_df[filtered_df["Fiscal Week"].isin(selected_fw)]

    # Plant
    plant_list = sorted(filtered_df["Plant"].unique())
    selected_plants = st.sidebar.multiselect(
        "Plant",
        options=["All"] + plant_list,
        default=["All"],
        key="acc_plant"
    )

    if "All" not in selected_plants:
        filtered_df = filtered_df[filtered_df["Plant"].isin(selected_plants)]

    # Product Category
    if "Product Category" in filtered_df.columns:
        category_list = sorted(filtered_df["Product Category"].dropna().unique())
        selected_categories = st.sidebar.multiselect(
            "Product Category",
            options=["All"] + category_list,
            default=["All"],
            key="acc_category"
        )

        if "All" not in selected_categories:
            filtered_df = filtered_df[
                filtered_df["Product Category"].isin(selected_categories)
            ]

    # -------------------------
    # WEEKLY METRICS
    # -------------------------
    weekly = (
        filtered_df
        .groupby(["Plant", "Product Category", "Fiscal Week"], as_index=False)
        .agg({
            "Yield Kg": "sum",
            "Forecast Kg": "sum"
        })
    )

    weekly["Disparity Kg"] = weekly["Forecast Kg"] - weekly["Yield Kg"]
    weekly["Abs_Disparity_Kg"] = weekly["Disparity Kg"].abs()

    weekly["Forecast Accuracy"] = (
        1 - (
            weekly["Abs_Disparity_Kg"] /
            weekly["Yield Kg"].replace(0, pd.NA)
        )
    ) * 100

    weekly["Forecast Accuracy"] = (
        weekly["Forecast Accuracy"]
        .fillna(0)
        .clip(0, 100)
    )

    # -------------------------
    # HEATMAP
    # -------------------------
    st.subheader("🟩 Weekly Forecast Accuracy Heatmap")

    heatmap = (
        alt.Chart(weekly)
        .mark_rect()
        .encode(
            x=alt.X(
                "Fiscal Week:O",
                title="Fiscal Week",
                sort="ascending"
            ),
            y=alt.Y(
                "Plant:N",
                title="Plant"
            ),
            color=alt.Color(
                "Forecast Accuracy:Q",
                scale=alt.Scale(
                    domain=[0, 75, 90, 100],
                    range=["#f8696b", "#ffeb84", "#63be7b", "#1f9d55"]
                ),
                legend=alt.Legend(title="Forecast Accuracy (%)")
            ),
            tooltip=[
                "Plant",
                "Fiscal Week",
                alt.Tooltip("Forecast Accuracy:Q", format=".1f"),
                alt.Tooltip("Abs_Disparity_Kg:Q", title="Abs Error (kg)", format=",.0f")
            ]
        )
        .properties(height=400)
    )

    st.altair_chart(heatmap, use_container_width=True)

    # -------------------------
    # KPI SUMMARY
    # -------------------------
    st.subheader("📌 Accuracy Summary (Selected Period)")

    weighted_accuracy = (
        (weekly["Forecast Accuracy"] * weekly["Yield Kg"]).sum()
        / weekly["Yield Kg"].sum()
    )

    avg_abs_error = weekly["Abs_Disparity_Kg"].mean()
    cum_abs_error = weekly["Abs_Disparity_Kg"].sum()

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "Weighted Forecast Accuracy",
        f"{weighted_accuracy:.0f}%"
    )

    c2.metric(
        "Avg Absolute Forecast Variance (ton)",
        f"{avg_abs_error / 1000:,.1f}"
    )

    c3.metric(
        "Cumulative Absolute Forecast Variance (ton)",
        f"{cum_abs_error / 1000:,.0f}"
    )

    # -------------------------
    # DETAIL TABLE
    # -------------------------
    st.subheader("📋 Weekly Forecast Accuracy Table")

    st.dataframe(
        weekly.sort_values(["Plant", "Fiscal Week"]),
        use_container_width=True
    )

else:
    # ============================================================
    # WEEKLY ANALYSIS — LOAD & NORMALISE
    # ============================================================
    st.title("📈 Weekly Forecast vs Actual Analysis (Week-Out)")

    df_week = load_week_out_with_season().copy()

    df_week = df_week.rename(columns={
        "Weeks_out": "Weeks Out",
        "As at Fiscal Week": "Fiscal Week",
        "Year": "Fiscal Year",
        "Actual": "Actual Kg",
        "Forecast": "Forecast Kg"
    })

    df_week["Fiscal Week"] = df_week["Fiscal Week"].astype(int)
    df_week["Fiscal Year"] = df_week["Fiscal Year"].astype(int)

    st.sidebar.markdown("### 🔎 Weekly Analysis Filters")

    # ---- Season
    season_list = sorted(df_week["Season"].dropna().unique())
    season_sel = st.sidebar.multiselect(
        "Season",
        options=season_list,
        default=season_list,
        key="wk_season"
    )

    if season_sel:
        df_week = df_week[df_week["Season"].isin(season_sel)]

    # ---- Plant
    plant_list = sorted(df_week["Plant"].dropna().unique())
    plant_sel = st.sidebar.multiselect(
        "Plant",
        options=plant_list,
        default=plant_list[:1],
        key="wk_plant"
    )

    if plant_sel:
        df_week = df_week[df_week["Plant"].isin(plant_sel)]

    # ---- Product Category
    category_list = sorted(df_week["Product Category"].dropna().unique())
    category_sel = st.sidebar.multiselect(
        "Product Category",
        options=category_list,
        default=[],
        key="wk_category"
    )

    if not category_sel:
        st.info("Select a Product Category to display analysis.")
        st.stop()
    
    df_week = df_week[df_week["Product Category"].isin(category_sel)]



    # ============================================================
    # AGGREGATE — ONE ROW PER WEEK / HORIZON
    # ============================================================
    weekly_plot = (
        df_week
        .groupby(
            ["Season", "Fiscal Year", "Weeks Out", "Fiscal Week"],
            as_index=False
        )
        .agg({
            "Actual Kg": "sum",
            "Forecast Kg": "sum"
        })
    )

    # ============================================================
    # METRICS
    # ============================================================
    weekly_plot["Disparity Kg"] = (
        weekly_plot["Forecast Kg"] - weekly_plot["Actual Kg"]
    )

    weekly_plot["Forecast Accuracy"] = (
        1 - (
            weekly_plot["Disparity Kg"].abs()
            / weekly_plot["Actual Kg"].replace(0, pd.NA)
        )
    ) * 100

    weekly_plot["Forecast Accuracy"] = (
        weekly_plot["Forecast Accuracy"]
        .fillna(0)
        .clip(0, 100)
    )

    weekly_plot["Weeks Out Label"] = weekly_plot["Weeks Out"].apply(
        lambda x: f"{x} week{'s' if x > 1 else ''}-out"
    )

    weekly_plot["Series"] = "Actual"
    forecast_df = weekly_plot.copy()
    forecast_df["Series"] = "Forecast"


    # ============================================================
    # COLOR SCALES
    # ============================================================
    accuracy_scale = alt.Scale(
        domain=[0, 75, 90, 100],
        range=["#f8696b", "#ffeb84", "#63be7b", "#1f9d55"]
    )

    bucket_scale = alt.Scale(
        domain=["Excellent", "Good", "Acceptable", "Bad"],
        range=["#1a9641", "#66bd63", "#fee08b", "#d7191c"]
    )

    # ============================================================
    # CHART — ACTUAL vs FORECAST (PER WEEKS-OUT)
    # ============================================================

    
    base = alt.Chart(weekly_plot).encode(
        x=alt.X("Fiscal Week:O", title="Fiscal Week")
    )

    bars = base.mark_bar().encode(
        y=alt.Y(
            "Actual Kg:Q",
            title="Actual Volume (kg)",
            axis=alt.Axis(format=",.0f")
        ),
        color=alt.Color(
            "Forecast Accuracy:Q",
            scale=accuracy_scale,
            legend=alt.Legend(title="Forecast Accuracy (%)")
        ),
        tooltip=[
            "Season:N",
            "Weeks Out:Q",
            "Fiscal Week:O",
            alt.Tooltip("Actual Kg:Q", format=","),
            alt.Tooltip("Forecast Kg:Q", format=","),
            alt.Tooltip("Forecast Accuracy:Q", format=".1f")
        ]
    )

    forecast_line = base.mark_line(
        strokeWidth=2,
        strokeDash=[6,4],
        color="black"
    ).encode(
        y=alt.Y("Forecast Kg:Q"),
        detail="Weeks Out:N"
    )
   

    weeks_out_chart = (
        (bars + forecast_line)
        .properties(height=140)
        .facet(
            row=alt.Row(
                "Weeks Out Label:N",
                sort=alt.SortField(field="Weeks Out", order="ascending"),
                title=None
            )
        )
        .resolve_scale(y="independent")
    )


    st.altair_chart(weeks_out_chart, use_container_width=True)

    st.caption(
        "📊 Bars = Actual volume | Black ticks = Forecast | Numbers = Forecast Accuracy (%)"
    )

    # ============================================================
    # HEATMAP — DISPARITY BUCKET (FIXED)
    # ============================================================
    heatmap_df = weekly_plot.copy()

    st.subheader("🔥 Weekly Forecast Disparity Heatmap")

    heatmap = (
        alt.Chart(heatmap_df)
        .mark_rect(stroke="white", strokeWidth=0.4)
        .encode(
            x=alt.X("Fiscal Week:O", title="Fiscal Week"),
            y=alt.Y("Weeks Out:O", title="Weeks Out"),
            color=alt.Color(
                "Forecast Accuracy:Q",
                scale=accuracy_scale,
                legend=alt.Legend(title="Forecast Accuracy (%)")
            ),
            tooltip=[
                "Season:N",
                "Weeks Out:O",
                "Fiscal Week:O",
                alt.Tooltip("Actual Kg:Q", format=","),
                alt.Tooltip("Forecast Kg:Q", format=","),
                alt.Tooltip("Disparity Kg:Q", format="+,")
            ]
        )
        .facet(
            row=alt.Row(
                "Season:N",
                header=alt.Header(labelFontWeight="bold")
            )
        )
    )

    st.altair_chart(heatmap, use_container_width=True)


    # ============================================================
    # KPI METRICS BY WEEKS OUT
    # ============================================================
    weekly = (
        df_week
        .groupby(
            ["Season", "Fiscal Year", "Weeks Out", "Fiscal Week"],
            as_index=False
        )
        .agg({
            "Actual Kg": "sum",
            "Forecast Kg": "sum"
        })
    )

    weekly["Disparity Kg"] = weekly["Forecast Kg"] - weekly["Actual Kg"]
    weekly["Abs_Disparity_Kg"] = weekly["Disparity Kg"].abs()

    weekly["Forecast Accuracy"] = (
        1 - (
            weekly["Abs_Disparity_Kg"]
            / weekly["Actual Kg"].replace(0, pd.NA)
        )
    ) * 100

    weekly["Forecast Accuracy"] = (
        weekly["Forecast Accuracy"]
        .fillna(0)
        .clip(0, 100)
    )

    st.subheader("📌 Forecast Accuracy Summary")

    # Defensive check
    if "Weeks Out" not in weekly.columns:
        st.error("❌ Column 'Weeks Out' missing in weekly data")
    else:
        weeks_out_list = sorted(weekly["Weeks Out"].dropna().unique())

        for w in weeks_out_list:
            subset = weekly[weekly["Weeks Out"] == w]

            acc, avg_err, cum_err = compute_kpis(subset)

            if acc is None:
                continue

            # Section title per horizon
            st.markdown(f"### ⏱ {w} week{'s' if w > 1 else ''}-out")

            # KPI cards
            c1, c2, c3 = st.columns(3)

            c1.metric(
                "Weighted Forecast Accuracy",
                f"{acc:.0f}%"
            )

            c2.metric(
                "Avg Absolute Forecast Variance (ton)",
                f"{avg_err / 1000:,.1f}"
            )

            c3.metric(
                "Cumulative Absolute Forecast Variance (ton)",
                f"{cum_err / 1000:,.0f}"
            )

            st.markdown("---")
