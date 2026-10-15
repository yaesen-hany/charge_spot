class ChargeSpotError(Exception):

    default_message = "Something went wrong."
    default_code = "CS_GEN_000"

    def __init__(self, value=None, message=None, code=None):

        if message is None:
            message = self.default_message
        if code is None:
            code = self.default_code
        if value is not None:
            message = message + " (got: " + str(value) + ")"
        self.message = message
        self.code = code
        self.value = value
        Exception.__init__(self, message)

    def __str__(self):
        return "[" + self.code + "] " + self.message
# ---------------- Validation ----------------
class ValidationError(ChargeSpotError):
    default_message = "Invalid input."
    default_code = "CS_VAL_000"
class InvalidPlateFormatError(ValidationError):
    default_message = "Invalid plate format."
    default_code = "CS_VAL_001"
class DuplicatePlateError(ValidationError):
    default_message = "Vehicle plate number is already registered."
    default_code = "CS_VAL_002"
class InvalidBookingCodeError(ValidationError):
    default_message = "Invalid booking code."
    default_code = "CS_VAL_003"
class InvalidEnergyValueError(ValidationError):
    default_message = "Energy must be a number greater than zero."
    default_code = "CS_VAL_004"
class InvalidTimeFormatError(ValidationError):
    default_message = "Time must be in HH:MM format."
    default_code = "CS_VAL_005"
# ---------------- Booking / Scheduling ----------------
class SlotAlreadyBookedError(ChargeSpotError):
    default_message = "This slot is already booked."
    default_code = "CS_SLOT_001"
class SlotNotFoundError(ChargeSpotError):
    default_message = "Slot not found."
    default_code = "CS_SLOT_002"
class BookingNotFoundError(ChargeSpotError):
    default_message = "Booking not found."
    default_code = "CS_BOOK_001"
class DuplicateBookingError(ChargeSpotError):
    default_message = "This booking already exists."
    default_code = "CS_BOOK_002"
class StationNotFoundError(ChargeSpotError):
    default_message = "Station not found."
    default_code = "CS_STN_001"
class StationFullError(ChargeSpotError):
    default_message = "No free slot at this station."
    default_code = "CS_STN_002"
class BookingLimitExceededError(ChargeSpotError):
    default_message = "Driver booking limit exceeded."
    default_code = "CS_BOOK_003"
# ---------------- Data structures ----------------
class QueueEmptyError(ChargeSpotError):
    default_message = "The queue is empty."
    default_code = "CS_QUE_001"
class EmptyHistoryError(ChargeSpotError):
    default_message = "There is no action to undo."
    default_code = "CS_HIS_001"
# ---------------- Authentication ----------------
class AuthenticationError(ChargeSpotError):
    default_message = "Wrong username or password."
    default_code = "CS_AUTH_001"
class UnauthorizedAccessError(ChargeSpotError):
    default_message = "You do not have permission to open this page."
    default_code = "CS_AUTH_002"
# ---------------- Persistence ----------------
class PersistenceError(ChargeSpotError):
    default_message = "Problem reading or writing a data file."
    default_code = "CS_FILE_001"
class CorruptedDataFileError(PersistenceError):
    default_message = "The data file is corrupted."
    default_code = "CS_FILE_002"