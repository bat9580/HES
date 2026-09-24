"""TCP uplink for an ESP32 that speaks IEC 62056-21 to DDSD285_2018 meters.

The ESP32 is registered like a DCU (registered_dcus.dcu_number = device id).
Meters of type DDSD285_2018 store that id in installed_meters.DCU_number.
HES sends one text job per OBIS; the ESP32 runs the RS485 session locally.
"""

import asyncio

from services.database import get_db_connection
from services.state import connected_clients
from utils.DCU_functions import task_executor
from utils.meter_task_functions import meter_writer

METER_TYPE = "DDSD285_2018"
READ_TIMEOUT_S = 40


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
    client["tasks"] = [
        asyncio.create_task(meter_writer(esp_id)),
        asyncio.create_task(keep_connection(esp_id)),
        asyncio.create_task(task_executor(esp_id)),
    ]


async def drop_previous_connection(esp_id):
    """Close a previous socket for this device id so a WiFi reconnect can replace it."""
    old = connected_clients.get(esp_id)
    if not old:
        return
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


async def enqueue_obis_read(esp_id, meter_number, obis, password, timeout=READ_TIMEOUT_S):
    """Queue one READ on the ESP32 bus. One job runs at a time."""
    if esp_id not in connected_clients:
        return {"error": "OFFLINE"}

    async def task():
        client = connected_clients.get(esp_id)
        if not client:
            return
        response_queue = client["response_queue"]
        result_queue = client["real_time_result"]
        while True:
            try:
                response_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        try:
            command = f"READ {meter_number} {obis} {password}\n".encode("ascii")
        except UnicodeEncodeError:
            await result_queue.put({"error": "BAD_PASSWORD"})
            return
        await client["queue"].put(command)
        try:
            parsed = await _next_result(response_queue, timeout)
        except asyncio.TimeoutError:
            await result_queue.put({"error": "TIMEOUT"})
            return
        await result_queue.put(parsed)

    await connected_clients[esp_id]["task_queue"].put((0, task))
    return None
