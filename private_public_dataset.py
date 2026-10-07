"""
Private vs Public Hospital - Admissions & Live Births
Converted from Private_and_Public_Hospital.ipynb to run on GitHub Actions.

Inputs : M870341.csv (SingStat hospital admissions), sdb-1h-2026.xlsx (tab T9, live births)
Outputs: hospital_admissions_and_live_births_2026.csv + chart PNGs in the 'output' subfolder
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # save charts to file without opening windows
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

# ==========================================
# Paths
# ==========================================
# Repo layout: data/ holds the two input files, output/ receives the results
PROJECT_DIR = Path(__file__).resolve().parent
ADMISSIONS_FILE = PROJECT_DIR / "data" / "M870341.csv"
BIRTHS_FILE = PROJECT_DIR / "data" / "sdb-1h-2026.xlsx"
OUTPUT_DIR = PROJECT_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

BIRTHS_YEAR = 2026  # year of the live births file (sdb-1h-2026)

# ==========================================
# 1. Load data
# ==========================================
admissions_df = pd.read_csv(ADMISSIONS_FILE)
print("Hospital Admissions Data (First 5 rows):")
print(admissions_df.head())

live_births_df = pd.read_excel(BIRTHS_FILE, sheet_name="T9")
print("\nLive Births Data (First 15 rows):")
print(live_births_df.head(15))

# ==========================================
# 2. Clean admissions data
# ==========================================
# Find the row with the most non-NaN values to use as the header
valid_rows_counts = admissions_df.notna().sum(axis=1)
header_idx = valid_rows_counts.idxmax()

# Set the new header and drop the metadata rows above it
admissions_clean = admissions_df.iloc[header_idx + 1:].copy()
admissions_clean.columns = admissions_df.iloc[header_idx]

# Drop columns and rows that are entirely NaN, then reset index
admissions_clean = admissions_clean.dropna(axis=1, how="all")
admissions_clean = admissions_clean.dropna(axis=0, how="all")
admissions_clean = admissions_clean.reset_index(drop=True)

print("\nCleaned Admissions Data (First 5 rows):")
print(admissions_clean.head())

# ==========================================
# 3. Clean live births data
# ==========================================
live_births_clean = live_births_df.dropna(axis=1, how="all").dropna(axis=0, how="all")
live_births_clean = live_births_clean.reset_index(drop=True)

print("\nCleaned Live Births Data (First 10 rows):")
print(live_births_clean.head(10))

# ==========================================
# 4. Tidy live births (Month / Sector / Total)
# ==========================================
tidy_data = []
current_month = None
months = ["January", "February", "March", "April", "May", "June",
          "July", "August", "September", "October", "November", "December"]

for index, row in live_births_clean.iterrows():
    row_str = row.astype(str).str.strip()

    # Check if the row contains a month name
    for month in months:
        if month in row_str.values:
            current_month = month
            break

    # Public and Private sectors are in 'Unnamed: 1'; total for all ethnic groups in 'Unnamed: 3'
    place = str(row.get("Unnamed: 1", "")).strip()
    if place in ["Public Sector Hospitals", "Private Sector Hospitals"]:
        tidy_data.append({
            "Month": current_month,
            "Sector": place,
            "Total_Live_Births": row.get("Unnamed: 3", None),
        })

live_births_tidy = pd.DataFrame(tidy_data)

if live_births_tidy.empty:
    raise SystemExit("Error: No live births data was extracted. Please check the logic and column structures.")

live_births_tidy["Month"] = live_births_tidy["Month"] + f" {BIRTHS_YEAR}"
live_births_tidy["Total_Live_Births"] = pd.to_numeric(live_births_tidy["Total_Live_Births"], errors="coerce")

print("\nTidy Live Births Data:")
print(live_births_tidy.head(10))

# ==========================================
# 5. Tidy admissions (Acute Hospitals: Public & Non-Public)
# ==========================================
admissions_subset = admissions_clean.iloc[1:3].copy()

first_col = admissions_subset.columns[0]
admissions_subset = admissions_subset.rename(columns={first_col: "Sector"})

# Standardise sector names to match the live births data
admissions_subset["Sector"] = admissions_subset["Sector"].astype(str).str.strip().map({
    "Public": "Public Sector Hospitals",
    "Non-Public": "Private Sector Hospitals",
})

# Melt date columns into rows
admissions_tidy = pd.melt(admissions_subset, id_vars=["Sector"], var_name="Month", value_name="Total_Admissions")

# Month format: '2026 Jul'
admissions_tidy["Month"] = pd.to_datetime(admissions_tidy["Month"].astype(str).str.strip(), format="%Y %b", errors="coerce")
admissions_tidy["Total_Admissions"] = pd.to_numeric(admissions_tidy["Total_Admissions"], errors="coerce")
admissions_tidy = admissions_tidy.dropna().reset_index(drop=True)

# Live births Month format: 'January 2026'
live_births_tidy["Month"] = pd.to_datetime(live_births_tidy["Month"], format="%B %Y", errors="coerce")

print("\nTidy Admissions Data (First 10 rows):")
print(admissions_tidy.head(10))

# ==========================================
# 6. Merge + trend charts
# ==========================================
dashboard_data = pd.merge(admissions_tidy, live_births_tidy, on=["Month", "Sector"], how="inner")
dashboard_data = dashboard_data.sort_values("Month")

plt.figure(figsize=(16, 6))

plt.subplot(1, 2, 1)
sns.lineplot(data=dashboard_data, x="Month", y="Total_Admissions", hue="Sector", marker="o", palette="Set1")
plt.title(f"Hospital Admissions in Singapore (First Half {BIRTHS_YEAR})")
plt.ylabel("Total Admissions")
plt.xlabel("Month")
plt.xticks(rotation=45)
plt.grid(True, alpha=0.3)

plt.subplot(1, 2, 2)
sns.lineplot(data=dashboard_data, x="Month", y="Total_Live_Births", hue="Sector", marker="o", palette="Set2")
plt.title(f"Live Births in Singapore (First Half {BIRTHS_YEAR})")
plt.ylabel("Total Live Births")
plt.xlabel("Month")
plt.xticks(rotation=45)
plt.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig(OUTPUT_DIR / "01_admissions_and_births_trend.png", dpi=150)
plt.close()

print("\nMerged Dashboard Data:")
print(dashboard_data)

# ==========================================
# 7. Sector totals (bar) + scatter
# ==========================================
sector_totals = dashboard_data.groupby("Sector").sum(numeric_only=True).reset_index()

fig, axes = plt.subplots(1, 2, figsize=(14, 6))

sns.barplot(data=sector_totals, x="Sector", y="Total_Admissions", ax=axes[0], hue="Sector", legend=False, palette="Set1")
axes[0].set_title(f"Total Hospital Admissions (Jan-Jun {BIRTHS_YEAR})")
axes[0].set_ylabel("Total Admissions")
for p in axes[0].patches:
    axes[0].annotate(f"{int(p.get_height()):,}", (p.get_x() + p.get_width() / 2.0, p.get_height()), ha="center", va="bottom")

sns.barplot(data=sector_totals, x="Sector", y="Total_Live_Births", ax=axes[1], hue="Sector", legend=False, palette="Set2")
axes[1].set_title(f"Total Live Births (Jan-Jun {BIRTHS_YEAR})")
axes[1].set_ylabel("Total Live Births")
for p in axes[1].patches:
    axes[1].annotate(f"{int(p.get_height()):,}", (p.get_x() + p.get_width() / 2.0, p.get_height()), ha="center", va="bottom")

plt.tight_layout()
plt.savefig(OUTPUT_DIR / "02_sector_totals.png", dpi=150)
plt.close()

plt.figure(figsize=(10, 6))
sns.scatterplot(data=dashboard_data, x="Total_Admissions", y="Total_Live_Births", hue="Sector", s=150, palette=["#E41A1C", "#377EB8"])
plt.title("Monthly Hospital Admissions vs Live Births")
plt.xlabel("Total Admissions")
plt.ylabel("Total Live Births")
plt.grid(True, alpha=0.3)
plt.savefig(OUTPUT_DIR / "03_admissions_vs_births_scatter.png", dpi=150)
plt.close()

# ==========================================
# 8. Yearly admissions trend + proportions (2x2 dashboard)
# ==========================================
admissions_df_viz = admissions_tidy.copy()
admissions_df_viz["Year"] = admissions_df_viz["Month"].dt.year

# Exclude the current partial year (causes a misleading drop)
admissions_df_viz = admissions_df_viz[admissions_df_viz["Year"] < BIRTHS_YEAR]
adm_yearly = admissions_df_viz.groupby(["Year", "Sector"])["Total_Admissions"].sum().reset_index()

adm_pivot = adm_yearly.pivot(index="Year", columns="Sector", values="Total_Admissions")
adm_prop = adm_pivot.div(adm_pivot.sum(axis=1), axis=0) * 100

births_df_viz = live_births_tidy.copy()
births_df_viz["Month_Str"] = births_df_viz["Month"].dt.strftime("%Y-%m")
birth_trend = births_df_viz.groupby(["Month_Str", "Sector"])["Total_Live_Births"].sum().reset_index()

birth_pivot = birth_trend.pivot(index="Month_Str", columns="Sector", values="Total_Live_Births")
birth_prop = birth_pivot.div(birth_pivot.sum(axis=1), axis=0) * 100

fig, axes = plt.subplots(2, 2, figsize=(18, 12))


def add_line_labels(ax, df, x_col, y_col):
    for _, row in df.iterrows():
        if pd.notna(row[y_col]):
            ax.annotate(f"{int(row[y_col]):,}", (row[x_col], row[y_col]),
                        textcoords="offset points", xytext=(0, 5), ha="center", fontsize=8)


# Plot 1: Admissions yearly trend
first_year = int(adm_yearly["Year"].min()) if not adm_yearly.empty else ""
last_year = int(adm_yearly["Year"].max()) if not adm_yearly.empty else ""
sns.lineplot(data=adm_yearly, x="Year", y="Total_Admissions", hue="Sector", marker="o", ax=axes[0, 0], palette="Set1")
axes[0, 0].set_title(f"Yearly Hospital Admissions Trend ({first_year}-{last_year})")
axes[0, 0].set_ylabel("Total Admissions")
axes[0, 0].grid(True, alpha=0.3)
axes[0, 0].set_yticks([])
add_line_labels(axes[0, 0], adm_yearly, "Year", "Total_Admissions")

# Plot 2: Admissions proportions
adm_prop.plot(kind="bar", stacked=True, ax=axes[0, 1], color=["#377EB8", "#E41A1C"], width=0.8)
axes[0, 1].set_title("Proportion of Admissions (Public vs Private)")
axes[0, 1].set_ylabel("")
axes[0, 1].set_yticks([])
for i, label in enumerate(axes[0, 1].get_xticklabels()):
    if i % 4 != 0:
        label.set_visible(False)
axes[0, 1].tick_params(axis="x", rotation=45)
axes[0, 1].legend(title="Sector")
for c in axes[0, 1].containers:
    axes[0, 1].bar_label(c, label_type="center", fmt="%.1f%%", color="white", fontsize=8)

# Plot 3: Live births trend
sns.lineplot(data=birth_trend, x="Month_Str", y="Total_Live_Births", hue="Sector", marker="o", ax=axes[1, 0], palette="Set2")
axes[1, 0].set_title(f"Live Births Trend (Jan-Jun {BIRTHS_YEAR})")
axes[1, 0].set_ylabel("Total Live Births")
axes[1, 0].set_xlabel("Month")
axes[1, 0].tick_params(axis="x", rotation=45)
axes[1, 0].grid(True, alpha=0.3)
axes[1, 0].set_yticks([])
add_line_labels(axes[1, 0], birth_trend, "Month_Str", "Total_Live_Births")

# Plot 4: Live births proportions
birth_prop.plot(kind="bar", stacked=True, ax=axes[1, 1], color=["#FC8D62", "#66C2A5"], width=0.6)
axes[1, 1].set_title("Proportion of Live Births (Public vs Private)")
axes[1, 1].set_ylabel("")
axes[1, 1].set_xlabel("Month")
axes[1, 1].tick_params(axis="x", rotation=45)
axes[1, 1].legend(title="Sector")
axes[1, 1].set_yticks([])
for c in axes[1, 1].containers:
    axes[1, 1].bar_label(c, label_type="center", fmt="%.1f%%", color="white", fontsize=10)

plt.tight_layout()
plt.savefig(OUTPUT_DIR / "04_dashboard_trends_and_proportions.png", dpi=150)
plt.close()

# ==========================================
# 9. Export merged dataset
# ==========================================
export_file = OUTPUT_DIR / f"hospital_admissions_and_live_births_{BIRTHS_YEAR}.csv"
dashboard_data.to_csv(export_file, index=False)

print(f"\nData successfully exported to: {export_file}")
print(f"Charts saved to: {OUTPUT_DIR}")
