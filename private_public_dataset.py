"""
Private vs Public Hospital - Admissions & Live Births (2021 onwards)
GITHUB ACTIONS VERSION - reads from the repo's data/ folder.

Inputs (all in the data/ folder):
  - M870341.csv                 SingStat hospital admissions
  - every *sdb*.xlsx / *.xls    Live births releases (quarterly and half-yearly)
Outputs (output/ folder):
  - hospital_admissions_and_live_births_2021_onwards.csv   merged table
  - live_births_by_sector_2021_onwards.csv                 live births with source file
  - files_processed.csv                                    what was read from each file
  - duplicate_months_check.csv                             only if a month appears in more than one file
  - chart PNGs
"""

import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

# ==========================================
# Settings - paths are relative to the repo, so this works on GitHub
# ==========================================
PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR = PROJECT_DIR / "data"
ADMISSIONS_FILE = DATA_DIR / "M870341.csv"
OUTPUT_DIR = PROJECT_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

START_DATE = pd.Timestamp("2021-01-01")   # keep data from this month onwards

MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"], start=1)}
MONTHS.update({m[:3]: i for m, i in list(MONTHS.items())})

# ==========================================
# 1. Admissions (same logic as the notebook)
# ==========================================
admissions_df = pd.read_csv(ADMISSIONS_FILE)

valid_rows_counts = admissions_df.notna().sum(axis=1)
header_idx = valid_rows_counts.idxmax()
admissions_clean = admissions_df.iloc[header_idx + 1:].copy()
admissions_clean.columns = admissions_df.iloc[header_idx]
admissions_clean = admissions_clean.dropna(axis=1, how="all").dropna(axis=0, how="all").reset_index(drop=True)

admissions_subset = admissions_clean.iloc[1:3].copy()
admissions_subset = admissions_subset.rename(columns={admissions_subset.columns[0]: "Sector"})
admissions_subset["Sector"] = admissions_subset["Sector"].astype(str).str.strip().map({
    "Public": "Public Sector Hospitals",
    "Non-Public": "Private Sector Hospitals",
})

admissions_tidy = pd.melt(admissions_subset, id_vars=["Sector"], var_name="Month", value_name="Total_Admissions")
admissions_tidy["Month"] = pd.to_datetime(admissions_tidy["Month"].astype(str).str.strip(), format="%Y %b", errors="coerce")
admissions_tidy["Total_Admissions"] = pd.to_numeric(admissions_tidy["Total_Admissions"], errors="coerce")
admissions_tidy = admissions_tidy.dropna().reset_index(drop=True)
print(f"Admissions: {admissions_tidy['Month'].min():%b %Y} to {admissions_tidy['Month'].max():%b %Y}")

# ==========================================
# 2. Live births - read every sdb file
# ==========================================
def cell_text(v):
    return "" if pd.isna(v) else str(v).strip()


def to_number(v):
    if pd.isna(v):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(",", "").strip())
    except ValueError:
        return None


def find_births_sheet(path):
    """Find the 'Live Births ... by Place of Occurrence' table (T9 in half-year files, T11 in quarterly)."""
    sheets = pd.read_excel(path, sheet_name=None, header=None)
    candidates = []
    for name, df in sheets.items():
        if str(name).strip().upper().startswith("CONTENT"):
            continue
        # normalise: older files write "Live-Births"; also tolerate "Occurence" spelling
        text = " ".join(cell_text(v) for v in df.head(15).values.ravel()).lower().replace("-", " ")
        if "live birth" in text and re.search(r"place of occurr?ence", text):
            score = 2 if str(name).strip().upper() == "T9" else 1
            candidates.append((score, name, df))
    if not candidates:
        return None, None
    candidates.sort(key=lambda c: -c[0])
    return candidates[0][1], candidates[0][2]


def find_year(df, path):
    """Year from the table title, else from the file name."""
    for v in df.head(10).values.ravel():
        t = cell_text(v)
        if "live birth" in t.lower().replace("-", " "):
            years = re.findall(r"20\d\d", t)
            if years:
                return int(years[-1])
    years = re.findall(r"20\d\d", path.stem)
    return int(years[-1]) if years else None


def sector_of(label):
    l = label.lower()
    if "hospital" in l and "public" in l:
        return "Public Sector Hospitals"
    if "hospital" in l and "private" in l:
        return "Private Sector Hospitals"
    return None


def extract_births(path):
    sheet, df = find_births_sheet(path)
    if df is None:
        return pd.DataFrame(), "No live-births-by-place-of-occurrence table found"
    year = find_year(df, path)
    if year is None:
        return pd.DataFrame(), f"Sheet {sheet}: could not work out the year"

    rows, current_month = [], None
    for _, row in df.iterrows():
        cells = [cell_text(v) for v in row.values]
        numbers = [to_number(v) for v in row.values]

        # Heading rows (no numbers): a single month name sets the month; other headings clear it
        if not any(n is not None for n in numbers):
            labels = [c for c in cells if c]
            if len(labels) == 1:
                # strip footnote marks, e.g. "March*"
                current_month = MONTHS.get(re.sub(r"[^a-z]", "", labels[0].lower()))
            continue

        # Data rows: sector label, then first number to its right (= Total, all ethnic groups)
        for i, c in enumerate(cells):
            sector = sector_of(c) if c else None
            if sector and current_month:
                total = next((n for n in numbers[i + 1:] if n is not None), None)
                rows.append({"Month": pd.Timestamp(year=year, month=current_month, day=1),
                             "Sector": sector, "Total_Live_Births": total, "Source_File": path.name})
                break

    out = pd.DataFrame(rows)
    return out, f"Sheet {sheet}, year {year}: {out['Month'].nunique() if len(out) else 0} months"


birth_files = sorted(p for p in DATA_DIR.iterdir()
                     if p.suffix.lower() in (".xlsx", ".xls") and "sdb" in p.name.lower())
if not birth_files:
    raise SystemExit("No sdb*.xlsx files found in the data folder.")

all_births, log = [], []
for f in birth_files:
    try:
        b, note = extract_births(f)
    except Exception as e:
        b, note = pd.DataFrame(), f"ERROR: {e}"
    print(f"{f.name}: {note}")
    months = sorted(b["Month"].dt.strftime("%Y-%m").unique()) if len(b) else []
    log.append({"File": f.name, "Result": note, "Months": ", ".join(months)})
    all_births.append(b)

pd.DataFrame(log).to_csv(OUTPUT_DIR / "files_processed.csv", index=False)
live_births_tidy = pd.concat(all_births, ignore_index=True)
if live_births_tidy.empty:
    raise SystemExit("Error: No live births data was extracted. See output/files_processed.csv")

# Same month in more than one file: use the half-year release, list overlaps for checking
live_births_tidy["_priority"] = live_births_tidy["Source_File"].str.lower().str.contains(r"[12]h").astype(int)
live_births_tidy = live_births_tidy.sort_values(["Month", "Sector", "_priority"])
dupes = live_births_tidy[live_births_tidy.duplicated(["Month", "Sector"], keep=False)]
if not dupes.empty:
    differing = (dupes.groupby(["Month", "Sector"])["Total_Live_Births"].nunique() > 1).sum()
    print(f"\nNote: {len(dupes[['Month', 'Sector']].drop_duplicates())} month/sector figures appear in more than one file "
          f"({differing} differ). Half-year release used. See duplicate_months_check.csv")
    dupes.drop(columns="_priority").to_csv(OUTPUT_DIR / "duplicate_months_check.csv", index=False)
live_births_tidy = (live_births_tidy.drop_duplicates(["Month", "Sector"], keep="last")
                    .drop(columns="_priority").reset_index(drop=True))

live_births_tidy = live_births_tidy[live_births_tidy["Month"] >= START_DATE].sort_values(["Month", "Sector"])
live_births_tidy.assign(Month=live_births_tidy["Month"].dt.strftime("%Y-%m")).to_csv(
    OUTPUT_DIR / "live_births_by_sector_2021_onwards.csv", index=False)

expected = pd.date_range(live_births_tidy["Month"].min(), live_births_tidy["Month"].max(), freq="MS")
missing = sorted(set(expected) - set(live_births_tidy["Month"]))
if missing:
    print("WARNING - live births missing for:", ", ".join(m.strftime("%b %Y") for m in missing))
print(f"Live births: {live_births_tidy['Month'].min():%b %Y} to {live_births_tidy['Month'].max():%b %Y}")

# ==========================================
# 3. Merge (2021 onwards)
# ==========================================
dashboard_data = pd.merge(admissions_tidy[admissions_tidy["Month"] >= START_DATE],
                          live_births_tidy.drop(columns="Source_File"),
                          on=["Month", "Sector"], how="inner").sort_values(["Month", "Sector"])
period = f"{dashboard_data['Month'].min():%b %Y} - {dashboard_data['Month'].max():%b %Y}"

export_file = OUTPUT_DIR / "hospital_admissions_and_live_births_2021_onwards.csv"
dashboard_data.assign(Month=dashboard_data["Month"].dt.strftime("%Y-%m")).to_csv(export_file, index=False)
print(f"\nMerged table: {len(dashboard_data)} rows ({period}) -> {export_file.name}")

# ==========================================
# 4. Charts
# ==========================================
plt.figure(figsize=(16, 6))
plt.subplot(1, 2, 1)
sns.lineplot(data=dashboard_data, x="Month", y="Total_Admissions", hue="Sector", marker="o", palette="Set1")
plt.title(f"Hospital Admissions in Singapore ({period})")
plt.ylabel("Total Admissions"); plt.xticks(rotation=45); plt.grid(True, alpha=0.3)
plt.subplot(1, 2, 2)
sns.lineplot(data=dashboard_data, x="Month", y="Total_Live_Births", hue="Sector", marker="o", palette="Set2")
plt.title(f"Live Births in Singapore ({period})")
plt.ylabel("Total Live Births"); plt.xticks(rotation=45); plt.grid(True, alpha=0.3)
plt.tight_layout(); plt.savefig(OUTPUT_DIR / "01_admissions_and_births_trend.png", dpi=150); plt.close()

yearly = dashboard_data.assign(Year=dashboard_data["Month"].dt.year).groupby(["Year", "Sector"])[
    ["Total_Admissions", "Total_Live_Births"]].sum().reset_index()
fig, axes = plt.subplots(1, 2, figsize=(16, 6))
for ax, col, title, pal in [(axes[0], "Total_Admissions", "Hospital Admissions by Year", "Set1"),
                            (axes[1], "Total_Live_Births", "Live Births by Year", "Set2")]:
    sns.barplot(data=yearly, x="Year", y=col, hue="Sector", ax=ax, palette=pal)
    ax.set_title(f"{title} (latest year may be partial)")
    for c in ax.containers:
        ax.bar_label(c, labels=[f"{int(v):,}" for v in c.datavalues], fontsize=8)
plt.tight_layout(); plt.savefig(OUTPUT_DIR / "02_sector_totals_by_year.png", dpi=150); plt.close()

plt.figure(figsize=(10, 6))
sns.scatterplot(data=dashboard_data, x="Total_Admissions", y="Total_Live_Births", hue="Sector", s=100,
                palette=["#E41A1C", "#377EB8"])
plt.title(f"Monthly Hospital Admissions vs Live Births ({period})")
plt.grid(True, alpha=0.3)
plt.savefig(OUTPUT_DIR / "03_admissions_vs_births_scatter.png", dpi=150); plt.close()

adm = admissions_tidy.assign(Year=admissions_tidy["Month"].dt.year)
months_per_year = adm.groupby("Year")["Month"].nunique()
adm = adm[adm["Year"].isin(months_per_year[months_per_year == 12].index)]
adm_yearly = adm.groupby(["Year", "Sector"])["Total_Admissions"].sum().reset_index()
adm_pivot = adm_yearly.pivot(index="Year", columns="Sector", values="Total_Admissions")
adm_prop = adm_pivot.div(adm_pivot.sum(axis=1), axis=0) * 100

births_viz = live_births_tidy.assign(Month_Str=live_births_tidy["Month"].dt.strftime("%Y-%m"))
birth_trend = births_viz.groupby(["Month_Str", "Sector"])["Total_Live_Births"].sum().reset_index()
birth_pivot = birth_trend.pivot(index="Month_Str", columns="Sector", values="Total_Live_Births")
birth_prop = birth_pivot.div(birth_pivot.sum(axis=1), axis=0) * 100


def thin_xticks(ax, every):
    for i, label in enumerate(ax.get_xticklabels()):
        label.set_visible(i % every == 0)


fig, axes = plt.subplots(2, 2, figsize=(20, 12))
sns.lineplot(data=adm_yearly, x="Year", y="Total_Admissions", hue="Sector", marker="o", ax=axes[0, 0], palette="Set1")
axes[0, 0].set_title(f"Yearly Hospital Admissions Trend ({adm_yearly['Year'].min()}-{adm_yearly['Year'].max()})")
axes[0, 0].grid(True, alpha=0.3)

adm_prop.plot(kind="bar", stacked=True, ax=axes[0, 1], color=["#377EB8", "#E41A1C"], width=0.8)
axes[0, 1].set_title("Proportion of Admissions (Public vs Private)"); axes[0, 1].set_yticks([])
thin_xticks(axes[0, 1], 4); axes[0, 1].tick_params(axis="x", rotation=45)
for c in axes[0, 1].containers:
    axes[0, 1].bar_label(c, labels=[f"{v:.0f}%" if i % 4 == 0 else "" for i, v in enumerate(c.datavalues)],
                         label_type="center", color="white", fontsize=7)

sns.lineplot(data=birth_trend, x="Month_Str", y="Total_Live_Births", hue="Sector", marker="o", ax=axes[1, 0], palette="Set2")
axes[1, 0].set_title(f"Live Births Trend ({birth_trend['Month_Str'].min()} to {birth_trend['Month_Str'].max()})")
axes[1, 0].set_xlabel("Month"); axes[1, 0].grid(True, alpha=0.3)
thin_xticks(axes[1, 0], 3); axes[1, 0].tick_params(axis="x", rotation=45)

birth_prop.plot(kind="bar", stacked=True, ax=axes[1, 1], color=["#FC8D62", "#66C2A5"], width=0.8)
axes[1, 1].set_title("Proportion of Live Births (Public vs Private)"); axes[1, 1].set_yticks([])
axes[1, 1].set_xlabel("Month"); thin_xticks(axes[1, 1], 3); axes[1, 1].tick_params(axis="x", rotation=45)
for c in axes[1, 1].containers:
    axes[1, 1].bar_label(c, labels=[f"{v:.0f}%" if i % 3 == 0 else "" for i, v in enumerate(c.datavalues)],
                         label_type="center", color="white", fontsize=7)

for ax in (axes[0, 1], axes[1, 1]):
    ax.legend(title="Sector", loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=2)
plt.tight_layout(); plt.savefig(OUTPUT_DIR / "04_dashboard_trends_and_proportions.png", dpi=150); plt.close()
print(f"Charts saved to: {OUTPUT_DIR}")
