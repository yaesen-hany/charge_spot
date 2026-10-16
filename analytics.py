import pandas as pd
import random
import numpy as np
from datetime import datetime, timedelta
import plotly.express as px
import os
import time
from fpdf import FPDF

try:
    from exceptions import PersistenceError
except ImportError:
    class PersistenceError(Exception):
        pass

try:
    from sorting_engine import merge_sort, quick_sort
except ImportError:
    def merge_sort(items, key=None, reverse=False, stats=None):
        return sorted(items, key=key, reverse=reverse), None

    def quick_sort(items, key=None, reverse=False, stats=None):
        return sorted(items, key=key, reverse=reverse), None

DATA_PATH = "data/charging_data.csv"

#=====================================================================================
def generate_egypt_charging_data(num_records=600, seed=42):
    random.seed(seed)
    np.random.seed(seed)
    
    stations = [
        {"station_id": "ST-01", "station_name": "Infinity Cairo Festival City", "area": "New Cairo", "chargers": ["fast", "normal"]},
        {"station_id": "ST-02", "station_name": "Revolta Carrefour Maadi", "area": "Maadi", "chargers": ["fast", "normal"]},
        {"station_id": "ST-03", "station_name": "Watanya Chillout Ahly Club", "area": "Nasr City", "chargers": ["fast"]},
        {"station_id": "ST-04", "station_name": "Infinity City Stars", "area": "Nasr City", "chargers": ["normal"]},
    ]

    end_date = datetime.now()
    start_date = end_date - timedelta(days=75)

    hours = list(range(24))
    weights = [1]*6 + [3]*2 + [8]*3 + [4]*6 + [8]*4 + [2]*3

    records = []
    
    for i in range(1, num_records + 1):
        session_id = f"SES-{i:06d}"
        station = random.choice(stations)
        charger_type = random.choice(station["chargers"])

        random_days = random.randint(0, 75)
        selected_hour = random.choices(hours, weights=weights)[0]
        selected_minute = random.randint(0, 59)
        start_time = start_date + timedelta(days=random_days)
        start_time = start_time.replace(hour=selected_hour, minute=selected_minute, second=0, microsecond=0)

        if charger_type == "fast":
            power_kw = round(random.uniform(50.0, 150.0), 1)
            duration_min = random.randint(20, 60)
        else:
            power_kw = round(random.uniform(7.0, 22.0), 1)
            duration_min = random.randint(60, 240)

        end_time = start_time + timedelta(minutes=duration_min)
        
        efficiency = random.uniform(0.85, 0.95)
        energy_kwh = round(power_kw * (duration_min / 60) * efficiency, 2)
        
        cost = round(energy_kwh * 2.5, 2) 

        letters = "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ", k=3))
        digits = "".join(random.choices("0123456789", k=random.choice([3, 4])))
        driver_plate = f"{letters}-{digits}"

        status = random.choices(["completed", "cancelled"], weights=[95, 5])[0]

        records.append({
            "session_id": session_id,
            "station_id": station["station_id"],
            "station_name": station["station_name"],
            "area": station["area"],
            "charger_type": charger_type,
            "power_kw": power_kw,
            "driver_plate": driver_plate,
            "start_time": start_time,
            "end_time": end_time,
            "duration_min": float(duration_min),
            "energy_kwh": energy_kwh,
            "cost": cost,
            "status": status
        })

    df = pd.DataFrame(records)

    num_dirty = int(num_records * 0.04)
    dirty_indices = random.sample(range(num_records), num_dirty)

    for idx in dirty_indices:
        dirt_type = random.randint(1, 4)
        if dirt_type == 1:
            df.at[idx, 'energy_kwh'] = np.nan 
        elif dirt_type == 2:
            df.at[idx, 'end_time'] = pd.NaT 
        elif dirt_type == 3:
            df.at[idx, 'duration_min'] = -abs(df.at[idx, 'duration_min']) 
        elif dirt_type == 4:
            df.at[idx, 'driver_plate'] = " " + df.at[idx, 'driver_plate'].lower() + " "

    duplicates = df.sample(n=5, random_state=seed)
    df = pd.concat([df, duplicates], ignore_index=True)

    return df
#=====================================================================================
def load_data(path=DATA_PATH):
    target_path = path
    if not os.path.exists(target_path):
        if os.path.exists("charging_data.csv"):
            target_path = "charging_data.csv"
        elif os.path.exists("data/charging_data.csv"):
            target_path = "data/charging_data.csv"
        else:
            raise PersistenceError(f"File not found: {path}")
    df = pd.read_csv(target_path)
    if "hour" not in df.columns or df["energy_kwh"].isna().any() or df["end_time"].isna().any():
        df = clean_data(df)
        try:
            os.makedirs("data", exist_ok=True)
            df.to_csv(DATA_PATH, index=False)
        except Exception:
            pass
    else:
        df["start_time"] = pd.to_datetime(df["start_time"], errors="coerce")
        df["end_time"] = pd.to_datetime(df["end_time"], errors="coerce")
    return df
#=====================================================================================
def clean_data(df):
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()

    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].astype(str).str.strip()
        df.loc[df[col].isin(["nan", "NaT", "None", ""]), col] = np.nan

    df['driver_plate'] = df['driver_plate'].str.strip().str.upper()
    df['charger_type'] = df['charger_type'].str.strip().str.lower()
    df['status'] = df['status'].str.strip().str.lower()

    df['start_time'] = pd.to_datetime(df['start_time'], errors='coerce')
    df['end_time'] = pd.to_datetime(df['end_time'], errors='coerce')

    df = df.drop_duplicates()
    df = df.drop_duplicates(subset=['session_id'])
    df.dropna(subset=['start_time'], inplace=True)

    valid_times = df['start_time'].notna() & df['end_time'].notna() & (df['duration_min'] > 0)
    recomputed = (df.loc[valid_times, 'end_time'] - df.loc[valid_times, 'start_time']).dt.total_seconds() / 60.0
    df.loc[valid_times & (recomputed > 0), 'duration_min'] = recomputed[recomputed > 0].round(2)

    missing_end = df['end_time'].isna() & (df['duration_min'] > 0)
    duration_as_time = pd.to_timedelta(df.loc[missing_end, 'duration_min'], unit='m')
    df.loc[missing_end, 'end_time'] = df.loc[missing_end, 'start_time'] + duration_as_time

    df['energy_kwh'] = df.groupby('charger_type')['energy_kwh'].transform(lambda x: x.fillna(x.median()))

    df = df[(df['duration_min'] > 0) & (df['energy_kwh'] >= 0) & (df['power_kw'] > 0)]

    df['hour'] = df['start_time'].dt.hour
    df['weekday'] = df['start_time'].dt.weekday
    df['date'] = df['start_time'].dt.date

    df = df.reset_index(drop=True)

    return df
#=====================================================================================
def get_cleaning_report(raw_df, clean_df):
    rows_before = len(raw_df)
    rows_after = len(clean_df)
    rows_dropped = rows_before - rows_after
    duplicates_removed = int(raw_df.duplicated().sum() + raw_df.drop_duplicates().duplicated(subset=['session_id']).sum())
    missing_values_filled = int(raw_df['energy_kwh'].isna().sum() + raw_df['end_time'].isna().sum())
    invalid_rows_dropped = max(0, rows_dropped - duplicates_removed)

    report = {
        "rows_before": rows_before,
        "rows_after": rows_after,
        "rows_dropped": rows_dropped,
        "duplicates_removed": duplicates_removed,
        "missing_values_filled": missing_values_filled,
        "invalid_rows_dropped": invalid_rows_dropped
    }
    return report
#=====================================================================================
def clean_stations_data(csv_path="stations_slots.csv"):
    """Clean stations and slots from CSV using Pandas and return hierarchical station dicts."""
    target_path = csv_path
    if not os.path.exists(target_path):
        if os.path.exists(os.path.join("data", "stations_slots.csv")):
            target_path = os.path.join("data", "stations_slots.csv")
        elif os.path.exists("stations_slots.csv"):
            target_path = "stations_slots.csv"
        else:
            return [], {"error": f"File not found: {csv_path}"}

    import re
    df_raw = pd.read_csv(target_path, encoding="utf-8-sig")
    rows_before = len(df_raw)

    df = df_raw.copy()

    # 1. Clean whitespace across all text columns
    for col in df.columns:
        if df[col].dtype == "object" or isinstance(df[col].dtype, pd.StringDtype):
            df[col] = df[col].astype(str).str.strip()

    # 2. Lowercase and normalize categorical fields
    df["charger_type"] = df["charger_type"].astype(str).str.strip().str.lower()
    df["status"] = df["status"].astype(str).str.strip().str.lower()

    # 3. Numeric conversions
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    df["power_kw"] = pd.to_numeric(df["power_kw"], errors="coerce")

    # 4. Remove duplicate rows and duplicate slot IDs
    dups_full = int(df.duplicated().sum())
    df = df.drop_duplicates()
    dups_slot = int(df.duplicated(subset=["slot_id"]).sum())
    df = df.drop_duplicates(subset=["slot_id"])

    time_regex_pattern = r"^\d{2}:\d{2}$"
    valid_mask = (
        df["latitude"].notna() &
        df["longitude"].notna() &
        (df["power_kw"] > 0) &
        df["charger_type"].isin(["fast", "normal"]) &
        df["status"].isin(["free", "booked", "maintenance"]) &
        df["start_time"].astype(str).str.match(time_regex_pattern) &
        df["end_time"].astype(str).str.match(time_regex_pattern)
    )
    df = df[valid_mask]

    stations_map = {}
    valid_slots_count = 0

    for row in df.itertuples(index=False):
        s_id = str(row.station_id).strip()
        slot_dict = {
            "slot_id": str(row.slot_id).strip(),
            "station_id": s_id,
            "charger_type": row.charger_type,
            "power_kw": float(row.power_kw),
            "start_time": str(row.start_time).strip(),
            "end_time": str(row.end_time).strip(),
            "status": row.status
        }

        if s_id not in stations_map:
            stations_map[s_id] = {
                "station_id": s_id,
                "name": str(row.name).strip(),
                "area": str(row.area).strip(),
                "latitude": float(row.latitude),
                "longitude": float(row.longitude),
                "slots": []
            }
        stations_map[s_id]["slots"].append(slot_dict)
        valid_slots_count += 1

    cleaned_stations = list(stations_map.values())

    report = {
        "rows_before": rows_before,
        "rows_after": valid_slots_count,
        "stations_count": len(cleaned_stations),
        "slots_count": valid_slots_count,
        "duplicates_removed": dups_full + dups_slot,
        "invalid_rows_dropped": max(0, rows_before - valid_slots_count - dups_full - dups_slot)
    }
    return cleaned_stations, report
#=====================================================================================
def total_energy_kwh(df):
    if df is None or df.empty:
        return 0.0
    completed = df[df['status'] == 'completed'] if 'status' in df.columns else df
    return round(float(completed['energy_kwh'].sum()), 2)
#=====================================================================================
def average_charge_time_min(df):
    if df is None or df.empty:
        return 0.0
    return round(float(df['duration_min'].mean()), 2)
#=====================================================================================
def station_occupancy_rate(df, open_hours_per_day=16, chargers_per_station=None):
    if df is None or df.empty:
        return pd.DataFrame(columns=['station_id', 'duration_min', 'occupancy_rate_%'])

    if chargers_per_station is None:
        chargers_per_station = {"ST-01": 2, "ST-02": 2, "ST-03": 1, "ST-04": 1}
        
    s_start = pd.to_datetime(df['start_time'], errors='coerce')
    total_days = (s_start.max() - s_start.min()).days if s_start.notna().any() else 1
    if total_days <= 0 or pd.isna(total_days): 
        total_days = 1
        
    df_occupancy = df.groupby('station_id')['duration_min'].sum().reset_index()
    
    rates = []
    for index, row in df_occupancy.iterrows():
        station = row['station_id']
        used_minutes = row['duration_min']
        
        chargers_count = chargers_per_station.get(station, 1)
        available_minutes = total_days * open_hours_per_day * 60 * chargers_count
        
        rate = (used_minutes / available_minutes) * 100
        rates.append(round(rate, 2))
        
    df_occupancy['occupancy_rate_%'] = rates
    return df_occupancy
#=====================================================================================
def compute_kpis(df):
    if df is None or df.empty:
        return {
            "total_energy_kwh": 0.0,
            "avg_charge_time_min": 0.0,
            "avg_occupancy_rate": 0.0,
            "total_sessions": 0,
            "busiest_station": "N/A",
        }

    total_energy = total_energy_kwh(df)
    avg_time = average_charge_time_min(df)
    occupancy_df = station_occupancy_rate(df)
    avg_occupancy = round(float(occupancy_df['occupancy_rate_%'].mean()), 2) if not occupancy_df.empty else 0.0
    total_sessions = len(df)
    busiest = df['station_name'].mode()[0]
    
    kpis = {
        "total_energy_kwh": total_energy,
        "avg_charge_time_min": avg_time,
        "avg_occupancy_rate": avg_occupancy,
        "total_sessions": total_sessions,
        "busiest_station": busiest,
    }
    
    return kpis
#=====================================================================================
def peak_hours_analysis(df):
    hourly = df.groupby('hour').agg(
        sessions_count=('session_id', 'count'),
        total_energy_kwh=('energy_kwh', 'sum')
    ).reset_index()
    hourly['total_energy_kwh'] = hourly['total_energy_kwh'].round(2)
    return hourly.sort_values(by='sessions_count', ascending=False).reset_index(drop=True)

def fast_vs_normal_comparison(df):
    comp = df.groupby('charger_type').agg(
        sessions_count=('session_id', 'count'),
        avg_duration_min=('duration_min', 'mean'),
        avg_energy_kwh=('energy_kwh', 'mean')
    ).reset_index()
    comp['avg_duration_min'] = comp['avg_duration_min'].round(1)
    comp['avg_energy_kwh'] = comp['avg_energy_kwh'].round(2)
    comp['energy_per_hour'] = (comp['avg_energy_kwh'] / (comp['avg_duration_min'] / 60)).round(2)
    return comp
#=====================================================================================
def generate_insights(df):
    if df is None or df.empty:
        return ["No data available."]

    insights = []
    
    peak_df = peak_hours_analysis(df)
    peak_hour = int(peak_df.iloc[0]['hour'])
    peak_count = int(peak_df.iloc[0]['sessions_count'])
    quiet_hour = int(peak_df.iloc[-1]['hour'])
    insights.append(f"Peak charging hour is {peak_hour:02d}:00 with {peak_count} sessions, while the quietest hour is {quiet_hour:02d}:00.")
    
    type_df = fast_vs_normal_comparison(df)
    fast_row = type_df[type_df['charger_type'] == 'fast'].iloc[0]
    normal_row = type_df[type_df['charger_type'] == 'normal'].iloc[0]
    insights.append(
        f"Average charge time for fast chargers: {fast_row['avg_duration_min']} min ({fast_row['avg_energy_kwh']} kWh), "
        f"for normal chargers: {normal_row['avg_duration_min']} min ({normal_row['avg_energy_kwh']} kWh)."
    )
    
    return insights


def chart_sessions_by_hour(df):
    hourly_counts = df.groupby('hour')['session_id'].count().reset_index()
    hourly_counts.columns = ['hour', 'sessions_count']
    
    fig = px.bar(hourly_counts, x='hour', y='sessions_count', title="Charging Sessions by Hour",
                 labels={'hour': 'Hour of Day', 'sessions_count': 'Sessions Count'})
    return fig

def chart_energy_by_station(df):
    station_energy = df.groupby('station_name')['energy_kwh'].sum().reset_index()
    
    fig = px.bar(station_energy, x='station_name', y='energy_kwh', title="Total Energy Dispensed by Station",
                 color='station_name', labels={'station_name': 'Station', 'energy_kwh': 'Energy (kWh)'})
    return fig

def chart_fast_vs_normal(df):
    comp_df = fast_vs_normal_comparison(df)
    
    fig = px.bar(comp_df, x='charger_type', y=['avg_duration_min', 'avg_energy_kwh'], barmode='group',
                 title="Fast vs Normal Chargers: Duration (min) & Energy (kWh)",
                 labels={'charger_type': 'Charger Type', 'value': 'Value'})
    return fig

def get_all_charts(df):
    return {
        "hourly": chart_sessions_by_hour(df),
        "energy": chart_energy_by_station(df),
        "type": chart_fast_vs_normal(df)
    }
#=====================================================================================

def generate_test_data(n, scenario="random", seed=42):
    random.seed(seed)
    if scenario == "random":
        return [random.randint(1, 10000) for _ in range(n)]
    
    elif scenario == "sorted":
        return list(range(1, n + 1))
    
    elif scenario == "reversed":
        return list(range(n, 0, -1))

    elif scenario == "nearly_sorted":
        arr = list(range(1, n + 1))
        for _ in range(max(1, n // 20)):
            i, j = random.randint(0, n - 1), random.randint(0, n - 1)
            arr[i], arr[j] = arr[j], arr[i]
        return arr
    
    elif scenario == "duplicates":
        return [random.choice([1, 2, 3]) for _ in range(n)]
    else:
        return []
    
def benchmark_algorithm(algorithm_name, data, runs=5, scenario="random"):
    times = []
    comparisons = 0
    calls = 0
    
    for r in range(runs):
        data_copy = data.copy()
        start_time = time.perf_counter()
        
        if algorithm_name == "merge_sort":
            res = merge_sort(data_copy)
        elif algorithm_name == "quick_sort":
            res = quick_sort(data_copy)
        else:
            res = None
        
        elapsed_time = (time.perf_counter() - start_time) * 1000
        times.append(elapsed_time)

        if r == 0 and isinstance(res, tuple) and len(res) == 2 and res[1] is not None:
            comparisons = getattr(res[1], "comparisons", 0)
            calls = getattr(res[1], "recursive_calls", getattr(res[1], "calls", 0))
    
    avg_time = round(sum(times) / runs, 2)
    return {
        "algorithm": algorithm_name,
        "n": len(data),
        "scenario": scenario,
        "avg_time_ms": avg_time,
        "comparisons": comparisons,
        "calls": calls
    }

def compare_sorting_algorithms(sizes=[100, 500, 1000, 5000], scenarios=None):
    if scenarios is None:
        scenarios = ["random", "sorted", "reversed", "nearly_sorted", "duplicates"]

    results = []
    
    for size in sizes:
        for scenario in scenarios:
            test_data = generate_test_data(size, scenario)
            
            merge_res = benchmark_algorithm("merge_sort", test_data, scenario=scenario)
            quick_res = benchmark_algorithm("quick_sort", test_data, scenario=scenario)
            
            results.append(merge_res)
            results.append(quick_res)
    
    return pd.DataFrame(results)
#=====================================================================================
def comparison_chart(result_df):
    fig = px.bar(result_df, x='n', y='avg_time_ms', color='algorithm', facet_col='scenario',
                 color_discrete_sequence=['blue', 'orange'],
                 barmode='group',
                 title="Sorting Algorithm Performance Comparison",
                 labels={'avg_time_ms': 'Time (ms)', 'n': 'Input Size'},
                 text_auto=True)
    
    fig.update_layout(legend_title_text='Algorithm')
    return fig

def comparison_summary(result_df):
    summary = result_df.groupby('algorithm')['avg_time_ms'].mean()
    merge_avg = round(summary.get('merge_sort', 0.0), 2)
    quick_avg = round(summary.get('quick_sort', 0.0), 2)
    faster = "Quick Sort" if quick_avg < merge_avg else "Merge Sort"
    return [
        f"{faster} was faster overall (Quick Sort avg: {quick_avg} ms vs Merge Sort avg: {merge_avg} ms).",
        "Merge Sort maintains steady O(n log n) performance across sorted and reversed inputs."
    ]
#=====================================================================================
def export_energy_report_csv(df, filepath=None):
    csv_string = df.to_csv(index=False, encoding='utf-8-sig')
    
    csv_bytes = csv_string.encode('utf-8-sig')
    
    if filepath:
        with open(filepath, 'wb') as f:
            f.write(csv_bytes)
        return filepath
    
    return csv_bytes
#====================================================================================

def export_energy_report_pdf(df, kpis, insights, filepath=None):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=14, style="B")
    
    pdf.cell(190, 10, text="ChargeSpot Energy Report", align='C', new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5) 
    
    pdf.set_font("Helvetica", style="B", size=12)
    pdf.cell(190, 8, text="Key Performance Indicators:", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=11)
    
    for key, value in kpis.items():
        text_line = f"  - {key}: {value}"
        pdf.cell(190, 7, text=text_line, new_x="LMARGIN", new_y="NEXT")
        
    pdf.ln(5)
    
    pdf.set_font("Helvetica", style="B", size=12)
    pdf.cell(190, 8, text="Data Insights:", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=11)
    
    for insight in insights:
        pdf.multi_cell(190, 7, text=str(insight))
        pdf.ln(3)
        
    if filepath:
        pdf.output(filepath)
        return filepath
        
    out = pdf.output()
    return bytes(out) if not isinstance(out, (bytes, bytearray)) else bytes(out)
#====================================================================================
def export_bookings_csv(bookings: list, filepath=None):
    rows = [b.to_dict() if hasattr(b, 'to_dict') else b for b in bookings] if bookings else []
    df = pd.DataFrame(rows) if rows else pd.DataFrame({"Message": ["No bookings available"]})
    
    csv_string = df.to_csv(index=False, encoding='utf-8-sig')
    
    csv_bytes = csv_string.encode('utf-8-sig')
    
    if filepath:
        with open(filepath, 'wb') as f:
            f.write(csv_bytes)
        return filepath
    
    return csv_bytes

def export_bookings_pdf(bookings: list, filepath=None):
    rows = [b.to_dict() if hasattr(b, 'to_dict') else b for b in bookings] if bookings else []
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=14, style="B")
    
    pdf.cell(190, 10, text="ChargeSpot Bookings Report", align='C', new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5) 
    
    if rows:
        keys = list(rows[0].keys())
        col_width = max(20, int(190 / len(keys)))
        pdf.set_font("Helvetica", size=8, style="B")
        for key in keys:
            pdf.cell(col_width, 8, text=str(key)[:12], border=1)
        pdf.ln()
        
        pdf.set_font("Helvetica", size=8)
        for booking in rows:
            for key in keys:
                pdf.cell(col_width, 7, text=str(booking[key])[:12], border=1)
            pdf.ln()
    else:
        pdf.set_font("Helvetica", size=11)
        pdf.cell(190, 10, text="No bookings available.", new_x="LMARGIN", new_y="NEXT")
    
    if filepath:
        pdf.output(filepath)
        return filepath
        
    out = pdf.output()
    return bytes(out) if not isinstance(out, (bytes, bytearray)) else bytes(out)
#====================================================================================
if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    
    raw_data = generate_egypt_charging_data(600)
    file_path = "data/charging_data.csv"
    raw_data.to_csv(file_path, index=False)
    print(f"✅ Successfully generated {len(raw_data)} records and saved to {file_path}")
    clean_df = clean_data(raw_data)
    
    kpis = compute_kpis(clean_df)
    insights = generate_insights(clean_df)
    
    export_energy_report_pdf(clean_df, kpis, insights, filepath="data/ChargeSpot_Report.pdf")
    print("✅ Successfully generated PDF report and saved to data/ChargeSpot_Report.pdf")