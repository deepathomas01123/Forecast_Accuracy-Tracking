import streamlit as st
import pandas as pd
import altair as alt

# =========================
# PAGE CONFIG
# =========================
st.set_page_config(
    page_title="Forecast Volume Accuracy – One Week Out",
    layout="wide"
)

# =========================
# COLUMN NAME CONSTANTS
# Adjust these if your Excel headers differ
# =========================
COL_PICKER_COST   = "Picker Costs (Excl Ancillary Costs)"
COL_PICKER_HOURS  = "Picker Hours (Excl Ancillary Hours)"
COL_OVERHEAD      = "Total Overhead Costs"
COL_BREAK_MOVE    = "Paid Break & Move Costs $ (Picker Only)"
COL_ABSENCE       = "Paid Absence Cost $ (Picker Only)"
COL_HARVEST_HOURS = "Total Harvest Hours"
COL_EA_RATE       = "EAAverageCompetentRate"
COL_YIELD         = "Yield Kg"

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
    actuals = pd.read_excel(
        "data/Actuals.xlsx"
    )
    forecast = pd.read_excel(
        "data/Roster_Data.xlsx"
    )
    actuals.columns = actuals.columns.str.strip()
    forecast.columns = forecast.columns.str.strip()
    return actuals, forecast

@st.cache_data
def load_week_out_with_season():
    df = pd.read_excel(
        "data/4-week-out packed forecast with Fiscal_Week_and_Season.xlsx"
    )
    df.columns = df.columns.str.strip()
    return df

@st.cache_data
def load_wages_data():
    """Load wages raw data."""
    df = pd.read_excel(
        "data/wages raw data new.xlsx"
    )
    df.columns = df.columns.str.strip()
    return df


def aggregate_wages(wages_df, group_cols):
    """
    Aggregate wages data by summing raw cost & hours columns,
    then derive Cost/Hr metrics using the correct formulas:

        Picker Cost/Hr  = Picker Costs (Excl Ancillary Costs)
                          ─────────────────────────────────────
                          Picker Hours (Excl Ancillary Hours)

        Total Harvest Cost = Picker Costs (Excl Ancillary Costs)
                           + Total Overhead Costs
                           + Paid Break & Move Costs (Picker only)
                           + Absence Paid Cost (Picker only)

        Total Harvest Cost/Hr = Total Harvest Cost / Total Harvest Hours
    """
    # Columns to SUM — raw financials & hours must never be averaged
    raw_sum_cols = [
        COL_PICKER_COST,
        COL_PICKER_HOURS,
        COL_OVERHEAD,
        COL_BREAK_MOVE,
        COL_ABSENCE,
        COL_HARVEST_HOURS,
        COL_YIELD,
    ]
    # EA Rate is a reference rate — average it
    raw_mean_cols = [COL_EA_RATE]

    agg_dict = {}
    for c in raw_sum_cols:
        if c in wages_df.columns:
            agg_dict[c] = "sum"
    for c in raw_mean_cols:
        if c in wages_df.columns:
            agg_dict[c] = "mean"

    agg = wages_df.groupby(group_cols, as_index=False).agg(agg_dict)

    # ── Derived: Picker Cost per Hour ────────────────────────────────────────
    if COL_PICKER_COST in agg.columns and COL_PICKER_HOURS in agg.columns:
        agg["Picker Cost/Hr"] = (
            agg[COL_PICKER_COST] / agg[COL_PICKER_HOURS].replace(0, pd.NA)
        )
    else:
        agg["Picker Cost/Hr"] = pd.NA

    # ── Derived: Total Harvest Cost (sum of four components) ─────────────────
    cost_components = [COL_PICKER_COST, COL_OVERHEAD, COL_BREAK_MOVE, COL_ABSENCE]
    present = [c for c in cost_components if c in agg.columns]
    agg["Total Harvest Cost"] = agg[present].sum(axis=1)

    # ── Derived: Total Harvest Cost per Hour ─────────────────────────────────
    if COL_HARVEST_HOURS in agg.columns:
        agg["Total Cost/Hr"] = (
            agg["Total Harvest Cost"] / agg[COL_HARVEST_HOURS].replace(0, pd.NA)
        )
    else:
        agg["Total Cost/Hr"] = pd.NA

    # Rename EA Rate for downstream consistency
    if COL_EA_RATE in agg.columns:
        agg = agg.rename(columns={COL_EA_RATE: "EA Rate"})
    else:
        agg["EA Rate"] = pd.NA

    # Rename Yield for consistency
    if COL_YIELD in agg.columns:
        agg = agg.rename(columns={COL_YIELD: "Yield Kg"})

    # ── Variance calculations ─────────────────────────────────────────────────
    agg["Picker Variance from EA"] = agg["Picker Cost/Hr"] - agg["EA Rate"]
    agg["Total Variance from EA"]  = agg["Total Cost/Hr"]  - agg["EA Rate"]
    agg["Picker % Variance"] = (
        (agg["Picker Variance from EA"] / agg["EA Rate"]) * 100
    )
    agg["Total % Variance"] = (
        (agg["Total Variance from EA"] / agg["EA Rate"]) * 100
    )

    return agg


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

    fy_list = sorted(filtered_df["Fiscal Year"].unique())
    selected_fy = st.sidebar.multiselect(
        "Fiscal Year",
        options=["All"] + fy_list,
        default=["All"],
        key="acc_fy"
    )
    if "All" not in selected_fy:
        filtered_df = filtered_df[filtered_df["Fiscal Year"].isin(selected_fy)]

    fw_list = sorted(filtered_df["Fiscal Week"].unique())
    selected_fw = st.sidebar.multiselect(
        "Fiscal Week",
        options=["All"] + fw_list,
        default=["All"],
        key="acc_fw"
    )
    if "All" not in selected_fw:
        filtered_df = filtered_df[filtered_df["Fiscal Week"].isin(selected_fw)]

    plant_list = sorted(filtered_df["Plant"].unique())
    selected_plants = st.sidebar.multiselect(
        "Plant",
        options=["All"] + plant_list,
        default=["All"],
        key="acc_plant"
    )
    if "All" not in selected_plants:
        filtered_df = filtered_df[filtered_df["Plant"].isin(selected_plants)]

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
        .agg({"Yield Kg": "sum", "Forecast Kg": "sum"})
    )

    weekly["Disparity Kg"] = weekly["Forecast Kg"] - weekly["Yield Kg"]
    weekly["Abs_Disparity_Kg"] = weekly["Disparity Kg"].abs()
    weekly["Forecast Accuracy"] = (
        1 - (weekly["Abs_Disparity_Kg"] / weekly["Yield Kg"].replace(0, pd.NA))
    ) * 100
    weekly["Forecast Accuracy"] = weekly["Forecast Accuracy"].fillna(0).clip(0, 100)

    # -------------------------
    # HEATMAP
    # -------------------------
    st.subheader("🟩 Weekly Forecast Accuracy Heatmap")

    heatmap = (
        alt.Chart(weekly)
        .mark_rect()
        .encode(
            x=alt.X("Fiscal Week:O", title="Fiscal Week", sort="ascending"),
            y=alt.Y("Plant:N", title="Plant"),
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
    c1.metric("Weighted Forecast Accuracy", f"{weighted_accuracy:.0f}%")
    c2.metric("Avg Absolute Forecast Variance (ton)", f"{avg_abs_error / 1000:,.1f}")
    c3.metric("Cumulative Absolute Forecast Variance (ton)", f"{cum_abs_error / 1000:,.0f}")

    # -------------------------
    # DETAIL TABLE
    # -------------------------
    st.subheader("📋 Weekly Forecast Accuracy Table")
    st.dataframe(weekly.sort_values(["Plant", "Fiscal Week"]), use_container_width=True)


elif selected_tab == "Weekly Analysis":
    # ============================================================
    # WEEKLY ANALYSIS
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

    season_list = sorted(df_week["Season"].dropna().unique())
    season_sel = st.sidebar.multiselect("Season", options=season_list, default=season_list, key="wk_season")
    if season_sel:
        df_week = df_week[df_week["Season"].isin(season_sel)]

    plant_list = sorted(df_week["Plant"].dropna().unique())
    plant_sel = st.sidebar.multiselect("Plant", options=plant_list, default=plant_list[:1], key="wk_plant")
    if plant_sel:
        df_week = df_week[df_week["Plant"].isin(plant_sel)]

    category_list = sorted(df_week["Product Category"].dropna().unique())
    category_sel = st.sidebar.multiselect("Product Category", options=["All"] + category_list, default=["All"], key="wk_category")
    if "All" not in category_sel:
        df_week = df_week[df_week["Product Category"].isin(category_sel)]
    if not category_sel:
        st.info("Select a Product Category to display analysis.")
        st.stop()

    weekly_plot = (
        df_week
        .groupby(["Season", "Fiscal Year", "Weeks Out", "Fiscal Week"], as_index=False)
        .agg({"Actual Kg": "sum", "Forecast Kg": "sum"})
    )

    weekly_plot["Disparity Kg"] = weekly_plot["Forecast Kg"] - weekly_plot["Actual Kg"]
    weekly_plot["Forecast Accuracy"] = (
        1 - (weekly_plot["Disparity Kg"].abs() / weekly_plot["Actual Kg"].replace(0, pd.NA))
    ) * 100
    weekly_plot["Forecast Accuracy"] = weekly_plot["Forecast Accuracy"].fillna(0).clip(0, 100)
    weekly_plot["Weeks Out Label"] = weekly_plot["Weeks Out"].apply(
        lambda x: f"{x} week{'s' if x > 1 else ''}-out"
    )

    accuracy_scale = alt.Scale(
        domain=[0, 75, 90, 100],
        range=["#f8696b", "#ffeb84", "#63be7b", "#1f9d55"]
    )

    base = alt.Chart(weekly_plot).encode(x=alt.X("Fiscal Week:O", title="Fiscal Week"))

    bars = base.mark_bar().encode(
        y=alt.Y("Actual Kg:Q", title="Actual Volume (kg)", axis=alt.Axis(format=",.0f")),
        color=alt.Color("Forecast Accuracy:Q", scale=accuracy_scale, legend=alt.Legend(title="Forecast Accuracy (%)")),
        tooltip=[
            "Season:N", "Weeks Out:Q", "Fiscal Week:O",
            alt.Tooltip("Actual Kg:Q", format=","),
            alt.Tooltip("Forecast Kg:Q", format=","),
            alt.Tooltip("Forecast Accuracy:Q", format=".1f")
        ]
    )

    forecast_line = base.mark_line(strokeWidth=2, strokeDash=[6, 4], color="black").encode(
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
    st.caption("📊 Bars = Actual volume | Black ticks = Forecast | Numbers = Forecast Accuracy (%)")

    st.subheader("🔥 Weekly Forecast Disparity Heatmap")
    heatmap = (
        alt.Chart(weekly_plot)
        .mark_rect(stroke="white", strokeWidth=0.4)
        .encode(
            x=alt.X("Fiscal Week:O", title="Fiscal Week"),
            y=alt.Y("Weeks Out:O", title="Weeks Out"),
            color=alt.Color("Forecast Accuracy:Q", scale=accuracy_scale, legend=alt.Legend(title="Forecast Accuracy (%)")),
            tooltip=[
                "Season:N", "Weeks Out:O", "Fiscal Week:O",
                alt.Tooltip("Actual Kg:Q", format=","),
                alt.Tooltip("Forecast Kg:Q", format=","),
                alt.Tooltip("Disparity Kg:Q", format="+,")
            ]
        )
        .facet(row=alt.Row("Season:N", header=alt.Header(labelFontWeight="bold")))
    )
    st.altair_chart(heatmap, use_container_width=True)

    weekly = (
        df_week
        .groupby(["Season", "Fiscal Year", "Weeks Out", "Fiscal Week"], as_index=False)
        .agg({"Actual Kg": "sum", "Forecast Kg": "sum"})
    )
    weekly["Disparity Kg"] = weekly["Forecast Kg"] - weekly["Actual Kg"]
    weekly["Abs_Disparity_Kg"] = weekly["Disparity Kg"].abs()
    weekly["Forecast Accuracy"] = (
        1 - (weekly["Abs_Disparity_Kg"] / weekly["Actual Kg"].replace(0, pd.NA))
    ) * 100
    weekly["Forecast Accuracy"] = weekly["Forecast Accuracy"].fillna(0).clip(0, 100)

    st.subheader("📌 Forecast Accuracy Summary")
    for w in sorted(weekly["Weeks Out"].dropna().unique()):
        subset = weekly[weekly["Weeks Out"] == w]
        acc, avg_err, cum_err = compute_kpis(subset)
        if acc is None:
            continue
        st.markdown(f"### ⏱ {w} week{'s' if w > 1 else ''}-out")
        c1, c2, c3 = st.columns(3)
        c1.metric("Weighted Forecast Accuracy", f"{acc:.0f}%")
        c2.metric("Avg Absolute Forecast Variance (ton)", f"{avg_err / 1000:,.1f}")
        c3.metric("Cumulative Absolute Forecast Variance (ton)", f"{cum_err / 1000:,.0f}")
        st.markdown("---")


else:
    # ============================================================
    # WAGES ANALYSIS
    # ============================================================
    st.title("💰 Wages Analysis: Cost per Hour vs EA Average Competent Rate")

    try:
        wages_df = load_wages_data()
    except Exception as e:
        st.error(f"❌ Error loading wages data: {str(e)}")
        st.stop()

    # Validate that required columns exist
    required_cols = [COL_PICKER_COST, COL_PICKER_HOURS, COL_HARVEST_HOURS, COL_EA_RATE]
    missing = [c for c in required_cols if c not in wages_df.columns]
    if missing:
        st.error(
            f"❌ The following required columns were not found in the wages file:\n\n"
            + "\n".join(f"  • `{c}`" for c in missing)
            + "\n\nPlease check the column names and update the constants at the top of the script."
        )
        with st.expander("📋 Columns found in wages file"):
            st.write(list(wages_df.columns))
        st.stop()

    # -------------------------
    # CHECK FOR TEAM COLUMN
    # -------------------------
    team_col_candidates = [c for c in wages_df.columns if "team" in c.lower()]
    team_col = team_col_candidates[0] if team_col_candidates else None

    # -------------------------
    # SIDEBAR FILTERS
    # -------------------------
    st.sidebar.markdown("### 🔎 Wages Analysis Filters")

    granularity_options = ["Weekly", "Daily", "Team"]
    if team_col is None:
        granularity_options = ["Weekly", "Daily"]
        st.sidebar.warning("⚠️ No Team column found in wages data. Team view unavailable.")

    time_granularity = st.sidebar.radio(
        "⏱️ Time Granularity",
        options=granularity_options,
        index=0,
        key="time_gran",
        help=(
            "Weekly: aggregated by fiscal week. "
            "Daily: individual pick dates. "
            "Team: aggregated by team across selected period."
        )
    )

    fy_list = sorted(wages_df["Costa Fiscal Year"].unique(), reverse=True)
    fy_sel = st.sidebar.multiselect("Fiscal Year", options=["All"] + fy_list, default=[fy_list[0]], key="wages_fy")
    if "All" not in fy_sel:
        wages_df = wages_df[wages_df["Costa Fiscal Year"].isin(fy_sel)]

    fw_list = sorted(wages_df["Fiscal Week No"].unique())
    if time_granularity == "Daily":
        default_weeks = fw_list[:4] if len(fw_list) >= 4 else fw_list
        fw_help = "💡 Tip: Select fewer weeks for clearer daily view"
    elif time_granularity == "Team":
        default_weeks = fw_list[:4] if len(fw_list) >= 4 else fw_list
        fw_help = "💡 Tip: Select a date range to compare teams within that period"
    else:
        default_weeks = ["All"]
        fw_help = None

    fw_sel = st.sidebar.multiselect("Fiscal Week", options=["All"] + fw_list, default=default_weeks, key="wages_fw", help=fw_help)
    if "All" not in fw_sel:
        wages_df = wages_df[wages_df["Fiscal Week No"].isin(fw_sel)]

    plant_list = sorted(wages_df["Plant"].unique())
    plant_sel = st.sidebar.multiselect("Plant", options=["All"] + plant_list, default=[plant_list[0]] if plant_list else ["All"], key="wages_plant")
    if "All" not in plant_sel:
        wages_df = wages_df[wages_df["Plant"].isin(plant_sel)]

    if team_col:
        team_list = sorted(wages_df[team_col].dropna().unique())
        team_sel = st.sidebar.multiselect("Team", options=["All"] + list(team_list), default=["All"], key="wages_team")
        if "All" not in team_sel:
            wages_df = wages_df[wages_df[team_col].isin(team_sel)]

    category_list = sorted(wages_df["Product Category"].unique())
    category_sel = st.sidebar.multiselect("Product Category", options=["All"] + category_list, default=[category_list[0]] if category_list else ["All"], key="wages_category")
    if "All" not in category_sel:
        wages_df = wages_df[wages_df["Product Category"].isin(category_sel)]

    variety_list = sorted(wages_df["Product Variety"].unique())
    variety_sel = st.sidebar.multiselect("Product Variety", options=["All"] + variety_list, default=["All"], key="wages_variety")
    if "All" not in variety_sel:
        wages_df = wages_df[wages_df["Product Variety"].isin(variety_sel)]

    location_list = sorted(wages_df["Location"].unique())
    location_sel = st.sidebar.multiselect("Location", options=["All"] + location_list, default=["All"], key="wages_location")
    if "All" not in location_sel:
        wages_df = wages_df[wages_df["Location"].isin(location_sel)]

    # -------------------------
    # DETERMINE GROUP COLUMNS & AGGREGATE
    # -------------------------
    if time_granularity == "Daily":
        wages_df["Pick Date"] = pd.to_datetime(wages_df["Pick Date"])
        group_cols = ["Costa Fiscal Year", "Fiscal Week No", "Pick Date", "Plant", "Product Category"]
        time_col = "Pick Date:T"
        time_title = "Date"

    elif time_granularity == "Team":
        if team_col is None:
            st.error("❌ No Team column found in data.")
            st.stop()
        group_cols = ["Costa Fiscal Year", "Fiscal Week No", team_col, "Plant", "Product Category"]
        time_col = f"{team_col}:N"
        time_title = "Team"

    else:  # Weekly
        group_cols = ["Costa Fiscal Year", "Fiscal Week No", "Plant", "Product Category"]
        time_col = "Fiscal Week No:O"
        time_title = "Fiscal Week"

    # ── KEY CHANGE: use aggregate_wages() which sums raw cols then derives metrics ──
    aggregated_wages = aggregate_wages(wages_df, group_cols)

    # -------------------------
    # KPI SUMMARY CARDS
    # -------------------------
    st.subheader("📊 Overall Summary")

    col1, col2, col3, col4 = st.columns(4)
    avg_picker   = aggregated_wages["Picker Cost/Hr"].mean()
    avg_total    = aggregated_wages["Total Cost/Hr"].mean()
    avg_ea       = aggregated_wages["EA Rate"].mean()
    avg_variance = aggregated_wages["Picker % Variance"].mean()

    col1.metric("Avg Picker Cost/Hr",    f"${avg_picker:.2f}", delta=f"{avg_variance:+.1f}% vs EA")
    col2.metric("Avg Total Cost/Hr",     f"${avg_total:.2f}")
    col3.metric("Avg EA Rate",           f"${avg_ea:.2f}")
    col4.metric("Total Volume (tons)",   f"{aggregated_wages['Yield Kg'].sum() / 1000:,.0f}")

    # Show the formula being used
    with st.expander("ℹ️ How Cost/Hr is calculated"):
        st.markdown(f"""
**Picker Cost/Hr**
```
{COL_PICKER_COST}
──────────────────────────────────────
{COL_PICKER_HOURS}
```

**Total Harvest Cost/Hr**
```
Total Harvest Cost  =  {COL_PICKER_COST}
                     + {COL_OVERHEAD}
                     + {COL_BREAK_MOVE}
                     + {COL_ABSENCE}

Total Harvest Cost/Hr  =  Total Harvest Cost  /  {COL_HARVEST_HOURS}
```
> All cost and hours columns are **summed** across the selected grouping before division, ensuring the rate reflects true weighted averages rather than an average of averages.
        """)

    # -------------------------
    # TREND / BAR CHART
    # -------------------------
    if time_granularity == "Team":
        st.subheader("📊 Cost per Hour by Team vs EA Average Competent Rate")

        team_summary = (
            aggregated_wages
            .groupby([team_col], as_index=False)
            .agg({
                "Picker Cost/Hr": "mean",
                "Total Cost/Hr": "mean",
                "EA Rate": "mean",
                "Picker % Variance": "mean",
                "Yield Kg": "sum"
            })
            .sort_values("Picker Cost/Hr", ascending=False)
        )

        base_team = alt.Chart(team_summary)

        picker_bars = base_team.mark_bar(opacity=0.85).encode(
            y=alt.Y(f"{team_col}:N", sort="-x", title="Team"),
            x=alt.X("Picker Cost/Hr:Q", title="Cost per Hour ($)", scale=alt.Scale(zero=True)),
            color=alt.Color(
                "Picker % Variance:Q",
                scale=alt.Scale(domain=[-25, 0, 25], range=["#1a9641", "#ffffbf", "#d7191c"]),
                legend=alt.Legend(title="% vs EA Rate")
            ),
            tooltip=[
                alt.Tooltip(f"{team_col}:N", title="Team"),
                alt.Tooltip("Picker Cost/Hr:Q", format="$.2f", title="Picker Cost/Hr"),
                alt.Tooltip("Total Cost/Hr:Q", format="$.2f", title="Total Cost/Hr"),
                alt.Tooltip("EA Rate:Q", format="$.2f", title="EA Rate"),
                alt.Tooltip("Picker % Variance:Q", format="+.1f", title="% vs EA"),
                alt.Tooltip("Yield Kg:Q", format=",.0f", title="Volume (kg)")
            ]
        )

        ea_rule = base_team.mark_rule(color="#F18F01", strokeWidth=2, strokeDash=[4, 4]).encode(
            x=alt.X("mean(EA Rate):Q")
        )

        team_chart = (picker_bars + ea_rule).properties(height=max(300, len(team_summary) * 30))
        st.altair_chart(team_chart, use_container_width=True)
        st.caption("🔵 Bars = Avg Picker Cost/Hr (coloured by % variance from EA) | 🟠 Dashed = EA Average Competent Rate")

        if "Fiscal Week No" in aggregated_wages.columns:
            st.subheader("📈 Weekly Cost Trend by Team")
            team_weekly = (
                aggregated_wages
                .groupby(["Fiscal Week No", team_col], as_index=False)
                .agg({"Picker Cost/Hr": "mean", "Total Cost/Hr": "mean", "EA Rate": "mean"})
            )
            base_tw = alt.Chart(team_weekly).encode(x=alt.X("Fiscal Week No:O", title="Fiscal Week"))
            picker_line_tw = base_tw.mark_line(strokeWidth=2, point=True).encode(
                y=alt.Y("Picker Cost/Hr:Q", title="Cost/Hr ($)", scale=alt.Scale(zero=False)),
                color=alt.Color(f"{team_col}:N", legend=alt.Legend(title="Team")),
                tooltip=[
                    alt.Tooltip(f"{team_col}:N", title="Team"),
                    "Fiscal Week No:O",
                    alt.Tooltip("Picker Cost/Hr:Q", format="$.2f"),
                    alt.Tooltip("EA Rate:Q", format="$.2f")
                ]
            )
            ea_line_tw = base_tw.mark_line(strokeWidth=1.5, strokeDash=[3, 3], color="#F18F01").encode(
                y=alt.Y("EA Rate:Q")
            )
            team_trend_chart = (picker_line_tw + ea_line_tw).properties(height=350).interactive()
            st.altair_chart(team_trend_chart, use_container_width=True)
            st.caption("Lines = Picker Cost/Hr per team | 🟠 Dotted = EA Rate | 💡 Drag to pan, scroll to zoom")

    else:
        st.subheader(f"📈 Cost per Hour Trend vs EA Average Competent Rate ({time_granularity})")

        base = alt.Chart(aggregated_wages).encode(x=alt.X(time_col, title=time_title))

        picker_line = base.mark_line(
            strokeWidth=2.5, color="#2E86AB",
            point=True if time_granularity == "Daily" else False
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

        total_line = base.mark_line(
            strokeWidth=2.5, color="#A23B72", strokeDash=[5, 5],
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

        ea_line = base.mark_line(strokeWidth=2, color="#F18F01", strokeDash=[2, 2]).encode(
            y=alt.Y("EA Rate:Q"),
            tooltip=[
                "Costa Fiscal Year:O",
                alt.Tooltip("Pick Date:T", format="%Y-%m-%d", title="Date") if time_granularity == "Daily" else alt.Tooltip("Fiscal Week No:O", title="Week"),
                alt.Tooltip("EA Rate:Q", format="$.2f", title="EA Rate")
            ]
        )

        trend_chart = (picker_line + total_line + ea_line).properties(height=400).interactive()
        if time_granularity == "Weekly":
            trend_chart = trend_chart.facet(column=alt.Column("Costa Fiscal Year:O", title="Fiscal Year"))

        st.altair_chart(trend_chart, use_container_width=True)
        if time_granularity == "Daily":
            st.caption("🔵 Solid = Picker Cost/Hr | 🟣 Dashed = Total Harvest Cost/Hr | 🟠 Dotted = EA Average Competent Rate | 💡 Drag to pan, scroll to zoom")
        else:
            st.caption("🔵 Solid = Picker Cost/Hr | 🟣 Dashed = Total Harvest Cost/Hr | 🟠 Dotted = EA Average Competent Rate")

    # -------------------------
    # VARIANCE HEATMAP
    # -------------------------
    st.subheader("🔥 Cost Variance Heatmap (% vs EA Rate)")

    if aggregated_wages.empty or aggregated_wages["Picker % Variance"].isna().all():
        st.warning("⚠️ No data available for the selected filters.")
    else:
        min_variance = aggregated_wages["Picker % Variance"].min()
        max_variance = aggregated_wages["Picker % Variance"].max()

        if pd.isna(min_variance) or pd.isna(max_variance):
            st.warning("⚠️ Cannot calculate variance. Please check your data or filter selection.")
        else:
            scale_limit = max(abs(min_variance), abs(max_variance), 25)
            scale_limit = ((scale_limit // 5) + 1) * 5
            num_plants = aggregated_wages["Plant"].nunique()

            if time_granularity == "Daily":
                aggregated_wages["Pick Date"] = pd.to_datetime(aggregated_wages["Pick Date"])
                aggregated_wages["Pick Date Str"] = aggregated_wages["Pick Date"].dt.strftime("%Y-%m-%d")
                x_encoding = alt.X("Pick Date Str:O", title="Date", sort="ascending", axis=alt.Axis(labelAngle=-45))
                if num_plants == 1:
                    y_encoding = alt.Y("Product Category:N", title="Product Category")
                    heatmap_tooltip = [
                        "Product Category:N", "Plant:N",
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

            elif time_granularity == "Team":
                x_encoding = alt.X("Fiscal Week No:O", title="Fiscal Week")
                y_encoding = alt.Y(f"{team_col}:N", title="Team")
                heatmap_tooltip = [
                    alt.Tooltip(f"{team_col}:N", title="Team"),
                    "Fiscal Week No:O",
                    alt.Tooltip("Picker Cost/Hr:Q", format="$.2f"),
                    alt.Tooltip("EA Rate:Q", format="$.2f"),
                    alt.Tooltip("Picker % Variance:Q", format="+.1f", title="% Variance"),
                    alt.Tooltip("Yield Kg:Q", format=",.0f", title="Volume (kg)")
                ]

            else:  # Weekly
                x_encoding = alt.X("Fiscal Week No:O", title="Fiscal Week")
                y_encoding = alt.Y("Plant:N", title="Plant")
                heatmap_tooltip = [
                    "Plant:N", "Costa Fiscal Year:O", "Fiscal Week No:O",
                    alt.Tooltip("Picker Cost/Hr:Q", format="$.2f"),
                    alt.Tooltip("EA Rate:Q", format="$.2f"),
                    alt.Tooltip("Picker % Variance:Q", format="+.1f", title="% Variance")
                ]

            heatmap = (
                alt.Chart(aggregated_wages)
                .mark_rect(stroke="white", strokeWidth=0.5)
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
                .interactive()
            )
            st.altair_chart(heatmap, use_container_width=True)

            caption_text = (
                f"📊 Variance range: {min_variance:.1f}% to {max_variance:.1f}% | "
                f"🟢 Green = Below EA Rate | 🟡 Yellow = At EA Rate | 🔴 Red = Above EA Rate"
            )
            if time_granularity == "Team":
                caption_text += " | Each cell = one team × one fiscal week"
            elif time_granularity == "Daily" and num_plants == 1:
                caption_text += " | 💡 Showing Product Categories (select multiple plants to compare plants)"
            st.caption(caption_text)

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
    elif time_granularity == "Team":
        display_cols = [c for c in [
            "Costa Fiscal Year", "Fiscal Week No", team_col, "Plant", "Product Category",
            "Picker Cost/Hr", "Total Cost/Hr", "EA Rate",
            "Picker Variance from EA", "Picker % Variance", "Yield Kg"
        ] if c in aggregated_wages.columns]
        sort_cols = [team_col, "Fiscal Week No"]
    else:
        display_cols = [
            "Costa Fiscal Year", "Fiscal Week No", "Plant", "Product Category",
            "Picker Cost/Hr", "Total Cost/Hr", "EA Rate",
            "Picker Variance from EA", "Picker % Variance", "Yield Kg"
        ]
        sort_cols = ["Costa Fiscal Year", "Fiscal Week No", "Plant"]

    display_df = aggregated_wages[[c for c in display_cols if c in aggregated_wages.columns]].sort_values(sort_cols)

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

    st.dataframe(display_df.style.format(format_dict), use_container_width=True)
