import math

class QueueEmptyError(Exception):
    pass
class StationNotFoundError(Exception):
    pass
class SlotAlreadyBookedError(Exception):
    pass

SLOT_MINUTES = 30
DAY_START = "06:00"
DAY_END = "22:00"
CHARGER_POWER = {"fast": 150.0, "ultra": 350.0, "medium": 50.0, "slow": 22.0}
MAINTENANCE = "MAINT"


class ChargingStation:
    def __init__(self, station_id, charger_type="medium", power_kw=None):
        self.station_id = station_id
        self.charger_type = charger_type
        self.power_kw = power_kw

class BookingRequest:
    def __init__(self, booking_code, energy_kwh=30.0, requested_time="06:00", preferred_charger=None, status="pending"):
        self.booking_code = booking_code
        self.energy_kwh = energy_kwh
        self.requested_time = requested_time
        self.preferred_charger = preferred_charger
        self.status = status

    def complete(self):
        self.status = "completed"

    def cancel(self):
        self.status = "cancelled"

    def confirm(self):
        self.status = "confirmed"

def to_minutes(t):
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def total_slots():
    return (to_minutes(DAY_END) - to_minutes(DAY_START)) // SLOT_MINUTES


def time_to_index(t):
    return (to_minutes(t) - to_minutes(DAY_START)) // SLOT_MINUTES


def index_to_time(i):
    minutes = to_minutes(DAY_START) + i * SLOT_MINUTES
    return "%02d:%02d" % (minutes // 60, minutes % 60)


def station_power(station):
    if station.power_kw:
        return station.power_kw
    return CHARGER_POWER.get(station.charger_type, 50.0)


def slots_needed(energy_kwh, power_kw):
    minutes = energy_kwh / power_kw * 60
    return max(1, math.ceil(minutes / SLOT_MINUTES))


class Node:
    def __init__(self, data):
        self.data = data
        self.next = None


class EVQueue:
    def __init__(self):
        self.head = None
        self.tail = None
        self.size = 0

    def enqueue(self, booking):
        node = Node(booking)
        if self.tail is None:
            self.head = node
        else:
            self.tail.next = node
        self.tail = node
        self.size += 1

    def dequeue(self):
        if self.head is None:
            raise QueueEmptyError("Queue is empty")
        node = self.head
        self.head = node.next
        if self.head is None:
            self.tail = None
        self.size -= 1
        return node.data

    def peek(self):
        if self.head is None:
            raise QueueEmptyError("Queue is empty")
        return self.head.data

    def is_empty(self):
        return self.size == 0

    def __len__(self):
        return self.size

    def __iter__(self):
        current = self.head
        while current:
            yield current.data
            current = current.next


class ScheduleGrid:
    def __init__(self):
        self.stations = {}
        self.cells = {}

    def add_station(self, station):
        self.stations[station.station_id] = station
        self.cells[station.station_id] = [None] * total_slots()

    def get_station(self, station_id):
        if station_id not in self.stations:
            raise StationNotFoundError("Station %s not found" % station_id)
        return self.stations[station_id]

    def is_free(self, station_id, start, k):
        row = self.cells[station_id]
        if start < 0 or start + k > len(row):
            return False
        for i in range(start, start + k):
            if row[i] is not None:
                return False
        return True

    def book(self, station_id, start, k, code):
        self.get_station(station_id)
        if not self.is_free(station_id, start, k):
            raise SlotAlreadyBookedError("Slots already taken")
        for i in range(start, start + k):
            self.cells[station_id][i] = code

    def set_maintenance(self, station_id, slot):
        self.get_station(station_id)
        if self.cells[station_id][slot] is not None:
            raise SlotAlreadyBookedError("Slot already taken")
        self.cells[station_id][slot] = MAINTENANCE

    def cancel(self, code):
        found = False
        for row in self.cells.values():
            for i in range(len(row)):
                if row[i] == code:
                    row[i] = None
                    found = True
        return found

    def first_fit(self, station_id, earliest, k):
        for start in range(earliest, total_slots() - k + 1):
            if self.is_free(station_id, start, k):
                return start
        return None


class GreedyScheduler:
    def __init__(self, stations):
        self.grid = ScheduleGrid()
        for s in stations:
            self.grid.add_station(s)

    def candidate_stations(self, booking):
        stations = list(self.grid.stations.values())
        if booking.preferred_charger:
            chosen = [s for s in stations if s.charger_type == booking.preferred_charger]
            if chosen:
                return chosen
        return stations

    def schedule_one(self, booking):
        earliest = max(0, time_to_index(booking.requested_time))
        best = None
        for station in self.candidate_stations(booking):
            k = slots_needed(booking.energy_kwh, station_power(station))
            start = self.grid.first_fit(station.station_id, earliest, k)
            if start is None:
                continue
            if best is None or start + k < best[1] + best[2]:
                best = (station, start, k)
        if best is None:
            return None
        station, start, k = best
        self.grid.book(station.station_id, start, k, booking.booking_code)
        return {
            "booking_code": booking.booking_code,
            "station_id": station.station_id,
            "start": index_to_time(start),
            "end": index_to_time(start + k),
            "slots": k,
        }

    def run(self, queue):
        scheduled = []
        failed = []
        while not queue.is_empty():
            booking = queue.dequeue()
            result = self.schedule_one(booking)
            if result is None:
                failed.append(booking)
            else:
                scheduled.append(result)
        return scheduled, failed


def check(name, ok):
    print(("PASS  " if ok else "FAIL  ") + name)


def run_tests():
    q = EVQueue()
    for code in ["A", "B", "C"]:
        q.enqueue(BookingRequest(code))
    check("queue size", len(q) == 3)
    check("queue peek", q.peek().booking_code == "A")
    order = [q.dequeue().booking_code for _ in range(3)]
    check("queue FIFO order", order == ["A", "B", "C"])
    try:
        q.dequeue()
        check("dequeue on empty queue", False)
    except QueueEmptyError:
        check("dequeue on empty queue", True)

    check("slots per day", total_slots() == 32)
    check("time to index", time_to_index("07:30") == 3)
    check("index to time", index_to_time(3) == "07:30")
    check("slots needed 30kWh at 50kW", slots_needed(30, 50) == 2)

    grid = ScheduleGrid()
    grid.add_station(ChargingStation("S1"))
    grid.book("S1", 0, 2, "X")
    try:
        grid.book("S1", 1, 2, "Y")
        check("double booking", False)
    except SlotAlreadyBookedError:
        check("double booking", True)
    try:
        grid.get_station("S9")
        check("unknown station", False)
    except StationNotFoundError:
        check("unknown station", True)
    grid.cancel("X")
    check("cancel frees slots", grid.is_free("S1", 0, 2))

    sched = GreedyScheduler([ChargingStation("S1", charger_type="medium")])
    q = EVQueue()
    q.enqueue(BookingRequest("B1", energy_kwh=50, requested_time="06:00"))
    q.enqueue(BookingRequest("B2", energy_kwh=25, requested_time="06:00"))
    done, failed = sched.run(q)
    check("first car starts at 06:00", done[0]["start"] == "06:00")
    check("second car waits for first", done[1]["start"] == "07:00")

    sched = GreedyScheduler([ChargingStation("S1", charger_type="slow"),
                             ChargingStation("S2", charger_type="ultra")])
    q = EVQueue()
    q.enqueue(BookingRequest("B1", energy_kwh=40, requested_time="06:00"))
    q.enqueue(BookingRequest("B2", energy_kwh=40, requested_time="06:00"))
    done, failed = sched.run(q)
    check("faster station chosen", done[0]["station_id"] == "S2")
    check("second car uses free time on S2", done[1]["start"] == "06:30")

    sched = GreedyScheduler([ChargingStation("S1", charger_type="slow")])
    q = EVQueue()
    q.enqueue(BookingRequest("B1", energy_kwh=500, requested_time="06:00"))
    done, failed = sched.run(q)
    check("car that does not fit is rejected", len(done) == 0 and len(failed) == 1)


if __name__ == "__main__":
    run_tests()
