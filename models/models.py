from datetime import datetime

from exceptions import (
    InvalidPlateFormatError,
    InvalidBookingCodeError,
    InvalidEnergyValueError,
    InvalidTimeFormatError,
    ValidationError,
    SlotAlreadyBookedError,
    SlotNotFoundError,
    StationFullError,
    BookingLimitExceededError,)
class User:
    def __init__(self, user_id, name, email, password, phone, city, role="user"):
        import re
        if email:
            email_pattern = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
            if not email_pattern.match(str(email).strip()):
                raise ValidationError(value=email, message="Invalid email pattern format.")
        if phone:
            phone_pattern = re.compile(r"^01[0125]\d{8}$")
            if not phone_pattern.match(str(phone).strip()):
                raise ValidationError(value=phone, message="Invalid Egyptian phone number pattern.")

        self.__user_id = user_id
        self.__name = name
        self.__email = email
        self.__phone = phone
        self.__password = password    
        self.__city = city
        self.__role = role

    def name(self):
        return self.__name

    def role(self):
        return self.__role

    @property
    def city(self):
        return self.__city

    @property
    def user_id(self):
        return self.__user_id

    @property
    def email(self):
        return self.__email

    def to_dict(self):
        return {
            "user_id": self.__user_id,
            "name": self.__name,
            "email": self.__email,
            "phone": self.__phone,
            "password": self.__password,
            "city": self.__city,
            "role": self.__role,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(**data)

    def get_role(self):
        return self.__role

    def get_dashboard_title(self):
        return "User Dashboard"

    def __str__(self):
        return f"{self.__name} ({self.__role})"
class Driver(User):
    def __init__(self, user_id, name, email, password, phone, city, plate_number, vehicle_model,
                 battery_capacity_kwh, role="driver"):
        super().__init__(user_id, name, email, password, phone, city, "driver")
        import re
        plate_str = str(plate_number).strip() if plate_number is not None else ""
        plate_pattern = re.compile(r"^[A-Za-z0-9\u0600-\u06FF\- ]{2,15}$")
        if not plate_pattern.match(plate_str):
            raise InvalidPlateFormatError(value=plate_number)

        self.plate_number = plate_str
        self.vehicle_model = vehicle_model
        self.battery_capacity_kwh = float(battery_capacity_kwh) if battery_capacity_kwh is not None else 0.0

    def to_dict(self):
        d = super().to_dict()
        d["plate_number"] = self.plate_number
        d["vehicle_model"] = self.vehicle_model
        d["battery_capacity_kwh"] = self.battery_capacity_kwh
        return d

    def get_dashboard_title(self):
        return "Driver Dashboard"

    def __str__(self):
        return f"Driver {self.name()} ({self.plate_number})"
class Operator(User):
    def __init__(self, user_id, name, email, password, phone, city, station_id, role="operator"):
        super().__init__(user_id, name, email, password, phone, city, "operator")
        sid_str = str(station_id).strip() if station_id is not None else ""
        if not sid_str:
            raise ValidationError(value=station_id, message="Station ID is required for Operator.")
        self.station_id = sid_str

    def to_dict(self):
        d = super().to_dict()
        d["station_id"] = self.station_id
        return d

    def get_dashboard_title(self):
        return "Operator Dashboard"

    def __str__(self):
        return f"Operator {self.name()} (Station {self.station_id})"
class Admin(User):
    def __init__(self, user_id, name, email, password, phone, city, role="admin"):
        super().__init__(user_id, name, email, password, phone, city, "admin")

    def to_dict(self):
        return super().to_dict()

    def get_dashboard_title(self):
        return "Admin Dashboard"

    def __str__(self):
        return f"Admin {self.name()}"
class ChargingSlot:
    CHARGER_TYPES = {"fast", "normal"}
    STATUSES = {"free", "booked", "maintenance"}

    def __init__(self, slot_id, station_id, charger_type, power_kw, start_time, end_time,
                 status="free"):

        if charger_type not in self.CHARGER_TYPES:
            raise ValidationError(value=charger_type,
                                  message="Charger type must be 'fast' or 'normal'.")
        if not isinstance(power_kw, (int, float)) or power_kw <= 0:
            raise InvalidEnergyValueError(value=power_kw)
        if status not in self.STATUSES:
            raise ValidationError(value=status,
                                  message="Slot status must be 'free', 'booked', or 'maintenance'.")

        import re
        time_pattern = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
        if not time_pattern.match(str(start_time)):
            raise InvalidTimeFormatError(value=start_time)
        if not time_pattern.match(str(end_time)):
            raise InvalidTimeFormatError(value=end_time)

        self.slot_id = slot_id
        self.station_id = station_id
        self.charger_type = charger_type
        self.power_kw = power_kw
        self.start_time = start_time
        self.end_time = end_time
        self.status = status

    def is_free(self):
        return self.status == "free"

    def book(self):
        if not self.is_free():
            raise SlotAlreadyBookedError(value=self.slot_id)
        self.status = "booked"

    def release(self):
        if self.status == "booked":
            self.status = "free"

    def to_dict(self):
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, data):
        return cls(**data)
class ChargingStation:
    def __init__(self, station_id, name, area, latitude, longitude, slots=None):
        self.station_id = station_id
        self.name = name
        self.area = area
        self.latitude = latitude
        self.longitude = longitude
        self.slots = [slot if isinstance(slot, ChargingSlot) else ChargingSlot.from_dict(slot)
                      for slot in (slots or [])]

    def add_slot(self, slot):
        if not isinstance(slot, ChargingSlot):
            raise ValidationError(value=type(slot).__name__,
                                  message="slot must be a ChargingSlot instance.")
        self.slots.append(slot)

    def find_slot_by_id(self, slot_id):
        for slot in self.slots:
            if slot.slot_id == slot_id:
                return slot
        raise SlotNotFoundError(value=slot_id)

    def get_free_slots(self):
        free = [slot for slot in self.slots if slot.is_free()]
        if not free:
            raise StationFullError(value=self.station_id)
        return free

    def to_dict(self):
        return {
            "station_id": self.station_id,
            "name": self.name,
            "area": self.area,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "slots": [slot.to_dict() for slot in self.slots],
        }

    @classmethod
    def from_dict(cls, data):
        return cls(**data)
class BookingRequest:
    STATUSES = {"pending", "confirmed", "cancelled", "completed"}

    def __init__(self, booking_code, driver_plate, station_id, slot_id, requested_time,
                 energy_kwh, status="pending", date_time=None, **kwargs):

        import re

        if not booking_code or not isinstance(booking_code, str):
            raise InvalidBookingCodeError(value=booking_code)

        plate_pattern = re.compile(r"^[A-Za-z0-9\u0600-\u06FF\- ]{2,15}$")
        if not plate_pattern.match(str(driver_plate).strip()):
            raise InvalidPlateFormatError(value=driver_plate)

        if not isinstance(energy_kwh, (int, float)) or energy_kwh <= 0:
            raise InvalidEnergyValueError(value=energy_kwh)

        time_pattern = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
        if not time_pattern.match(str(requested_time)):
            raise InvalidTimeFormatError(value=requested_time)

        if status not in self.STATUSES:
            raise ValidationError(
                value=status,
                message="Booking status must be 'pending', 'confirmed', 'cancelled', or 'completed'.")

        self.booking_code = booking_code
        self.driver_plate = driver_plate
        self.station_id = station_id
        self.slot_id = slot_id
        self.requested_time = requested_time
        self.energy_kwh = energy_kwh
        self.status = status
        self.date_time = date_time if date_time else datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def complete(self):
        self.status = "completed"

    def cancel(self):
        self.status = "cancelled"

    def confirm(self):
        self.status = "confirmed"

    def to_dict(self):
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, data):
        return cls(**data)