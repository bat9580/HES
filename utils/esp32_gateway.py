"""TCP uplink for an ESP32 that speaks IEC 62056-21 to DDSD285_2018 meters.

The ESP32 is registered like a DCU (registered_dcus.dcu_number = device id).
Meters of type DDSD285_2018 store that id in installed_meters.DCU_number.
HES sends one text job per OBIS; the ESP32 runs the RS485 session locally.

System tasks use the same cron rows as GPRS meters. Each job is registered on
the gateway and fans out to the RS485 meters behind it.
"""

import asyncio
import copy
from datetime import datetime

import pytz

from services.database import get_db_connection, update_online_status
from services.state import connected_clients
from utils.meter_task_functions import meter_writer
from utils.parser_functions import (
    calculate_value_with_ratio_single,
    calculate_with_transformer_values,
)
from utils.storer import store_meter_reading_energy_profile, store_meter_reading_instant_profile

METER_TYPE = "DDSD285_2018"
READ_TIMEOUT_S = 40
PRIORITY_LIVE = 0
PRIORITY_SCHEDULED = 1
tz = pytz.timezone("Asia/Ulaanbaatar")

VOLTAGE_OBIS = ["32.7.0",]
CURRENT_OBIS = ["31.7.0",]
POWER_OBIS = ["15.7.0",]
ENERGY_REGISTERS = [
    "1.8.0",
]
TASK_OBIS = {
    "Voltage read": VOLTAGE_OBIS,
    "Active Power read": ["15.7.0"],
    "Instantanious load profile": VOLTAGE_OBIS + CURRENT_OBIS + POWER_OBIS,
    "Energy load profile": ENERGY_REGISTERS,
}


def is_esp_hello(data):
    return esp_device_id(data) is not None


def esp_device_id(data):
    """Device id from the first line: HELLO <id>"""
    if not data or not data.startswith(b"HELLO "):
        return None
    line = data.split(b"\n", 1)[0].strip(b"\r")
    parts = line.split()
    if len(parts) != 2:
        return None
    try:
        device_id = parts[1].decode("ascii")
    except UnicodeDecodeError:
        return None
    if not device_id or not device_id.replace("_", "").replace("-", "").isalnum():
        return None
    return device_id


def is_hello_line(line):
    return line.startswith(b"HELLO ")


def split_lines(buf):
    lines = []
    while b"\n" in buf:
        line, buf = buf.split(b"\n", 1)
        line = line.strip(b"\r")
        if line:
            lines.append(line)
    return lines, buf


def is_esp_installed(esp_id):
    conn = get_db_connection()
    result = conn.execute(
        "SELECT 1 FROM registered_dcus WHERE dcu_number = ?",
        (str(esp_id),),
    ).fetchone()
    conn.close()
    return result is not None


def is_ddsd285(meter_type):
    return str(meter_type or "").strip().lower() == METER_TYPE.lower()


def uses_esp32(device_type, meter_type):
    """True for module type RS485 with ESP32, or meter type DDSD285_2018."""
    module = str(device_type or "").strip().lower()
    return "esp32" in module or is_ddsd285(meter_type)


def creat_esp_task(esp_id):
    print(f"beginning ESP32 task for {esp_id}")
    client = connected_clients[esp_id]
    client["link"] = "esp32"
    client["esp_rx_buf"] = b""
    client["esp_task_seq"] = 0
    client["tasks"] = [
        asyncio.create_task(meter_writer(esp_id)),
        asyncio.create_task(keep_connection(esp_id)),
        asyncio.create_task(esp_task_executor(esp_id)),
    ]
    from utils.utility_functions import add_system_task
    add_system_task(esp_id)


async def drop_previous_connection(esp_id):
    """Close a previous socket for this device id so a WiFi reconnect can replace it."""
    old = connected_clients.get(esp_id)
    if not old:
        return
    if old.get("link") == "esp32":
        try:
            from utils.utility_functions import clear_scheduled_jobs
            clear_scheduled_jobs(esp_id)
        except Exception as exc:
            print(f"ESP32 clear jobs {esp_id}: {exc}")
    connected_clients.pop(esp_id, None)
    tasks = old.get("tasks") or []
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    writer = old.get("writer")
    if writer is not None:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


async def keep_connection(esp_id):
    client = connected_clients.get(esp_id)
    if not client:
        return
    keep_queue = client["keep_connection_queue"]
    sender_queue = client["queue"]
    while esp_id in connected_clients and connected_clients.get(esp_id) is client:
        try:
            message = await asyncio.wait_for(keep_queue.get(), timeout=300)
            if message and is_hello_line(message):
                await sender_queue.put(b"OK\n")
        except asyncio.TimeoutError:
            continue
        except asyncio.CancelledError:
            break
        except Exception as exc:
            print(f"ESP32 keep_connection {esp_id}: {exc}")
            break


def parse_result_line(raw):
    text = raw.decode("ascii", "ignore").strip()
    parts = text.split()
    if len(parts) < 4 or parts[0] not in ("OK", "ERR"):
        return None
    if parts[0] == "OK":
        return {"value": parts[3], "obis": parts[2], "meter": parts[1]}
    return {"error": parts[3], "obis": parts[2], "meter": parts[1]}


async def _next_result(response_queue, timeout):
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        remaining = deadline - loop.time()
        if remaining <= 0:
            raise asyncio.TimeoutError
        raw = await asyncio.wait_for(response_queue.get(), timeout=remaining)
        parsed = parse_result_line(raw)
        if parsed is not None:
            return parsed


async def _put_task(esp_id, priority, task):
    """Queue (priority, sequence, task). Sequence keeps equal priorities comparable."""
    client = connected_clients.get(esp_id)
    if not client or client.get("link") != "esp32":
        raise KeyError(esp_id)
    seq = client.get("esp_task_seq", 0) + 1
    client["esp_task_seq"] = seq
    await client["task_queue"].put((priority, seq, task))


async def esp_task_executor(esp_id):
    client = connected_clients.get(esp_id)
    if not client:
        return
    queue = client.get("task_queue")
    if not queue:
        return
    print(f"ESP32 task executor started for {esp_id}")
    while esp_id in connected_clients and connected_clients.get(esp_id) is client:
        try:
            item = await queue.get()
        except asyncio.CancelledError:
            break
        task_func = item[-1] if isinstance(item, tuple) and len(item) >= 2 else None
        if task_func is None:
            continue
        try:
            await task_func()
        except asyncio.CancelledError:
            break
        except Exception as exc:
            print(f"ESP32 task failed for {esp_id}: {exc}")


async def _read_obis_now(client, meter_number, obis, password, timeout):
    """Send one READ and wait for OK/ERR. Does not touch real_time_result."""
    response_queue = client["response_queue"]
    while True:
        try:
            response_queue.get_nowait()
        except asyncio.QueueEmpty:
            break
    try:
        command = f"READ {meter_number} {obis} {password}\n".encode("ascii")
    except UnicodeEncodeError:
        return {"error": "BAD_PASSWORD"}
    await client["queue"].put(command)
    try:
        return await _next_result(response_queue, timeout)
    except asyncio.TimeoutError:
        return {"error": "TIMEOUT"}


async def enqueue_obis_read(esp_id, meter_number, obis, password, timeout=READ_TIMEOUT_S):
    """Queue one READ on the ESP32 bus. One job runs at a time."""
    if esp_id not in connected_clients:
        return {"error": "OFFLINE"}

    async def task():
        client = connected_clients.get(esp_id)
        if not client:
            return
        result_queue = client["real_time_result"]
        parsed = await _read_obis_now(client, meter_number, obis, password, timeout)
        await result_queue.put(parsed)

    try:
        await _put_task(esp_id, PRIORITY_LIVE, task)
    except KeyError:
        return {"error": "OFFLINE"}
    return None


def get_meters_for_esp(esp_id):
    """RS485 meters whose gateway id is this ESP32."""
    conn = get_db_connection()
    rows = conn.execute(
        """
        SELECT meter_number, password, CT_ratio, VT_ratio, device_type, type
        FROM installed_meters
        WHERE DCU_number = ?
        """,
        (str(esp_id),),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows if uses_esp32(row["device_type"], row["type"])]


def _as_ratio(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 1.0


def _meter_password(meter):
    return str(meter.get("password") or "").strip().replace(" ", "") or "00000000"


def _profile_timestamp():
    moment = datetime.now(tz).replace(minute=0, second=0, microsecond=0).replace(tzinfo=None)
    return moment.strftime("%Y-%m-%dT%H:%M:%S")


def _store_scheduled_reading(meter_number, invoke_target, values, ct_ratio, vt_ratio):
    if invoke_target in ("Voltage read", "Active Power read"):
        calculated = {"timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S")}
        for obis, value in values.items():
            calculated[obis] = calculate_value_with_ratio_single(value, obis, ct_ratio, vt_ratio)
        store_meter_reading_instant_profile(meter_number, [calculated], "regular_task_readings")
        return

    timestamp = _profile_timestamp()
    raw = [dict(values, timestamp=timestamp)]
    if invoke_target == "Energy load profile":
        store_meter_reading_energy_profile(meter_number, raw)
        calculated = calculate_with_transformer_values(copy.deepcopy(raw), ct_ratio, vt_ratio)
        store_meter_reading_energy_profile(
            meter_number, calculated, "energy_profile_readings_calculated"
        )
        return

    store_meter_reading_instant_profile(meter_number, raw)
    calculated = calculate_with_transformer_values(copy.deepcopy(raw), ct_ratio, vt_ratio)
    store_meter_reading_instant_profile(
        meter_number, calculated, "instantaneous_profile_readings_calculated"
    )


async def read_scheduled_meter(esp_id, meter, invoke_target, obis_list):
    meter_number = str(meter["meter_number"]).strip()
    password = _meter_password(meter)
    ct_ratio = _as_ratio(meter.get("CT_ratio"))
    vt_ratio = _as_ratio(meter.get("VT_ratio"))
    values = {}
    timed_out = False
    print(f"ESP32 {esp_id} scheduled {invoke_target} meter {meter_number}")

    for obis in obis_list:
        client = connected_clients.get(esp_id)
        if not client or client.get("link") != "esp32":
            timed_out = True
            break
        parsed = await _read_obis_now(client, meter_number, obis, password, READ_TIMEOUT_S)
        if parsed.get("error") in ("TIMEOUT", "BAD_PASSWORD"):
            print(f"ESP32 {esp_id} meter {meter_number} {obis}: {parsed['error']}")
            timed_out = True
            break
        if parsed.get("error"):
            print(f"ESP32 {esp_id} meter {meter_number} {obis}: {parsed['error']}")
            continue
        if str(parsed.get("meter")) != meter_number or parsed.get("obis") != obis:
            print(f"ESP32 {esp_id} meter {meter_number} unexpected reply {parsed}")
            continue
        try:
            values[obis] = float(str(parsed["value"]).replace(",", "."))
        except (TypeError, ValueError):
            print(f"ESP32 {esp_id} meter {meter_number} {obis} bad value {parsed.get('value')}")

    if values:
        try:
            _store_scheduled_reading(meter_number, invoke_target, values, ct_ratio, vt_ratio)
            print(f"Stored {invoke_target} for meter {meter_number}")
        except Exception as exc:
            print(f"ESP32 store failed for meter {meter_number}: {exc}")
            timed_out = True
    if timed_out or not values:
        update_online_status(meter_number, False)
    else:
        update_online_status(meter_number, True)


async def enqueue_meter_tasks(esp_id, invoke_target):
    if esp_id not in connected_clients:
        return
    obis_list = TASK_OBIS.get(invoke_target)
    if not obis_list:
        print(f"{invoke_target} not available")
        return
    meters = get_meters_for_esp(esp_id)
    if not meters:
        print(f"No ESP32 meters for {esp_id}")
        return
    for meter in meters:
        async def task(m=meter):
            await read_scheduled_meter(esp_id, m, invoke_target, obis_list)

        try:
            await _put_task(esp_id, PRIORITY_SCHEDULED, task)
        except KeyError:
            print(f"ESP32 {esp_id} disconnected while queueing {invoke_target}")
            return
    print(f"Enqueued {len(meters)} {invoke_target} tasks for ESP32 {esp_id}")


async def schedule_esp_reading(esp_id, invoke_target):
    """Cron entry. Queues an orchestrator; each meter is its own later task."""
    if invoke_target not in TASK_OBIS:
        print(f"{invoke_target} not available")
        return
    if esp_id not in connected_clients:
        print(f"ESP32 {esp_id} not connected, skip {invoke_target}")
        return

    async def orchestrator():
        await enqueue_meter_tasks(esp_id, invoke_target)

    try:
        await _put_task(esp_id, PRIORITY_SCHEDULED, orchestrator)
    except KeyError:
        print(f"ESP32 {esp_id} not connected, skip {invoke_target}")
