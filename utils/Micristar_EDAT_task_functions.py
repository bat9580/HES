import asyncio
from datetime import datetime

import pytz

from services.database import get_db_connection
from services.state import connected_clients
from utils import frames
from utils.Microstar_EDAT_generator_functions import (
    build_AARQ_frame,
    build_profile_get_request,
    build_SNRM_frame,
    build_get_request,
)
from utils.parser_functions import (
    calculate_with_transformer_values,
    map_meter_data,
    parse_dlms_frame,
    process_dlms_data,
)
from utils.storer import store_meter_reading_energy_profile

tz = pytz.timezone("Asia/Ulaanbaatar")


def get_meters_for_edat(edat_number):
    """Get all RS485 meters behind this EDAT device from installed_meters."""
    conn = get_db_connection()
    conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
    rows = conn.execute(
        """
        SELECT meter_number, com_address, password, CT_ratio, VT_ratio
        FROM installed_meters
        WHERE DCU_number = ?
        """,
        (str(edat_number),),
    ).fetchall()
    conn.close()
    return rows


async def schedule_voltage_read(meter_number):
    async def task():
        await voltageReadTask(meter_number)

    # Put the task into the meter's queue
    queue = connected_clients[meter_number]['task_queue']
    await queue.put((2, task))
    # asyncio.create_task(queue.put((2, task))) 

async def voltageReadTask(meter_number):
    client = connected_clients[meter_number]
    response_queue = client['response_queue'] 
    sender_queue = client['queue']
    print("voltage task started")
    try:
        print("voltage read")
        await sender_queue.put(bytes.fromhex(frames.METER_AARQ))  
        response = await asyncio.wait_for(response_queue.get(),timeout=10) 
        print(response)
        await sender_queue.put(bytes.fromhex(frames.METER_VOLTAGE_PHASE_A))  
        response = await asyncio.wait_for(response_queue.get(),timeout=10)    
        print(response)   
    except Exception as e:
            await sender_queue.put(bytes.fromhex(frames.METER_VOLTAGE_PHASE_A))  
            response = await asyncio.wait_for(response_queue.get(),timeout=10)    
            print(response)



PRIORITY_SCHEDULED = 1  # Load profile; real-time uses 0 and runs between meters


async def load_profile_one_meter(EDAT_number, meter, date_now):
    """
    Read load profile for a single meter. Each meter is a separate task so
    real-time tasks (priority 0) can run between meters.
    """
    client = connected_clients[EDAT_number]
    response_queue = client["response_queue"]
    sender_queue = client["queue"]

    meter_number = str(meter["meter_number"])
    hdlc_addr = str(meter.get("com_address", "1"))
    password = str(meter.get("password", "00000000"))[:8].ljust(8, "0")
    ct_ratio = meter.get("CT_ratio") or 1
    vt_ratio = meter.get("VT_ratio") or 1

    try:
        print(f"📋 Load profile: EDAT {EDAT_number} meter {meter_number} (HDLC {hdlc_addr})")

        # 1. Handshake: SNRM
        snrm = build_SNRM_frame(hdlc_addr)
        await sender_queue.put(bytes.fromhex(snrm))
        await asyncio.wait_for(response_queue.get(), timeout=15)

        # 2. Handshake: AARQ
        aarq = build_AARQ_frame(hdlc_addr, password)
        await sender_queue.put(bytes.fromhex(aarq))
        await asyncio.wait_for(response_queue.get(), timeout=15)

        # 3. Get profile definition (99.1.0 attribute 3)
        def_frame = build_get_request(hdlc_addr, "99.1.0", class_id="0007", attribute="03")
        await sender_queue.put(bytes.fromhex(def_frame))
        def_response = await asyncio.wait_for(response_queue.get(), timeout=15)
        definition_list = process_dlms_data(parse_dlms_frame(def_response))

        # 4. Get profile data with time range
        profile_frame = build_profile_get_request(hdlc_addr, date_now, date_now)
        await sender_queue.put(bytes.fromhex(profile_frame))
        data_response = await asyncio.wait_for(response_queue.get(), timeout=15)
        data_list = process_dlms_data(parse_dlms_frame(data_response))

        mapped_data = map_meter_data(definition_list, data_list)
        if mapped_data:
            store_meter_reading_energy_profile(meter_number, mapped_data)
            mapped_calc = calculate_with_transformer_values(mapped_data, ct_ratio, vt_ratio)
            store_meter_reading_energy_profile(
                meter_number, mapped_calc, "energy_profile_readings_calculated"
            )
            print(f"✅ Stored profile for meter {meter_number}")
        else:
            print(f"⚠️ No profile data for meter {meter_number}")

    except asyncio.TimeoutError:
        print(f"❌ Timeout reading profile from meter {meter_number}")
    except Exception as e:
        print(f"❌ Error reading profile from meter {meter_number}: {e}")


async def loadProfileTask(EDAT_number):
    """
    Orchestrator: enqueue one load-profile task per meter so real-time tasks
    (priority 0) can run between meters.
    """
    if EDAT_number not in connected_clients:
        print(f"❌ EDAT {EDAT_number} not connected, skipping load profile")
        return

    task_queue = connected_clients[EDAT_number]["task_queue"]
    meters = get_meters_for_edat(EDAT_number)
    if not meters:
        print(f"No meters found for EDAT {EDAT_number}")
        return

    date_now = datetime.now(tz).replace(minute=0, second=0, microsecond=0).replace(tzinfo=None)

    for meter in meters:
        async def task(m=meter):
            await load_profile_one_meter(EDAT_number, m, date_now)

        await task_queue.put((PRIORITY_SCHEDULED, task))
    print(f"📋 Enqueued {len(meters)} load profile tasks for EDAT {EDAT_number}")


async def schedule_load_profile_edat(EDAT_number):
    """
    Trigger load profile collection for all meters on an EDAT.
    Enqueues the orchestrator task (which then enqueues per-meter tasks).
    Use with cron or manual trigger.
    """
    if EDAT_number not in connected_clients:
        print(f"❌ EDAT {EDAT_number} not connected")
        return
    task_queue = connected_clients[EDAT_number]["task_queue"]

    async def orchestrator():
        await loadProfileTask(EDAT_number)

    await task_queue.put((PRIORITY_SCHEDULED, orchestrator)) 