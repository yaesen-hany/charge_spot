import os
import json
import re
import hashlib
from models.models import Driver, User, Operator, Admin
import models
from exceptions import (
    ValidationError,
    InvalidPlateFormatError,
    DuplicatePlateError,
    InvalidEnergyValueError,
)

def _resolve_data_path(filename):
    p = os.path.join("data", filename)
    if os.path.exists(p):
        return p
    return filename

USERS_DATA = _resolve_data_path("users.json")
BOOKINGS_DATA = _resolve_data_path("bookings.json")


def load_data(filename):
    path = filename
    if not os.path.exists(path):
        p_data = os.path.join("data", os.path.basename(filename))
        if os.path.exists(p_data):
            path = p_data
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_data(data, filename):
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        return True
    except Exception as e:
        print(f"Error saving data: {e}")
        return False


def validate_name(name):
    if not name or not isinstance(name, str):
        return False
    pattern = r'^[A-Za-z\u0600-\u06FF\s.\-]{2,50}$'
    if not re.match(pattern, name.strip()):
        return False
    return True


def validate_email(email):
    if not email or not isinstance(email, str):
        return False
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(pattern, email.strip()):
        return False
    return True


def check_email(email):
    if not email:
        return False
    users_data = load_data(USERS_DATA)
    clean = str(email).strip().lower()
    for user in users_data:
        u_email = str(user.get("email", "") or "").strip().lower()
        if u_email == clean:
            return False
    return True


def validate_phone(phone):
    if not phone:
        return False
    pattern = r'^01[0125]\d{8}$'
    if not re.match(pattern, str(phone).strip()):
        return False
    return True


def validate_plate(plate):
    if not plate:
        return False
    pattern = r'^[A-Za-z0-9\u0600-\u06FF\- ]{2,15}$'
    if not re.match(pattern, str(plate).strip()):
        return False
    return True


def check_plate(plate, data=USERS_DATA):
    if not plate:
        return False
    users_data = load_data(data)
    clean = str(plate).strip().upper()
    clean_norm = re.sub(r'[\s\-]+', '', clean)
    for user in users_data:
        u_plate = str(user.get("plate_number") or "").strip().upper()
        if not u_plate:
            continue
        u_norm = re.sub(r'[\s\-]+', '', u_plate)
        if clean == u_plate or (clean_norm and clean_norm == u_norm):
            return False
    return True


def validate_password(password):
    if not password or len(str(password)) < 6:
        return False
    return True


def hash_password(password):
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def next_user_id(data=USERS_DATA):
    data = load_data(data)
    max_id = 0
    for u in data:
        uid = u.get("user_id") if isinstance(u, dict) else None
        if isinstance(uid, int):
            max_id = max(max_id, uid)
        elif isinstance(uid, str) and uid.isdigit():
            max_id = max(max_id, int(uid))
    return max_id + 1


def next_booking_id(data=BOOKINGS_DATA):
    data = load_data(data)
    max_id = 0
    for b in data:
        bid = b.get("booking_id") if isinstance(b, dict) else None
        if isinstance(bid, int):
            max_id = max(max_id, bid)
        elif isinstance(bid, str) and bid.isdigit():
            max_id = max(max_id, int(bid))
    return max_id + 1


def register_user(name, email, password, phone, city, plate_number, vehicle_model, battery_capacity_kwh):
    clean_name = str(name).strip() if name else ""
    if not validate_name(clean_name):
        raise ValidationError(value=name, message="Name must be between 2 and 50 characters (letters only).")

    clean_email = str(email).strip() if email else ""
    if not validate_email(clean_email):
        raise ValidationError(value=email, message="Invalid email pattern format.")
    if not check_email(clean_email):
        raise ValidationError(value=email, message="This email is already registered.")

    if not validate_password(password):
        raise ValidationError(message="Password must be at least 6 characters.")

    clean_phone = str(phone).strip() if phone else ""
    if not validate_phone(clean_phone):
        raise ValidationError(value=phone, message="Invalid Egyptian phone number pattern (01[0125]XXXXXXXX).")

    clean_city = str(city).strip() if city else ""
    if not clean_city:
        raise ValidationError(value=city, message="City is required.")

    clean_plate = str(plate_number).strip() if plate_number else ""
    if not validate_plate(clean_plate):
        raise InvalidPlateFormatError(value=plate_number)
    if not check_plate(clean_plate):
        raise DuplicatePlateError(value=plate_number, message="Vehicle plate number is already registered.")

    clean_model = str(vehicle_model).strip() if vehicle_model else ""
    if not clean_model:
        raise ValidationError(value=vehicle_model, message="Vehicle model is required.")

    try:
        battery_kwh = float(battery_capacity_kwh)
        if battery_kwh <= 0:
            raise InvalidEnergyValueError(value=battery_capacity_kwh)
    except (ValueError, TypeError):
        raise InvalidEnergyValueError(value=battery_capacity_kwh)

    new_id = next_user_id()
    new_user = models.Driver(
        new_id,
        clean_name,
        clean_email,
        hash_password(password),
        clean_phone,
        clean_city,
        clean_plate,
        clean_model,
        battery_kwh,
    )
    data = load_data(USERS_DATA)
    user_dict = new_user.to_dict() if hasattr(new_user, "to_dict") else vars(new_user)
    data.append(user_dict)
    save_data(data, USERS_DATA)
    return user_dict


def register_operator(name, email, password, phone, city, station_id):
    clean_name = str(name).strip() if name else ""
    if not validate_name(clean_name):
        raise ValidationError(value=name, message="Name must be between 2 and 50 characters (letters only).")

    clean_email = str(email).strip() if email else ""
    if not validate_email(clean_email):
        raise ValidationError(value=email, message="Invalid email pattern format.")
    if not check_email(clean_email):
        raise ValidationError(value=email, message="This email is already registered.")

    if not validate_password(password):
        raise ValidationError(message="Password must be at least 6 characters.")

    clean_phone = str(phone).strip() if phone else ""
    if not validate_phone(clean_phone):
        raise ValidationError(value=phone, message="Invalid Egyptian phone number pattern (01[0125]XXXXXXXX).")

    clean_city = str(city).strip() if city else ""
    if not clean_city:
        raise ValidationError(value=city, message="City is required.")

    clean_sid = str(station_id).strip() if station_id else ""
    if not clean_sid:
        raise ValidationError(value=station_id, message="Station ID is required.")

    new_id = next_user_id()
    new_op = models.Operator(
        new_id,
        clean_name,
        clean_email,
        hash_password(password),
        clean_phone,
        clean_city,
        clean_sid,
    )
    data = load_data(USERS_DATA)
    op_dict = new_op.to_dict() if hasattr(new_op, "to_dict") else vars(new_op)
    data.append(op_dict)
    save_data(data, USERS_DATA)
    return op_dict


def login(user_id, password):
    data = load_data(USERS_DATA)
    user_password = hash_password(password)
    for user in data:
        uid = user.get("user_id")
        uemail = str(user.get("email", "")).strip().lower()
        if (uid == user_id or str(uid) == str(user_id) or uemail == str(user_id).strip().lower()) and user.get("password") == user_password:
            return True
    return False
