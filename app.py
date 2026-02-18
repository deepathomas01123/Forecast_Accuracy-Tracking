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

@st.cache_data
def load_wages_data():
    df = pd.read_excel(
        os.path.join(DATA_DIR, "wages raw data.xlsx")
    )
    df.columns = df.columns.str.strip()
    return df

# =========================
# TAB SELECTION IN SIDEBAR
# =========================
st.sidebar.markdown("## 📊 Select View")
selected_tab = st.sidebar.radio(
    "Choose analysis:",
    ["Accuracy Overview", "Weekly Analysis", "Wages Analysis"],
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

elif selected_tab == "Weekly Analysis":
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
        options=["All"] + category_list,
        default=["All"],  # Set "All" as default
        key="wk_category"
    )

    if "All" not in category_sel:
        df_week = df_week[df_week["Product Category"].isin(category_sel)]

    # Remove the old filtering logic below
    if not category_sel:
        st.info("Select a Product Category to display analysis.")
        st.stop()
    
    # This line is no longer needed since we handle "All" above
    # df_week = df_week[df_week["Product Category"].isin(category_sel)]



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

else:
    # ============================================================
    # WAGES ANALYSIS — NEW TAB
    # ============================================================
    st.title("💰 Wages Analysis: Cost per Hour vs EA Average Competent Rate")

    try:
        wages_df = load_wages_data()
    except Exception as e:
        st.error(f"❌ Error loading wages data: {str(e)}")
        st.stop()

    # -------------------------
    # SIDEBAR FILTERS
    # -------------------------
    st.sidebar.markdown("### 🔎 Wages Analysis Filters")

    # Time Granularity Selector
    time_granularity = st.sidebar.radio(
        "⏱️ Time Granularity",
        options=["Weekly", "Daily"],
        index=0,
        key="time_gran",
        help="Weekly view aggregates data by week. Daily view shows individual days."
    )

    # Fiscal Year
    fy_list = sorted(wages_df["Costa Fiscal Year"].unique(), reverse=True)
    fy_sel = st.sidebar.multiselect(
        "Fiscal Year",
        options=["All"] + fy_list,
        default=[fy_list[0]],  # Most recent year by default
        key="wages_fy"
    )

    if "All" not in fy_sel:
        wages_df = wages_df[wages_df["Costa Fiscal Year"].isin(fy_sel)]

    # Fiscal Week
    fw_list = sorted(wages_df["Fiscal Week No"].unique())
    
    # For daily view, default to fewer weeks to avoid crowding
    if time_granularity == "Daily":
        default_weeks = fw_list[:4] if len(fw_list) >= 4 else fw_list  # First 4 weeks
        fw_help = "💡 Tip: Select fewer weeks for clearer daily view"
    else:
        default_weeks = ["All"]
        fw_help = None
    
    fw_sel = st.sidebar.multiselect(
        "Fiscal Week",
        options=["All"] + fw_list,
        default=default_weeks,
        key="wages_fw",
        help=fw_help
    )

    if "All" not in fw_sel:
        wages_df = wages_df[wages_df["Fiscal Week No"].isin(fw_sel)]

    # Plant
    plant_list = sorted(wages_df["Plant"].unique())
    plant_sel = st.sidebar.multiselect(
        "Plant",
        options=["All"] + plant_list,
        default=[plant_list[0]] if plant_list else ["All"],  # First plant by default
        key="wages_plant"
    )

    if "All" not in plant_sel:
        wages_df = wages_df[wages_df["Plant"].isin(plant_sel)]

    # Product Category
    category_list = sorted(wages_df["Product Category"].unique())
    category_sel = st.sidebar.multiselect(
        "Product Category",
        options=["All"] + category_list,
        default=[category_list[0]] if category_list else ["All"],  # First category by default
        key="wages_category"
    )

    if "All" not in category_sel:
        wages_df = wages_df[wages_df["Product Category"].isin(category_sel)]

    # Product Variety
    variety_list = sorted(wages_df["Product Variety"].unique())
    variety_sel = st.sidebar.multiselect(
        "Product Variety",
        options=["All"] + variety_list,
        default=["All"],
        key="wages_variety"
    )

    if "All" not in variety_sel:
        wages_df = wages_df[wages_df["Product Variety"].isin(variety_sel)]

    # Location
    location_list = sorted(wages_df["Location"].unique())
    location_sel = st.sidebar.multiselect(
        "Location",
        options=["All"] + location_list,
        default=["All"],
        key="wages_location"
    )

    if "All" not in location_sel:
        wages_df = wages_df[wages_df["Location"].isin(location_sel)]

    # -------------------------
    # AGGREGATE BY TIME GRANULARITY
    # -------------------------
    if time_granularity == "Daily":
        group_cols = ["Costa Fiscal Year", "Fiscal Week No", "Pick Date", "Plant", "Product Category"]
        time_col = "Pick Date:T"
        time_title = "Date"
        
        # Format date for display
        wages_df["Pick Date"] = pd.to_datetime(wages_df["Pick Date"])
        
    else:  # Weekly
        group_cols = ["Costa Fiscal Year", "Fiscal Week No", "Plant", "Product Category"]
        time_col = "Fiscal Week No:O"
        time_title = "Fiscal Week"

    aggregated_wages = (
        wages_df
        .groupby(group_cols, as_index=False)
        .agg({
            "Cost Per Hour – Picker Cost (Excl Ancillary Costs)": "mean",
            "Cost Per Hour - Total Harvest Cost": "mean",
            "EAAverageCompetentRate": "mean",
            "Yield Kg": "sum"
        })
        .rename(columns={
            "Cost Per Hour – Picker Cost (Excl Ancillary Costs)": "Picker Cost/Hr",
            "Cost Per Hour - Total Harvest Cost": "Total Cost/Hr",
            "EAAverageCompetentRate": "EA Rate"
        })
    )

    # Calculate variance from EA Rate
    aggregated_wages["Picker Variance from EA"] = (
        aggregated_wages["Picker Cost/Hr"] - aggregated_wages["EA Rate"]
    )
    aggregated_wages["Total Variance from EA"] = (
        aggregated_wages["Total Cost/Hr"] - aggregated_wages["EA Rate"]
    )

    # Calculate percentage variance
    aggregated_wages["Picker % Variance"] = (
        (aggregated_wages["Picker Variance from EA"] / aggregated_wages["EA Rate"]) * 100
    )
    aggregated_wages["Total % Variance"] = (
        (aggregated_wages["Total Variance from EA"] / aggregated_wages["EA Rate"]) * 100
    )

    # -------------------------
    # KPI SUMMARY CARDS
    # -------------------------
    st.subheader("📊 Overall Summary")

    col1, col2, col3, col4 = st.columns(4)

    avg_picker = aggregated_wages["Picker Cost/Hr"].mean()
    avg_total = aggregated_wages["Total Cost/Hr"].mean()
    avg_ea = aggregated_wages["EA Rate"].mean()
    avg_variance = aggregated_wages["Picker % Variance"].mean()

    col1.metric(
        "Avg Picker Cost/Hr",
        f"${avg_picker:.2f}",
        delta=f"{avg_variance:+.1f}% vs EA"
    )

    col2.metric(
        "Avg Total Cost/Hr",
        f"${avg_total:.2f}"
    )

    col3.metric(
        "Avg EA Rate",
        f"${avg_ea:.2f}"
    )

    col4.metric(
        "Total Volume (tons)",
        f"{aggregated_wages['Yield Kg'].sum() / 1000:,.0f}"
    )

    # -------------------------
    # TREND LINE CHART
    # -------------------------
    st.subheader(f"📈 Cost per Hour Trend vs EA Average Competent Rate ({time_granularity})")

    # Create base chart
    base = alt.Chart(aggregated_wages).encode(
        x=alt.X(time_col, title=time_title)
    )

    # Picker cost line
    picker_line = base.mark_line(
        strokeWidth=2.5,
        color="#2E86AB",
        point=True if time_granularity == "Daily" else False  # Show points on daily view
    ).encode(
        y=alt.Y("Picker Cost/Hr:Q", title="Cost per Hour ($)", scale=alt.Scale(zero=False)),
        tooltip=[
            "Costa Fiscal Year:O",
            alt.Tooltip("Pick Date:T", format="%Y-%m-%d", title="Date") if time_granularity == "Daily" else alt.Tooltip("Fiscal Week No:O", title="Week"),
            alt.Tooltip("Picker Cost/Hr:Q", format="$.2f", title="Picker Cost/Hr"),
            alt.Tooltip("EA Rate:Q", format="$.2f", title="EA Rate"),
            alt.Tooltip("Picker % Variance:Q", format="+.1f", title="% Variance")
        ]
    )

    # Total cost line
    total_line = base.mark_line(
        strokeWidth=2.5,
        color="#A23B72",
        strokeDash=[5,5],
        point=True if time_granularity == "Daily" else False
    ).encode(
        y=alt.Y("Total Cost/Hr:Q"),
        tooltip=[
            "Costa Fiscal Year:O",
            alt.Tooltip("Pick Date:T", format="%Y-%m-%d", title="Date") if time_granularity == "Daily" else alt.Tooltip("Fiscal Week No:O", title="Week"),
            alt.Tooltip("Total Cost/Hr:Q", format="$.2f", title="Total Cost/Hr"),
            alt.Tooltip("EA Rate:Q", format="$.2f", title="EA Rate")
        ]
    )

    # EA Rate line (benchmark)
    ea_line = base.mark_line(
        strokeWidth=2,
        color="#F18F01",
        strokeDash=[2,2]
    ).encode(
        y=alt.Y("EA Rate:Q"),
        tooltip=[
            "Costa Fiscal Year:O",
            alt.Tooltip("Pick Date:T", format="%Y-%m-%d", title="Date") if time_granularity == "Daily" else alt.Tooltip("Fiscal Week No:O", title="Week"),
            alt.Tooltip("EA Rate:Q", format="$.2f", title="EA Rate")
        ]
    )

    # Combine all lines with interactivity
    trend_chart = (
        (picker_line + total_line + ea_line)
        .properties(
            height=400,
            width=1000 if time_granularity == "Daily" else 1000
        )
        .interactive()  # Enable pan and zoom for daily view
    )
    
    # Only facet by year if weekly view
    if time_granularity == "Weekly":
        trend_chart = trend_chart.facet(
            column=alt.Column(
                "Costa Fiscal Year:O",
                title="Fiscal Year"
            )
        )

    st.altair_chart(trend_chart, use_container_width=True)

    if time_granularity == "Daily":
        st.caption(
            "🔵 Solid = Picker Cost/Hr | 🟣 Dashed = Total Harvest Cost/Hr | "
            "🟠 Dotted = EA Average Competent Rate | 💡 **Drag to pan, scroll to zoom**"
        )
    else:
        st.caption(
            "🔵 Solid = Picker Cost/Hr | 🟣 Dashed = Total Harvest Cost/Hr | "
            "🟠 Dotted = EA Average Competent Rate"
        )

    # -------------------------
    # VARIANCE HEATMAP
    # -------------------------
    st.subheader("🔥 Cost Variance Heatmap (% vs EA Rate)")

    if aggregated_wages.empty or aggregated_wages["Picker % Variance"].isna().all():
        st.warning("⚠️ No data available for the selected filters. Please adjust your filter selection.")
    else:
        # Calculate min/max variance for dynamic scaling
        min_variance = aggregated_wages["Picker % Variance"].min()
        max_variance = aggregated_wages["Picker % Variance"].max()
        
        # Handle case where all values are the same or NaN
        if pd.isna(min_variance) or pd.isna(max_variance):
            st.warning("⚠️ Cannot calculate variance. Please check your data or filter selection.")
        else:
            # Set symmetric scale around 0, with minimum of ±25
            scale_limit = max(abs(min_variance), abs(max_variance), 25)
            # Round up to nearest 5 for cleaner legend
            scale_limit = ((scale_limit // 5) + 1) * 5
            
            # Choose axes based on granularity and number of plants
            num_plants = aggregated_wages["Plant"].nunique()
            
            # Debug info to understand data
            if time_granularity == "Daily":
                unique_dates = aggregated_wages["Pick Date"].nunique() if "Pick Date" in aggregated_wages.columns else 0
                #st.info(f"🔍 Debug: {len(aggregated_wages)} data points | {unique_dates} unique dates | {num_plants} plant(s)")
            
            if time_granularity == "Daily":
                # Ensure dates are properly formatted
                if "Pick Date" in aggregated_wages.columns:
                    aggregated_wages["Pick Date"] = pd.to_datetime(aggregated_wages["Pick Date"])
                    aggregated_wages["Pick Date Str"] = aggregated_wages["Pick Date"].dt.strftime("%Y-%m-%d")
                
                x_encoding = alt.X(
                    "Pick Date Str:O",   # Ordinal string = one discrete cell per day
                    title="Date",
                    sort="ascending",
                    axis=alt.Axis(labelAngle=-45)
                )
                
                # If single plant, show Product Category on Y-axis for better visualization
                if num_plants == 1:
                    y_encoding = alt.Y("Product Category:N", title="Product Category")
                    heatmap_tooltip = [
                        "Product Category:N",
                        "Plant:N",
                        alt.Tooltip("Pick Date:T", format="%Y-%m-%d", title="Date"),
                        alt.Tooltip("Picker Cost/Hr:Q", format="$.2f"),
                        alt.Tooltip("EA Rate:Q", format="$.2f"),
                        alt.Tooltip("Picker % Variance:Q", format="+.1f", title="% Variance")
                    ]
                else:
                    y_encoding = alt.Y("Plant:N", title="Plant")
                    heatmap_tooltip = [
                        "Plant:N",
                        alt.Tooltip("Pick Date:T", format="%Y-%m-%d", title="Date"),
                        alt.Tooltip("Picker Cost/Hr:Q", format="$.2f"),
                        alt.Tooltip("EA Rate:Q", format="$.2f"),
                        alt.Tooltip("Picker % Variance:Q", format="+.1f", title="% Variance")
                    ]
            else:  # Weekly
                x_encoding = alt.X("Fiscal Week No:O", title="Fiscal Week")
                y_encoding = alt.Y("Plant:N", title="Plant")
                heatmap_tooltip = [
                    "Plant:N",
                    "Costa Fiscal Year:O",
                    "Fiscal Week No:O",
                    alt.Tooltip("Picker Cost/Hr:Q", format="$.2f"),
                    alt.Tooltip("EA Rate:Q", format="$.2f"),
                    alt.Tooltip("Picker % Variance:Q", format="+.1f", title="% Variance")
                ]
            
            heatmap = (
                alt.Chart(aggregated_wages)
                .mark_rect(stroke="white", strokeWidth=0.5)  # Add cell borders
                .encode(
                    x=x_encoding,
                    y=y_encoding,
                    color=alt.Color(
                        "Picker % Variance:Q",
                        scale=alt.Scale(
                            domain=[-scale_limit, 0, scale_limit],
                            range=["#1a9641", "#ffffbf", "#d7191c"]
                        ),
                        legend=alt.Legend(title="% Variance from EA")
                    ),
                    tooltip=heatmap_tooltip
                )
                .properties(height=400)
                .interactive()  # Enable zoom/pan
            )

            st.altair_chart(heatmap, use_container_width=True)
            
            # Show variance range info
            caption_text = (
                f"📊 Variance range: {min_variance:.1f}% to {max_variance:.1f}% | "
                f"🟢 Green = Below EA Rate | 🟡 Yellow = At EA Rate | 🔴 Red = Above EA Rate"
            )
            
            if time_granularity == "Daily" and num_plants == 1:
                caption_text += " | 💡 Showing Product Categories (select multiple plants to compare plants instead)"
            
            st.caption(caption_text)

    # # -------------------------
    # # SCATTER PLOT: COST VS VOLUME
    # # -------------------------
    # st.subheader("📊 Cost per Hour vs Volume Produced")

    # scatter = (
    #     alt.Chart(aggregated_wages)
    #     .mark_circle(size=100, opacity=0.7)
    #     .encode(
    #         x=alt.X("Yield Kg:Q", title=f"{'Daily' if time_granularity == 'Daily' else 'Weekly'} Volume (kg)", scale=alt.Scale(zero=False)),
    #         y=alt.Y("Picker Cost/Hr:Q", title="Picker Cost/Hr ($)", scale=alt.Scale(zero=False)),
    #         color=alt.Color(
    #             "Product Category:N",
    #             legend=alt.Legend(title="Product Category")
    #         ),
    #         size=alt.Size("EA Rate:Q", legend=None),
    #         tooltip=[
    #             "Plant:N",
    #             "Product Category:N",
    #             "Costa Fiscal Year:O",
    #             alt.Tooltip("Pick Date:T", format="%Y-%m-%d", title="Date") if time_granularity == "Daily" else alt.Tooltip("Fiscal Week No:O", title="Week"),
    #             alt.Tooltip("Yield Kg:Q", format=",.0f", title="Volume (kg)"),
    #             alt.Tooltip("Picker Cost/Hr:Q", format="$.2f"),
    #             alt.Tooltip("EA Rate:Q", format="$.2f")
    #         ]
    #     )
    #     .properties(height=400)
    #     .interactive()
    # )

    # st.altair_chart(scatter, use_container_width=True)

    # -------------------------
    # DETAILED DATA TABLE
    # -------------------------
    st.subheader("📋 Detailed Wages Data")

    if time_granularity == "Daily":
        display_cols = [
            "Costa Fiscal Year", "Fiscal Week No", "Pick Date", "Plant", "Product Category",
            "Picker Cost/Hr", "Total Cost/Hr", "EA Rate",
            "Picker Variance from EA", "Picker % Variance", "Yield Kg"
        ]
        sort_cols = ["Pick Date", "Plant"]
    else:
        display_cols = [
            "Costa Fiscal Year", "Fiscal Week No", "Plant", "Product Category",
            "Picker Cost/Hr", "Total Cost/Hr", "EA Rate",
            "Picker Variance from EA", "Picker % Variance", "Yield Kg"
        ]
        sort_cols = ["Costa Fiscal Year", "Fiscal Week No", "Plant"]

    display_df = aggregated_wages[display_cols].sort_values(sort_cols)

    format_dict = {
        "Picker Cost/Hr": "${:.2f}",
        "Total Cost/Hr": "${:.2f}",
        "EA Rate": "${:.2f}",
        "Picker Variance from EA": "${:+.2f}",
        "Picker % Variance": "{:+.1f}%",
        "Yield Kg": "{:,.0f}"
    }
    
    if time_granularity == "Daily":
        format_dict["Pick Date"] = lambda x: x.strftime("%Y-%m-%d")

    st.dataframe(
        display_df.style.format(format_dict),
        use_container_width=True
    )
    
    
