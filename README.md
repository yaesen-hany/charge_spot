# ⚡ ChargeSpot Egypt — Smart EV Charging & Scheduling Infrastructure

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.30%2B-FF4B4B.svg)](https://streamlit.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

An intelligent, full-stack electric vehicle (EV) charging station management, slot scheduling, waitlist optimization, and analytics platform built specifically for Egypt's national EV infrastructure.

---

## 🌟 Key Features

### 1. Role-Based Access Control (RBAC) & Polymorphism
- **EV Drivers**: Search 1,200+ stations across all 27 Egyptian governorates, book charging slots, view live maps with Folium pins, manage active sessions, and interact with the Driver AI Copilot.
- **Station Operators**: Monitor real-time slot hardware telemetry, manage queue congestion via greedy scheduling algorithms, execute O(1) hash table booking lookups, and review interactive station performance analytics.
- **System Administrators**: Oversee national infrastructure, register verified station operators, expand charging networks, and inspect system-wide energy and revenue reports.

### 2. Algorithmic Engineering & Data Structures
- **Greedy Scheduler (`scheduler.py`)**: Real-time slot allocation minimizing total driver turnaround time and avoiding grid overload.
- **O(1) Hash Table (`lookup_engine.py`)**: Custom hash table with open chaining (linked buckets) and dynamic resizing (load factor > 0.75) for instant booking code and license plate verification.
- **Custom Sorting Algorithms (`sorting_engine.py`)**: Implementation of Merge Sort and Quick Sort with benchmark comparisons and an undo action history stack.
- **Data Cleaning Pipeline (`analytics.py`)**: Automated handling of missing values, duplicate detection, and outlier correction across 500+ real-world charging records.

### 3. Smart Driver & Station Validation
- Strict validation for Egyptian phone numbers (`01[0125]XXXXXXXX`).
- Unique vehicle license plate enforcement with case-insensitive and space/hyphen agnostic normalization.
- Selection from the official 27 Egyptian Governorates with geographic coordinate mapping for distance estimation.

---

## 📁 Project Structure

```text
final_project/
├── .streamlit/
│   ├── config.toml               # Custom UI theme configuration
│   └── secrets.toml.example      # Template for Gemini API secrets
├── assets/
│   └── chargespot_bg.jpg         # Hero background graphics
├── data/
│   ├── bookings.json             # Active and confirmed booking records
│   ├── chargespot_state.json     # Golden backup and system state snapshot
│   ├── charging_data.csv         # Historical telemetry and session logs
│   ├── stations_slots.csv        # 1,200 stations and 4,398 charging slots
│   └── users.json                # User accounts (Admin, Operators, Drivers)
├── models/
│   ├── __init__.py
│   └── models.py                 # Pure Python domain entities (OOP)
├── photo/
│   ├── background.jpg            # High-resolution landing artwork
│   └── photo.jpg
├── analytics.py                  # Analytics engine, KPI calculations & Plotly charts
├── app.py                        # Streamlit web application & router
├── auth.py                       # User registration, authentication & validation
├── exceptions.py                 # Custom domain error hierarchy
├── lookup_engine.py              # Hash tables, binary search, and slot indexes
├── scheduler.py                  # Greedy scheduler, EV queue, and time grid
├── sorting_engine.py             # Merge Sort, Quick Sort, and HistoryStack
├── requirements.txt              # Project package dependencies
├── .gitignore                    # Git exclusions (caches, virtual envs, secrets)
└── README.md                     # Project documentation
```

---

## 🚀 Getting Started

### Prerequisites
- Python 3.10, 3.11, or 3.12 installed.

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/your-username/chargespot-egypt.git
   cd chargespot-egypt
   ```

2. **Create and activate a virtual environment (recommended):**
   ```bash
   python -m venv venv
   # On Windows:
   venv\Scripts\activate
   # On macOS/Linux:
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **(Optional) Configure Gemini AI Copilot:**
   Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and add your Google Gemini API key:
   ```toml
   GEMINI_API_KEY = "your_actual_api_key_here"
   ```

5. **Run the application:**
   ```bash
   streamlit run app.py
   ```

---

## 🔑 Demo Accounts

You can sign in with any of the following pre-configured accounts:

| Role | Email | Password | Assigned Scope |
|---|---|---|---|
| **Admin** | `admin@chargespot.com` | `admin123` | National Network Administrator |
| **Operator** | `cairo.op@chargespot.com` | `operator123` | Cairo Festival City Hub (ST-01) |
| **Operator** | `giza.op@chargespot.com` | `operator123` | Carrefour Maadi Hub (ST-02) |
| **Driver** | `omar.khaled@gmail.com` | `driver123` | EV Driver (Plate: ABC-1234) |

*You can also register a new driver account anytime directly from the landing page.*

---

## 📄 License
This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
