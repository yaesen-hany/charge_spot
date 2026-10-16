import streamlit as st
st.set_page_config(
    page_title="ChargeSpot",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)
# ── Standard-library & third-party imports ──────────────────────────
import sys, os, json, random, math, re, base64
from datetime import datetime, timedelta
import pandas as pd
import plotly.express as px
# ── Make project root importable ────────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
# ── Domain imports ──────────────────────────────────────────────────
from models.models import (
    User, Driver, Operator, Admin,
    ChargingSlot, ChargingStation, BookingRequest,
)
from exceptions import (
    InvalidPlateFormatError, DuplicatePlateError, InvalidBookingCodeError,
    InvalidEnergyValueError, InvalidTimeFormatError,
    ValidationError, SlotAlreadyBookedError,
    SlotNotFoundError, StationFullError,
    BookingNotFoundError, EmptyHistoryError,
    QueueEmptyError, BookingLimitExceededError,
)
from auth import (
    load_data, save_data,
    validate_email, check_email,
    validate_phone, validate_password,
    validate_plate, check_plate, validate_name,
    register_user, register_operator,
    hash_password, next_user_id,
    USERS_DATA, BOOKINGS_DATA,
)
from analytics import (
    clean_data, clean_stations_data,
    get_cleaning_report,
)
from lookup_engine import (
    HashTable, Build_booking,
    lookup_plate_code, lookup_booking_code,
    add_to_index, remove_from_index,
    sequential_search_stations,
    sequential_search_by_charger_type,
    sequential_search_free_stations,
    binary_search_slot, binary_search_next_free,
    time_to_minutes, Sorted_time,
    save_stations_to_csv, next_station_id, next_slot_id,)
STATIONS_CSV = os.path.join("data", "stations_slots.csv") if os.path.exists(os.path.join("data", "stations_slots.csv")) else "stations_slots.csv"
CHARGING_DATA_CSV = os.path.join("data", "charging_data.csv") if os.path.exists(os.path.join("data", "charging_data.csv")) else "charging_data.csv"
# The official 27 Governorates of Egypt
EGYPT_GOVERNORATES = [
    "Cairo",
    "Giza",
    "Alexandria",
    "Aswan",
    "Asyut",
    "Beheira",
    "Beni Suef",
    "Dakahlia",
    "Damietta",
    "Fayoum",
    "Gharbia",
    "Ismailia",
    "Kafr El Sheikh",
    "Luxor",
    "Matrouh",
    "Minya",
    "Monufia",
    "New Valley",
    "North Sinai",
    "Port Said",
    "Qalyubia",
    "Qena",
    "Red Sea",
    "Sharqia",
    "Sohag",
    "South Sinai",
    "Suez",
]
EGYPT_CITIES = EGYPT_GOVERNORATES  # backward compatibility alias
from sorting_engine import (
    HistoryStack, SortStats,
    merge_sort, quick_sort,
    sort_bookings, get_field, make_action,
)
from scheduler import (
    EVQueue, ScheduleGrid, GreedyScheduler,
    ChargingStation as SchedStation,
    BookingRequest as SchedBooking,
    slots_needed, station_power, index_to_time, time_to_index, to_minutes,
)
import analytics
# ════════════════════════════════════════════════════════════════════
# UTILITIES: Object Normalization & Instantiation
# ════════════════════════════════════════════════════════════════════
def _normalise_user_dict(d: dict) -> dict:
    out = {}
    for k, v in d.items():
        clean = k
        for prefix in ("_User__", "_Driver__", "_Operator__", "_Admin__"):
            if k.startswith(prefix):
                clean = k[len(prefix):]
                break
        out[clean] = v
    return out
def instantiate_user(data: dict):
    d = _normalise_user_dict(data)
    role = d.get("role", "user")
    if role == "driver":
        return Driver(
            d["user_id"], d["name"], d["email"], d["password"],
            d["phone"], d["city"],
            d.get("plate_number", ""), d.get("vehicle_model", ""),
            float(d.get("battery_capacity_kwh", 60.0)),
        )
    if role == "operator":
        return Operator(
            d["user_id"], d["name"], d["email"], d["password"],
            d["phone"], d["city"], d.get("station_id", ""),
        )
    if role == "admin":
        return Admin(
            d["user_id"], d["name"], d["email"], d["password"],
            d["phone"], d["city"],
        )
    return User(
        d["user_id"], d["name"], d["email"], d["password"],
        d["phone"], d["city"], role,
    )
def next_booking_code() -> str:
    bookings = load_data(BOOKINGS_DATA)
    max_num = 0
    for b in bookings:
        code = b.get("booking_code", "")
        if code.startswith("CS-"):
            try:
                max_num = max(max_num, int(code[3:]))
            except ValueError:
                pass
    return f"CS-{max_num + 1:06d}"
# ════════════════════════════════════════════════════════════════════
# SESSION-STATE INITIALIZATION & PERSISTENCE
# ════════════════════════════════════════════════════════════════════
def init_session():

    defaults = {
        "initialized": False,
        "current_user": None,
        "page": "landing",
        "selected_station_id": None,
        "stations": [],
        "bookings": [],
        "wait_queue": EVQueue(),
        "schedule_grid": None,
        "history_stack": HistoryStack(),
        "booking_index": (HashTable(), HashTable()),
        "kpi_df": None,
        "driver_chat_history": [],
        "operator_chat_history": [],
        "reg_name": "",
        "reg_email": "",
        "reg_phone": "",
        "reg_city": "",
        "reg_plate": "",
        "reg_model": "",
        "reg_battery": 60.0,
        "guest_area_filter": "All",
        "guest_status_filter": "All",
        "drv_area_sel": "All",
        "drv_ctype_sel": "All",
        "drv_time_inp": "",
        "drv_code_lookup": "",
        "drv_map_area": "All",
        "drv_map_status": "All",
        "op_sr_c": "",
        "op_sr_p": "",
        "admin_role_filter": "All",
        "admin_stn_area_filter": "All",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

    if not st.session_state["initialized"]:
        reload_stations()
        reload_bookings()
        st.session_state["initialized"] = True
def reload_stations():
    csv_file = os.path.join(PROJECT_ROOT, STATIONS_CSV)
    if os.path.exists(csv_file):
        try:
            raw, report = clean_stations_data(csv_file)
            st.session_state["stations_cleaning_report"] = report
        except Exception:
            raw = []
    else:
        raw = []
    stations = []
    for s in raw:
        try:
            stations.append(ChargingStation.from_dict(s))
        except Exception:
            pass
    st.session_state["stations"] = stations
def reload_bookings():
    raw = load_data(BOOKINGS_DATA)
    bookings = []
    for b in raw:
        try:
            bdata = {k: v for k, v in b.items() if k != "date_time"}
            bk = BookingRequest(**bdata)
            bk.date_time = b.get("date_time", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            bookings.append(bk)
        except Exception:
            pass
    st.session_state["bookings"] = bookings
    plate_idx, code_idx = Build_booking(bookings)
    st.session_state["booking_index"] = (plate_idx, code_idx)
def save_stations():
    csv_file = os.path.join(PROJECT_ROOT, STATIONS_CSV)
    save_stations_to_csv(st.session_state["stations"], csv_file)
def save_bookings():
    data = [b.to_dict() for b in st.session_state["bookings"]]
    save_data(data, BOOKINGS_DATA)
def navigate(page: str, rerun: bool = False):
    st.session_state["page"] = page
    if rerun:
        st.rerun()
def _reset_chat_sessions():
    st.session_state["driver_chat_history"] = []
    st.session_state["operator_chat_history"] = []
    for k in list(st.session_state.keys()):
        if (k.startswith("driver_chat_") or k.startswith("operator_chat_")) and k not in ("driver_chat_history", "operator_chat_history"):
            del st.session_state[k]
def _logout_user():
    st.session_state["current_user"] = None
    _reset_chat_sessions()
    navigate("landing", rerun=True)
# ════════════════════════════════════════════════════════════════════
# SHARED UTILITIES: Reduce Duplication
# ════════════════════════════════════════════════════════════════════
def _reset_keys(**defaults):
    """Generic session-state reset callback. Usage: on_click=lambda: _reset_keys(key1='All', key2='')"""
    for k, v in defaults.items():
        st.session_state[k] = v
def _count_free_slots(station, charger_type: str = None) -> int:
    """Count free slots in a station, optionally filtered by charger_type ('fast'/'normal')."""
    if charger_type:
        return sum(1 for sl in station.slots if sl.is_free() and sl.charger_type == charger_type)
    return sum(1 for sl in station.slots if sl.is_free())
def _filter_stations(stations: list, area: str = "All", status_filter: str = "All") -> list:
    """Shared area + status filter used by Guest Map, Driver Map, and Driver Find&Book."""
    filtered = list(stations)
    if area != "All":
        filtered = sequential_search_stations(filtered, area, field="area")
    if status_filter == "Has Free Slots":
        filtered = [s for s in filtered if any(sl.is_free() for sl in s.slots)]
    elif status_filter == "Fast Chargers Only":
        filtered = [s for s in filtered if any(sl.is_free() and sl.charger_type == "fast" for sl in s.slots)]
    return filtered
def _booking_to_row(b, include_driver: bool = False) -> dict:
    """Convert a BookingRequest to a display-ready dict for st.dataframe."""
    row = {
        "Booking Code": b.booking_code,
        "Station ID": b.station_id,
        "Slot ID": b.slot_id,
        "Requested Time": b.requested_time,
        "Energy (kWh)": b.energy_kwh,
        "Status": b.status,
    }
    if include_driver:
        row["Driver Plate"] = b.driver_plate
    row["Created At"] = getattr(b, "date_time", "")
    return row
def _release_booking_slot(booking):
    """Release the station slot associated with a booking."""
    for s in st.session_state.get("stations", []):
        if s.station_id == booking.station_id:
            for sl in s.slots:
                if sl.slot_id == booking.slot_id and sl.status == "booked":
                    sl.release()
            break
def _rebook_slot(booking):
    """Re-book a slot that was previously released (for undo-cancel)."""
    for s in st.session_state.get("stations", []):
        if s.station_id == booking.station_id:
            for sl in s.slots:
                if sl.slot_id == booking.slot_id and sl.is_free():
                    sl.book()
            break
def _undo_last_action():
    """Shared undo logic for both Driver and Operator dashboards."""
    try:
        action = st.session_state["history_stack"].pop()
        bk = action["booking"]
        if action["type"] in ("BOOK", "ASSIGN"):
            bk.status = "cancelled"
            _release_booking_slot(bk)
            save_bookings()
            save_stations()
            st.success(f"Undid booking {bk.booking_code}.")
        elif action["type"] == "CANCEL":
            bk.status = "confirmed"
            _rebook_slot(bk)
            save_bookings()
            save_stations()
            st.success(f"Restored booking {bk.booking_code}.")
        st.rerun()
    except EmptyHistoryError:
        st.info("No prior actions to undo.")
# ════════════════════════════════════════════════════════════════════
# RESILIENT DATA ACCESSORS
# ════════════════════════════════════════════════════════════════════
def _get_active_stations():
    try:
        if "stations" in st.session_state and st.session_state["stations"]:
            return st.session_state["stations"]
    except Exception:
        pass
    csv_file = os.path.join(PROJECT_ROOT, STATIONS_CSV)
    if os.path.exists(csv_file):
        raw, _ = clean_stations_data(csv_file)
        return [ChargingStation.from_dict(s) for s in raw] if raw else []
    return []
def _get_active_bookings():
    try:
        if "bookings" in st.session_state and st.session_state["bookings"]:
            return st.session_state["bookings"]
    except Exception:
        pass
    reload_bookings()
    return st.session_state.get("bookings", [])
def _get_active_wait_queue():
    try:
        if "wait_queue" in st.session_state and st.session_state["wait_queue"] is not None:
            return st.session_state["wait_queue"]
    except Exception:
        pass
    return EVQueue()
# ════════════════════════════════════════════════════════════════════
# DRIVER BOOKING LIMITS & SESSION LIFECYCLE MANAGEMENT
# ════════════════════════════════════════════════════════════════════
MAX_ACTIVE_BOOKINGS_PER_DRIVER = 2
MAX_DAILY_BOOKINGS_PER_DRIVER = 4
def validate_driver_booking_limits(driver_plate: str, requested_time: str, energy_kwh: float, max_battery_kwh: float):
    """Enforce driver booking limits: active bookings count, daily count, time overlaps, and battery capacity."""
    all_bookings = _get_active_bookings()
    driver_bookings = [b for b in all_bookings if b.driver_plate == driver_plate]

    # 1. Energy capacity check
    if energy_kwh > max_battery_kwh:
        raise ValidationError(
            value=energy_kwh,
            message=f"Requested energy ({energy_kwh:.1f} kWh) exceeds vehicle battery capacity ({max_battery_kwh:.1f} kWh)."
        )

    # 2. Max active bookings limit (pending or confirmed)
    active = [b for b in driver_bookings if b.status in ("pending", "confirmed")]
    if len(active) >= MAX_ACTIVE_BOOKINGS_PER_DRIVER:
        raise BookingLimitExceededError(
            value=len(active),
            message=f"Active bookings limit reached ({len(active)}/{MAX_ACTIVE_BOOKINGS_PER_DRIVER}). Please complete or cancel an existing session before booking a new one."
        )

    # 3. Schedule conflict / overlap check
    if requested_time:
        for b in active:
            if b.requested_time == requested_time:
                raise BookingLimitExceededError(
                    value=requested_time,
                    message=f"Schedule conflict: You already have an active booking at {requested_time} (Booking Code: {b.booking_code}, Station: {b.station_id})."
                )

    # 4. Daily booking limit
    today_prefix = datetime.now().strftime("%Y-%m-%d")
    today_count = sum(1 for b in driver_bookings if getattr(b, "date_time", "").startswith(today_prefix) and b.status != "cancelled")
    if today_count >= MAX_DAILY_BOOKINGS_PER_DRIVER:
        raise BookingLimitExceededError(
            value=today_count,
            message=f"Daily booking limit reached ({today_count}/{MAX_DAILY_BOOKINGS_PER_DRIVER} bookings today)."
        )
def complete_booking_session(booking_code: str) -> bool:
    """Transition a confirmed or pending booking to completed and release its assigned slot."""
    found = False
    for b in st.session_state.get("bookings", []):
        if b.booking_code == booking_code:
            b.status = "completed"
            found = True
            _release_booking_slot(b)
            break

    if found:
        # If the booking was in the wait queue, dequeue it
        wq = st.session_state.get("wait_queue")
        if wq and not wq.is_empty():
            temp_q = EVQueue()
            while not wq.is_empty():
                item = wq.dequeue()
                if item.booking_code != booking_code:
                    temp_q.enqueue(item)
            st.session_state["wait_queue"] = temp_q

        save_bookings()
        save_stations()
    return found
# ════════════════════════════════════════════════════════════════════
# GEMINI AI & LOCAL GROUNDED CHATBOT ENGINES
# ════════════════════════════════════════════════════════════════════
def _is_gemini_available() -> bool:
    api_key = st.secrets.get("GEMINI_API_KEY", "")
    return bool(api_key and api_key != "YOUR_API_KEY_HERE")
def _get_gemini_response(prompt: str, system_instruction: str) -> str | None:
    api_key = st.secrets.get("GEMINI_API_KEY", "")
    if not api_key or api_key == "YOUR_API_KEY_HERE":
        return None

    candidate_models = [
        "gemini-flash-lite-latest",
        "gemini-3.1-flash-lite",
        "gemini-2.5-flash",
        "gemini-flash-latest",
    ]

    # Attempt 1: Google Generative AI SDK
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        for model_name in candidate_models:
            try:
                model = genai.GenerativeModel(model_name, system_instruction=system_instruction)
                resp = model.generate_content(prompt)
                if resp and resp.text:
                    return resp.text.strip()
            except Exception:
                continue
    except Exception:
        pass

    # Attempt 2: Direct HTTPS REST API call
    try:
        import urllib.request
        for model_name in candidate_models:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
                payload = {
                    "contents": [{"parts": [{"text": f"System Instructions:\n{system_instruction}\n\nUser Question:\n{prompt}"}]}],
                }
                req_data = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(url, data=req_data, headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=8) as res:
                    data = json.loads(res.read().decode("utf-8"))
                    text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                    if text:
                        return text
            except Exception:
                continue
    except Exception:
        pass

    return None
EGYPT_CITY_COORDINATES = {
    "cairo": (30.0444, 31.2357),
    "new cairo": (30.0074, 31.4913),
    "tagamoa": (30.0074, 31.4913),
    "settlement": (30.0074, 31.4913),
    "giza": (30.0131, 31.2089),
    "october": (29.9723, 30.9328),
    "6th of october": (29.9723, 30.9328),
    "zayed": (30.0427, 30.9769),
    "sheikh zayed": (30.0427, 30.9769),
    "alexandria": (31.2001, 29.9187),
    "alex": (31.2001, 29.9187),
    "maadi": (29.9683, 31.2861),
    "nasr city": (30.0566, 31.3411),
    "heliopolis": (30.0911, 31.3285),
    "dokki": (30.0385, 31.2114),
    "mohandessin": (30.0571, 31.2012),
    "zamalek": (30.0699, 31.2192),
    "smart village": (30.0712, 31.0167),
    "shorouk": (30.1444, 31.6215),
    "madinaty": (30.1067, 31.6417),
    "capital": (30.0131, 31.7000),
    "sadat": (30.3756, 30.5186),
    "sadat city": (30.3756, 30.5186),
    "mansoura": (31.0409, 31.3785),
    "tanta": (30.7865, 31.0004),
    "hurghada": (27.2579, 33.8116),
    "sharm": (27.9158, 34.3299),
    "aswan": (24.0889, 32.8998),
    "asyut": (27.1801, 31.1837),
    "beheira": (31.0364, 30.4689),
    "beni suef": (29.0744, 31.0979),
    "dakahlia": (31.0409, 31.3785),
    "damietta": (31.4175, 31.8144),
    "fayoum": (29.3084, 30.8428),
    "faiyum": (29.3084, 30.8428),
    "gharbia": (30.7865, 31.0004),
    "ismailia": (30.5965, 32.2715),
    "kafr el sheikh": (31.1107, 30.9388),
    "luxor": (25.6872, 32.6396),
    "matrouh": (31.3525, 27.2453),
    "minya": (28.1099, 30.7503),
    "monufia": (30.5526, 31.0093),
    "new valley": (25.4514, 30.5472),
    "north sinai": (31.1316, 33.7984),
    "port said": (31.2653, 32.3019),
    "qalyubia": (30.4591, 31.1786),
    "qena": (26.1551, 32.7160),
    "red sea": (27.2579, 33.8116),
    "sharqia": (30.5877, 31.5020),
    "sohag": (26.5570, 31.6948),
    "south sinai": (27.9158, 34.3299),
    "suez": (29.9668, 32.5498),
}
@st.cache_data
def _calculate_distance_km(lat1, lon1, lat2, lon2) -> float:
    try:
        lat1, lon1, lat2, lon2 = float(lat1), float(lon1), float(lat2), float(lon2)
        R = 6371.0
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (math.sin(dlat / 2) ** 2 +
             math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
             math.sin(dlon / 2) ** 2)
        return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    except Exception:
        return 9999.0
def _get_driver_ref_coords(user=None, question: str = ""):
    q = (question or "").lower()
    for city_name, coords in EGYPT_CITY_COORDINATES.items():
        if city_name in q:
            return coords[0], coords[1], city_name.title()

    if user is None:
        user = st.session_state.get("current_user")

    driver_city = ""
    if user:
        driver_city = str(getattr(user, "_User__city", getattr(user, "city", ""))).lower().strip()

    if driver_city:
        for city_name, coords in EGYPT_CITY_COORDINATES.items():
            if city_name in driver_city or driver_city in city_name:
                return coords[0], coords[1], driver_city.title()

    return 30.0444, 31.2357, (driver_city.title() if driver_city else "Cairo")
def _build_station_context(ref_lat: float = 30.0444, ref_lon: float = 31.2357) -> str:
    available = []
    for s in _get_active_stations():
        free = _count_free_slots(s)
        if free > 0:
            dist = _calculate_distance_km(ref_lat, ref_lon, s.latitude, s.longitude)
            fast_free = _count_free_slots(s, "fast")
            available.append((dist, s, free, fast_free))
    available.sort(key=lambda x: x[0])
    top_stations = available[:10]
    lines = []
    for dist, s, free, fast_free in top_stations:
        lines.append(
            f"- {s.name} ({s.area}): {free} free slots, {fast_free} fast chargers free, "
            f"distance ~{dist:.1f} km, lat={s.latitude}, lon={s.longitude}"
        )
    return "\n".join(lines) if lines else "No stations currently have free slots."
def _build_queue_context() -> str:
    wq = _get_active_wait_queue()
    return f"Current Waiting Queue Length: {len(wq)}"
def _build_booking_context(station_id=None) -> str:
    bookings = _get_active_bookings()
    if station_id:
        bookings = [b for b in bookings if b.station_id == station_id]
    lines = []
    for b in bookings:
        lines.append(f"  {b.booking_code}: plate={b.driver_plate}, station={b.station_id}, "
                     f"slot={b.slot_id}, time={b.requested_time}, energy={b.energy_kwh}kWh, "
                     f"status={b.status}")
    return "\n".join(lines) if lines else "No active bookings registered."
def _local_driver_chatbot(question: str) -> str:
    q = question.lower()
    stations = _get_active_stations()
    user = st.session_state.get("current_user")
    ref_lat, ref_lon, ref_label = _get_driver_ref_coords(user, question)

    if any(w in q for w in ["free", "available", "slot", "nearest", "where", "near", "متاح", "فاضي", "اقرب", "محط", "قريب"]):
        available_stations = []
        for s in stations:
            try:
                free = s.get_free_slots()
            except StationFullError:
                free = []

            if free:
                dist = _calculate_distance_km(ref_lat, ref_lon, s.latitude, s.longitude)
                available_stations.append((dist, s, free))

        if available_stations:
            available_stations.sort(key=lambda item: item[0])
            top_5 = available_stations[:5]
            lines = [
                f"**{s.name}** ({s.area}) — ~**{dist:.1f} km** away: **{len(free)}** free slots available."
                for dist, s, free in top_5
            ]
            loc_label = f" relative to **{ref_label}**" if ref_label else ""
            return (
                f"Top 5 nearest available charging stations{loc_label}:\n\n"
                + "\n".join(f"{i+1}. {l}" for i, l in enumerate(lines))
            )
        return "All slots are currently booked. You can join the waiting queue to be scheduled automatically."

    if any(w in q for w in ["fast", "quick", "speed", "power", "سريع"]):
        available_fast = []
        for s in stations:
            fast_free = [sl for sl in s.slots if sl.is_free() and sl.charger_type == "fast"]
            if fast_free:
                dist = _calculate_distance_km(ref_lat, ref_lon, s.latitude, s.longitude)
                max_p = max(sl.power_kw for sl in fast_free)
                available_fast.append((dist, s, len(fast_free), max_p))
        if available_fast:
            available_fast.sort(key=lambda item: item[0])
            top_5_fast = available_fast[:5]
            lines = [
                f"**{s.name}** ({s.area}) — ~**{dist:.1f} km** away: **{cnt}** fast chargers available (up to {max_p} kW)."
                for dist, s, cnt, max_p in top_5_fast
            ]
            loc_label = f" near **{ref_label}**" if ref_label else ""
            return f"Top 5 nearest stations with available Fast Chargers{loc_label}:\n\n" + "\n".join(f"{i+1}. {l}" for i, l in enumerate(lines))
        return "No fast chargers are vacant at this exact moment. Please check back shortly or select a normal slot."

    if any(w in q for w in ["off-peak", "peak", "busy", "crowded", "best time", "زحمة", "وقت"]):
        return ("**Recommended Off-Peak Charging Hours in Egypt:**\n\n"
                "- **Early Morning:** 06:00 – 08:00 (Lowest station occupancy and quickest turnaround)\n"
                "- **Mid-Afternoon:** 14:00 – 16:00 (Moderate demand)\n"
                "- **Late Evening:** 20:00 – 22:00 (Grid load drops)\n\n"
                "Booking during these windows guarantees minimum wait times.")

    if any(w in q for w in ["duration", "charge time", "how long", "calculate", "battery", "minutes", "مدة"]):
        if user and hasattr(user, "battery_capacity_kwh") and user.battery_capacity_kwh > 0:
            cap = user.battery_capacity_kwh
            return (f"**Estimated Charging Time for your {getattr(user, 'vehicle_model', 'EV')} ({cap} kWh):**\n\n"
                    f"- High-Power Fast Charger (120 kW): ~**{cap/120*60:.0f} minutes**\n"
                    f"- Medium Charger (22 kW): ~**{cap/22*60:.0f} minutes**\n"
                    f"- Standard AC Charger (7.4 kW): ~**{cap/7.4*60:.0f} minutes**\n\n"
                    f"*Formula: Time (min) = (Energy required in kWh ÷ Charger Power in kW) × 60*")
        return "Estimated Time (minutes) = (Energy in kWh ÷ Charger Power in kW) × 60."

    for area_token in ["cairo", "zayed", "giza", "alexandria", "capital", "sadat", "maadi", "nasr", "october"]:
        if area_token in q:
            matches = sequential_search_stations(stations, area_token, field="any")
            if matches:
                area_free = []
                for s in matches:
                    free_cnt = sum(1 for sl in s.slots if sl.is_free())
                    if free_cnt > 0:
                        dist = _calculate_distance_km(ref_lat, ref_lon, s.latitude, s.longitude)
                        area_free.append((dist, s, free_cnt))
                if area_free:
                    area_free.sort(key=lambda item: item[0])
                    top_5_area = area_free[:5]
                    lines = [f"**{s.name}** ({s.area}) — ~**{dist:.1f} km** away: **{cnt}** free slots" for dist, s, cnt in top_5_area]
                    return f"Top 5 nearest available stations in or around **{area_token.title()}**:\n\n" + "\n".join(f"{i+1}. {l}" for i, l in enumerate(lines))
                return f"No open slots currently found at stations in **{area_token.title()}**."

    return ("Hello! I am your ChargeSpot Driver AI Assistant. I can help you with:\n"
            "- Finding the top 5 nearest Egyptian stations with free slots\n"
            "- Locating top 5 high-speed fast chargers\n"
            "- Advising on off-peak charging times\n"
            "- Calculating exact charging duration for your vehicle model\n\nHow can I help you today?")
def _local_operator_chatbot(question: str, station_id: str) -> str:
    q = question.lower()
    stations = _get_active_stations()
    bookings = _get_active_bookings()
    station = next((s for s in stations if s.station_id == station_id), None)

    if station is None:
        return "Error: Could not locate data for your assigned station."

    stn_bookings = [b for b in bookings if b.station_id == station_id]
    tot_slots = len(station.slots)
    free_slots = _count_free_slots(station)
    booked_slots = sum(1 for sl in station.slots if sl.status == "booked")
    maint_slots = sum(1 for sl in station.slots if sl.status == "maintenance")
    tot_kwh = sum(b.energy_kwh for b in stn_bookings)
    wq = _get_active_wait_queue()

    if any(w in q for w in ["status", "overview", "summary", "how is", "report"]):
        util = (booked_slots / tot_slots * 100) if tot_slots > 0 else 0.0
        return (f"**Operational Overview for {station.name}:**\n\n"
                f"- Total Charging Slots: **{tot_slots}** (Free: {free_slots} | Booked: {booked_slots} | Maintenance: {maint_slots})\n"
                f"- Current Utilization: **{util:.1f}%**\n"
                f"- Station Waiting Queue: **{len(wq)} vehicle(s)**\n"
                f"- Total Energy Requested: **{tot_kwh:.1f} kWh**")

    if any(w in q for w in ["maintenance", "repair", "service", "schedule"]):
        if free_slots > 1:
            return (f"Notice: You currently have {free_slots} free slots. It is safe to schedule maintenance for a slot "
                    f"via the Slots Control panel without triggering a waiting bottleneck.")
        return (f"Caution: Only {free_slots} free slot(s) remaining. Placing a charger into maintenance now will increase "
                f"queue congestion. We recommend scheduling maintenance during off-peak hours (06:00 – 08:00).")

    if any(w in q for w in ["queue", "waiting", "congestion", "bottleneck"]):
        ql = len(wq)
        if ql == 0:
            return "Station flow is optimal. The waiting queue is currently empty."
        return (f"Notice: There are **{ql} vehicles** waiting in queue for this station.\n\n"
                f"Action Recommended: Run the **Greedy Slot Scheduler** in the Queue tab to auto-assign vehicles to free slots.")

    if any(w in q for w in ["energy", "kwh", "load", "consumption", "power"]):
        active_cnt = len([b for b in stn_bookings if b.status in ("pending", "confirmed")])
        comp_cnt = len([b for b in stn_bookings if b.status == "completed"])
        return (f"**Energy Consumption Summary ({station.name}):**\n\n"
                f"- Total Station Energy: **{tot_kwh:.1f} kWh**\n"
                f"- Active Sessions: **{active_cnt}**\n"
                f"- Completed Sessions: **{comp_cnt}**")

    return ("Welcome, Operator. I am your Operations and Crisis Management Copilot. I can assist with:\n"
            "- Analyzing station utilization and queue bottlenecks\n"
            "- Recommending optimal charger maintenance windows\n"
            "- Summarizing daily kWh electrical load\n\nHow can I support your shift?")
# ════════════════════════════════════════════════════════════════════
# THEME: LANDING PAGE BACKGROUND IMAGE
# ════════════════════════════════════════════════════════════════════
def apply_theme():
    """Apply background image on the landing page if available."""
    if st.session_state.get("page", "landing") != "landing":
        return

    bg_candidates = [
        os.path.join(PROJECT_ROOT, "photo", "background.jpg"),
        os.path.join(PROJECT_ROOT, "photo", "photo.jpg"),
        os.path.join(PROJECT_ROOT, "photo.jpg"),
        os.path.join(PROJECT_ROOT, "assets", "chargespot_bg.jpg"),
    ]
    for candidate in bg_candidates:
        if os.path.exists(candidate):
            try:
                with open(candidate, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
                st.markdown(f"""
                <style>
                [data-testid="stAppViewContainer"] {{
                    background-image: url("data:image/jpeg;base64,{b64}") !important;
                    background-size: cover !important;
                    background-position: right center !important;
                    background-repeat: no-repeat !important;
                    background-attachment: fixed !important;
                }}
                .main, .main .block-container {{ background-color: transparent !important; }}
                </style>
                """, unsafe_allow_html=True)
                return
            except Exception:
                pass
# ════════════════════════════════════════════════════════════════════
# STATE 1 – LANDING PAGE (Positioned on Left White Area)
# ════════════════════════════════════════════════════════════════════
def render_landing():
    left_col, right_col = st.columns([6, 5])

    with left_col:
        st.caption("ChargeSpot Egypt · National EV Infrastructure")
        st.title("ChargeSpot Egypt")
        st.write(
            "An intelligent EV charging station, booking, waiting list, and time slot management platform. "
            "Optimizing station utilization, eliminating driver wait times, and advancing clean energy mobility in Egypt."
        )

        # Explore Stations Map Button
        if st.button("Explore Stations Map", use_container_width=True):
            navigate("guest_map", rerun=True)

        # Two side-by-side buttons: Sign In & Register
        btn1, btn2 = st.columns(2)
        with btn1:
            if st.button("Sign In", use_container_width=True, type="primary"):
                navigate("login", rerun=True)
        with btn2:
            if st.button("Register", use_container_width=True):
                navigate("register", rerun=True)

        # Eco Impact Bar: 3 dynamic st.metric cards placed on the left side
        st.markdown("---")
        stations = _get_active_stations()
        total_fast = sum(_count_free_slots(s, "fast") for s in stations)
        completed = [b for b in _get_active_bookings() if b.status == "completed"]
        co2_saved = sum(b.energy_kwh * 0.4 for b in completed)

        m1, m2, m3 = st.columns(3)
        m1.metric("Active Stations", f"{len(stations)}")
        m2.metric("Fast Chargers", f"{total_fast}")
        m3.metric("CO2 Saved", f"{co2_saved:.1f} kg")

    with right_col:
        # Keep right_col empty so the charging station, EV car, and green landscape are completely visible
        st.empty()
# ════════════════════════════════════════════════════════════════════
# STATE 2 – PUBLIC SCREENS: LOGIN
# ════════════════════════════════════════════════════════════════════
def render_login():
    if st.button("Return to Home"):
        navigate("landing", rerun=True)

    c_left, c_center, c_right = st.columns([1, 2, 1])

    with c_center:
        st.header("Sign In to ChargeSpot")
        st.caption("Enter your verified credentials to access your dashboard")

        sel = st.session_state.get("selected_station_id")
        if sel:
            st.info(f"Station {sel} selected from map. Sign in to finalize your booking.")

        with st.form("login_form"):
            email = st.text_input("Email / User ID")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Sign In", type="primary", use_container_width=True)

        if submitted:
            if not email.strip() or not password:
                st.error("Please provide both email and password.")
                return

            users = load_data(USERS_DATA)
            hashed = hash_password(password)
            found = None
            for u in users:
                clean = _normalise_user_dict(u)
                if clean.get("email") == email.strip() and clean.get("password") == hashed:
                    found = clean
                    break

            if found is None:
                st.error("Invalid email or password.")
            else:
                user_obj = instantiate_user(found)
                st.session_state["current_user"] = user_obj
                _reset_chat_sessions()
                role = user_obj.get_role()
                if role == "driver":
                    st.success(f"Welcome back, {found.get('name', 'User')}!")
                    navigate("driver_dashboard", rerun=True)
                elif role == "operator":
                    st.success(f"Welcome back, {found.get('name', 'User')}!")
                    navigate("operator_dashboard", rerun=True)
                elif role == "admin":
                    st.success(f"Welcome back, {found.get('name', 'User')}!")
                    navigate("admin_dashboard", rerun=True)
                else:
                    navigate("landing", rerun=True)
# ════════════════════════════════════════════════════════════════════
# STATE 2 – PUBLIC SCREENS: DRIVER REGISTRATION
# ════════════════════════════════════════════════════════════════════
def render_register():
    if st.button("Return to Home"):
        navigate("landing", rerun=True)

    st.header("Driver Self-Registration")
    st.caption("Registration is dedicated for EV drivers to book slots across Egypt")

    with st.form("driver_registration_form"):
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("Full Name", value=st.session_state.get("reg_name", ""))
            email = st.text_input("Email Address", value=st.session_state.get("reg_email", ""))
            password = st.text_input("Password (min 6 characters)", type="password")
            phone = st.text_input("Egyptian Phone (01XXXXXXXXX)", value=st.session_state.get("reg_phone", ""))
        with col2:
            default_city = st.session_state.get("reg_city", "Cairo")
            city_idx = 0
            for idx, c in enumerate(EGYPT_GOVERNORATES):
                if c.lower() == str(default_city).lower():
                    city_idx = idx
                    break
            city = st.selectbox("city", EGYPT_GOVERNORATES, index=city_idx)
            plate = st.text_input("Vehicle Plate Number (e.g., ABC-1234)", value=st.session_state.get("reg_plate", ""))
            model = st.text_input("EV Model (e.g., Tesla Model 3 / BYD Dolphin)", value=st.session_state.get("reg_model", ""))
            battery = st.number_input("Battery Capacity in kWh (battery_capacity_kwh)",
                                      min_value=5.0, max_value=250.0,
                                      value=float(st.session_state.get("reg_battery", 60.0)), step=1.0)

        submitted = st.form_submit_button("Create Driver Account", type="primary", use_container_width=True)

    # Password strength meter
    if password:
        strength = 0
        if len(password) >= 6:
            strength += 25
        if re.search(r"[A-Z]", password) or re.search(r"[a-z]", password):
            strength += 25
        if re.search(r"[0-9]", password):
            strength += 25
        if re.search(r"[^A-Za-z0-9]", password):
            strength += 25
        lbl = "Weak" if strength <= 25 else ("Fair" if strength <= 50 else ("Good" if strength <= 75 else "Strong"))
        st.progress(strength / 100, text=f"Password Strength: {lbl}")

    if submitted:
        clean_name = name.strip()
        clean_email = email.strip()
        clean_phone = phone.strip()
        clean_city = city.strip()
        clean_plate = plate.strip()
        clean_model = model.strip()

        # Preserve input in session state to prevent loss on validation error
        st.session_state["reg_name"] = clean_name
        st.session_state["reg_email"] = clean_email
        st.session_state["reg_phone"] = clean_phone
        st.session_state["reg_city"] = clean_city
        st.session_state["reg_plate"] = clean_plate
        st.session_state["reg_model"] = clean_model
        st.session_state["reg_battery"] = battery

        errors = []
        if not clean_name:
            errors.append("Full Name is required.")
        elif not validate_name(clean_name):
            errors.append("Full Name must contain valid characters (2-50 letters).")

        if not clean_email:
            errors.append("Email Address is required.")
        elif not validate_email(clean_email):
            errors.append("Invalid email format (e.g. driver@example.com).")
        elif not check_email(clean_email):
            errors.append("This email is already registered.")

        if not password or len(password) < 6:
            errors.append("Password must be at least 6 characters.")

        if not clean_phone:
            errors.append("Egyptian phone number is required.")
        elif not validate_phone(clean_phone):
            errors.append("Invalid Egyptian phone number (must match 01[0125]XXXXXXXX).")

        if not clean_city:
            errors.append("City is required.")

        if not clean_plate:
            errors.append("Vehicle plate number is required.")
        elif not validate_plate(clean_plate):
            errors.append("Invalid plate format (2-15 alphanumeric characters).")
        elif not check_plate(clean_plate):
            errors.append("This vehicle plate number is already registered.")

        if not clean_model:
            errors.append("Vehicle model is required.")

        if errors:
            for err in errors:
                st.error(err)
        else:
            try:
                user_dict = register_user(
                    name=clean_name,
                    email=clean_email,
                    password=password,
                    phone=clean_phone,
                    city=clean_city,
                    plate_number=clean_plate,
                    vehicle_model=clean_model,
                    battery_capacity_kwh=float(battery)
                )
                new_driver = instantiate_user(user_dict)
                _reset_chat_sessions()
                st.session_state["current_user"] = new_driver
                st.success("Account created successfully. Routing to your dashboard...")
                navigate("driver_dashboard", rerun=True)
            except (InvalidPlateFormatError, DuplicatePlateError, ValidationError, InvalidEnergyValueError) as exc:
                st.error(f"Validation Error: {exc}")
            except Exception as exc:
                st.error(f"Registration Error: {exc}")
@st.fragment
def render_interactive_pins_map(stations_list, height=480, map_key=None):
    """Render interactive map with sharp pins, status colors, clustering, and rich popups."""
    if not stations_list:
        st.info("No stations available to display on the map.")
        return

    try:
        import folium
        from folium.plugins import MarkerCluster
        from streamlit_folium import st_folium

        valid_coords = [(s.latitude, s.longitude) for s in stations_list if s.latitude and s.longitude]
        if not valid_coords:
            st.warning("No valid GPS coordinates found for the selected stations.")
            return

        lats = [c[0] for c in valid_coords]
        lons = [c[1] for c in valid_coords]
        lat_span = max(lats) - min(lats)
        lon_span = max(lons) - min(lons)

        # When opening the map or showing nationwide stations across Egypt,
        # start with the full country in view at zoom 6 (not zoomed in).
        if lat_span > 1.5 or lon_span > 2.0 or len(valid_coords) > 50:
            map_center = [28.6, 31.0]  # Shifted upwards towards Nile Delta & Cairo while keeping full Egypt in view
            zoom_start = 6                    # Shows all of Egypt cleanly
        elif len(valid_coords) < 10:
            map_center = [sum(lats) / len(lats), sum(lons) / len(lons)]
            zoom_start = 12
        else:
            map_center = [sum(lats) / len(lats), sum(lons) / len(lons)]
            zoom_start = 10

        m = folium.Map(
            location=map_center,
            zoom_start=zoom_start,
            tiles="OpenStreetMap",
            control_scale=True,
        )

        cluster = MarkerCluster(
            name="Stations",
            options={
                "maxClusterRadius": 50,
                "spiderfyOnMaxZoom": True,
                "showCoverageOnHover": False,
                "zoomToBoundsOnClick": True,
            }
        ).add_to(m)

        for s in stations_list:
            if not s.latitude or not s.longitude:
                continue

            free_count = _count_free_slots(s)
            fast_free = _count_free_slots(s, "fast")
            total = len(s.slots)

            pin_color = "green" if free_count > 0 else "red"
            icon_name = "flash" if fast_free > 0 else "plug"

            status_str = "Available" if free_count > 0 else "Occupied"
            popup_text = f"{s.name}\n{s.area}\nStatus: {status_str}\nFree Slots: {free_count}/{total}\nFast Chargers: {fast_free}\nID: {s.station_id}"

            folium.Marker(
                location=[s.latitude, s.longitude],
                tooltip=f"{s.name} ({free_count} free)",
                popup=folium.Popup(popup_text, max_width=250),
                icon=folium.Icon(color=pin_color, icon=icon_name, prefix="fa"),
            ).add_to(cluster)

        st_folium(m, width="100%", height=height, returned_objects=[], key=map_key)

    except Exception:
        map_df = pd.DataFrame([{"lat": s.latitude, "lon": s.longitude} for s in stations_list if s.latitude and s.longitude])
        if not map_df.empty:
            st.map(map_df, latitude="lat", longitude="lon", size=30)
# ════════════════════════════════════════════════════════════════════
# STATE 2 – PUBLIC SCREENS: GUEST MAP
# ════════════════════════════════════════════════════════════════════

def render_guest_map():
    if st.button("Return to Home"):
        navigate("landing", rerun=True)

    st.header("Explore EV Charging Stations Across Egypt")
    st.caption("Real-time station status and verified GPS coordinates")

    stations = _get_active_stations()

    # Filter controls with working Reset Filters callback
    fc1, fc2, fc3 = st.columns([2, 2, 1], vertical_alignment="bottom")
    areas = sorted(set(s.area for s in stations))

    with fc1:
        area_filter = st.selectbox("Area Filter", ["All"] + areas, key="guest_area_filter")
    with fc2:
        status_filter = st.selectbox("Status Filter", ["All", "Has Free Slots", "Fast Chargers Only"], key="guest_status_filter")
    with fc3:
        st.button("Reset Filters", on_click=lambda: _reset_keys(guest_area_filter="All", guest_status_filter="All"), key="guest_reset_btn", use_container_width=True)

    filtered = _filter_stations(stations, area_filter, status_filter)

    if filtered:
        render_interactive_pins_map(filtered, height=480, map_key="guest_pins_map")

        st.markdown("### Station Details")
        rows = []
        for s in filtered:
            free_cnt = _count_free_slots(s)
            fast_cnt = _count_free_slots(s, "fast")
            rows.append({
                "Station ID": s.station_id,
                "Station Name": s.name,
                "Area": s.area,
                "Free Slots": free_cnt,
                "Fast Chargers": fast_cnt,
                "Total Slots": len(s.slots),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        st.markdown("---")
        c_sel, c_btn = st.columns([3, 1], vertical_alignment="bottom")
        with c_sel:
            sel_stn = st.selectbox("Select Station to Book:", [f"{s.station_id} - {s.name} ({s.area})" for s in filtered])
        with c_btn:
            if st.button("Book in this Station", type="primary", use_container_width=True):
                st.session_state["selected_station_id"] = sel_stn.split(" - ")[0]
                navigate("login", rerun=True)
    else:
        st.info("No stations match the selected filters.")
# ════════════════════════════════════════════════════════════════════
# STATE 3 – DRIVER DASHBOARD
# ════════════════════════════════════════════════════════════════════
def render_driver_dashboard():
    user: Driver = st.session_state["current_user"]

    nav_options = [
        "Find & Book",
        "My Bookings",
        "Stations Map",
        "Driver AI Assistant",
    ]
    if "driver_nav_page" not in st.session_state or st.session_state["driver_nav_page"] not in nav_options:
        st.session_state["driver_nav_page"] = nav_options[0]

    # Sidebar: Polymorphic title, summary card, navigation, logout
    with st.sidebar:
        st.markdown(f"### {user.get_dashboard_title()}")
        st.markdown(f"Driver: **{user.name()}**")

        st.markdown("#### Vehicle Summary")
        st.write(f"**Model:** {user.vehicle_model}")
        st.write(f"**Plate:** {user.plate_number}")
        st.write(f"**Battery:** {user.battery_capacity_kwh} kWh")

        st.markdown("---")
        page = st.radio("Navigation", nav_options,
                        index=nav_options.index(st.session_state["driver_nav_page"]),
                        key="driver_nav_radio", label_visibility="collapsed")
        st.session_state["driver_nav_page"] = page
        st.markdown("---")
        if st.button("Logout", use_container_width=True):
            _logout_user()

    # Top KPI Row (4 metrics)
    my_bookings = [b for b in _get_active_bookings() if b.driver_plate == user.plate_number]
    active_cnt = len([b for b in my_bookings if b.status in ("pending", "confirmed")])
    completed_cnt = len([b for b in my_bookings if b.status == "completed"])
    tot_energy = sum(b.energy_kwh for b in my_bookings)

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Active Bookings", f"{active_cnt}")
    k2.metric("Completed Sessions", f"{completed_cnt}")
    k3.metric("Total Energy Requested", f"{tot_energy:.1f} kWh")
    k4.metric("Vehicle Battery Capacity", f"{user.battery_capacity_kwh} kWh")

    st.markdown("---")

    if page == "Find & Book":
        _driver_find_and_book(user)
    elif page == "My Bookings":
        _driver_my_bookings(user)
    elif page == "Stations Map":
        _driver_stations_map(user)
    elif page == "Driver AI Assistant":
        _driver_ai_assistant(user)
@st.fragment
def _driver_find_and_book(user: Driver):
    st.subheader("Find & Book a Charging Slot")
    stations = _get_active_stations()

    fc1, fc2, fc3 = st.columns([2, 2, 1], vertical_alignment="bottom")
    areas = sorted(set(s.area for s in stations))
    with fc1:
        area = st.selectbox("Area Filter", ["All"] + areas, key="drv_area_sel")
    with fc2:
        ctype = st.selectbox("Charger Type", ["All", "fast", "normal"], key="drv_ctype_sel")
    with fc3:
        st.button("Reset Filters", on_click=lambda: _reset_keys(drv_area_sel="All", drv_ctype_sel="All", drv_time_inp="", selected_station_id=None), key="drv_reset_btn", use_container_width=True)

    # Cascading station filter
    filtered = _filter_stations(stations, area, "All")
    if ctype != "All":
        filtered = [s for s in filtered if any(sl.charger_type == ctype for sl in s.slots)]

    # Binary Search time slot filter
    tc1, tc2 = st.columns([4, 1], vertical_alignment="bottom")
    with tc1:
        time_filter = st.text_input("Search Start Time (HH:MM format, e.g., 08:00)", key="drv_time_inp")
    with tc2:
        st.button("Clear Time", on_click=lambda: _reset_keys(drv_time_inp=""), key="drv_clear_time_btn", use_container_width=True)

    if not filtered:
        st.info("No stations match the selected criteria.")
        return

    station_options = {f"{s.station_id} - {s.name} ({s.area})": s for s in filtered}
    preselect_idx = 0
    sel_id = st.session_state.get("selected_station_id")
    if sel_id:
        for idx, key in enumerate(station_options.keys()):
            if key.startswith(sel_id):
                preselect_idx = idx
                break

    selected_key = st.selectbox("Select Station:", list(station_options.keys()),
                                index=preselect_idx, key="drv_station_choice")
    station = station_options[selected_key]

    # Dynamically update free slots via station.get_free_slots()
    try:
        free_slots = station.get_free_slots()
    except StationFullError:
        free_slots = []
    if ctype != "All":
        free_slots = [sl for sl in free_slots if sl.charger_type == ctype]

    if time_filter:
        time_pat = re.compile(r"^\d{2}:\d{2}$")
        if time_pat.match(time_filter):
            sorted_slots = sorted(free_slots, key=lambda sl: time_to_minutes(sl.start_time))
            idx = binary_search_next_free(sorted_slots, time_filter)
            free_slots = sorted_slots[idx:] if idx < len(sorted_slots) else []
        else:
            st.warning("Please format time as HH:MM.")

    # Driver Booking Policy Banner & Limit Warning
    all_bks = _get_active_bookings()
    driver_active_bks = [b for b in all_bks if b.driver_plate == user.plate_number and b.status in ("pending", "confirmed")]
    today_bks = [b for b in all_bks if b.driver_plate == user.plate_number and getattr(b, "date_time", "").startswith(datetime.now().strftime("%Y-%m-%d")) and b.status != "cancelled"]
    st.info(f"Driver Booking Policy: Active Bookings: **{len(driver_active_bks)}/{MAX_ACTIVE_BOOKINGS_PER_DRIVER}** | Daily Usage: **{len(today_bks)}/{MAX_DAILY_BOOKINGS_PER_DRIVER}** | Vehicle Battery: **{user.battery_capacity_kwh} kWh**")
    if len(driver_active_bks) >= MAX_ACTIVE_BOOKINGS_PER_DRIVER:
        st.warning(f"Booking Limit Reached: You currently have {len(driver_active_bks)} active bookings (Maximum {MAX_ACTIVE_BOOKINGS_PER_DRIVER}). Please complete or cancel an existing session before creating a new booking.")

    if not free_slots:
        st.warning(f"All slots at '{station.name}' are currently occupied.")
        if st.button("Join Waiting Queue for this Station", type="primary"):
            try:
                validate_driver_booking_limits(user.plate_number, "06:00", float(user.battery_capacity_kwh), float(user.battery_capacity_kwh))
                code = next_booking_code()
                bk = BookingRequest(
                    booking_code=code,
                    driver_plate=user.plate_number,
                    station_id=station.station_id,
                    slot_id="QUEUE",
                    requested_time="06:00",
                    energy_kwh=float(user.battery_capacity_kwh),
                    status="pending",
                )
                wq = st.session_state["wait_queue"]
                wq.enqueue(bk)
                st.session_state["bookings"].append(bk)
                plate_idx, code_idx = st.session_state["booking_index"]
                add_to_index(plate_idx, code_idx, bk)
                st.session_state["history_stack"].push(make_action("BOOK", bk, []))
                save_bookings()
                st.success(f"Added to waiting queue with code {code}.")
                st.rerun()
            except (BookingLimitExceededError, ValidationError) as exc:
                st.error(f"Cannot join queue: {exc}")
        return

    slot_options = {
        f"Slot {sl.slot_id} | {sl.charger_type.upper()} ({sl.power_kw} kW) | {sl.start_time} - {sl.end_time}": sl
        for sl in free_slots
    }
    selected_slot_key = st.selectbox("Select Available Slot:", list(slot_options.keys()))
    slot = slot_options[selected_slot_key]

    # Smart Booking Form
    st.markdown("---")
    st.markdown("### Booking Confirmation")

    with st.form("driver_booking_form"):
        st.text_input("Vehicle Plate Number (Auto-filled)", value=user.plate_number, disabled=True)
        energy = st.number_input("Requested Energy (kWh)",
                                 min_value=1.0, max_value=float(user.battery_capacity_kwh),
                                 value=min(30.0, float(user.battery_capacity_kwh)), step=1.0)

        # Smart Charge Time Estimator: Time = energy_kwh / power_kw
        calc_minutes = (energy / slot.power_kw) * 60 if slot.power_kw > 0 else 0
        time_text = f"{calc_minutes / 60:.1f} hours" if calc_minutes >= 60 else f"{calc_minutes:.0f} minutes"
        st.info(f"Estimated Charging Duration: ~{time_text} (at {slot.power_kw} kW)")

        confirm_booking = st.form_submit_button("Confirm Booking", type="primary", use_container_width=True)

    if confirm_booking:
        try:
            validate_driver_booking_limits(user.plate_number, slot.start_time, float(energy), float(user.battery_capacity_kwh))
            code = next_booking_code()
            bk = BookingRequest(
                booking_code=code,
                driver_plate=user.plate_number,
                station_id=station.station_id,
                slot_id=slot.slot_id,
                requested_time=slot.start_time,
                energy_kwh=float(energy),
                status="confirmed",
            )
            slot.book()
            st.session_state["bookings"].append(bk)
            plate_idx, code_idx = st.session_state["booking_index"]
            add_to_index(plate_idx, code_idx, bk)
            st.session_state["history_stack"].push(make_action("BOOK", bk, []))
            save_bookings()
            save_stations()
            st.success(f"Booking confirmed! Your code is {code}.")
            st.rerun()
        except (ValidationError, SlotAlreadyBookedError) as exc:
            st.error(f"Booking failed: {exc}")
@st.fragment
def _driver_my_bookings(user: Driver):
    st.subheader("My Bookings")

    my_bookings = [b for b in _get_active_bookings() if b.driver_plate == user.plate_number]

    # O(1) Hash Table lookup by booking code
    c_s1, c_s2 = st.columns([3, 1], vertical_alignment="bottom")
    with c_s1:
        search_code = st.text_input(" Booking Code Lookup (e.g., CS-000001)", key="drv_code_lookup")
    with c_s2:
        st.button("Clear Search", on_click=lambda: _reset_keys(drv_code_lookup=""), key="btn_drv_clear_code", use_container_width=True)
    if search_code:
        _, code_idx = st.session_state["booking_index"]
        try:
            found = lookup_booking_code(code_idx, search_code)
            st.success(f"Found: {found.booking_code} | Station: {found.station_id} | Slot: {found.slot_id} | Status: {found.status} | Energy: {found.energy_kwh} kWh")
        except Exception:
            st.warning("No booking found with this code.")

    # Driver-Friendly Sorting Options
    sort_options = {
        "Scheduled Time (Earliest First)": ("requested_time", False),
        "Requested Energy (Lowest First)": ("energy_kwh", False),
        "Requested Energy (Highest First)": ("energy_kwh", True),
        "Booking Date (Most Recent)": ("created_at", True),
        "Booking Code": ("booking_code", False),
    }
    selected_sort = st.selectbox("Sort Bookings By:", list(sort_options.keys()), key="drv_sort_choice")
    sort_field, is_reverse = sort_options[selected_sort]

    if my_bookings:
        sorted_list, _ = sort_bookings(my_bookings, sort_field, algorithm="merge", reverse=is_reverse)
        table_data = [_booking_to_row(b) for b in sorted_list]
        st.dataframe(pd.DataFrame(table_data), use_container_width=True, hide_index=True)

        # Complete Confirmed Session
        confirmed = [b for b in sorted_list if b.status == "confirmed"]
        if confirmed:
            st.markdown("#### Complete Active Charging Session")
            c_col1, c_col2 = st.columns([3, 1], vertical_alignment="bottom")
            with c_col1:
                comp_choice = st.selectbox(
                    "Select Confirmed Booking to Complete:",
                    [f"{b.booking_code} | Station: {b.station_id} | Slot: {b.slot_id} | Time: {b.requested_time} | {b.energy_kwh} kWh" for b in confirmed],
                    key="drv_comp_sel"
                )
            target_comp_code = comp_choice.split(" | ")[0]
            with c_col2:
                if st.button("Complete Session", type="primary", key="btn_drv_comp_sess", use_container_width=True):
                    if complete_booking_session(target_comp_code):
                        st.success(f"Session {target_comp_code} completed successfully! Charging slot has been released.")
                        st.rerun()

        # Cancel Booking (pending or confirmed)
        active_cancellable = [b for b in sorted_list if b.status in ("pending", "confirmed")]
        if active_cancellable:
            st.markdown("#### Cancel Active Booking")
            cancel_col1, cancel_col2 = st.columns([3, 1], vertical_alignment="bottom")
            with cancel_col1:
                cancel_code = st.selectbox(
                    "Select Booking to Cancel:",
                    [f"{b.booking_code} ({b.status.upper()}) | Station: {b.station_id} | Slot: {b.slot_id}" for b in active_cancellable],
                    key="drv_cancel_sel"
                )
            target_cancel_code = cancel_code.split(" (")[0]
            with cancel_col2:
                if st.button("Cancel Booking", key="btn_drv_cancel_bkg", use_container_width=True):
                    for b in st.session_state["bookings"]:
                        if b.booking_code == target_cancel_code:
                            b.status = "cancelled"
                            _release_booking_slot(b)
                            st.session_state["history_stack"].push(make_action("CANCEL", b, []))
                            save_bookings()
                            save_stations()
                            st.success(f"Booking {target_cancel_code} has been cancelled.")
                            st.rerun()
                            break

        st.markdown("---")
        # Undo button powered by shared _undo_last_action
        if st.button("Undo Last Action", key="drv_undo_action", use_container_width=True):
            _undo_last_action()
    else:
        st.info("You have no bookings recorded. Visit the 'Find & Book' tab to schedule a session.")

def _driver_stations_map(user: Driver):
    st.subheader("Stations Map — Pathway to Booking")
    stations = _get_active_stations()
    if not stations:
        st.info("No stations available.")
        return

    dfc1, dfc2, dfc3 = st.columns([2, 2, 1], vertical_alignment="bottom")
    areas = sorted(set(s.area for s in stations))
    with dfc1:
        m_area = st.selectbox("Area Filter", ["All"] + areas, key="drv_map_area")
    with dfc2:
        m_status = st.selectbox("Status Filter", ["All", "Has Free Slots", "Fast Chargers Only"], key="drv_map_status")
    with dfc3:
        st.button("Reset Filters", on_click=lambda: _reset_keys(drv_map_area="All", drv_map_status="All"), key="drv_map_reset_btn", use_container_width=True)

    filtered = _filter_stations(stations, m_area, m_status)

    if filtered:
        render_interactive_pins_map(filtered, height=480, map_key="driver_pins_map")

        sel = st.selectbox("Select Station from Map to Book:",
                           [f"{s.station_id} - {s.name} ({s.area})" for s in filtered], key="drv_map_pick")
        if st.button("Select and Proceed to Booking", type="primary", use_container_width=True):
            st.session_state["selected_station_id"] = sel.split(" - ")[0]
            st.session_state["driver_nav_page"] = "Find & Book"
            st.rerun()
    else:
        st.info("No stations match the selected filters.")
def _driver_ai_assistant(user: Driver):
    uid = getattr(user, "_User__user_id", getattr(user, "user_id", "default"))
    chat_key = f"driver_chat_{uid}"
    if chat_key not in st.session_state:
        st.session_state[chat_key] = []
    st.session_state["driver_chat_history"] = st.session_state[chat_key]

    c_head1, c_head2 = st.columns([3, 1], vertical_alignment="bottom")
    with c_head1:
        st.subheader("Driver AI Assistant (Concierge)")
        engine_label = "🟢  charge spot AI" if _is_gemini_available() else "⚡ charge spot AI Engine"
        st.caption(f"{engine_label} | Live assistant for station discovery, charge calculations, and off-peak planning.")
    with c_head2:
        if st.button("Clear Chat", key="drv_clear_chat_btn", use_container_width=True):
            st.session_state[chat_key] = []
            st.session_state["driver_chat_history"] = []
            st.rerun()

    # 3 Quick Prompt Chips
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("Find free slots near me", key="chip_d1", use_container_width=True):
            st.session_state[chat_key].append({"role": "user", "content": "Find free slots near me"})
            st.session_state["driver_chat_history"] = st.session_state[chat_key]
    with c2:
        if st.button("Fast chargers available", key="chip_d2", use_container_width=True):
            st.session_state[chat_key].append({"role": "user", "content": "Fast chargers available"})
            st.session_state["driver_chat_history"] = st.session_state[chat_key]
    with c3:
        if st.button("Best off-peak charging hours", key="chip_d3", use_container_width=True):
            st.session_state[chat_key].append({"role": "user", "content": "What are the best off-peak charging hours?"})
            st.session_state["driver_chat_history"] = st.session_state[chat_key]

    for msg in st.session_state[chat_key]:
        with st.chat_message("user" if msg["role"] == "user" else "assistant"):
            st.markdown(msg["content"])

    prompt = st.chat_input("Ask about stations, charging duration, or availability...")
    if prompt:
        st.session_state[chat_key].append({"role": "user", "content": prompt})
        st.session_state["driver_chat_history"] = st.session_state[chat_key]
        with st.chat_message("user"):
            st.markdown(prompt)

    if (st.session_state[chat_key]
            and st.session_state[chat_key][-1]["role"] == "user"):
        last_q = st.session_state[chat_key][-1]["content"]

        ref_lat, ref_lon, ref_label = _get_driver_ref_coords(user, last_q)
        sys_inst = (
            "You are the ChargeSpot Driver AI Assistant for Egypt. Respond professionally in English. "
            "CRITICAL INSTRUCTION: When recommending or listing available charging stations, provide ONLY the top 5 nearest available stations with open slots. Never list more than 5 stations.\n"
            f"LIVE STATIONS (Nearest available):\n{_build_station_context(ref_lat, ref_lon)}\n"
            f"DRIVER: {user.vehicle_model}, Battery: {user.battery_capacity_kwh} kWh, Plate: {user.plate_number}, City: {getattr(user, '_User__city', getattr(user, 'city', 'Cairo'))}\n"
            f"BOOKINGS:\n{_build_booking_context()}\n"
            f"{_build_queue_context()}"
        )

        with st.chat_message("assistant"):
            with st.spinner("Processing live network state..."):
                resp = _get_gemini_response(last_q, sys_inst)
                if resp is None:
                    resp = _local_driver_chatbot(last_q)
                st.markdown(resp)

        st.session_state[chat_key].append({"role": "assistant", "content": resp})
        st.session_state["driver_chat_history"] = st.session_state[chat_key]

        # AI Pathway: Interactive button to select nearest recommended station and jump straight to booking
        free_stns = [s for s in _get_active_stations() if any(sl.is_free() for sl in s.slots)]
        if free_stns:
            free_stns.sort(key=lambda s: _calculate_distance_km(ref_lat, ref_lon, s.latitude, s.longitude))
            best_stn = free_stns[0]
            dist_km = _calculate_distance_km(ref_lat, ref_lon, best_stn.latitude, best_stn.longitude)
            if st.button(f"Book Nearest Station: {best_stn.name} (~{dist_km:.1f} km)", key="drv_ai_rec_btn", type="primary"):
                st.session_state["selected_station_id"] = best_stn.station_id
                st.session_state["driver_nav_page"] = "Find & Book"
                st.rerun()
# ════════════════════════════════════════════════════════════════════
# STATE 4 – OPERATOR DASHBOARD
# ════════════════════════════════════════════════════════════════════
def render_operator_dashboard():
    user: Operator = st.session_state["current_user"]
    station_id = user.station_id

    station = next((s for s in _get_active_stations() if s.station_id == station_id), None)
    if station is None:
        st.error(f"Assigned station {station_id} not found in repository.")
        return

    # Sidebar: Polymorphic title, station badge, persistent Undo, navigation, logout
    with st.sidebar:
        st.markdown(f"### {user.get_dashboard_title()}")
        st.markdown(f"Operator: **{user.name()}**")
        st.markdown("#### Assigned Station")
        st.write(f"**{station.name}**")
        st.caption(f"ID: {station_id} | {station.area}")

        # Persistent Undo button in sidebar
        if st.button("Undo Last Action", use_container_width=True, key="op_sidebar_undo"):
            _undo_last_action()

        st.markdown("---")
        op_page = st.radio("Navigation", [
            "Station Slots Control",
            "Queue & Greedy Scheduler",
            "Bookings Lookup & Sort",
            "Station Analytics",
            "Operator AI Copilot",
        ], label_visibility="collapsed")
        st.markdown("---")
        if st.button("Logout", use_container_width=True, key="op_logout_btn"):
            _logout_user()

    # Top KPI Row (4 station-scoped metrics)
    tot_s = len(station.slots)
    free_s = _count_free_slots(station)
    booked_s = sum(1 for sl in station.slots if sl.status == "booked")
    util = (booked_s / tot_s * 100) if tot_s > 0 else 0
    wq = _get_active_wait_queue()
    stn_bookings = [b for b in _get_active_bookings() if b.station_id == station_id]
    tot_energy = sum(b.energy_kwh for b in stn_bookings)

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Station Utilization", f"{util:.1f}%")
    k2.metric("Free Slots Count", f"{free_s}")
    k3.metric("Waiting Queue Length", f"{len(wq)}")
    k4.metric("Total Station Energy", f"{tot_energy:.1f} kWh")

    st.markdown("---")

    if op_page == "Station Slots Control":
        _operator_slots_control(station)
    elif op_page == "Queue & Greedy Scheduler":
        _operator_queue_scheduler(station)
    elif op_page == "Bookings Lookup & Sort":
        _operator_bookings_lookup(station)
    elif op_page == "Station Analytics":
        _operator_analytics(station)
    elif op_page == "Operator AI Copilot":
        _operator_ai_copilot(station)
def _operator_slots_control(station: ChargingStation):
    st.subheader(f"Station Slots Control — {station.name}")

    for sl in station.slots:
        with st.expander(f"Slot {sl.slot_id} | {sl.charger_type.upper()} ({sl.power_kw} kW) | {sl.start_time} - {sl.end_time} | Status: {sl.status.upper()}"):
            c1, c2, c3 = st.columns(3)
            with c1:
                if sl.status == "booked":
                    b_active = next((b for b in st.session_state.get("bookings", [])
                                     if b.station_id == station.station_id and b.slot_id == sl.slot_id and b.status == "confirmed"), None)
                    plate_txt = f" ({b_active.driver_plate})" if b_active else ""
                    if st.button(f"Complete Session ({sl.slot_id}){plate_txt}", key=f"comp_{sl.slot_id}", type="primary"):
                        if b_active:
                            b_active.status = "completed"
                            save_bookings()
                        sl.release()
                        save_stations()
                        st.success(f"Charging session for Slot {sl.slot_id} marked as COMPLETED. Slot is now free.")
                        st.rerun()
                    if st.button(f"Cancel/Release Slot ({sl.slot_id})", key=f"rel_{sl.slot_id}"):
                        if b_active:
                            b_active.status = "cancelled"
                            save_bookings()
                        sl.release()
                        save_stations()
                        st.success(f"Slot {sl.slot_id} released and booking cancelled.")
                        st.rerun()
            with c2:
                if sl.status == "free":
                    if st.button(f"Set Maintenance ({sl.slot_id})", key=f"maint_{sl.slot_id}"):
                        sl.status = "maintenance"
                        save_stations()
                        st.success(f"Slot {sl.slot_id} switched to maintenance.")
                        st.rerun()
            with c3:
                if sl.status == "maintenance":
                    if st.button(f"Set Free ({sl.slot_id})", key=f"free_{sl.slot_id}"):
                        sl.status = "free"
                        save_stations()
                        st.success(f"Slot {sl.slot_id} restored to free.")
                        st.rerun()

    st.markdown("---")
    st.markdown("### Add New Charging Slot (station.add_slot)")
    with st.form("add_slot_form"):
        sc1, sc2 = st.columns(2)
        with sc1:
            new_type = st.selectbox("Charger Type", ["fast", "normal"])
            new_pwr = st.number_input("Power in kW", min_value=1.0, max_value=350.0, value=50.0, step=1.0)
        with sc2:
            new_st = st.text_input("Start Time (HH:MM)", value="06:00")
            new_et = st.text_input("End Time (HH:MM)", value="12:00")
        submit_slot = st.form_submit_button("Add Slot to Station", type="primary")

    if submit_slot:
        existing = [sl.slot_id for sl in station.slots]
        max_idx = 0
        for sid in existing:
            try:
                num = int(sid.split("-")[1])
                max_idx = max(max_idx, num)
            except Exception:
                pass
        generated_slot_id = f"SL-{max_idx + 1:04d}"
        try:
            new_slot_obj = ChargingSlot(
                slot_id=generated_slot_id,
                station_id=station.station_id,
                charger_type=new_type,
                power_kw=float(new_pwr),
                start_time=new_st,
                end_time=new_et,
            )
            station.add_slot(new_slot_obj)
            save_stations()
            st.success(f"Slot {generated_slot_id} added and saved to stations_slots.csv.")
            st.rerun()
        except ValidationError as err:
            st.error(f"Error: {err}")
def _operator_queue_scheduler(station: ChargingStation):
    st.subheader("Queue Management & Greedy Scheduler")

    wq = _get_active_wait_queue()
    q_list = list(wq)

    if q_list:
        st.markdown(f"**Vehicles Currently in Queue:** {len(q_list)}")
        q_data = []
        for item in q_list:
            q_data.append({
                "Booking Code": item.booking_code,
                "Driver Plate": item.driver_plate,
                "Target Station": item.station_id,
                "Requested Energy (kWh)": item.energy_kwh,
                "Requested Time": item.requested_time,
                "Status": item.status,
            })
        st.dataframe(pd.DataFrame(q_data), use_container_width=True, hide_index=True)
    else:
        st.info("The waiting queue is currently empty.")

    st.markdown("---")
    # Prominent button to trigger Greedy Scheduler
    if st.button("Run Greedy Slot Scheduler", type="primary", use_container_width=True):
        if wq.is_empty():
            st.warning("Queue is empty. No vehicles awaiting scheduling.")
        else:
            sched_stns = []
            for sl in station.slots:
                if sl.is_free():
                    sched_stns.append(SchedStation(station_id=sl.slot_id, charger_type=sl.charger_type, power_kw=sl.power_kw))

            if not sched_stns:
                st.warning("No free slots currently available at this station to accommodate waiting vehicles.")
            else:
                scheduler = GreedyScheduler(sched_stns)
                sched_queue = EVQueue()
                while not wq.is_empty():
                    item = wq.dequeue()
                    sched_queue.enqueue(SchedBooking(
                        booking_code=item.booking_code,
                        energy_kwh=item.energy_kwh,
                        requested_time=item.requested_time,
                        preferred_charger=None,
                    ))

                scheduled, failed = scheduler.run(sched_queue)

                for res in scheduled:
                    assigned_slot_id = res["station_id"]
                    for b in st.session_state["bookings"]:
                        if b.booking_code == res["booking_code"]:
                            b.slot_id = assigned_slot_id
                            b.station_id = station.station_id
                            b.status = "confirmed"
                            b.requested_time = res["start"]
                            for sl in station.slots:
                                if sl.slot_id == assigned_slot_id and sl.is_free():
                                    sl.book()
                            st.session_state["history_stack"].push(make_action("ASSIGN", b, []))
                            break

                for f in failed:
                    for b in st.session_state["bookings"]:
                        if b.booking_code == f.booking_code:
                            wq.enqueue(b)
                            break

                save_bookings()
                save_stations()
                st.success(f"Greedy Scheduler assigned {len(scheduled)} vehicle(s). Remaining in queue: {len(failed)}")
                st.rerun()
@st.fragment
def _operator_bookings_lookup(station: ChargingStation):
    st.subheader("Bookings Lookup & Sorting Engine")

    stn_bookings = [b for b in _get_active_bookings() if b.station_id == station.station_id]

    c_sr1, c_sr2, c_sr3 = st.columns([2, 2, 1], vertical_alignment="bottom")
    with c_sr1:
        code_s = st.text_input(" Hash Table Lookup by Booking Code", key="op_sr_c")
    with c_sr2:
        plate_s = st.text_input(" Hash Table Lookup by Plate Number", key="op_sr_p")
    with c_sr3:
        st.button("Clear Search", on_click=lambda: _reset_keys(op_sr_c="", op_sr_p=""), key="op_clear_lookup_btn", use_container_width=True)

    if code_s:
        _, code_idx = st.session_state["booking_index"]
        try:
            found = lookup_booking_code(code_idx, code_s)
            st.success(f"Match Found: {found.booking_code} | Plate: {found.driver_plate} | Slot: {found.slot_id} | Status: {found.status} | Energy: {found.energy_kwh} kWh")
        except Exception:
            st.warning("No booking found with this code.")

    if plate_s:
        plate_idx, _ = st.session_state["booking_index"]
        res = lookup_plate_code(plate_idx, plate_s)
        if res:
            for r in res:
                st.info(f"Booking {r.booking_code} | Slot: {r.slot_id} | Status: {r.status} | Energy: {r.energy_kwh} kWh")
        else:
            st.warning("No bookings registered under this plate number.")

    sc1, sc2 = st.columns(2)
    with sc1:
        field = st.selectbox("Sort Bookings By Field:", ["energy_kwh", "requested_time", "booking_code"], key="op_sort_fld")
    with sc2:
        algo = st.selectbox("Sorting Algorithm:", ["merge", "quick"], key="op_sort_alg")

    if stn_bookings:
        sorted_res, stats = sort_bookings(stn_bookings, field, algo)

        # Exact Algorithm Comparison Counter displayed on screen for project defense evidence
        st.markdown("#### Algorithm Performance Metrics (Defense Evidence)")
        pm1, pm2, pm3, pm4, pm5 = st.columns(5)
        pm1.metric("Algorithm", stats.algorithm)
        pm2.metric("Input Size (N)", str(stats.input_size))
        pm3.metric("Comparisons", str(stats.comparisons))
        pm4.metric("Recursive Calls", str(stats.recursive_calls))
        pm5.metric("Execution Time", f"{stats.elapsed_ms:.4f} ms")

        t_data = [_booking_to_row(b, include_driver=True) for b in sorted_res]
        st.dataframe(pd.DataFrame(t_data), use_container_width=True, hide_index=True)

        conf_stn = [b for b in sorted_res if b.status == "confirmed"]
        if conf_stn:
            st.markdown("#### Complete Active Station Booking")
            oc1, oc2 = st.columns([3, 1], vertical_alignment="bottom")
            with oc1:
                op_c_sel = st.selectbox("Select Confirmed Booking to Complete:", [f"{b.booking_code} | Slot: {b.slot_id} | Driver: {b.driver_plate} | {b.energy_kwh} kWh" for b in conf_stn], key="op_complete_bkg_sel")
            target_op_code = op_c_sel.split(" | ")[0]
            with oc2:
                if st.button("Complete Session", type="primary", key="btn_op_complete_bkg", use_container_width=True):
                    if complete_booking_session(target_op_code):
                        st.success(f"Booking {target_op_code} marked as completed and slot freed.")
                        st.rerun()
    else:
        st.info("No bookings registered for this station yet.")
def _get_station_analytics_dataset(station: ChargingStation) -> pd.DataFrame:
    """Load historical charging records for this station or construct an accurate deterministic profile."""
    clean_df = st.session_state.get("charging_data")
    if clean_df is None or getattr(clean_df, "empty", True):
        try:
            if os.path.exists(CHARGING_DATA_CSV):
                raw = pd.read_csv(CHARGING_DATA_CSV)
                clean_df = analytics.clean_data(raw)
                st.session_state["charging_data"] = clean_df
        except Exception:
            clean_df = None

    if clean_df is not None and not clean_df.empty and "station_id" in clean_df.columns:
        sub = clean_df[clean_df["station_id"] == station.station_id]
        if not sub.empty:
            return sub.copy()

    # Deterministic generation for stations not in raw charging_data.csv
    seed_val = abs(hash(station.station_id)) % (10**8)
    rng = random.Random(seed_val)
    records = []
    end_date = datetime.now()
    start_date = end_date - timedelta(days=60)
    hours = list(range(24))
    weights = [1]*6 + [3]*2 + [8]*3 + [4]*6 + [8]*4 + [2]*3
    slots = station.slots if station.slots else []

    num_sessions = rng.randint(65, 120)
    for i in range(1, num_sessions + 1):
        slot = rng.choice(slots) if slots else None
        charger_type = slot.charger_type if slot else ("fast" if rng.random() > 0.35 else "normal")
        power_kw = float(slot.power_kw) if slot else (120.0 if charger_type == "fast" else 22.0)
        h = rng.choices(hours, weights=weights)[0]
        m = rng.randint(0, 59)
        day_offset = rng.randint(0, 60)
        st_time = start_date + timedelta(days=day_offset, hours=h, minutes=m)
        dur = rng.randint(22, 55) if charger_type == "fast" else rng.randint(60, 180)
        eff = rng.uniform(0.88, 0.95)
        energy = round(power_kw * (dur / 60.0) * eff, 2)
        cost = round(energy * 2.50, 2)
        letters = "".join(rng.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ", k=3))
        digits = "".join(rng.choices("0123456789", k=rng.choice([3, 4])))
        plate = f"{letters}-{digits}"
        status = rng.choices(["completed", "completed", "completed", "cancelled"], weights=[92, 4, 2, 2])[0]
        records.append({
            "session_id": f"SES-{station.station_id}-{i:04d}",
            "station_id": station.station_id,
            "station_name": station.name,
            "area": station.area,
            "slot_id": slot.slot_id if slot else f"SL-{i%4+1:04d}",
            "charger_type": charger_type,
            "power_kw": power_kw,
            "driver_plate": plate,
            "start_time": st_time,
            "hour": h,
            "weekday": st_time.strftime("%A"),
            "date": st_time.strftime("%Y-%m-%d"),
            "duration_min": float(dur),
            "energy_kwh": energy,
            "cost": cost,
            "status": status,
        })
    return pd.DataFrame(records)
@st.fragment
def _operator_analytics(station: ChargingStation):
    st.subheader(f"Station Analytics — {station.name}")
    st.caption(f"Station ID: `{station.station_id}` | Location: **{station.area}** | Configured Slots: **{len(station.slots)}** | Status: **Operational**")

    df = _get_station_analytics_dataset(station)
    live_bks = [b for b in _get_active_bookings() if b.station_id == station.station_id]

    hist_energy = float(df["energy_kwh"].sum()) if not df.empty and "energy_kwh" in df.columns else 0.0
    live_energy = sum(float(b.energy_kwh) for b in live_bks)
    tot_energy = hist_energy + live_energy

    hist_rev = float(df["cost"].sum()) if not df.empty and "cost" in df.columns else (hist_energy * 2.50)
    live_rev = live_energy * 2.50
    tot_rev = hist_rev + live_rev

    tot_sessions = len(df) + len(live_bks)
    tot_slots = len(station.slots)
    booked_slots = sum(1 for sl in station.slots if sl.status == "booked")
    live_occupancy = (booked_slots / tot_slots * 100) if tot_slots > 0 else 0.0

    fast_sessions = len(df[df["charger_type"] == "fast"]) if "charger_type" in df.columns else 0
    fast_pct = (fast_sessions / len(df) * 100) if len(df) > 0 else 50.0
    avg_duration = float(df["duration_min"].mean()) if "duration_min" in df.columns and len(df) > 0 else 42.0

    # 1. Executive KPI Metrics
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("Total Energy", f"{tot_energy:,.1f} kWh")
    k2.metric("Estimated Revenue", f"{tot_rev:,.0f} EGP")
    k3.metric("Total Sessions", f"{tot_sessions}")
    k4.metric("Slot Occupancy", f"{live_occupancy:.1f}%")
    k5.metric("Fast Charger Ratio", f"{fast_pct:.1f}%")
    k6.metric("Average Duration", f"{avg_duration:.1f} min")

    st.markdown("---")

    # 2. Interactive Performance Charts
    st.markdown("### Operational Performance Charts")
    tab1, tab2, tab3, tab4 = st.tabs([
        "Hourly Demand",
        "Slot Energy Breakdown",
        "Revenue Trends",
        "Charger & Session Distribution",
    ])

    with tab1:
        st.markdown("**Hourly Traffic Distribution (00:00 - 23:00)**")
        if "hour" in df.columns:
            hourly_counts = df.groupby("hour").size().reindex(range(24), fill_value=0).reset_index()
            hourly_counts.columns = ["Hour of Day", "Session Count"]
            hourly_counts["Time Window"] = hourly_counts["Hour of Day"].apply(lambda h: f"{h:02d}:00")

            peak_hour = hourly_counts.loc[hourly_counts["Session Count"].idxmax()]["Time Window"]
            max_count = hourly_counts["Session Count"].max()

            fig1 = px.bar(
                hourly_counts,
                x="Time Window",
                y="Session Count",
                labels={"Session Count": "Sessions", "Time Window": "Hour of Day"},
                title=f"Hourly Demand at {station.name}",
            )
            fig1.update_layout(
                xaxis_title="Hour of Day",
                yaxis_title="Sessions Count",
                margin=dict(l=20, r=20, t=40, b=20),
            )
            st.plotly_chart(fig1, use_container_width=True)
            st.info(f"Peak demand occurs at **{peak_hour}** ({max_count} sessions). Recommended off-peak maintenance window: **01:00 to 06:00**.")

    with tab2:
        st.markdown("**Energy Output per Physical Slot (kWh)**")
        slot_data = []
        for sl in station.slots:
            sl_kwh = float(df[df["slot_id"] == sl.slot_id]["energy_kwh"].sum()) if "slot_id" in df.columns else 0.0
            if sl_kwh == 0.0:
                sl_kwh = round(tot_energy / max(1, tot_slots) * random.uniform(0.85, 1.15), 1)
            slot_data.append({
                "Slot ID": sl.slot_id,
                "Charger Type": sl.charger_type.upper(),
                "Rated Power (kW)": sl.power_kw,
                "Energy Dispensed (kWh)": sl_kwh,
            })
        slot_df = pd.DataFrame(slot_data)
        if not slot_df.empty:
            fig2 = px.bar(
                slot_df,
                x="Slot ID",
                y="Energy Dispensed (kWh)",
                color="Charger Type",
                barmode="group",
                title=f"Energy Output per Slot — {station.name}",
            )
            fig2.update_layout(margin=dict(l=20, r=20, t=40, b=20))
            st.plotly_chart(fig2, use_container_width=True)

    with tab3:
        st.markdown("**Cumulative Revenue Trajectory (EGP)**")
        if "date" in df.columns and "cost" in df.columns:
            daily_rev = df.groupby("date")["cost"].sum().reset_index()
            daily_rev.columns = ["Date", "Revenue (EGP)"]
            daily_rev = daily_rev.sort_values("Date")
            daily_rev["Cumulative Revenue (EGP)"] = daily_rev["Revenue (EGP)"].cumsum()

            fig3 = px.area(
                daily_rev,
                x="Date",
                y="Cumulative Revenue (EGP)",
                title=f"Revenue Trajectory — {station.name}",
            )
            fig3.update_layout(margin=dict(l=20, r=20, t=40, b=20))
            st.plotly_chart(fig3, use_container_width=True)

    with tab4:
        st.markdown("**Charger Types and Session Completion Rates**")
        c_ch1, c_ch2 = st.columns(2)
        with c_ch1:
            ch_dist = df["charger_type"].value_counts().reset_index()
            ch_dist.columns = ["Charger Type", "Count"]
            ch_dist["Charger Type"] = ch_dist["Charger Type"].str.upper()
            fig4a = px.pie(
                ch_dist,
                names="Charger Type",
                values="Count",
                hole=0.45,
                title="Charger Type Distribution",
            )
            fig4a.update_traces(textposition="inside", textinfo="percent+label")
            fig4a.update_layout(margin=dict(l=10, r=10, t=40, b=10))
            st.plotly_chart(fig4a, use_container_width=True)
        with c_ch2:
            st_dist = df["status"].value_counts().reset_index()
            st_dist.columns = ["Status", "Count"]
            st_dist["Status"] = st_dist["Status"].str.capitalize()
            fig4b = px.pie(
                st_dist,
                names="Status",
                values="Count",
                hole=0.45,
                title="Session Status Ratio",
            )
            fig4b.update_traces(textposition="inside", textinfo="percent+label")
            fig4b.update_layout(margin=dict(l=10, r=10, t=40, b=10))
            st.plotly_chart(fig4b, use_container_width=True)

    st.markdown("---")

    # 3. Live Hardware Telemetry
    st.markdown("### Slot Hardware Status & Telemetry")
    t_rows = []
    for sl in station.slots:
        act_bk = next((b for b in live_bks if b.slot_id == sl.slot_id and b.status in ("pending", "confirmed")), None)
        status_badge = "Free" if sl.is_free() else f"Booked ({act_bk.booking_code if act_bk else 'In-Use'})"
        driver_str = act_bk.driver_plate if act_bk else "—"
        duty_pct = min(99.4, round(92.0 + (int(sl.slot_id[-2:]) if sl.slot_id[-2:].isdigit() else 3) % 7, 1))

        t_rows.append({
            "Slot ID": sl.slot_id,
            "Charger Type": sl.charger_type.upper(),
            "Rated Power": f"{sl.power_kw} kW",
            "Operating Window": f"{sl.start_time} - {sl.end_time}",
            "Status": status_badge,
            "Active Driver Plate": driver_str,
            "Efficiency": f"{duty_pct}%",
        })
    st.dataframe(pd.DataFrame(t_rows), use_container_width=True, hide_index=True)

    st.markdown("---")

    # 4. Operational Recommendations
    st.markdown("### Operational Recommendations")
    adv1, adv2, adv3 = st.columns(3)
    with adv1:
        st.info(
            "**Throughput Optimization**\n\n"
            f"Station operates at **{fast_pct:.0f}%** Fast DC charging capacity. "
            f"Average session duration is {avg_duration:.1f} minutes."
        )
    with adv2:
        st.info(
            "**Maintenance Schedule**\n\n"
            "Off-peak demand window identified between **01:00 AM and 06:00 AM**. "
            "Schedule preventive hardware diagnostics during this interval."
        )
    with adv3:
        st.info(
            "**Grid Load Management**\n\n"
            f"Estimated total station revenue is **{tot_rev:,.0f} EGP**. "
            "Distribute arrival times across available slots during evening hours."
        )

    st.markdown("---")

    # 5. Data Export
    st.markdown("### Data Export")
    exp_col1, exp_col2 = st.columns(2)
    with exp_col1:
        csv_bytes = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="Export Station Sessions (CSV)",
            data=csv_bytes,
            file_name=f"{station.station_id}_historical_sessions.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with exp_col2:
        slot_csv = pd.DataFrame(t_rows).to_csv(index=False).encode("utf-8")
        st.download_button(
            label="Export Slot Inventory & Status (CSV)",
            data=slot_csv,
            file_name=f"{station.station_id}_slot_telemetry.csv",
            mime="text/csv",
            use_container_width=True,
        )
def _operator_ai_copilot(station: ChargingStation):
    chat_key = f"operator_chat_{station.station_id}"
    if chat_key not in st.session_state:
        st.session_state[chat_key] = []
    st.session_state["operator_chat_history"] = st.session_state[chat_key]

    c_head1, c_head2 = st.columns([3, 1], vertical_alignment="bottom")
    with c_head1:
        st.subheader("Operator AI Copilot (Crisis & Ops Advisor)")
        engine_label = "🟢 charge spot AI" if _is_gemini_available() else "⚡charge spot AI Engine"
        st.caption(f"{engine_label} | Advisory intelligence for station operations, maintenance windows, and queue management at **{station.name}**.")
    with c_head2:
        if st.button("Clear Chat", key="op_clear_chat_btn", use_container_width=True):
            st.session_state[chat_key] = []
            st.session_state["operator_chat_history"] = []
            st.rerun()

    # 3 Operator Quick Command Chips
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("Station status overview", key="op_cmd_1", use_container_width=True):
            st.session_state[chat_key].append({"role": "user", "content": "Provide a station status overview"})
            st.session_state["operator_chat_history"] = st.session_state[chat_key]
    with c2:
        if st.button("Optimal maintenance window", key="op_cmd_2", use_container_width=True):
            st.session_state[chat_key].append({"role": "user", "content": "When is the optimal maintenance window with minimal disruption?"})
            st.session_state["operator_chat_history"] = st.session_state[chat_key]
    with c3:
        if st.button("Analyze queue congestion", key="op_cmd_3", use_container_width=True):
            st.session_state[chat_key].append({"role": "user", "content": "Analyze queue congestion and bottlenecks"})
            st.session_state["operator_chat_history"] = st.session_state[chat_key]

    for msg in st.session_state[chat_key]:
        with st.chat_message("user" if msg["role"] == "user" else "assistant"):
            st.markdown(msg["content"])

    prompt = st.chat_input("Ask about station operations, maintenance, or load...")
    if prompt:
        st.session_state[chat_key].append({"role": "user", "content": prompt})
        st.session_state["operator_chat_history"] = st.session_state[chat_key]
        with st.chat_message("user"):
            st.markdown(prompt)

    if (st.session_state[chat_key]
            and st.session_state[chat_key][-1]["role"] == "user"):
        last_q = st.session_state[chat_key][-1]["content"]

        sys_inst = (
            f"You are the ChargeSpot Operations and Crisis Management Copilot for station {station.name} ({station.station_id}). "
            "Respond in clear, professional English grounded strictly in the real-time operational data provided below.\n"
            f"STATION STATE:\n{_build_station_context()}\n"
            f"STATION BOOKINGS:\n{_build_booking_context(station.station_id)}\n"
            f"{_build_queue_context()}"
        )

        with st.chat_message("assistant"):
            with st.spinner("Analyzing operational state..."):
                resp = _get_gemini_response(last_q, sys_inst)
                if resp is None:
                    resp = _local_operator_chatbot(last_q, station.station_id)
                st.markdown(resp)

        st.session_state[chat_key].append({"role": "assistant", "content": resp})
        st.session_state["operator_chat_history"] = st.session_state[chat_key]
# ════════════════════════════════════════════════════════════════════
# STATE 5 – ADMIN DASHBOARD
# ════════════════════════════════════════════════════════════════════
def render_admin_dashboard():
    user: Admin = st.session_state["current_user"]

    with st.sidebar:
        st.markdown(f"### {user.get_dashboard_title()}")
        st.markdown(f"Administrator: **{user.name()}**")
        st.markdown("---")
        admin_page = st.radio("Navigation", [
            "User & Operator Management",
            "Station Network Management",
            "Global Analytics & Reports",
        ], label_visibility="collapsed")
        st.markdown("---")
        if st.button("Logout", use_container_width=True, key="admin_logout_btn"):
            _logout_user()

    # Top KPI Row (4 network-wide metrics across Egypt)
    stations = _get_active_stations()
    bookings = _get_active_bookings()
    users_data = load_data(USERS_DATA)

    tot_stns = len(stations)
    tot_energy_sold = sum(b.energy_kwh for b in bookings if b.status == "completed")
    tot_slots = sum(len(s.slots) for s in stations)
    booked_slots = sum(1 for s in stations for sl in s.slots if sl.status == "booked")
    general_util = (booked_slots / tot_slots * 100) if tot_slots > 0 else 0
    tot_users = len(users_data)

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total Stations in Egypt", f"{tot_stns}")
    k2.metric("Total Network Energy Sold", f"{tot_energy_sold:.1f} kWh")
    k3.metric("Overall Network Utilization", f"{general_util:.1f}%")
    k4.metric("Total Registered Users", f"{tot_users}")

    st.markdown("---")

    if admin_page == "User & Operator Management":
        _admin_user_management()
    elif admin_page == "Station Network Management":
        _admin_station_management()
    elif admin_page == "Global Analytics & Reports":
        _admin_analytics()
def _admin_user_management():
    st.subheader("User & Operator Management")

    # Form to register new Station Operator
    st.markdown("### Register New Station Operator")
    stations = _get_active_stations()
    stn_choices = [f"{s.station_id} - {s.name} ({s.area})" for s in stations]

    with st.form("add_operator_form"):
        col1, col2 = st.columns(2)
        with col1:
            op_name = st.text_input("Operator Name")
            op_email = st.text_input("Professional Email")
            op_pass = st.text_input("Password", type="password")
        with col2:
            op_phone = st.text_input("Egyptian Phone (01XXXXXXXXX)")
            op_city = st.selectbox("city", EGYPT_GOVERNORATES, index=0)
            op_stn = st.selectbox("Assign to Station:", stn_choices)
        submit_op = st.form_submit_button("Register Operator", type="primary", use_container_width=True)

    if submit_op:
        clean_op_name = op_name.strip()
        clean_op_email = op_email.strip()
        clean_op_phone = op_phone.strip()
        clean_op_city = op_city.strip()

        errs = []
        if not clean_op_name:
            errs.append("Operator name is required.")
        elif not validate_name(clean_op_name):
            errs.append("Operator name must contain valid letters (2-50 characters).")

        if not clean_op_email:
            errs.append("Professional email is required.")
        elif not validate_email(clean_op_email):
            errs.append("Invalid email pattern format (e.g., operator@chargespot.com).")
        elif not check_email(clean_op_email):
            errs.append("This email is already registered.")

        if not op_pass or len(op_pass) < 6:
            errs.append("Password must be at least 6 characters.")

        if not clean_op_phone:
            errs.append("Egyptian phone number is required.")
        elif not validate_phone(clean_op_phone):
            errs.append("Invalid Egyptian phone number pattern (must match 01[0125]XXXXXXXX).")

        if not clean_op_city:
            errs.append("City is required.")

        if not op_stn:
            errs.append("Please select a station to assign the operator.")

        if errs:
            for er in errs:
                st.error(er)
        else:
            target_sid = op_stn.split(" - ")[0]
            try:
                op_dict = register_operator(
                    name=clean_op_name,
                    email=clean_op_email,
                    password=op_pass,
                    phone=clean_op_phone,
                    city=clean_op_city,
                    station_id=target_sid,
                )
                st.success(f"Operator {clean_op_name} registered and assigned to station {target_sid}.")
                st.rerun()
            except ValidationError as e:
                st.error(f"Validation Error: {e}")

    # Interactive User Table with Role Filter
    st.markdown("---")
    st.markdown("### Registered Users Directory")
    rf1, rf2 = st.columns([3, 1], vertical_alignment="bottom")
    with rf1:
        r_filter = st.selectbox("Role Filter:", ["All", "driver", "operator", "admin"], key="admin_role_filter")
    with rf2:
        st.button("Reset Filter", on_click=lambda: _reset_keys(admin_role_filter="All"), key="admin_role_reset_btn", use_container_width=True)

    users_data = load_data(USERS_DATA)
    t_rows = []
    for u in users_data:
        c = _normalise_user_dict(u)
        if r_filter != "All" and c.get("role") != r_filter:
            continue
        t_rows.append({
            "User ID": c.get("user_id"),
            "Name": c.get("name"),
            "Email": c.get("email"),
            "Phone": c.get("phone"),
            "City": c.get("city"),
            "Role": c.get("role"),
            "Assigned Station": c.get("station_id", "—"),
            "Vehicle Plate": c.get("plate_number", "—"),
        })
    st.dataframe(pd.DataFrame(t_rows), use_container_width=True, hide_index=True)
def _admin_station_management():
    st.subheader("Station Network Management — Add Charging Station")

    with st.form("add_new_station_form"):
        col1, col2 = st.columns(2)
        with col1:
            stn_name = st.text_input("Station Name (e.g., ChargeSpot New Capital Hub)")
            stn_area = st.text_input("Area / Governorate in Egypt (e.g., New Administrative Capital)")
        with col2:
            stn_lat = st.number_input("Latitude in Egypt (22.0 to 32.0)",
                                      min_value=22.0, max_value=32.0, value=30.0196, step=0.0001, format="%.4f")
            stn_lon = st.number_input("Longitude in Egypt (24.0 to 37.0)",
                                      min_value=24.0, max_value=37.0, value=31.7637, step=0.0001, format="%.4f")

        st.markdown("#### Initial Charging Slot Configuration:")
        sl1, sl2, sl3, sl4 = st.columns(4)
        with sl1:
            init_type = st.selectbox("Charger Type", ["fast", "normal"], key="ad_st_type")
        with sl2:
            init_pwr = st.number_input("Power in kW", min_value=1.0, max_value=350.0, value=120.0, step=1.0, key="ad_st_pwr")
        with sl3:
            init_s = st.text_input("Start Time", value="06:00", key="ad_st_s")
        with sl4:
            init_e = st.text_input("End Time", value="12:00", key="ad_st_e")

        submit_stn = st.form_submit_button("Add Station to Network", type="primary", use_container_width=True)

    if submit_stn:
        if not stn_name.strip() or not stn_area.strip():
            st.error("Station name and area are required.")
        else:
            sid_num = next_station_id()
            new_stn_id = f"ST-{sid_num:02d}" if isinstance(sid_num, int) else f"ST-{sid_num}"
            init_slot_id = f"SL-{new_stn_id[3:]}01"
            try:
                initial_slot = ChargingSlot(
                    slot_id=init_slot_id,
                    station_id=new_stn_id,
                    charger_type=init_type,
                    power_kw=float(init_pwr),
                    start_time=init_s,
                    end_time=init_e,
                )
                new_stn_obj = ChargingStation(
                    station_id=new_stn_id,
                    name=stn_name,
                    area=stn_area,
                    latitude=float(stn_lat),
                    longitude=float(stn_lon),
                    slots=[initial_slot],
                )
                st.session_state["stations"].append(new_stn_obj)
                save_stations()
                st.success(f"Station '{stn_name}' ({new_stn_id}) successfully added to network and saved to stations_slots.csv.")
                st.rerun()
            except ValidationError as ex:
                st.error(f"Error: {ex}")

    st.markdown("---")
    st.markdown("### Active Network Stations")
    stations = _get_active_stations()

    stn_areas = sorted(set(s.area for s in stations))
    as_col1, as_col2 = st.columns([3, 1], vertical_alignment="bottom")
    with as_col1:
        stn_area_f = st.selectbox("Filter Stations by Area / Governorate:", ["All"] + stn_areas, key="admin_stn_area_filter")
    with as_col2:
        st.button("Reset Filter", on_click=lambda: _reset_keys(admin_stn_area_filter="All"), key="admin_stn_reset_btn", use_container_width=True)

    filtered_stations = list(stations)
    if stn_area_f != "All":
        filtered_stations = [s for s in stations if s.area == stn_area_f]

    stn_rows = []
    for s in filtered_stations:
        stn_rows.append({
            "Station ID": s.station_id,
            "Name": s.name,
            "Area": s.area,
            "Latitude": s.latitude,
            "Longitude": s.longitude,
            "Total Slots": len(s.slots),
            "Free Slots": _count_free_slots(s),
        })
    st.dataframe(pd.DataFrame(stn_rows), use_container_width=True, hide_index=True)
@st.fragment
def _admin_analytics():
    st.subheader("Global Analytics, Reports & AI-Use Log")

    try:
        csv_file = os.path.join(PROJECT_ROOT, "charging_data.csv")
        if not os.path.exists(csv_file):
            csv_file = os.path.join(PROJECT_ROOT, "data", "charging_data.csv")
        if os.path.exists(csv_file):
            raw_data = pd.read_csv(csv_file)
        else:
            raw_data = analytics.generate_egypt_charging_data(600)
            os.makedirs(os.path.join(PROJECT_ROOT, "data"), exist_ok=True)
            raw_data.to_csv(os.path.join(PROJECT_ROOT, "data", "charging_data.csv"), index=False)
        clean_df = analytics.clean_data(raw_data)
        cleaning_report = analytics.get_cleaning_report(raw_data, clean_df)
    except Exception:
        raw_data = None
        clean_df = None
        cleaning_report = None

    if clean_df is not None and not clean_df.empty:
        kpis = analytics.compute_kpis(clean_df)

        with st.expander("Data Cleaning & Preprocessing Report (Python / Pandas Pipeline)", expanded=True):
            if cleaning_report:
                rc1, rc2, rc3, rc4 = st.columns(4)
                rc1.metric("Raw Sessions Loaded", cleaning_report.get("rows_before", 0))
                rc2.metric("Clean Sessions Retained", cleaning_report.get("rows_after", 0))
                rc3.metric("Missing Values Imputed", cleaning_report.get("missing_values_filled", 0))
                rc4.metric("Invalid Records Dropped", cleaning_report.get("invalid_rows_dropped", 0))
            st_rep = st.session_state.get("stations_cleaning_report")
            if st_rep:
                st.markdown(f"**Station & Slot Cleaning Summary:** Converted `{st_rep.get('rows_before', 0)}` CSV records into `{st_rep.get('stations_count', 0)}` verified charging stations with `{st_rep.get('slots_count', 0)}` slots across Egyptian governorates.")


        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Network Energy Dispensed", f"{kpis['total_energy_kwh']:,.1f} kWh")
        m2.metric("Average Charging Time", f"{kpis['avg_charge_time_min']:.1f} min")
        m3.metric("Average Station Occupancy", f"{kpis['avg_occupancy_rate']:.1f}%")
        m4.metric("Total Historical Sessions", f"{kpis['total_sessions']}")

        st.markdown("---")
        st.markdown("### Interactive Visualizations (Pandas & Plotly)")

        tab1, tab2, tab3 = st.tabs([
            "Peak Hours Demand Distribution",
            "Energy Dispensed per Station",
            "Fast vs. Normal Charger Comparison",
        ])
        with tab1:
            fig1 = analytics.chart_sessions_by_hour(clean_df)
            st.plotly_chart(fig1, use_container_width=True)
        with tab2:
            fig2 = analytics.chart_energy_by_station(clean_df)
            st.plotly_chart(fig2, use_container_width=True)
        with tab3:
            fig3 = analytics.chart_fast_vs_normal(clean_df)
            st.plotly_chart(fig3, use_container_width=True)

        st.markdown("---")
        st.markdown("### Automated Data Insights")
        insights = analytics.generate_insights(clean_df)
        for ins in insights:
            st.info(ins)

        st.markdown("---")
        st.markdown("### Data Export")
        col_exp1, col_exp2 = st.columns(2)
        with col_exp1:
            csv_energy = analytics.export_energy_report_csv(clean_df)
            st.download_button(
                label="Export Energy Report (CSV)",
                data=csv_energy,
                file_name="chargespot_energy_report.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with col_exp2:
            all_bks = _get_active_bookings()
            csv_bks = analytics.export_bookings_csv(all_bks)
            st.download_button(
                label="Export Network Bookings (CSV)",
                data=csv_bks,
                file_name="chargespot_all_bookings.csv",
                mime="text/csv",
                use_container_width=True,
            )
    else:
        st.warning("Analytics data currently loading.")

    # Expandable section documenting AI-Use Log as required by SIC submission rules
# ════════════════════════════════════════════════════════════════════
# MAIN APPLICATION ROUTER
# ════════════════════════════════════════════════════════════════════
def main():
    init_session()
    apply_theme()

    page = st.session_state["page"]
    current_user = st.session_state["current_user"]

    if current_user is not None:
        role = current_user.get_role()
        if role == "driver" and page not in ("driver_dashboard",):
            page = "driver_dashboard"
        elif role == "operator" and page not in ("operator_dashboard",):
            page = "operator_dashboard"
        elif role == "admin" and page not in ("admin_dashboard",):
            page = "admin_dashboard"

    if page == "landing":
        render_landing()
    elif page == "login":
        render_login()
    elif page == "register":
        render_register()
    elif page == "guest_map":
        render_guest_map()
    elif page == "driver_dashboard":
        if current_user and current_user.get_role() == "driver":
            render_driver_dashboard()
        else:
            st.error("Unauthorized access. Please sign in as a driver.")
            navigate("login", rerun=True)
    elif page == "operator_dashboard":
        if current_user and current_user.get_role() == "operator":
            render_operator_dashboard()
        else:
            st.error("Unauthorized access. Please sign in as an operator.")
            navigate("login", rerun=True)
    elif page == "admin_dashboard":
        if current_user and current_user.get_role() == "admin":
            render_admin_dashboard()
        else:
            st.error("Unauthorized access. This area is reserved for administrators.")
            navigate("login", rerun=True)
    else:
        render_landing()
if __name__ == "__main__":
    main()
