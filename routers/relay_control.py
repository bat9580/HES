import asyncio
import sqlite3
from datetime import datetime
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from services.state import connected_clients
from services.database import get_db_connection, update_online_status
from utils.DCU_meter_reader_functions import generate_frame_from_obis_plc_meter, generate_relay_frame_plc, read_plc_meter_manual
from utils.Microstar_EDAT_generator_functions import build_get_request, build_relay_operation_byte
from utils.Microstar_EDAT_meter_reader_functions import read_RS485_with_EDAT_meter_manual, send_handshake_frame_to_edat
from utils.reader_functions import read_meter_manual
from utils.utility_functions import require_permission, template_response
import json

router = APIRouter()

RELAY_LOG_SORT_COLUMNS = {
    "index": "id",
    "meter_number": "meter_number",
    "zone": "zone",
    "power_grid": "power_grid",
    "dcu_number": "dcu_number",
    "task_name": "task_name",
    "task_type": "task_type",
    "start_time": "start_time",
    "end_time": "end_time",
    "process": "process",
    "try_times": "try_times",
    "user_name": "user_name",
    "result": "result",
}


def format_relay_log_result(status: str, message: str) -> str:
    if status == "success":
        return "Success"
    msg = (message or "").strip()
    lower = msg.lower()
    if "timeout" in lower or "timed out" in lower:
        return "Response timeout"
    if msg.startswith("Error: "):
        return msg[7:]
    if status == "failed":
        return msg or "Failed"
    return msg or "Error"


def get_meter_log_context(meter_number: str) -> dict:
    ctx = {
        "meter_number": str(meter_number),
        "zone": "",
        "power_grid": "",
        "dcu_number": "",
    }
    try:
        conn = get_db_connection()
        row = conn.execute(
            """
            SELECT meter_number, Zone, POWER_grid, DCU_number
            FROM installed_meters
            WHERE meter_number = ?
            """,
            (str(meter_number),),
        ).fetchone()
        conn.close()
        if row:
            ctx["meter_number"] = row["meter_number"]
            ctx["zone"] = row["Zone"] or ""
            ctx["power_grid"] = row["POWER_grid"] or ""
            ctx["dcu_number"] = str(row["DCU_number"] or "").strip()
    except Exception as e:
        print(f"Failed to load meter log context for {meter_number}: {e}")
    return ctx


def create_relay_operation_log(meter_number: str, task_name: str, user_name: str) -> int | None:
    ctx = get_meter_log_context(meter_number)
    start_time = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO relay_operation_log (
                meter_number, zone, power_grid, dcu_number,
                task_name, task_type, start_time, process, try_times, user_name, result, attempts_json
            ) VALUES (?, ?, ?, ?, ?, 'Action', ?, 'Waiting Processing', 1, ?, 'Processing', '[]')
            """,
            (
                ctx["meter_number"],
                ctx["zone"],
                ctx["power_grid"],
                ctx["dcu_number"],
                task_name,
                start_time,
                user_name,
            ),
        )
        log_id = cursor.lastrowid
        conn.commit()
        return log_id
    except Exception as e:
        print(f"Failed to create relay operation log: {e}")
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass


def finish_relay_operation_log(log_id: int | None, status: str, message: str = "") -> None:
    if not log_id:
        return
    end_time = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    result = format_relay_log_result(status, message)
    attempt_status = "Success" if status == "success" else "Failed"
    attempts = json.dumps([
        {"attempt": 1, "time": end_time, "status": attempt_status, "message": result}
    ])
    try:
        conn = get_db_connection()
        conn.execute(
            """
            UPDATE relay_operation_log
            SET end_time = ?, process = 'Finish', result = ?, attempts_json = ?
            WHERE id = ?
            """,
            (end_time, result, attempts, log_id),
        )
        conn.commit()
    except Exception as e:
        print(f"Failed to finish relay operation log {log_id}: {e}")
    finally:
        try:
            conn.close()
        except Exception:
            pass


def relay_result(results: list, log_id: int | None, entry: dict) -> None:
    finish_relay_operation_log(log_id, entry.get("status", "error"), entry.get("message", ""))
    results.append(entry)


def row_to_relay_log_record(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "meter_number": row["meter_number"] or "",
        "zone": row["zone"] or "",
        "power_grid": row["power_grid"] or "",
        "dcu_number": row["dcu_number"] or "",
        "task_name": row["task_name"] or "",
        "task_type": row["task_type"] or "Action",
        "start_time": row["start_time"] or "",
        "end_time": row["end_time"] or "",
        "process": row["process"] or "",
        "try_times": row["try_times"] or 1,
        "user_name": row["user_name"] or "",
        "result": row["result"] or "",
    }


def build_relay_log_filters(conn, where_sql: str, params: list) -> dict:
    meters = [
        r[0]
        for r in conn.execute(
            f"SELECT DISTINCT meter_number FROM relay_operation_log WHERE 1=1{where_sql} ORDER BY meter_number",
            params,
        ).fetchall()
        if r[0]
    ]
    dcus = [
        r[0]
        for r in conn.execute(
            f"SELECT DISTINCT dcu_number FROM relay_operation_log WHERE 1=1{where_sql} ORDER BY dcu_number",
            params,
        ).fetchall()
        if r[0]
    ]
    users = [
        r[0]
        for r in conn.execute(
            f"SELECT DISTINCT user_name FROM relay_operation_log WHERE 1=1{where_sql} ORDER BY user_name",
            params,
        ).fetchall()
        if r[0]
    ]
    return {"meters": meters, "dcus": dcus, "users": users}


def normalize_relay_log_datetime(value: str, end_of_range: bool = False) -> str:
    """Convert API date/datetime values to relay log storage format (YYYY/MM/DD HH:MM:SS)."""
    if not value:
        return ""
    value = value.strip()
    if "T" in value:
        date_part, time_part = value.split("T", 1)
        return f"{date_part.replace('-', '/')} {time_part}"
    suffix = " 23:59:59" if end_of_range else " 00:00:00"
    return value.replace("-", "/") + suffix


def build_relay_log_query(
    meter_number: str = "",
    dcu_number: str = "",
    user_name: str = "",
    task_name: str = "",
    start_date: str = "",
    end_date: str = "",
):
    where_sql = ""
    params: list = []
    if meter_number:
        where_sql += " AND meter_number LIKE ?"
        params.append(f"%{meter_number}%")
    if dcu_number:
        where_sql += " AND dcu_number LIKE ?"
        params.append(f"%{dcu_number}%")
    if user_name:
        where_sql += " AND user_name = ?"
        params.append(user_name)
    if task_name and task_name.lower() != "all":
        where_sql += " AND task_name = ?"
        params.append(task_name)
    if start_date:
        where_sql += " AND start_time >= ?"
        params.append(normalize_relay_log_datetime(start_date))
    if end_date:
        where_sql += " AND start_time <= ?"
        params.append(normalize_relay_log_datetime(end_date, end_of_range=True))
    return where_sql, params


def update_relay_status_in_db(meter_number: int, relay_status: str) -> None:
    """
    Persist the latest known relay status for a meter.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE installed_meters
            SET relay_status = ?, relay_status_updated_at = ?
            WHERE meter_number = ?
            """,
            (relay_status, datetime.utcnow().isoformat(), str(meter_number)),
        )
        conn.commit()
    except Exception as e:
        # Avoid breaking relay operations if DB update fails
        print(f"Failed to update relay status for meter {meter_number}: {e}")
    finally:
        try:
            conn.close()
        except Exception:
            pass

@router.get("/relay-control", response_class=HTMLResponse)
async def relay_control(request: Request, message: str = None, user: dict = Depends(require_permission("Remote Maintain"))):
    conn = get_db_connection()
    installed_meters = conn.execute("SELECT * FROM installed_meters").fetchall()
    conn.close()
    return template_response(
        request,
        "relay_control.html",
        {
            "request": request,
            "installed_meters": installed_meters,
            "connected_clients": connected_clients,
            "message": message,
        }
    )


@router.get("/search-meters-relay", response_class=HTMLResponse)
async def search_meter(
    request: Request,
    meter_number: str = "",
    line: str = " ",
    user: dict = Depends(require_permission("Remote Maintain"))
):
    query = "SELECT * FROM installed_meters WHERE 1=1"
    params = []
    if meter_number:
        query += " AND meter_number LIKE ?"
        params.append(f"%{meter_number}%")
    if line:
        query += " AND line LIKE ?"
        params.append(f"%{line}%")
    conn = get_db_connection()
    searched_meters = conn.execute(query, params).fetchall()
    conn.close()
    return template_response(
        request,
        "relay_control.html",
        {
            "request": request,
            "installed_meters": searched_meters,
            "meter_number": meter_number,
            "connected_clients": connected_clients,
        }
    )


@router.get("/api/relay-operation-log")
async def get_relay_operation_logs(
    request: Request,
    meter_number: str = "",
    dcu_number: str = "",
    user_name: str = "",
    task_name: str = "",
    start_date: str = "",
    end_date: str = "",
    page: int = 1,
    page_size: int = 15,
    sort_by: str = "start_time",
    sort_dir: str = "desc",
    user: dict = Depends(require_permission("Remote Maintain")),
):
    page = max(1, page)
    page_size = min(max(1, page_size), 200)
    sort_column = RELAY_LOG_SORT_COLUMNS.get(sort_by, "start_time")
    sort_direction = "DESC" if sort_dir.lower() != "asc" else "ASC"

    where_sql, params = build_relay_log_query(
        meter_number, dcu_number, user_name, task_name, start_date, end_date
    )

    conn = get_db_connection()
    try:
        total = conn.execute(
            f"SELECT COUNT(*) FROM relay_operation_log WHERE 1=1{where_sql}",
            params,
        ).fetchone()[0]
        total_pages = max(1, (total + page_size - 1) // page_size) if total else 1
        if page > total_pages:
            page = total_pages
        offset = (page - 1) * page_size

        rows = conn.execute(
            f"""
            SELECT *
            FROM relay_operation_log
            WHERE 1=1{where_sql}
            ORDER BY {sort_column} {sort_direction}, id DESC
            LIMIT ? OFFSET ?
            """,
            params + [page_size, offset],
        ).fetchall()

        filters = build_relay_log_filters(conn, where_sql, params)
        records = [row_to_relay_log_record(row) for row in rows]
    finally:
        conn.close()

    return JSONResponse(
        content={
            "records": records,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "filters": filters,
        }
    )


@router.get("/api/relay-operation-log/{log_id}")
async def get_relay_operation_log_detail(
    log_id: int,
    user: dict = Depends(require_permission("Remote Maintain")),
):
    conn = get_db_connection()
    row = conn.execute(
        "SELECT * FROM relay_operation_log WHERE id = ?",
        (log_id,),
    ).fetchone()
    conn.close()

    if not row:
        return JSONResponse(content={"error": "Log entry not found"}, status_code=404)

    record = row_to_relay_log_record(row)
    try:
        attempts = json.loads(row["attempts_json"] or "[]")
    except json.JSONDecodeError:
        attempts = []

    return JSONResponse(content={"record": record, "attempts": attempts})


@router.post("/relay-connect")
async def relay_connect(request: Request):
    data = await request.json()
    selected_meters = data.get("selected_meters", [])
    user = request.session.get("user") or {}
    username = user.get("username", "unknown")

    results = []
    for meter_id_str in selected_meters:
        log_id = create_relay_operation_log(meter_id_str, "Switch-On", username)
        meter_id = int(meter_id_str)
        conn = get_db_connection()
        conn.row_factory = sqlite3.Row
        meter_info = conn.execute(
            "SELECT device_type, DCU_number FROM installed_meters WHERE meter_number = ?",
            (str(meter_id_str),)
        ).fetchone()
        meter_info_registered = conn.execute(
                "SELECT device_type, com_address FROM registered_meters WHERE meter_number = ?", 
                (meter_id_str,)
            ).fetchone() 
        HDLC_addr = format(int(meter_info_registered['com_address']), 'X') 
        conn.close()
        if not meter_info:
            relay_result(results, log_id,{
                "meter_number": meter_id_str, 
                "status": "error",
                "message": "Error: Meter not found in database"
            })
            continue
        device_type = meter_info['device_type']
        dcu_number = meter_info["DCU_number"] 
        is_plc_meter = "plc" in device_type.lower() 
        is_rs485_with_edat = "rs485 with edat" in device_type.lower()  
        if dcu_number: 
            dcu_number = str(dcu_number).strip() 
        
        result = {
            "meter_number": meter_id_str,
            "status": "error",
            "message": ""
        }
        if is_plc_meter: 
            print("plc meter") 
            if not dcu_number: 
                update_online_status(meter_id_str, False)
                relay_result(results, log_id,{
                    "meter_number": meter_id_str,  
                    "status": "error",
                    "message": "Error: no DCU"  
                }) 
                continue
            elif dcu_number not in connected_clients:  
                print(connected_clients)  
                update_online_status(meter_id_str, False)
                relay_result(results, log_id,{
                    "meter_number": meter_id_str, 
                    "status": "error",
                    "message": "Error: DCU is offline" 
                }) 
                continue
            result_queue = None
            try:
                result_queue = connected_clients[dcu_number]['real_time_result']  
                response_queue = connected_clients[dcu_number]['response_queue'] 
                connected_clients[dcu_number]['pause_event'].clear() 
                while True:
                    try:
                        response_queue.get_nowait() 
                        print("Clearing old response from queue...")
                    except asyncio.QueueEmpty:
                        print("Response queue cleared.")
                        break 
                print("frame sent") 
                await read_plc_meter_manual(dcu_number, meter_id, generate_relay_frame_plc(meter_id, "connect"))       
                print("waiting for response") 
                response = await asyncio.wait_for(result_queue.get(), timeout=30) 
                print(f"response:{response}")   
                data_bytes = response['response']
                # Optimistically assume relay is now connected after successful command
                update_relay_status_in_db(meter_id, "connected")
                update_online_status(meter_id, True)
                relay_result(results, log_id,{
                    "meter_number": meter_id,
                    "status": "success",
                    "message": "Relay connected successfully",
                    "data": data_bytes
                }) 
            except asyncio.TimeoutError:
                print("timeout") 
                if result_queue:
                    while True:
                        try:
                            result_queue.get_nowait()
                            print("Clearing old response...")
                        except asyncio.QueueEmpty:
                            print("Queue is empty now.")
                            break 
                update_online_status(meter_id, False)
                update_online_status(meter_id, False)
                relay_result(results, log_id,{
                    "meter_number": meter_id_str,   
                    "status": "error",
                    "message": "Error: Timed out waiting for METER response" 
                })
            except Exception as e:
                print(f"Error processing PLC meter {meter_id}: {str(e)}")
                update_online_status(meter_id, False)
                relay_result(results, log_id,{
                    "meter_number": meter_id_str,
                    "status": "error",
                    "message": f"Error: {str(e)}"
                })
            finally: 
                 connected_clients[dcu_number]['pause_event'].set()  
        if is_rs485_with_edat: 
            print("is_rs485_with_edat") 
            if not dcu_number: 
                update_online_status(meter_id_str, False)
                relay_result(results, log_id,{
                    "meter_number": meter_id_str,  
                    "status": "error",
                    "message": "Error: no DCU"  
                }) 
                continue
            elif dcu_number not in connected_clients: 
                print(f"dcu_number: {dcu_number}")   
                print(connected_clients)  
                update_online_status(meter_id_str, False) 
                relay_result(results, log_id,{
                    "meter_number": meter_id_str, 
                    "status": "error",
                    "message": "Error: DCU is offline" 
                }) 
                continue
            result_queue = None
            try:
                result_queue = connected_clients[dcu_number]['real_time_result']  
                response_queue = connected_clients[dcu_number]['response_queue'] 
                connected_clients[dcu_number]['pause_event'].clear() 
                while True:
                    try:
                        response_queue.get_nowait() 
                        print("Clearing old response from queue...")
                    except asyncio.QueueEmpty:
                        print("Response queue cleared.")
                        break 
                print("frame sent") 
                await send_handshake_frame_to_edat(dcu_number,HDLC_addr,"47190205",100)
                await read_RS485_with_EDAT_meter_manual(dcu_number, meter_id,HDLC_addr,"47190205", build_get_request(HDLC_addr,"0.0.96.3.10.255","0046","03","76","C3")) 
                       
                response = await asyncio.wait_for(result_queue.get(), timeout=30) 
                await read_RS485_with_EDAT_meter_manual(dcu_number, meter_id,HDLC_addr,"47190205",  build_relay_operation_byte(HDLC_addr,"0.0.96.3.10.255","0046","0F","98","C4","02"))         
                print("waiting for response") 
                response = await asyncio.wait_for(result_queue.get(), timeout=30) 
                print(f"response:{response}")   
                data_bytes = response['response']
                # Optimistically assume relay is now connected after successful command
                if data_bytes[34:36] == "00": 
                    relay_result(results, log_id,{
                    "meter_number": meter_id_str, 
                    "status": "success",
                    "message": "Relay connected successfully",
                    "data": data_bytes
                    })         
                    update_relay_status_in_db(meter_id_str, "connected")   
                    
                else: 
                    relay_result(results, log_id,{
                    "meter_number": meter_id_str, 
                    "status": "failed", 
                    "message": "Relay connected unsuccessfully", 
                    "data": data_bytes
                    })
                update_online_status(meter_id_str, True)  
            except asyncio.TimeoutError:
                print("timeout") 
                if result_queue:
                    while True:
                        try:
                            result_queue.get_nowait()
                            print("Clearing old response...")
                        except asyncio.QueueEmpty:
                            print("Queue is empty now.")
                            break 
                update_online_status(meter_id, False)
                update_online_status(meter_id, False)
                relay_result(results, log_id,{
                    "meter_number": meter_id_str,   
                    "status": "error",
                    "message": "Error: Timed out waiting for METER response" 
                })
            except Exception as e:
                print(f"Error processing RS485 with EDAT meter {meter_id}: {str(e)}")
                update_online_status(meter_id_str, False) 
                relay_result(results, log_id,{
                    "meter_number": meter_id_str,
                    "status": "error",
                    "message": f"Error: {str(e)}"
                })
            finally: 
                 connected_clients[dcu_number]['pause_event'].set()
        else: 
            print("gprs meter") 
            if meter_id not in connected_clients:
                result["message"] = "Error: Meter is offline"
                update_online_status(meter_id, False)
                relay_result(results, log_id,result)
                continue
            
            try:
                # TODO: Implement actual relay connect frame
                # For now, this is a placeholder
                result_queue = connected_clients[meter_id]['real_time_result']
                response_queue = connected_clients[meter_id]['response_queue']
                
                # Clear response queue
                while True:
                    try:
                        response_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                
                # Send connect command (placeholder - replace with actual frame)
                # await read_meter_manual(meter_id, "RELAY_CONNECT_FRAME", True)
                
                result["status"] = "success"
                result["message"] = "Relay connected successfully"
                update_relay_status_in_db(meter_id, "connected")
            except Exception as e:
                result["message"] = f"Error: {str(e)}"
                update_online_status(meter_id, False)
            
            relay_result(results, log_id,result)
    
    return JSONResponse(content={"results": results})


@router.post("/relay-disconnect")
async def relay_disconnect(request: Request):
    data = await request.json()
    selected_meters = data.get("selected_meters", [])
    user = request.session.get("user") or {}
    username = user.get("username", "unknown")

    results = []
    for meter_id_str in selected_meters:
        log_id = create_relay_operation_log(meter_id_str, "Switch-Off", username)
        meter_id = int(meter_id_str)
        conn = get_db_connection()
        conn.row_factory = sqlite3.Row
        meter_info = conn.execute(
            "SELECT device_type, DCU_number FROM installed_meters WHERE meter_number = ?",
            (str(meter_id_str),)
        ).fetchone()
        meter_info_registered = conn.execute(
                "SELECT device_type, com_address FROM registered_meters WHERE meter_number = ?", 
                (meter_id_str,)
            ).fetchone() 
        HDLC_addr = format(int(meter_info_registered['com_address']), 'X')  
        conn.close()
        if not meter_info:
            relay_result(results, log_id,{
                "meter_number": meter_id_str, 
                "status": "error",
                "message": "Error: Meter not found in database"
            })
            continue
        device_type = meter_info['device_type']
        dcu_number = meter_info["DCU_number"] 
        is_plc_meter = "plc" in device_type.lower() 
        is_rs485_with_edat = "rs485 with edat" in device_type.lower() 
        if dcu_number: 
            dcu_number = str(dcu_number).strip()
        result = {
            "meter_number": meter_id,
            "status": "error",
            "message": ""
        }
        if is_plc_meter: 
            print("plc meter") 
            if not dcu_number: 
                update_online_status(meter_id, False)
                relay_result(results, log_id,{
                    "meter_number": meter_id_str,  
                    "status": "error",
                    "message": "Error: no DCU"  
                }) 
                continue
            elif dcu_number not in connected_clients:  
                print(connected_clients)  
                update_online_status(meter_id, False)
                relay_result(results, log_id,{
                    "meter_number": meter_id_str, 
                    "status": "error",
                    "message": "Error: DCU is offline" 
                }) 
                continue
            result_queue = None
            try:
                result_queue = connected_clients[dcu_number]['real_time_result']  
                response_queue = connected_clients[dcu_number]['response_queue'] 
                connected_clients[dcu_number]['pause_event'].clear() 
                while True:
                    try:
                        response_queue.get_nowait() 
                        print("Clearing old response from queue...")
                    except asyncio.QueueEmpty:
                        print("Response queue cleared.")
                        break 
                print("frame sent") 
                await read_plc_meter_manual(dcu_number, meter_id, generate_relay_frame_plc(meter_id, "disconnect"))       
                print("waiting for response") 
                response = await asyncio.wait_for(result_queue.get(), timeout=30) 
                print(f"response:{response}")   
                data_bytes = response['response']
                # Optimistically assume relay is now disconnected after successful command
                update_relay_status_in_db(meter_id, "disconnected")
                update_online_status(meter_id, True)
                relay_result(results, log_id,{
                    "meter_number": meter_id,
                    "status": "success",
                    "message": "Relay disconnected successfully",
                    "data": data_bytes
                }) 
            except asyncio.TimeoutError:
                print("timeout") 
                if result_queue:
                    while True:
                        try:
                            result_queue.get_nowait()
                            print("Clearing old response...")
                        except asyncio.QueueEmpty:
                            print("Queue is empty now.")
                            break 
                update_online_status(meter_id, False)
                relay_result(results, log_id,{
                    "meter_number": meter_id_str,   
                    "status": "error",
                    "message": "Error: Timed out waiting for METER response" 
                })
            except Exception as e:
                print(f"Error processing PLC meter {meter_id}: {str(e)}")
                update_online_status(meter_id, False)
                relay_result(results, log_id,{
                    "meter_number": meter_id_str,
                    "status": "error",
                    "message": f"Error: {str(e)}"
                }) 
            finally: 
                 connected_clients[dcu_number]['pause_event'].set()      
        if is_rs485_with_edat: 
            print("is_rs485_with_edat") 
            if not dcu_number: 
                update_online_status(meter_id_str, False)
                relay_result(results, log_id,{
                    "meter_number": meter_id_str,  
                    "status": "error",
                    "message": "Error: no DCU"  
                }) 
                continue
            elif dcu_number not in connected_clients: 
                print(f"dcu_number: {dcu_number}")   
                print(connected_clients)  
                update_online_status(meter_id_str, False) 
                relay_result(results, log_id,{
                    "meter_number": meter_id_str, 
                    "status": "error",
                    "message": "Error: DCU is offline" 
                }) 
                continue
            result_queue = None
            try:
                result_queue = connected_clients[dcu_number]['real_time_result']  
                response_queue = connected_clients[dcu_number]['response_queue'] 
                connected_clients[dcu_number]['pause_event'].clear() 
                while True:
                    try:
                        response_queue.get_nowait() 
                        print("Clearing old response from queue...")
                    except asyncio.QueueEmpty:
                        print("Response queue cleared.")
                        break 
                print("frame sent") 
                await send_handshake_frame_to_edat(dcu_number,HDLC_addr,"47190205",100)
                await read_RS485_with_EDAT_meter_manual(dcu_number, meter_id,HDLC_addr,"47190205", build_get_request(HDLC_addr,"0.0.96.3.10.255","0046","03","76","C3")) 
                       
                response = await asyncio.wait_for(result_queue.get(), timeout=30) 
                await read_RS485_with_EDAT_meter_manual(dcu_number, meter_id,HDLC_addr,"47190205",  build_relay_operation_byte(HDLC_addr,"0.0.96.3.10.255","0046","0F","98","C4","01"))         
                print("waiting for response") 
                response = await asyncio.wait_for(result_queue.get(), timeout=30) 
                print(f"response:{response}")   
                data_bytes = response['response']
                # Optimistically assume relay is now connected after successful command
                if data_bytes[34:36] == "00": 
                    relay_result(results, log_id,{
                    "meter_number": meter_id_str, 
                    "status": "success",
                    "message": "Relay disconnected successfully",
                    "data": data_bytes
                    })         
                    update_relay_status_in_db(meter_id_str, "connected")   
                    
                else: 
                    relay_result(results, log_id,{
                    "meter_number": meter_id_str, 
                    "status": "failed", 
                    "message": "Relay disconnected unsuccessfully", 
                    "data": data_bytes
                    })
                update_online_status(meter_id_str, True)  
            except asyncio.TimeoutError:
                print("timeout") 
                if result_queue:
                    while True:
                        try:
                            result_queue.get_nowait()
                            print("Clearing old response...")
                        except asyncio.QueueEmpty:
                            print("Queue is empty now.")
                            break 
                update_online_status(meter_id, False)
                update_online_status(meter_id, False)
                relay_result(results, log_id,{
                    "meter_number": meter_id_str,   
                    "status": "error",
                    "message": "Error: Timed out waiting for METER response" 
                })
            except Exception as e:
                print(f"Error processing RS485 with EDAT meter {meter_id}: {str(e)}")
                update_online_status(meter_id_str, False) 
                relay_result(results, log_id,{
                    "meter_number": meter_id_str,
                    "status": "error",
                    "message": f"Error: {str(e)}"
                })
            finally: 
                 connected_clients[dcu_number]['pause_event'].set()
        else: 
            print("gprs meter") 
            if meter_id not in connected_clients:
                result["message"] = "Error: Meter is offline"
                update_online_status(meter_id, False)
                relay_result(results, log_id,result)
                continue
            
            try:
                # TODO: Implement actual relay connect frame
                # For now, this is a placeholder
                result_queue = connected_clients[meter_id]['real_time_result']
                response_queue = connected_clients[meter_id]['response_queue']
                
                # Clear response queue
                while True:
                    try:
                        response_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                
                # Send connect command (placeholder - replace with actual frame)
                # await read_meter_manual(meter_id, "RELAY_CONNECT_FRAME", True)
                
                result["status"] = "success"
                result["message"] = "Relay disconnected successfully"
                update_relay_status_in_db(meter_id, "disconnected")
            except Exception as e:
                result["message"] = f"Error: {str(e)}"
                update_online_status(meter_id, False)
            
            relay_result(results, log_id,result)
    
    return JSONResponse(content={"results": results})


@router.post("/relay-status")
async def relay_status(request: Request):
    data = await request.json()
    selected_meters = data.get("selected_meters", [])
    
    results = []
    for meter_id_str in selected_meters:
        meter_id = int(meter_id_str)
        conn = get_db_connection()
        conn.row_factory = sqlite3.Row
        meter_info = conn.execute(
            "SELECT device_type, DCU_number FROM installed_meters WHERE meter_number = ?",
            (str(meter_id),)
        ).fetchone()
        conn.close()
        if not meter_info:
            results.append({
                "meter_number": meter_id_str, 
                "status": "error",
                "message": "Error: Meter not found in database"
            })
            continue
        device_type = meter_info['device_type']
        dcu_number = meter_info["DCU_number"] 
        is_plc_meter = "plc" in device_type.lower() 
        if dcu_number: 
            dcu_number = int(str(dcu_number).strip())
        result = {
            "meter_number": meter_id,
            "status": "error",
            "message": ""
        }
        if is_plc_meter: 
            print("plc meter") 
            if not dcu_number: 
                results.append({
                    "meter_number": meter_id_str,  
                    "status": "error",
                    "message": "Error: no DCU"  
                }) 
                continue
            elif dcu_number not in connected_clients:  
                print(connected_clients)  
                results.append({
                    "meter_number": meter_id_str, 
                    "status": "error",
                    "message": "Error: DCU is offline" 
                }) 
                continue
            result_queue = None
            try:
                result_queue = connected_clients[dcu_number]['real_time_result']  
                response_queue = connected_clients[dcu_number]['response_queue'] 
                connected_clients[dcu_number]['pause_event'].clear() 
                while True:
                    try:
                        response_queue.get_nowait() 
                        print("Clearing old response from queue...")
                    except asyncio.QueueEmpty:
                        print("Response queue cleared.")
                        break 
                print("frame sent") 
                await read_plc_meter_manual(dcu_number, meter_id, generate_relay_frame_plc(meter_id, "relay_status"))      
                print("waiting for response") 
                response = await asyncio.wait_for(result_queue.get(), timeout=30) 
                print(f"response:{response}")   
                data_bytes = response['response']
                print(len(data_bytes))  
                relay_stat = "Unknown" 
                if len(data_bytes) == 28: 
                    if data_bytes[26:] == "00":  
                        relay_stat = "disconnected" 
                    elif data_bytes[26:] == "01":
                        relay_stat = "connected" 
                # Persist the latest status read from the meter
                update_relay_status_in_db(meter_id, relay_stat)
                update_online_status(meter_id, True)
                results.append({
                    "meter_number": meter_id,
                    "status": "success", 
                    "relay_status": relay_stat, 
                    "message": "Relay status read successfully",
                    "data": data_bytes
                })  
            except asyncio.TimeoutError:
                print("timeout") 
                if result_queue:
                    while True:
                        try:
                            result_queue.get_nowait()
                            print("Clearing old response...")
                        except asyncio.QueueEmpty:
                            print("Queue is empty now.")
                            break 
                results.append({
                    "meter_number": meter_id_str,   
                    "status": "error",
                    "message": "Error: Timed out waiting for METER response" 
                })
            except Exception as e:
                print(f"Error processing PLC meter {meter_id}: {str(e)}")
                results.append({
                    "meter_number": meter_id_str,
                    "status": "error",
                    "message": f"Error: {str(e)}"
                }) 
            finally: 
                connected_clients[dcu_number]['pause_event'].set()   

        else: 
            print("gprs meter") 
            if meter_id not in connected_clients:
                result["message"] = "Error: Meter is offline"
                update_online_status(meter_id, False)
                results.append(result)
                continue
            
            try:
                # TODO: Implement actual relay connect frame
                # For now, this is a placeholder
                result_queue = connected_clients[meter_id]['real_time_result']
                response_queue = connected_clients[meter_id]['response_queue']
                
                # Clear response queue
                while True:
                    try:
                        response_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                
                # Send connect command (placeholder - replace with actual frame)
                # await read_meter_manual(meter_id, "RELAY_CONNECT_FRAME", True)
                
                result["status"] = "success"
                result["message"] = "Relay connected successfully"
            except Exception as e:
                result["message"] = f"Error: {str(e)}"
            
            results.append(result)
    
    return JSONResponse(content={"results": results})

