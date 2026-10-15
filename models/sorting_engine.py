
import time
import random

from exceptions import (
    EmptyHistoryError,
    BookingNotFoundError,
    ValidationError,
    InvalidEnergyValueError,
)

SUPPORTED_FIELDS = [
    "requested_time",
    "created_at",
    "energy_kwh",
    "driver_plate",
    "booking_code",
]


# =====================================================================
# Helpers
# =====================================================================
def get_field(booking, field):
    """بيقرأ field من booking سواء كان dictionary أو object."""
    if isinstance(booking, dict):
        val = booking.get(field)
        if val is None and field in ("created_at", "date_time"):
            val = booking.get("date_time") or booking.get("created_at")
        return val
    val = getattr(booking, field, None)
    if val is None and field in ("created_at", "date_time"):
        val = getattr(booking, "date_time", None) or getattr(booking, "created_at", None)
    return val


def make_action(action_type, booking, slots):
    return {"type": action_type, "booking": booking, "slots": slots}


# =====================================================================
# 1) HistoryStack
# =====================================================================
class HistoryStack:
    def __init__(self, max_size=100):
        self.max_size = max_size
        self._items = []

    def push(self, action):
        self._items.append(action)
        if len(self._items) > self.max_size:
            self._items.pop(0)

    def pop(self):
        if self.is_empty():
            raise EmptyHistoryError()
        return self._items.pop()

    def peek(self):
        if self.is_empty():
            raise EmptyHistoryError()
        return self._items[-1]

    def is_empty(self):
        return len(self._items) == 0

    def size(self):
        return len(self._items)

    def clear(self):
        self._items = []

    def to_list(self):
        return self._items[::-1]

    def undo_last_booking(self, bookings, schedule_grid, free_value=None):
        action = self.peek()
        action_type = action["type"]
        booking = action["booking"]
        slots = action.get("slots", [])
        code = get_field(booking, "booking_code")

        if action_type in ("BOOK", "ASSIGN"):
            self._remove_booking(bookings, code)
            for slot in slots:
                row, col = slot
                schedule_grid[row][col] = free_value
        elif action_type == "CANCEL":
            bookings.append(booking)
            for slot in slots:
                row, col = slot
                schedule_grid[row][col] = code
        else:
            raise ValidationError(action_type, message="Unknown action type.")

        self.pop()
        return action

    def _remove_booking(self, bookings, code):
        for i in range(len(bookings)):
            if get_field(bookings[i], "booking_code") == code:
                bookings.pop(i)
                return
        raise BookingNotFoundError(code)


# =====================================================================
# 2) SortStats
# =====================================================================
class SortStats:
    def __init__(self, algorithm="", input_size=0):
        self.algorithm = algorithm
        self.input_size = input_size
        self.comparisons = 0
        self.recursive_calls = 0
        self.swaps_or_merges = 0
        self.elapsed_ms = 0.0

    def to_dict(self):
        return {
            "algorithm": self.algorithm,
            "input_size": self.input_size,
            "comparisons": self.comparisons,
            "recursive_calls": self.recursive_calls,
            "swaps_or_merges": self.swaps_or_merges,
            "elapsed_ms": round(self.elapsed_ms, 4),
        }

    def __str__(self):
        return (self.algorithm + ": n=" + str(self.input_size)
                + ", comparisons=" + str(self.comparisons)
                + ", calls=" + str(self.recursive_calls)
                + ", time=" + str(round(self.elapsed_ms, 3)) + " ms")


def _identity(x):
    return x


# =====================================================================
# 3(a) Merge Sort
# =====================================================================
def merge_sort(items, key=None, reverse=False, stats=None):
    if key is None:
        key = _identity
    if stats is None:
        stats = SortStats()
    stats.algorithm = "Merge Sort"
    stats.input_size = len(items)

    # نعمل نسخة عشان نحافظ على اللستة الأصلية
    arr = list(items)
    start = time.perf_counter()
    if len(arr) > 1:
        _merge_sort_rec(arr, 0, len(arr) - 1, key, reverse, stats)
    stats.elapsed_ms = (time.perf_counter() - start) * 1000
    return arr, stats


def _merge_sort_rec(S, low, high, key, reverse, stats):
    stats.recursive_calls += 1
    if low < high:
        mid = (low + high) // 2
        _merge_sort_rec(S, low, mid, key, reverse, stats)
        _merge_sort_rec(S, mid + 1, high, key, reverse, stats)
        _merge_2(S, low, mid, high, key, reverse, stats)


def _merge_2(S, low, mid, high, key, reverse, stats):
    stats.swaps_or_merges += 1
    R = []
    i = low
    j = mid + 1

    while i <= mid and j <= high:
        stats.comparisons += 1
        val_i = key(S[i])
        val_j = key(S[j])

        if reverse:
            take_left = val_i >= val_j
        else:
            take_left = val_i <= val_j

        if take_left:
            R.append(S[i])
            i += 1
        else:
            R.append(S[j])
            j += 1

    if i > mid:
        for k in range(j, high + 1):
            R.append(S[k])
    else:
        for k in range(i, mid + 1):
            R.append(S[k])

    for k in range(len(R)):
        S[low + k] = R[k]


# =====================================================================
# 3b) Quick Sort
# =====================================================================
def quick_sort(items, key=None, reverse=False, stats=None):
    if key is None:
        key = _identity
    if stats is None:
        stats = SortStats()
    stats.algorithm = "Quick Sort"
    stats.input_size = len(items)

    arr = list(items)
    start = time.perf_counter()
    if len(arr) > 1:
        _quick_sort_rec(arr, 0, len(arr) - 1, key, reverse, stats)
    stats.elapsed_ms = (time.perf_counter() - start) * 1000
    return arr, stats


def _quick_sort_rec(S, low, high, key, reverse, stats):
    stats.recursive_calls += 1
    if low < high:
        pivot_point = _partition_2(S, low, high, key, reverse, stats)
        _quick_sort_rec(S, low, pivot_point - 1, key, reverse, stats)
        _quick_sort_rec(S, pivot_point + 1, high, key, reverse, stats)


def _partition_2(S, low, high, key, reverse, stats):
    ran = random.randint(low, high)
    S[low], S[ran] = S[ran], S[low]

    pivot = key(S[low])
    left = low
    right = high

    stats.swaps_or_merges += 1
    while left < right:
        while left < high:
            stats.comparisons += 1
            val_left = key(S[left])
            if reverse:
                condition = val_left >= pivot
            else:
                condition = val_left <= pivot
            if condition:
                left += 1
            else:
                break

        while right > low:
            stats.comparisons += 1
            val_right = key(S[right])
            if reverse:
                condition = val_right <= pivot
            else:
                condition = val_right >= pivot
            if condition:
                right -= 1
            else:
                break

        if left < right:
            S[left], S[right] = S[right], S[left]

    S[low], S[right] = S[right], S[low]
    return right


# =====================================================================
# 4) sort_bookings
# =====================================================================
def _make_key(field):
    if field == "energy_kwh":
        def energy_key(booking):
            value = get_field(booking, field)
            try:
                return float(value)
            except (TypeError, ValueError):
                raise InvalidEnergyValueError(value)

        return energy_key

    def text_key(booking):
        val = get_field(booking, field)
        return str(val).lower() if val is not None else ""

    return text_key


def sort_bookings(bookings, field, algorithm="merge", reverse=False):
    if field not in SUPPORTED_FIELDS:
        raise ValidationError(field, message="Unsupported sort field.")
    if algorithm not in ("merge", "quick"):
        raise ValidationError(algorithm, message="Unknown sorting algorithm.")

    present = []
    missing = []
    for booking in bookings:
        if get_field(booking, field) is None:
            missing.append(booking)
        else:
            present.append(booking)

    key = _make_key(field)
    for booking in present:
        key(booking)

    if algorithm == "merge":
        sorted_part, stats = merge_sort(present, key, reverse)
    else:
        sorted_part, stats = quick_sort(present, key, reverse)

    return sorted_part + missing, stats

"""
الي هيستخدمها يستخدمها كدا 

from sorting_engine import sort_bookings

sorted_list, stats = sort_bookings(bookings, field="energy_kwh", algorithm="merge", reverse=False)

sorted_list, stats = sort_bookings(bookings, field="requested_time", algorithm="quick", reverse=True)
"""