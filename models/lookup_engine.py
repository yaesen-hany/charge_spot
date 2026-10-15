import json
import os
from datetime import datetime
import shutil


try:
    from exceptions import BookingNotFoundError, CorruptedDataFileError, PersistenceError
except ImportError:
    class BookingNotFoundError(Exception):
        pass

    class CorruptedDataFileError(Exception):
        pass

    class PersistenceError(Exception):
        pass


class HashTable:
    def __init__(self,size=8):
        self.capacity = size
        self.count = 0
        self.buckets = [[] for _ in range(self.capacity)]

    def normalize_key(self,key):
        return str(key).strip().upper()

    def hash(self,key):
        h = 0
        for ch in str(key):
            h = (h * 31 + ord(ch)) % self.capacity
        return h

    def put(self, key, value):
        key = self.normalize_key(key)
        index = self.hash(key)
        bucket = self.buckets[index]

        for pair in bucket:
            if pair[0] == key:
                pair[1] = value
                return

        bucket.append([key, value])
        self.count += 1

        if self.load_factor() > 0.75:
            self.resize()

    def get(self,key,default=None):
        key = self.normalize_key(key)
        index = self.hash(key)
        bucket = self.buckets[index]
        for pair in bucket:
            if pair[0] == key:
                return pair[1]
        return default

    def remove(self,key):
        key = self.normalize_key(key)
        index = self.hash(key)
        bucket = self.buckets[index]
        for i in range(len(bucket)):
            if bucket[i][0] == key:
                del bucket[i]
                self.count -= 1
                return True
        return False

    def contains(self, key):
        key = self.normalize_key(key)
        index = self.hash(key)
        for pair in self.buckets[index]:
            if pair[0] == key:
                return True
        return False

    def keys(self):
        result = []
        for bucket in self.buckets:
            for pair in bucket:
                result.append(pair[0])
        return result

    def values(self):
        result = []
        for bucket in self.buckets:
            for pair in bucket:
                result.append(pair[1])
        return result

    def items(self):
        result = []
        for bucket in self.buckets:
            for pair in bucket:
                result.append((pair[0],pair[1]))
        return result

    def size(self):
        return self.count

    def load_factor(self):
        return self.count / self.capacity

    def resize(self):
        old_items = self.items()
        self.capacity = self.capacity * 2
        self.buckets = [[] for _ in range(self.capacity)]
        self.count = 0
        for key, value in old_items:
            self.put(key, value)

    def collision_count(self):
        count = 0
        for bucket in self.buckets:
            if len(bucket) > 1:
                count += 1
        return count


def Build_booking(bookings):
    plate_code = HashTable()
    booking_code = HashTable()

    for booking in bookings:
        add_to_index(plate_code,booking_code,booking)
    return plate_code,booking_code

def lookup_plate_code(index, plate):
    result = index.get(plate, [])
    return result if result else []

def lookup_booking_code(index, code):
    booking = index.get(code, None)
    if booking is None:
        raise BookingNotFoundError(f"No booking found with code {code}")
    return booking

def add_to_index(plate_code, booking_code, booking):
    if booking_code.contains(booking.booking_code):
        raise ValueError(f"Booking code {booking.booking_code} is already used")

    plate = booking.driver_plate
    Search = plate_code.get(plate, None)
    if Search is None:
        plate_code.put(plate, [booking])
    else:
        Search.append(booking)

    booking_code.put(booking.booking_code, booking)

def remove_from_index(plate_code, booking_code, booking):
    plate = booking.driver_plate
    Search = plate_code.get(plate, None)
    if Search is not None:
        for i in range(len(Search)):
            if Search[i].booking_code == booking.booking_code:
                del Search[i]
                break

    booking_code.remove(booking.booking_code)


def time_to_minutes(time_str):
    hours, minutes = time_str.split(":")
    return int(hours) * 60 + int(minutes)

def Sorted_time(slots):
    for i in range(len(slots) - 1):
        current_time = time_to_minutes(slots[i].start_time)
        next_time = time_to_minutes(slots[i + 1].start_time)
        if current_time > next_time:
            return False
    return True

def binary_search_slot(sorted_slots, target_time):
    low = 0
    high = len(sorted_slots) - 1
    target_minutes = time_to_minutes(target_time)

    while low <= high:
        mid = (low + high) // 2
        mid_minutes = time_to_minutes(sorted_slots[mid].start_time)

        if mid_minutes == target_minutes:
            return mid
        elif mid_minutes < target_minutes:
            low = mid + 1
        else:
            high = mid - 1

    return -1


def binary_search_next_free(sorted_slots, target_time):
    low = 0
    high = len(sorted_slots)
    target_minutes = time_to_minutes(target_time)

    while low < high:
        mid = (low + high) // 2
        mid_minutes = time_to_minutes(sorted_slots[mid].start_time)
        if mid_minutes < target_minutes:
            low = mid + 1
        else:
            high = mid
    return low

def sequential_search_stations(stations, query, field="name"):
    query = query.strip().lower()
    matches = []

    if query == "":
        return list(stations)

    for station in stations:
        if field == "name":
            if query in station.name.lower():
                matches.append(station)
        elif field == "area":
            if query in station.area.lower():
                matches.append(station)
        elif field == "any":
            if query in station.name.lower() or query in station.area.lower():
                matches.append(station)

    return matches

def sequential_search_by_charger_type(stations, charger_type):
    charger_type = charger_type.strip().lower()
    matches = []
    for station in stations:
        if hasattr(station, "charger_type") and station.charger_type.lower() == charger_type:
            matches.append(station)
    return matches

def sequential_search_free_stations(stations):
    matches = []
    for station in stations:
        for slot in getattr(station, "slots", []):
            if getattr(slot, "booking_code", None) is None:
                matches.append(station)
                break
    return matches









###### JSON PART ######
data_dir = "data"
STATE_FILE = os.path.join(data_dir, "chargespot_state.json")


def save_to_json(state, filepath=STATE_FILE):
    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)

    temp_path = filepath + ".tmp"
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(temp_path, filepath)
    except OSError as e:
        raise PersistenceError(f"Could not save data: {e}")

def load_from_json(filepath=STATE_FILE):
    if not os.path.exists(filepath):
        return {
            "version": 1,
            "saved_at": None,
            "stations": [],
            "bookings": [],
            "queue_codes": [],
            "grid": {},
        }

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        raise CorruptedDataFileError(f"Data file is corrupted: {e}")

    return data

def serialize_state(stations, bookings, queue_items, grid, users=None):
    return {
        "version": 1,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "stations": [s.to_dict() for s in stations],
        "bookings": [b.to_dict() for b in bookings],
        "queue_codes": [item.booking_code for item in queue_items],
        "grid": grid,
        "users": [u.to_dict() for u in users] if users else [],
    }

def deserialize_state(raw, StationClass=None, BookingClass=None):
    if StationClass is not None:
        stations = [StationClass.from_dict(s) for s in raw.get("stations", [])]
    else:
        stations = raw.get("stations", [])

    if BookingClass is not None:
        bookings = [BookingClass.from_dict(b) for b in raw.get("bookings", [])]
    else:
        bookings = raw.get("bookings", [])

    return {
        "stations": stations,
        "bookings": bookings,
        "queue_codes": raw.get("queue_codes", []),
        "grid": raw.get("grid", {}),
    }


def save_stations_to_csv(stations, csv_path=None):
    """Serialize stations and their slots directly to stations_slots.csv."""
    import pandas as pd
    if csv_path is None:
        csv_path = os.path.join("data", "stations_slots.csv") if os.path.exists("data") else "stations_slots.csv"
    rows = []
    for s in stations:
        if isinstance(s, dict):
            s_id = s.get("station_id")
            name = s.get("name")
            area = s.get("area")
            lat = s.get("latitude")
            lon = s.get("longitude")
            slots = s.get("slots", [])
        else:
            s_id = getattr(s, "station_id", "")
            name = getattr(s, "name", "")
            area = getattr(s, "area", "")
            lat = getattr(s, "latitude", 0.0)
            lon = getattr(s, "longitude", 0.0)
            slots = getattr(s, "slots", [])

        for sl in slots:
            if isinstance(sl, dict):
                slot_id = sl.get("slot_id")
                ctype = sl.get("charger_type")
                power = sl.get("power_kw")
                start = sl.get("start_time")
                end = sl.get("end_time")
                status = sl.get("status")
            else:
                slot_id = getattr(sl, "slot_id", "")
                ctype = getattr(sl, "charger_type", "")
                power = getattr(sl, "power_kw", 0.0)
                start = getattr(sl, "start_time", "")
                end = getattr(sl, "end_time", "")
                status = getattr(sl, "status", "free")

            rows.append({
                "station_id": s_id,
                "name": name,
                "area": area,
                "latitude": lat,
                "longitude": lon,
                "slot_id": slot_id,
                "charger_type": ctype,
                "power_kw": power,
                "start_time": start,
                "end_time": end,
                "status": status,
            })

    df = pd.DataFrame(rows)
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    return True


def next_station_id(csv_path=None):
    """Calculate the next sequential station number from CSV."""
    target_path = csv_path or (os.path.join("data", "stations_slots.csv") if os.path.exists("data") else "stations_slots.csv")
    if os.path.exists(target_path):
        try:
            import pandas as pd, re
            df = pd.read_csv(target_path, encoding="utf-8-sig")
            st_ids = df["station_id"].dropna().astype(str).tolist()
            max_num = 0
            for sid in st_ids:
                m = re.search(r"\d+", sid)
                if m:
                    max_num = max(max_num, int(m.group()))
            return max_num + 1
        except Exception:
            pass
    return 1


def next_slot_id(station_id="ST-01", csv_path=None):
    """Calculate the next slot number for a specific station."""
    target_path = csv_path or (os.path.join("data", "stations_slots.csv") if os.path.exists("data") else "stations_slots.csv")
    if os.path.exists(target_path):
        try:
            import pandas as pd, re
            df = pd.read_csv(target_path, encoding="utf-8-sig")
            stn_slots = df[df["station_id"] == station_id]["slot_id"].dropna().astype(str).tolist()
            max_num = 0
            for sl in stn_slots:
                m = re.search(r"\d+", sl)
                if m:
                    max_num = max(max_num, int(m.group()))
            return max_num + 1
        except Exception:
            pass
    return 1
