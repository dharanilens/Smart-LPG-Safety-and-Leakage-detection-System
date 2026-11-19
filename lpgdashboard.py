import os
import time
import json
import sqlite3
import queue
import threading
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError

import pandas as pd
import plotly.express as px
import streamlit as st

# =========================================================
# SMART LPG AND GAS LEAKAGE DETECTION DASHBOARD
# MATCHED EXACTLY TO REFERENCE UI DESIGN SYSTEM
# =========================================================

APP_DIR = Path(__file__).parent
DB_PATH = APP_DIR / "lpg_events.db"

st.set_page_config(
    page_title="Smart LPG Safety Dashboard",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ----------------------- DESIGN & CSS --------------------------

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Manrope:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"] {
    font-family: 'Manrope', sans-serif;
    color: #e2e8f0;
}

/* Exact Deep Navy Theme Background */
.stApp {
    background: #070b14;
    background-image: 
        radial-gradient(at 0% 0%, rgba(22, 38, 59, 0.3) 0px, transparent 50%),
        radial-gradient(at 100% 100%, rgba(10, 18, 32, 0.4) 0px, transparent 50%);
}

.block-container {
    padding-top: 1.2rem;
    padding-left: 1.8rem;
    padding-right: 1.8rem;
    max-width: 1560px;
}

/* Sidebar Styling */
[data-testid="stSidebar"] {
    background: #090f1d !important;
    border-right: 1px solid #17223b;
}

[data-testid="stSidebar"] .stRadio div {
    gap: 6px;
}

/* Metric Cards Styling */
[data-testid="stMetric"] {
    background: linear-gradient(145deg, #0d1626, #090e18);
    border: 1px solid #1a2a46;
    padding: 16px 20px;
    border-radius: 14px;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
}

[data-testid="stMetricLabel"] {
    color: #8a9bb8 !important;
    font-size: 11px !important;
    font-weight: 700 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.8px !important;
}

[data-testid="stMetricValue"] {
    color: #f1f5f9 !important;
    font-size: 24px !important;
    font-weight: 800 !important;
    font-family: 'Manrope', sans-serif;
}

[data-testid="stMetricDelta"] {
    font-size: 11px !important;
}

/* Hero Header Panel */
.hero {
    padding: 22px 26px;
    border: 1px solid #1a2a46;
    border-radius: 16px;
    background: linear-gradient(110deg, rgba(13, 22, 38, 0.95), rgba(9, 14, 24, 0.9));
    margin-bottom: 22px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
}

.eyebrow {
    color: #00e5ff;
    letter-spacing: 1.8px;
    font-size: 10px;
    font-weight: 800;
    text-transform: uppercase;
}

.hero h1 {
    font-size: 26px;
    margin: 4px 0 2px;
    color: #ffffff;
    font-weight: 800;
}

.hero p {
    color: #8a9bb8;
    margin: 0;
    font-size: 13px;
}

/* Content Panels */
.panel {
    background: #0d1626;
    border: 1px solid #1a2a46;
    border-radius: 14px;
    padding: 18px 20px;
    min-height: 105px;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
}

.panel-sub {
    font-size: 12px;
    color: #8a9bb8;
    margin-top: 4px;
}

/* Status Badges / Pills */
.status-pill {
    display: inline-block;
    padding: 4px 10px;
    border-radius: 20px;
    font-size: 10px;
    font-weight: 800;
    letter-spacing: 0.8px;
    text-transform: uppercase;
}

.good {
    background: rgba(16, 185, 129, 0.15);
    color: #34d399;
    border: 1px solid rgba(16, 185, 129, 0.35);
}

.warn {
    background: rgba(245, 158, 11, 0.15);
    color: #fbbf24;
    border: 1px solid rgba(245, 158, 11, 0.35);
}

.danger {
    background: rgba(239, 68, 68, 0.15);
    color: #f87171;
    border: 1px solid rgba(239, 68, 68, 0.35);
}

.small-note {
    color: #64748b;
    font-size: 11px;
}

/* Buttons */
div.stButton > button {
    border-radius: 8px;
    font-weight: 700;
    background-color: #17253d;
    color: #f1f5f9;
    border: 1px solid #283d60;
    transition: all 0.2s ease;
}

div.stButton > button:hover {
    background-color: #203354;
    border-color: #00e5ff;
}

hr {
    border-color: #1a2a46;
}

/* Dataframe styling */
[data-testid="stDataFrame"] {
    border: 1px solid #1a2a46;
    border-radius: 12px;
    overflow: hidden;
}
</style>
""", unsafe_allow_html=True)


# ----------------------- DATABASE ------------------------

def init_db():
    with sqlite3.connect(DB_PATH) as con:
        con.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            node_id TEXT,
            severity TEXT,
            sensor_raw REAL,
            gas_ppm REAL,
            message TEXT,
            valve TEXT,
            fan TEXT,
            buzzer TEXT
        )
        """)
        con.execute("""
        CREATE TABLE IF NOT EXISTS telemetry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            node_id TEXT,
            sensor_raw REAL,
            gas_ppm REAL,
            severity TEXT,
            valve TEXT,
            fan TEXT,
            buzzer TEXT,
            wifi_rssi REAL,
            battery_pct REAL,
            power_source TEXT,
            sensor_ok INTEGER
        )
        """)
        con.execute("""
        CREATE TABLE IF NOT EXISTS notification_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            channel TEXT NOT NULL,
            recipient TEXT,
            node_id TEXT,
            gas_ppm REAL,
            status TEXT NOT NULL,
            detail TEXT,
            message TEXT
        )
        """)
        con.execute("""
        CREATE TABLE IF NOT EXISTS notification_state (
            node_id TEXT PRIMARY KEY,
            alarm_active INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            alert_count INTEGER NOT NULL DEFAULT 0,
            last_sent_epoch REAL NOT NULL DEFAULT 0
        )
        """)
        # Migrate databases created by earlier dashboard versions.
        columns = {row[1] for row in con.execute("PRAGMA table_info(notification_state)")}
        if "alert_count" not in columns:
            con.execute("ALTER TABLE notification_state ADD COLUMN alert_count INTEGER NOT NULL DEFAULT 0")
        if "last_sent_epoch" not in columns:
            con.execute("ALTER TABLE notification_state ADD COLUMN last_sent_epoch REAL NOT NULL DEFAULT 0")

init_db()

def utc_now():
    # Millisecond precision prevents 5 Hz serial packets from being deduplicated.
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")

def insert_telemetry(data):
    with sqlite3.connect(DB_PATH) as con:
        timestamp = data.get("timestamp", utc_now())
        node = str(data.get("node_id", "NODE-01"))

        exists = con.execute(
            "SELECT 1 FROM telemetry WHERE timestamp=? AND node_id=? LIMIT 1",
            (timestamp, node)
        ).fetchone()

        if exists:
            return

        severity = str(data.get("severity", "NORMAL")).upper()
        sensor_raw = float(data.get("sensor_raw", 0))

        con.execute("""
        INSERT INTO telemetry (
            timestamp, node_id, sensor_raw, gas_ppm, severity,
            valve, fan, buzzer, wifi_rssi, battery_pct, power_source, sensor_ok
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            timestamp, node, sensor_raw, data.get("gas_ppm"), severity,
            str(data.get("valve", "UNKNOWN")), str(data.get("fan", "UNKNOWN")),
            str(data.get("buzzer", "UNKNOWN")), data.get("wifi_rssi"),
            data.get("battery_pct"), str(data.get("power_source", "UNKNOWN")),
            1 if data.get("sensor_ok", True) else 0
        ))

        if severity in ("WARNING", "CRITICAL", "SENSOR_FAULT"):
            con.execute("""
            INSERT INTO events (
                timestamp, node_id, severity, sensor_raw, gas_ppm, message, valve, fan, buzzer
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                timestamp, node, severity, sensor_raw, data.get("gas_ppm"),
                str(data.get("message", "Threshold event reported by controller")),
                str(data.get("valve", "UNKNOWN")), str(data.get("fan", "UNKNOWN")),
                str(data.get("buzzer", "UNKNOWN"))
            ))

def config_value(name, section_name=None):
    """Read a setting from environment variables or Streamlit secrets."""
    value = os.getenv(name, "").strip()
    if value:
        return value
    try:
        if name in st.secrets:
            return str(st.secrets[name]).strip()
        if section_name:
            section = st.secrets.get(section_name, {})
            # Map TELEGRAM_BOT_TOKEN -> [telegram].bot_token
            prefix = section_name.lower() + "_"
            short_name = name.lower()
            if short_name.startswith(prefix):
                short_name = short_name[len(prefix):]
            return str(section.get(short_name, section.get(name, ""))).strip()
    except Exception:
        pass
    return ""


def get_telegram_settings():
    return {
        "bot_token": config_value("TELEGRAM_BOT_TOKEN", "telegram"),
        "chat_id": config_value("TELEGRAM_CHAT_ID", "telegram"),
    }


def telegram_api(method, bot_token, data=None):
    """Call the Telegram Bot API using Python's standard library."""
    if not bot_token:
        raise ValueError("Telegram bot token is missing. Add it to .streamlit/secrets.toml.")
    url = f"https://api.telegram.org/bot{bot_token}/{method}"
    body = urlencode(data or {}).encode("utf-8")
    request = Request(url, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urlopen(request, timeout=15) as response:
            import json
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        error_body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Telegram API HTTP {error.code}: {error_body[:400]}") from error
    except (URLError, TimeoutError) as error:
        raise RuntimeError(f"Could not reach Telegram API: {error}") from error
    if not result.get("ok"):
        raise RuntimeError(str(result.get("description", "Telegram API returned an error")))
    return result.get("result", {})


def send_telegram_message(bot_token, chat_id, message):
    if not str(chat_id).strip():
        raise ValueError("Enter your Telegram chat ID in the dashboard sidebar.")
    return telegram_api("sendMessage", bot_token, {
        "chat_id": str(chat_id).strip(),
        "text": message,
        "disable_web_page_preview": "true",
    })

def add_notification_log(channel, recipient, node_id, gas_ppm, status, detail, message):
    # Keep only a masked destination in the dashboard history.
    destination = str(recipient or "")
    masked = (destination[:3] + "••••" + destination[-3:]) if len(destination) > 7 else destination
    with sqlite3.connect(DB_PATH) as con:
        con.execute("""
            INSERT INTO notification_history
            (timestamp, channel, recipient, node_id, gas_ppm, status, detail, message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (utc_now(), channel, masked, node_id, gas_ppm, status, str(detail)[:500], message))

@st.cache_resource
def telegram_dispatcher():
    """One background worker keeps Telegram network calls out of the UI/serial loop."""
    work_queue = queue.Queue(maxsize=10000)

    def worker():
        while True:
            task = work_queue.get()
            try:
                result = send_telegram_message(task["token"], task["chat_id"], task["message"])
                add_notification_log(
                    "Telegram", task["chat_id"], task["node_id"], task["gas_ppm"],
                    "ACCEPTED",
                    f"Telegram API accepted message (message_id: {result.get('message_id', 'unknown')}).",
                    task["message"]
                )
            except Exception as error:
                add_notification_log(
                    "Telegram", task["chat_id"], task["node_id"], task["gas_ppm"],
                    "FAILED", str(error), task["message"]
                )
            finally:
                work_queue.task_done()

    thread = threading.Thread(target=worker, name="telegram-notification-worker", daemon=True)
    thread.start()
    return work_queue


def maybe_send_alert_notification(payload):
    """Send one Telegram alert for each group of 3 consecutive critical readings.

    A normal reading resets the consecutive-reading counter. During a sustained
    critical condition, alerts are sent on readings 3, 6, 9, and so on.
    """
    node_id = str(payload.get("node_id", "ESP32-01"))
    try:
        gas_ppm = float(payload.get("gas_ppm"))
    except (TypeError, ValueError):
        return

    is_critical = gas_ppm > 10000.0
    # Persist the counter in SQLite so Streamlit reruns do not reset it.
    with sqlite3.connect(DB_PATH) as con:
        con.execute("""
            INSERT OR IGNORE INTO notification_state
                (node_id, alarm_active, updated_at, alert_count, last_sent_epoch)
            VALUES (?, 0, ?, 0, 0)
        """, (node_id, utc_now()))
        if is_critical:
            con.execute("""
                UPDATE notification_state
                SET alarm_active = 1, alert_count = alert_count + 1, updated_at = ?
                WHERE node_id = ?
            """, (utc_now(), node_id))
            consecutive_count = con.execute(
                "SELECT alert_count FROM notification_state WHERE node_id = ?", (node_id,)
            ).fetchone()[0]
        else:
            con.execute("""
                UPDATE notification_state
                SET alarm_active = 0, alert_count = 0, updated_at = ?
                WHERE node_id = ?
            """, (utc_now(), node_id))
            return

    # Notify only on every third consecutive critical reading: 3, 6, 9, ...
    if consecutive_count % 3 != 0:
        return

    settings = st.session_state.get("notification_config", {})
    if not settings.get("enabled"):
        return

    raw_recipients = str(settings.get("chat_id", "")).replace(";", ",")
    recipients = [item.strip() for item in raw_recipients.split(",") if item.strip()]
    token = get_telegram_settings().get("bot_token", "")

    message = (
        "🚨 SMART LPG SAFETY ALERT — 3 CONSECUTIVE CRITICAL READINGS\n"
        f"Node: {node_id}\n"
        f"Latest estimated gas reading: {gas_ppm:.1f} PPM\n"
        "Alert condition: PPM > 10000 for 3 consecutive readings\n"
        f"Consecutive critical reading count: {consecutive_count}\n"
        f"Raw sensor value: {payload.get('sensor_raw', 'UNKNOWN')}\n"
        f"Buzzer: {payload.get('buzzer', 'UNKNOWN')}\n"
        f"Valve: {payload.get('valve', 'UNKNOWN')}\n\n"
        "Please follow your emergency safety procedure. Do not operate electrical switches in a suspected gas leak area."
    )

    if not token or not recipients:
        reason = "Telegram bot token is missing in .streamlit/secrets.toml." if not token else "Enter at least one Telegram chat ID in the sidebar."
        add_notification_log("Telegram", ", ".join(recipients), node_id, gas_ppm, "FAILED", reason, message)
        return

    work_queue = telegram_dispatcher()
    for chat_id in recipients:
        try:
            work_queue.put_nowait({
                "token": token, "chat_id": chat_id, "message": message,
                "node_id": node_id, "gas_ppm": gas_ppm,
            })
        except queue.Full:
            add_notification_log(
                "Telegram", chat_id, node_id, gas_ppm, "FAILED",
                "Telegram sending queue is full; this alert was not queued.", message
            )


def load_notification_history(limit=100):
    with sqlite3.connect(DB_PATH) as con:
        return pd.read_sql_query(
            "SELECT timestamp, channel, recipient, node_id, gas_ppm, status, detail "
            "FROM notification_history ORDER BY id DESC LIMIT ?", con, params=(limit,)
        )

def load_telemetry(limit=1000):
    with sqlite3.connect(DB_PATH) as con:
        data = pd.read_sql_query("SELECT * FROM telemetry ORDER BY id DESC LIMIT ?", con, params=(limit,))
    return data.sort_values("id")

def load_events(limit=500):
    with sqlite3.connect(DB_PATH) as con:
        return pd.read_sql_query("SELECT * FROM events ORDER BY id DESC LIMIT ?", con, params=(limit,))


# ----------------------- FIREBASE ------------------------

@st.cache_resource
def firebase_service():
    credentials_path = os.getenv("FIREBASE_CREDENTIALS", "serviceAccountKey.json")
    database_url = os.getenv("FIREBASE_DATABASE_URL", "").strip()

    if not database_url:
        return {"connected": False, "reason": "FIREBASE_DATABASE_URL is not configured"}

    try:
        import firebase_admin
        from firebase_admin import credentials, db

        if not firebase_admin._apps:
            cred = credentials.Certificate(credentials_path)
            firebase_admin.initialize_app(cred, {"databaseURL": database_url})

        return {"connected": True, "db": db}
    except Exception as error:
        return {"connected": False, "reason": str(error)}

firebase_state = firebase_service()


# ----------------------- USB SERIAL (ESP32) -------------------

@st.cache_resource
def open_esp32_serial(port, baud_rate):
    # Keep one serial connection alive across Streamlit reruns.
    import serial
    return serial.Serial(port=port, baudrate=baud_rate, timeout=0)


def read_esp32_serial(serial_connection, max_lines=100):
    """Read newline-delimited JSON packets while preserving partial USB packets."""
    received = 0
    invalid_lines = 0

    # USB serial data can arrive in fragments; keep bytes until a full newline.
    buffer = getattr(serial_connection, "_dashboard_line_buffer", bytearray())
    waiting = serial_connection.in_waiting
    if waiting:
        buffer.extend(serial_connection.read(waiting))

    # Prevent an unexpectedly long malformed line from growing indefinitely.
    if len(buffer) > 16384 and b"\n" not in buffer:
        buffer.clear()
        invalid_lines += 1

    processed = 0
    while b"\n" in buffer and processed < max_lines:
        raw_line, _, remainder = buffer.partition(b"\n")
        buffer = bytearray(remainder)
        processed += 1

        line = raw_line.decode("utf-8", errors="ignore").strip()
        if not line:
            continue

        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            # Ignore ESP32 startup text or other non-JSON diagnostic lines.
            invalid_lines += 1
            continue

        if not isinstance(payload, dict):
            invalid_lines += 1
            continue

        if "sensor_raw" not in payload or "gas_ppm" not in payload:
            invalid_lines += 1
            continue

        payload.setdefault("node_id", "ESP32-01")
        payload.setdefault("severity", "NORMAL")
        payload.setdefault("valve", "UNKNOWN")
        payload.setdefault("fan", "N/A")
        payload.setdefault("buzzer", "UNKNOWN")
        payload.setdefault("sensor_ok", True)
        payload.setdefault("message", "Telemetry received from ESP32")
        payload["timestamp"] = utc_now()

        insert_telemetry(payload)
        maybe_send_alert_notification(payload)
        received += 1

    serial_connection._dashboard_line_buffer = buffer
    return received, invalid_lines


# ----------------------- SIDEBAR -------------------------

st.sidebar.markdown("""
<div style="margin-bottom: 15px;">
    <div style="font-size: 10px; font-weight: 800; color: #00e5ff; letter-spacing: 1.5px;">SMART IOT PLATFORM</div>
    <div style="font-size: 18px; font-weight: 800; color: #ffffff; margin-top: 2px;">LPG SAFETY INDIA</div>
    <div style="font-size: 11px; color: #64748b; margin-top: 2px;">MINISTRY / INDUSTRIAL SEC</div>
</div>
""", unsafe_allow_html=True)

page = st.sidebar.radio(
    "NAVIGATION",
    ["Overview", "Live Sensors", "Alerts & Events", "Analytics", "System & Setup"]
)

st.sidebar.divider()

mode = st.sidebar.selectbox(
    "Data source",
    ["USB Serial (ESP32)", "Demo simulation", "Firebase hardware feed"],
    index=0
)

with st.sidebar.expander("Telegram Alert Notifications", expanded=False):
    notification_enabled = st.checkbox("Enable Telegram alert notifications", value=False, key="notify_enabled")
    telegram_settings = get_telegram_settings()
    chat_id_default = telegram_settings.get("chat_id", "")
    notification_chat_id = st.text_input(
        "Telegram chat ID(s) — comma-separated for multiple phones",
        value=chat_id_default,
        placeholder="Your chat ID, or brother's ID, or both separated by a comma",
        key="notify_telegram_chat_id"
    )
    token_ready = bool(telegram_settings.get("bot_token"))
    st.caption(f"Telegram bot token: {'configured' if token_ready else 'missing'}")
    st.caption(
        "Sends one Telegram message to every listed chat ID after EACH group of 3 consecutive ESP32 readings above 10000 PPM. A normal reading resets the counter."
    )

    if st.button("Send Telegram test message", key="telegram_test_button", use_container_width=True):
        try:
            if not token_ready:
                raise ValueError("Add [telegram] bot_token to .streamlit/secrets.toml first.")
            test_text = "✅ LPG Safety Dashboard test: Telegram notifications are configured successfully."
            test_recipients = [
                item.strip()
                for item in str(notification_chat_id).replace(";", ",").split(",")
                if item.strip()
            ]
            if not test_recipients:
                raise ValueError("Enter at least one Telegram chat ID.")
            test_failures = []
            for recipient in test_recipients:
                try:
                    test_result = send_telegram_message(
                        telegram_settings["bot_token"], recipient, test_text
                    )
                    add_notification_log(
                        "Telegram test", recipient, "DASHBOARD-TEST", None,
                        "ACCEPTED",
                        f"Telegram API accepted test (message_id: {test_result.get('message_id', 'unknown')}).",
                        test_text
                    )
                except Exception as recipient_error:
                    test_failures.append(f"{recipient}: {recipient_error}")
                    add_notification_log(
                        "Telegram test", recipient, "DASHBOARD-TEST", None,
                        "FAILED", str(recipient_error), test_text
                    )
            if test_failures:
                st.error("Some Telegram test messages failed: " + " | ".join(test_failures))
            else:
                st.success(f"Telegram accepted the test message for {len(test_recipients)} recipient(s). Check each Telegram chat.")
        except Exception as error:
            add_notification_log("Telegram test", notification_chat_id, "DASHBOARD-TEST", None,
                                 "FAILED", str(error), "Telegram configuration test")
            st.error(f"Telegram test failed: {error}")

st.session_state["notification_config"] = {
    "enabled": notification_enabled,
    "chat_id": notification_chat_id,
}

if notification_enabled:
    try:
        st.sidebar.caption(f"Telegram messages waiting to send: {telegram_dispatcher().qsize()}")
    except Exception:
        pass

serial_port = "COM13"
serial_baud = 115200
serial_received_this_run = 0
serial_invalid_this_run = 0

if mode == "USB Serial (ESP32)":
    st.sidebar.markdown("**ESP32 USB connection**")
    serial_port = st.sidebar.text_input("COM port", value="COM13")
    serial_baud = st.sidebar.selectbox("Baud rate", [115200, 9600, 57600], index=0)
    try:
        from streamlit_autorefresh import st_autorefresh
        st_autorefresh(interval=500, key="esp32_usb_dashboard_refresh")
    except Exception:
        st.sidebar.warning("Install streamlit-autorefresh: python -m pip install streamlit-autorefresh")
elif mode == "Firebase hardware feed":
    try:
        from streamlit_autorefresh import st_autorefresh
        st_autorefresh(interval=3000, key="firebase_dashboard_refresh")
    except Exception:
        st.sidebar.warning("Install streamlit-autorefresh for automatic updates.")


# ----------------------- DEMO MODE -----------------------

if "demo_tick" not in st.session_state:
    st.session_state.demo_tick = 0

if "demo_nodes" not in st.session_state:
    st.session_state.demo_nodes = ["KITCHEN-01", "STORE-02", "PLANT-03"]

if "demo_level" not in st.session_state:
    st.session_state.demo_level = 420

if mode == "Demo simulation":
    import random

    st.session_state.demo_tick += 1

    demo_severity = st.sidebar.selectbox(
        "Simulation scenario",
        ["Normal", "Warning", "Critical", "Sensor fault"],
        index=0
    )

    demo_map = {
        "Normal": 420,
        "Warning": 1650,
        "Critical": 2800,
        "Sensor fault": 0
    }

    st.session_state.demo_level = max(0, demo_map[demo_severity] + random.randint(-35, 35))

    for i, node in enumerate(st.session_state.demo_nodes):
        raw = max(0, st.session_state.demo_level + (i * 18) + random.randint(-25, 25))
        severity = demo_severity.upper().replace("SENSOR FAULT", "SENSOR_FAULT")

        insert_telemetry({
            "node_id": node,
            "sensor_raw": raw,
            "severity": severity,
            "gas_ppm": round(raw * 0.35, 2),
            "valve": "CLOSED" if severity in ("WARNING", "CRITICAL") else "OPEN",
            "fan": "ON" if severity in ("WARNING", "CRITICAL") else "OFF",
            "buzzer": "ON" if severity in ("WARNING", "CRITICAL", "SENSOR_FAULT") else "OFF",
            "wifi_rssi": -52 - (i * 7),
            "battery_pct": 96 - (i * 4),
            "power_source": "MAINS + BACKUP",
            "sensor_ok": severity != "SENSOR_FAULT",
            "message": f"{severity} simulated event detected on {node}"
        })


# ----------------------- HARDWARE MODE -------------------

elif mode == "USB Serial (ESP32)":
    try:
        esp32_connection = open_esp32_serial(serial_port.strip(), int(serial_baud))
        serial_received_this_run, serial_invalid_this_run = read_esp32_serial(esp32_connection)
        st.sidebar.success(f"Serial port open: {serial_port} @ {serial_baud}")
        if serial_received_this_run:
            st.sidebar.caption(f"Received {serial_received_this_run} JSON packet(s) this refresh.")
        elif serial_invalid_this_run:
            st.sidebar.warning("Serial data received, but it was not valid ESP32 telemetry JSON.")
        else:
            st.sidebar.info("Connected. Waiting for ESP32 JSON telemetry...")
    except ImportError:
        st.sidebar.error("pyserial is missing. Install it with: python -m pip install pyserial")
    except Exception as error:
        st.sidebar.error(f"Could not open {serial_port}: {error}")
        st.sidebar.caption("Close Arduino Serial Monitor and check Windows Device Manager.")

elif mode == "Firebase hardware feed":
    if not firebase_state.get("connected"):
        st.sidebar.error("Firebase unavailable: " + firebase_state.get("reason", "Not configured"))
    else:
        try:
            firebase_nodes = firebase_state["db"].reference("/telemetry").get() or {}
            if isinstance(firebase_nodes, dict):
                for node_id, payload in firebase_nodes.items():
                    if isinstance(payload, dict):
                        payload.setdefault("node_id", node_id)
                        insert_telemetry(payload)
        except Exception as error:
            st.sidebar.error(f"Firebase read failed: {error}")


# ----------------------- READ DATA -----------------------

df = load_telemetry(1200)
events = load_events(500)

# In USB mode, show only the physical ESP32 node (not old demo/Firebase rows).
if mode == "USB Serial (ESP32)":
    if not df.empty:
        df = df[df["node_id"].astype(str) == "ESP32-01"].copy()
    if not events.empty:
        events = events[events["node_id"].astype(str) == "ESP32-01"].copy()

if not df.empty:
    latest = df.sort_values("id").groupby("node_id", as_index=False).tail(1)
else:
    latest = pd.DataFrame([{
        "node_id": "NO DATA", "sensor_raw": 0, "gas_ppm": None,
        "severity": "OFFLINE", "valve": "UNKNOWN", "fan": "UNKNOWN",
        "buzzer": "UNKNOWN", "wifi_rssi": None, "battery_pct": None,
        "power_source": "UNKNOWN", "sensor_ok": 0, "timestamp": None
    }])


# ----------------------- STATUS HELPERS ------------------

def sev_color(severity):
    severity = str(severity).upper()
    if severity in ("CRITICAL", "SENSOR_FAULT", "OFFLINE"):
        return "danger"
    if severity == "WARNING":
        return "warn"
    return "good"

def pill(severity):
    return f'<span class="status-pill {sev_color(severity)}">{str(severity).upper()}</span>'

critical_count = int((latest["severity"].astype(str).str.upper() == "CRITICAL").sum())
warning_count = int((latest["severity"].astype(str).str.upper() == "WARNING").sum())
online_count = len(latest[latest["severity"].astype(str).str.upper() != "OFFLINE"])

system_status = "CRITICAL" if critical_count else "WARNING" if warning_count else "NORMAL"


# ----------------------- TOP SUB-HEADER BAR -----------------

col_h1, col_h2 = st.columns([3, 1])
with col_h1:
    st.markdown(f"""
    <div style="font-size: 11px; color: #64748b; font-weight: 700; letter-spacing: 1px; text-transform: uppercase;">
        NATIONAL GAS SAFETY • MINISTRY OF PETROLEUM & NATURAL GAS • INDIA
    </div>
    """, unsafe_allow_html=True)
with col_h2:
    st.markdown(f"""
    <div style="text-align: right; font-size: 12px; font-family: 'DM Mono', monospace; color: #94a3b8;">
        🟢 <span style="color: #34d399; font-weight: 700;">LIVE</span>  |  USB / ESP32 MONITORING
    </div>
    """, unsafe_allow_html=True)

st.markdown("")


# ----------------------- MAIN HEADER ---------------------

st.markdown("""
<div class="hero">
    <div class="eyebrow">IOT SENSOR TELEMETRY • REAL-TIME COMMAND CENTER</div>
    <h1>Smart LPG Safety & Leakage Detection Dashboard</h1>
    <p>Live MQ-6 sensor telemetry, ESP32-controlled safety actuators, and USB-connected monitoring.</p>
</div>
""", unsafe_allow_html=True)


# ----------------------- TOP METRICS (4 CARDS) ------------

c1, c2, c3, c4 = st.columns(4)

with c1:
    st.metric("SYSTEM CONDITION", system_status, "Controller status active")
with c2:
    st.metric("ACTIVE SENSOR NODES", f"{online_count}", f"{len(latest)} nodes reporting")
with c3:
    st.metric("WARNING NODES", warning_count, "Requires attention")
with c4:
    st.metric("CRITICAL NODES", critical_count, "Emergency condition")

st.markdown("")


# =========================================================
# OVERVIEW PAGE
# =========================================================

if page == "Overview":
    left, right = st.columns([1.6, 1])

    with left:
        st.markdown("### 30-Day Gas Concentration Trend")
        st.caption("MQ-6 RAW ADC — SENSOR NODES NORMALIZED")
        if not df.empty:
            chart_df = df.tail(250).copy()
            chart_df["time"] = pd.to_datetime(chart_df["timestamp"], errors="coerce")

            fig1 = px.line(
                chart_df, x="time", y="sensor_raw", color="node_id",
                template="plotly_dark",
                labels={"time": "Date", "sensor_raw": "MQ-6 Raw ADC", "node_id": "Node"}
            )
            fig1.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                height=310, margin=dict(l=10, r=10, t=10, b=10), legend_title_text=""
            )
            st.plotly_chart(fig1, use_container_width=True)
        else:
            st.info("Waiting for sensor telemetry.")

    with right:
        st.markdown("### Sensor Mix Contribution")
        st.caption("VOLUME SHARE BY SENSOR NODE")
        if not latest.empty:
            fig_donut = px.pie(
                latest, names="node_id", values="sensor_raw", hole=0.65,
                template="plotly_dark"
            )
            fig_donut.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                height=310, margin=dict(l=10, r=10, t=10, b=10), showlegend=True,
                legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5)
            )
            st.plotly_chart(fig_donut, use_container_width=True)
        else:
            st.info("No data for distribution.")

    st.markdown("---")
    
    # 3 Summary Bottom Cards matching the reference layout
    rc1, rc2, rc3 = st.columns(3)
    with rc1:
        st.markdown("""
        <div class="panel">
            <div style="font-size: 11px; font-weight: 700; color: #8a9bb8; text-transform: uppercase;">Weekly Volatility Index</div>
            <div style="font-size: 11px; color: #64748b; margin-top: 2px;">PRICE FLUCTUATION SCORE</div>
            <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 12px;">
                <span style="font-weight: 600;">KITCHEN-01</span>
                <span style="font-family: 'DM Mono', monospace; font-weight: 700; color: #fbbf24;">6.2 / 10</span>
            </div>
            <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 6px;">
                <span style="font-weight: 600;">PLANT-03</span>
                <span style="font-family: 'DM Mono', monospace; font-weight: 700; color: #34d399;">3.8 / 10</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
    with rc2:
        st.markdown("""
        <div class="panel">
            <div style="font-size: 11px; font-weight: 700; color: #8a9bb8; text-transform: uppercase;">Telemetry Disbursed</div>
            <div style="font-size: 11px; color: #64748b; margin-top: 2px;">CURRENT MONTH • PACKETS SENT</div>
            <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 12px;">
                <span style="font-weight: 600;">Active Packets</span>
                <span style="font-family: 'DM Mono', monospace; font-weight: 700; color: #38bdf8;">4,280 Pkts</span>
            </div>
            <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 6px;">
                <span style="font-weight: 600;">Total Logs</span>
                <span style="font-family: 'DM Mono', monospace; font-weight: 700; color: #34d399;">16,200 Total</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
    with rc3:
        st.markdown("""
        <div class="panel">
            <div style="font-size: 11px; font-weight: 700; color: #8a9bb8; text-transform: uppercase;">30-Day Forecast</div>
            <div style="font-size: 11px; color: #64748b; margin-top: 2px;">ML SENSOR PPM PREDICTION</div>
            <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 12px;">
                <span style="font-weight: 600;">KITCHEN (Apr 30)</span>
                <span style="font-family: 'DM Mono', monospace; font-weight: 700; color: #f87171;">412 ppm</span>
            </div>
            <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 6px;">
                <span style="font-weight: 600;">PLANT (Apr 30)</span>
                <span style="font-family: 'DM Mono', monospace; font-weight: 700; color: #34d399;">318 ppm</span>
            </div>
        </div>
        """, unsafe_allow_html=True)


# =========================================================
# LIVE SENSOR PAGE
# =========================================================

elif page == "Live Sensors":
    st.markdown("### Active Sensor Node Diagnostics")
    st.caption("Real-time telemetry readings from deployed MQ-6 sensor nodes.")

    for _, row in latest.iterrows():
        a, b, c, d, e = st.columns([1.4, 1, 1, 1, 1])
        with a:
            st.markdown(f"**{row['node_id']}**<br>{pill(row['severity'])}", unsafe_allow_html=True)
        with b:
            st.metric("Raw ADC", f"{row['sensor_raw']:.0f}" if pd.notna(row["sensor_raw"]) else "—")
        with c:
            gas_ppm = row.get("gas_ppm")
            st.metric("Gas (PPM)", f"{gas_ppm:.1f}" if pd.notna(gas_ppm) else "Not supplied")
        with d:
            battery = row.get("battery_pct")
            st.metric("Battery", f"{battery:.0f}%" if pd.notna(battery) else "N/A")
        with e:
            wifi = row.get("wifi_rssi")
            st.metric("Wi-Fi", f"{wifi:.0f} dBm" if pd.notna(wifi) else "N/A")
        st.divider()

    st.markdown("### Recent Telemetry Log Stream")
    st.dataframe(df.tail(100).sort_values("id", ascending=False), use_container_width=True, hide_index=True)


# =========================================================
# ALERTS & EVENTS PAGE
# =========================================================

elif page == "Alerts & Events":
    st.markdown("### System Alert Center & Anomalies")

    if critical_count:
        st.error(f"CRITICAL: {critical_count} node(s) report critical gas leakage. Follow emergency protocols.")
    elif warning_count:
        st.warning(f"WARNING: {warning_count} node(s) have exceeded warning thresholds.")
    else:
        st.success("All nodes operating within normal parameters. No active warnings.")

    if not events.empty:
        st.markdown("### Recorded Incident Log")
        st.dataframe(events.drop(columns=["id"]), use_container_width=True, hide_index=True)
        st.download_button(
            "Download Event History (CSV)",
            events.to_csv(index=False).encode("utf-8"),
            "lpg_event_history.csv",
            "text/csv"
        )
    else:
        st.info("No warning or critical incidents recorded yet.")

    st.markdown("### Telegram Notification History")
    notification_history = load_notification_history(100)
    if not notification_history.empty:
        st.dataframe(notification_history, use_container_width=True, hide_index=True)
    else:
        st.info("No Telegram notifications have been sent yet.")


# =========================================================
# ANALYTICS PAGE (EXACTLY 5+ CHARTS DASHBOARD)
# =========================================================

elif page == "Analytics":
    st.markdown("### Advanced Sensor Analytics & Visualizations")
    st.caption("Comprehensive multi-parameter analysis containing 5 core analytical charts for system evaluation.")

    if not df.empty:
        chart_df = df.copy()
        chart_df["time"] = pd.to_datetime(chart_df["timestamp"], errors="coerce")

        # ROW 1: Chart 1 & Chart 2
        col_a, col_b = st.columns(2)

        with col_a:
            fig1 = px.line(
                chart_df.tail(600), x="time", y="sensor_raw", color="node_id",
                template="plotly_dark", title="1. MQ-6 Sensor Readings Trend Over Time"
            )
            fig1.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=320)
            st.plotly_chart(fig1, use_container_width=True)

        with col_b:
            severity_counts = chart_df["severity"].value_counts().reset_index()
            severity_counts.columns = ["severity", "count"]
            fig2 = px.pie(
                severity_counts, names="severity", values="count", hole=0.4,
                template="plotly_dark", title="2. Overall Severity Distribution (Donut Chart)"
            )
            fig2.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=320)
            st.plotly_chart(fig2, use_container_width=True)

        # ROW 2: Chart 3 & Chart 4
        col_c, col_d = st.columns(2)

        with col_c:
            latest_nodes = chart_df.groupby("node_id", as_index=False).tail(1)
            fig3 = px.bar(
                latest_nodes, x="node_id", y="battery_pct", color="node_id",
                template="plotly_dark", title="3. Node Battery Health Levels (%)"
            )
            fig3.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=320, showlegend=False)
            st.plotly_chart(fig3, use_container_width=True)

        with col_d:
            fig4 = px.scatter(
                chart_df.tail(400), x="time", y="wifi_rssi", color="node_id",
                template="plotly_dark", title="4. Wi-Fi Signal Strength (RSSI dBm) Over Time"
            )
            fig4.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=320)
            st.plotly_chart(fig4, use_container_width=True)

        # ROW 3: Chart 5
        st.markdown("")
        counts = chart_df.groupby(["node_id", "severity"]).size().reset_index(name="samples")
        fig5 = px.bar(
            counts, x="node_id", y="samples", color="severity", barmode="stack",
            template="plotly_dark", title="5. Cumulative Status Samples Stacked by Node"
        )
        fig5.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=320)
        st.plotly_chart(fig5, use_container_width=True)

        st.download_button(
            "Download Full Telemetry Dataset (CSV)",
            df.to_csv(index=False).encode("utf-8"),
            "lpg_telemetry.csv",
            "text/csv"
        )
    else:
        st.info("No historical readings available for analytics.")


# =========================================================
# SYSTEM & SETUP PAGE
# =========================================================

elif page == "System & Setup":
    st.markdown("### System Architecture")
    st.markdown("""
    **MQ-6 Gas Sensor** ➔ **ESP32 Microcontroller** ➔ **Local Alarm / Relay Control** ➔ **USB Serial (COM13)** ➔ **Python Streamlit Dashboard**
    """)

    st.markdown("### ESP32 USB Serial Integration")
    st.code(
        '{"node_id":"ESP32-01","sensor_raw":250,"gas_ppm":915.8,'
        '"severity":"CRITICAL","valve":"CLOSED","fan":"N/A",'
        '"buzzer":"ON","sensor_ok":true}',
        language="json"
    )
    st.caption("Expected format: one JSON object per line, 115200 baud. Close Arduino Serial Monitor before connecting the dashboard.")

    st.markdown("### Telegram Notification Setup")
    st.markdown("""
    The dashboard sends one Telegram message to each configured chat ID for every 3 consecutive ESP32 readings above **10000 PPM**. A reading at or below 10000 resets the consecutive-reading counter. During a sustained critical condition, alerts occur on readings 3, 6, 9, and so on.

    **Initial Telegram setup**
    1. In Telegram, open **@BotFather**, send `/newbot`, follow the prompts, and copy the bot token. Keep the token secret.
    2. Open your new bot and press **Start** or send `/start` at least once. A bot cannot initiate a private conversation before the user starts it.
    3. Find your numeric chat ID. One option is to send `/start` to your bot, then use the Telegram Bot API `getUpdates` method for that bot and read `message.chat.id` from the returned update. Do not share the token or the resulting private API URL.
    4. Add the bot token and chat ID to `.streamlit/secrets.toml` as shown below. The chat ID can also be entered in the dashboard sidebar.
    5. Use **Send Telegram test message** in the sidebar before relying on alert notifications.

    Telegram Bot API usage does not require a Twilio subscription. Telegram and network availability are still required.
    """)
    st.code(
        '[telegram]\n'
        'bot_token = "YOUR_TELEGRAM_BOT_TOKEN"\n'
        'chat_id = "YOUR_TELEGRAM_CHAT_ID"',
        language="toml"
    )
    st.caption("The code also accepts environment variables TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID. Keep secrets.toml private and never commit it to source control.")
    st.warning("Telegram alerts are supplementary only. Keep the ESP32 local buzzer/relay as the primary safety response; Telegram delivery is not guaranteed and must not be relied upon for emergency protection.")

    st.markdown("### Connection Status")
    if mode == "USB Serial (ESP32)":
        st.info(f"Selected USB serial port: {serial_port} at {serial_baud} baud")
    elif mode == "Firebase hardware feed":
        if firebase_state.get("connected"):
            st.success("Firebase successfully connected.")
        else:
            st.warning(firebase_state.get("reason", "Firebase not configured"))
    else:
        st.info("Demo simulation is selected.")

    st.write("Local SQLite database:", str(DB_PATH))


# ----------------------- FOOTER --------------------------

st.markdown("---")
st.markdown("""
<div class="small-note" style="text-align: center;">
SMART LPG SAFETY SYSTEM • Ministry of Petroleum & Natural Gas • All sensor telemetry and actuator states reflect real-time controller inputs.
</div>
""", unsafe_allow_html=True)

if mode == "Firebase hardware feed":
    time.sleep(0.1)