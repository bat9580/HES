import asyncio
import sqlite3
import json
from typing import Dict, List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from services.database import get_db_connection
from services.state import connected_clients, pending_requests
from utils import frames
from utils.utility_functions import require_permission, template_response
from utils.DCU_functions import build_dcu_download_frame
from utils.DCU_clear_meter import build_dcu_clear_frame
from utils.blacklist_parser import (
    estimate_entries_in_payload,
    parse_dlms_array,
    peek_blacklist_array_qty,
    stitch_blacklist_frames,
)
from utils.communication_quality_parser import parse_communication_quality_response
from utils.dcu_invoke_id import with_dcu_invoke

templates = Jinja2Templates(directory="templates")

router = APIRouter()


def _safe_fetch_all(conn: sqlite3.Connection, query: str) -> List[sqlite3.Row]:
    try:
        return conn.execute(query).fetchall()
    except sqlite3.OperationalError:
        return []

async def clear_response_queue(response_queue):
    """Clear all items from the response queue."""
    cleared_count = 0
    while True:
        try:
            response_queue.get_nowait()
            cleared_count += 1
        except asyncio.QueueEmpty:
            break
    if cleared_count > 0:
        print(f"🧹 Cleared {cleared_count} old response(s) from queue")
    return cleared_count 
@router.get("/meter-download", response_class=HTMLResponse)
async def meter_download(
    request: Request,
    zone: str = Query("", alias="zone"),
    power_grid: str = Query("", alias="power_grid"),
    dcu_number: str = Query("", alias="dcu_number"),
    meter_number: str = Query("", alias="meter_number"),
    point_number: int = Query(16, alias="point_number"),
    user: dict = Depends(require_permission("Archive")),
):
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row

    zones = [row[0] for row in _safe_fetch_all(conn, "SELECT DISTINCT Zone FROM installed_meters WHERE Zone IS NOT NULL AND Zone != '' ORDER BY Zone")]  # type: ignore[arg-type]
    power_grids = [row[0] for row in _safe_fetch_all(conn, "SELECT DISTINCT station FROM installed_meters WHERE station IS NOT NULL AND station != '' ORDER BY station")]  # type: ignore[arg-type]

    dcu_rows = _safe_fetch_all(
        conn,
        "SELECT dcu_number, status FROM registered_dcus ORDER BY dcu_number",
    )

    dcu_list: List[Dict[str, Optional[str]]] = [
        {
            "number": row["dcu_number"],
            "status": (row["status"] or "").lower(),
            "active": False,
        }
        for row in dcu_rows
    ]

    selected_dcu = dcu_number or (dcu_list[0]["number"] if dcu_list else "") 
    for dcu in dcu_list:
        if dcu["number"] == selected_dcu:
            dcu["active"] = True

    meters_query = "SELECT meter_number, com_address, device_type, type, status,online_status, point_number, COALESCE(downloaded_to_dcu, 0) as downloaded_to_dcu FROM installed_meters WHERE 1=1"
    params: List[str] = []

    if meter_number:
        meters_query += " AND meter_number LIKE ?"
        params.append(f"%{meter_number}%")
    if selected_dcu:
        meters_query += " AND TRIM(COALESCE(DCU_number, '')) = TRIM(?)"
        params.append(selected_dcu)
    if zone:
        meters_query += " AND (Zone LIKE ?)"
        params.append(f"%{zone}%")
    if power_grid:
        meters_query += " AND (station LIKE ?)"
        params.append(f"%{power_grid}%")

    meter_rows_raw = []
    try:
        meter_rows_raw = conn.execute(meters_query, params).fetchall()
    except sqlite3.OperationalError:
        meter_rows_raw = []

    conn.close()
    for row in meter_rows_raw:
        print(row["online_status"]) 
        print(row["meter_number"]) 
    meter_rows = [
        {
            "point_no": row["point_number"] if row["point_number"] is not None else 0, 
            "comm_address": row["com_address"],
            "meter_number": row["meter_number"],
            "meter_type": row["type"] or row["device_type"],
            "downloaded": row["downloaded_to_dcu"] == 1,
            "online": (row["online_status"] or "").lower() == "online", 
            "result": None,  # Result field should only show download operation results, not installation status
        }
        for idx, row in enumerate(meter_rows_raw)
    ]
    


    summary = {
        "dcu_number": selected_dcu or None,
        "total_meter_count": len(meter_rows),
        "downloaded_meter_count": sum(1 for row in meter_rows if row["downloaded"]),
        "online_meter_count": sum(1 for row in meter_rows if row["online"]),
        "latency": "—",
        "last_sync": "—",
    }

    filters = {
        "zone": zone,
        "power_grid": power_grid,
        "dcu_number": dcu_number,
        "meter_number": meter_number,
    }

    context = {
        "request": request,
        "filters": filters,
        "zones": zones,
        "power_grids": power_grids,
        "dcu_numbers": [dcu["number"] for dcu in dcu_list],
        "dcu_list": dcu_list,
        "summary": summary,
        "meter_rows": meter_rows,
        "connected_clients": connected_clients,
    }

    return template_response(request, "meter_download.html", context)


@router.get("/meter-download/search", response_class=HTMLResponse)
async def search_meter_download(
    request: Request,
    zone: str = Query("", alias="zone"),
    power_grid: str = Query("", alias="power_grid"),
    dcu_number: str = Query("", alias="dcu_number"),
    meter_number: str = Query("", alias="meter_number"),
    user: dict = Depends(require_permission("Archive")),
):
    
 
    # Redirect to main endpoint with query parameters
    # This maintains consistency with the main endpoint logic
    return await meter_download(request, zone, power_grid, dcu_number, meter_number, user)


@router.post("/check-downloaded-meters")
async def check_downloaded_meters(request: Request, user: dict = Depends(require_permission("Archive"))):
    """
    Check which meters are downloaded in the DCU by sending a query frame.
    Sends frame to DCU and returns the response.
    """
    try:
        data = await request.json()
        dcu_number = data.get("dcu_number", "")
        
        if not dcu_number:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "DCU number is required"}
            )
        
        # Check if DCU is connected
        dcu_number_int = int(dcu_number) if str(dcu_number).isdigit() else None
        if not dcu_number_int or dcu_number_int not in connected_clients:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": f"DCU {dcu_number} is not connected"}
            )
        
        # Frame template (invoke byte after c001 is set by with_dcu_invoke)
        check_frame = "000100500001000dc0014000010000803206ff0200"
        next_frame_header = "0001005000010007c002"
        dcu_k = str(dcu_number_int)

        try:
            queue = connected_clients[dcu_number_int]['queue']
            response_queue = connected_clients[dcu_number_int]['response_queue']
             
            # Clear pause event to allow communication
            connected_clients[dcu_number_int]['pause_event'].clear()
            await clear_response_queue(response_queue) 
            # Send frame to DCU
            check_frame = with_dcu_invoke(check_frame, dcu_k)
            print(f"📤 Sending check downloaded meters frame to DCU {dcu_number}: {check_frame}")
            is_last_frame = False
            frame_count = 1 
            await queue.put(bytes.fromhex(check_frame)) 
            responses = []  
            no_meters_downloaded = False   
            while not is_last_frame:
                response = await asyncio.wait_for(response_queue.get(), timeout=30)
                response_hex = response.hex().upper() if isinstance(response, bytes) else str(response) 
                if len(response) > 14 and response[0:6].hex() == "000100010050": 
                    print("frame number indicator")   
                    print(response[12:15].hex()) 
                    if response[12:15].hex() != "000000":     
                        responses.append(response) 
                        is_last_frame = True 
                        break  
                    if response[11:12].hex() == "01": 
                        responses.append(response)  
                        is_last_frame = True 
                        break 
                print("length: ")  
                print(len(response)) 
                print(response.hex()) 
                if len(response) == 1676:
                    responses.append(response) 
                    print("the frame is full, getting the next frame") 
                    frame_count += 1 
                    check_frame = with_dcu_invoke(
                        next_frame_header + "40" + f"{frame_count:08x}", dcu_k
                    )
                    await queue.put(bytes.fromhex(check_frame))    
                elif len(response) == 45:   
                    print("not expected response, listening again") 
                    continue 
                elif len(response) == 16: 
                    print("not expected response, listening again") 
                    continue  
                elif len(response) == 14:
                    
                    if(response[12:].hex() == "0100"): 
                        print("no meters downloaded")   
                        no_meters_downloaded = True  
                        is_last_frame = True  
                        break 
                elif len(response) < 1676:   
                    if int(response[6:8].hex(), 16) + 8 == len(response):
                        responses.append(response) 
                        check_frame = with_dcu_invoke(
                            next_frame_header + "40" + f"{frame_count:08x}", dcu_k
                        )
                        await queue.put(bytes.fromhex(check_frame)) 
                        continue
                    else:
                        print("the frame is not full, listening again")   
                        half_frame1 = response 
                        half_frame2 = await asyncio.wait_for(response_queue.get(), timeout=30) 
                        if  len(half_frame1) > 1024: 
                            full_frame = half_frame1 + half_frame2 
                        else: 
                            full_frame = half_frame2 + half_frame1 
                        print("full frame: ")  
                        print(full_frame.hex())   
                        responses.append(full_frame)   
                        check_frame = with_dcu_invoke(
                            next_frame_header + "40" + f"{frame_count:08x}", dcu_k
                        )
                        await queue.put(bytes.fromhex(check_frame)) 
                        continue
                        
            dataframe = ""  
            if not no_meters_downloaded: 
                for response in responses: 
                    dataframe = dataframe + response[20:].hex() 
                
                
                total_meter_number = int(dataframe[1:2], 16) 
                meter_numbers = []
                frame_hex = dataframe[2:] 
                i = 0
                while i < len(frame_hex) - 16:
                    if frame_hex[i:i+4] == "0906":
                        meter_hex = frame_hex[i+4:i+16]  # 6 bytes = 12 hex chars
                        meter_number = meter_hex.lstrip("0")
                        meter_numbers.append(meter_number) 
                        i += 16
                    else:
                        i += 2
            else: 
                # No meters downloaded in DCU
                meter_numbers = []
                total_meter_number = 0
                dataframe = ""

            connected_clients[dcu_number_int]['pause_event'].set()

            return JSONResponse(
                content={
                    "success": True,
                    "dcu_number": dcu_number,
                    "response_hex": response_hex,
                    "response_length": len(response),
                    "meter_numbers": meter_numbers,
                    "total_meter_number": total_meter_number,
                    "message": "Response received from DCU. Check terminal for details."
                }
            )
            
        except asyncio.TimeoutError:
            connected_clients[dcu_number_int]['pause_event'].set()
            print(f"❌ Timeout waiting for response from DCU {dcu_number}")
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": "Timed out waiting for DCU response"}
            )
        except Exception as comm_error:
            if dcu_number_int in connected_clients:
                connected_clients[dcu_number_int]['pause_event'].set()
            print(f"❌ Error communicating with DCU: {comm_error}")
            import traceback
            traceback.print_exc()
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": f"Failed to communicate with DCU: {str(comm_error)}"}
            )
        
    except ValueError as e:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": f"Invalid DCU number format: {str(e)}"}
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"Failed to check downloaded meters: {str(e)}"}
        )
@router.post("/check-online-meters") 
async def check_online(request: Request, user: dict = Depends(require_permission("Archive"))):
    """
    Check which meters are downloaded in the DCU by sending a query frame.
    Sends frame to DCU and returns the response.
    """
    try:
        data = await request.json()
        dcu_number = data.get("dcu_number", "")
        
        if not dcu_number:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "DCU number is required"}
            )
        
        # Check if DCU is connected
        dcu_number_int = int(dcu_number) if str(dcu_number).isdigit() else None
        if not dcu_number_int or dcu_number_int not in connected_clients:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": f"DCU {dcu_number} is not connected"}
            )
        
        check_frame = "000100500001000dc0014000010000803206ff0300"  # check online frame
        next_frame_header = "0001005000010007c002"
        dcu_k = str(dcu_number_int)

        try:
            queue = connected_clients[dcu_number_int]['queue']
            response_queue = connected_clients[dcu_number_int]['response_queue']
             
            # Clear pause event to allow communication
            connected_clients[dcu_number_int]['pause_event'].clear()
            await clear_response_queue(response_queue) 
            # Send frame to DCU
            check_frame = with_dcu_invoke(check_frame, dcu_k)
            print(f"📤 Sending check online meters frame to DCU {dcu_number}: {check_frame}")
            is_last_frame = False
            frame_count = 1 
            await queue.put(bytes.fromhex(check_frame)) 
            responses = []  
            no_meters_online = False     
            while not is_last_frame:
                response = await asyncio.wait_for(response_queue.get(), timeout=30)
                response_hex = response.hex().upper() if isinstance(response, bytes) else str(response) 
                if len(response) > 14 and response[0:6].hex() == "000100010050": 
                    print("frame number indicator")   
                    print(response[12:15].hex())
                    if response[12:15].hex() != "000000":     
                        responses.append(response) 
                        is_last_frame = True 
                        break  
                    if response[11:12].hex() == "01": 
                        responses.append(response)  
                        is_last_frame = True 
                        break 
                print("length: ")  
                print(len(response)) 
                print(response.hex()) 
                if len(response) > 370: 
                    responses.append(response) 
                    print("the frame is full, getting the next frame") 
                    frame_count += 1 
                    check_frame = with_dcu_invoke(
                        next_frame_header + "40" + f"{frame_count:08x}", dcu_k
                    )
                    await queue.put(bytes.fromhex(check_frame))    
                elif len(response) == 45:   
                    print("not expected response, listening again") 
                    continue 
                elif len(response) == 16: 
                    print("not expected response, listening again") 
                    continue  
                elif len(response) == 14:
                    if(response[12:].hex() == "0100"): 
                        print("no meters online")   
                        no_meters_online = True  
                        is_last_frame = True  
                        break 
                # elif len(response) < 1676:   
                #     if int(response[6:8].hex(), 16) + 8 == len(response):
                #         responses.append(response) 
                #         check_frame = next_frame_header + f"{inv_pri_second:02x}" + f"{frame_count:08x}"  
                #         await queue.put(bytes.fromhex(check_frame)) 
                #         continue
                #     else:
                #         print("the frame is not full, listening again")   
                #         half_frame1 = response 
                #         half_frame2 = await asyncio.wait_for(response_queue.get(), timeout=30) 
                #         if  len(half_frame1) > 1024: 
                #             full_frame = half_frame1 + half_frame2 
                #         else: 
                #             full_frame = half_frame2 + half_frame1 
                #         print("full frame: ")  
                #         print(full_frame.hex())   
                #         responses.append(full_frame)   
                #         check_frame = next_frame_header + f"{inv_pri_second:02x}" + f"{frame_count:08x}"  
                #         await queue.put(bytes.fromhex(check_frame)) 
                #         continue
                        
            dataframe = ""  
            if not no_meters_online:
                if len(responses) == 1:
                    dataframe = responses[0][13:].hex() 
                else: 
                    for response in responses: 
                        dataframe = dataframe + response[20:].hex()
                    
                total_meter_number = int(dataframe[1:2], 16) 
                meter_numbers = []
                frame_hex = dataframe[2:] 
                i = 0
                while i < len(frame_hex) - 16:
    
                    if frame_hex[i:i+4] == "0906":
                        meter_hex = frame_hex[i+4:i+16]  # 6 bytes = 12 hex chars
                        meter_number = meter_hex.lstrip("0")
                        meter_numbers.append(meter_number) 
                        i += 32
                    elif frame_hex[i:i+4] == "0904":
                        meter_hex = frame_hex[i+4:i+12]
                        meter_number = meter_hex.lstrip("0")
                        meter_numbers.append(meter_number) 
                        i += 24 
                    else: 
                        i += 2
            else: 
                # No meters downloaded in DCU
                meter_numbers = []
                total_meter_number = 0
                dataframe = ""

            connected_clients[dcu_number_int]['pause_event'].set()

            return JSONResponse(
                content={
                    "success": True,
                    "dcu_number": dcu_number,
                    "response_hex": response_hex,
                    "response_length": len(response),
                    "meter_numbers": meter_numbers,
                    "total_meter_number": total_meter_number,
                    "message": "Response received from DCU. Check terminal for details."
                }
            )
            
        except asyncio.TimeoutError:
            print(f"❌ Timeout waiting for response from DCU {dcu_number}")
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": "Timed out waiting for DCU response"}
            )
        except Exception as comm_error:
            if dcu_number_int in connected_clients:
                connected_clients[dcu_number_int]['pause_event'].set()
            print(f"❌ Error communicating with DCU: {comm_error}")
            import traceback
            traceback.print_exc()
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": f"Failed to communicate with DCU: {str(comm_error)}"}
            )
        
    except ValueError as e:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": f"Invalid DCU number format: {str(e)}"}
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"Failed to check online meters: {str(e)}"}
        )
    finally:
        connected_clients[dcu_number_int]['pause_event'].set() 

@router.post("/read-dcu-blacklist")
async def read_blacklist(request: Request, user: dict = Depends(require_permission("Archive"))):
    """
    Read DCU blacklist data from the connected DCU.
    Handles multi-frame block transfer when the blacklist is large.
    """
    try:
        data = await request.json()
        dcu_number = data.get("dcu_number")
        
        if not dcu_number:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "DCU number is required"}
            )
        
        # Check if DCU is connected
        dcu_number_int = int(dcu_number) if str(dcu_number).isdigit() else None
        is_connected = dcu_number_int in connected_clients if dcu_number_int else False
        if not is_connected:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": f"DCU {dcu_number} is not connected"}
            )
        
        try:
            queue = connected_clients[dcu_number_int]['queue'] 
            response_queue = connected_clients[dcu_number_int]['response_queue'] 
            dcu_k = str(dcu_number_int)
            next_frame_header = "0001005000010007c002"
            
            # Clear and pause
            connected_clients[dcu_number_int]['pause_event'].clear()
            
            # Clear old responses from queue
            await clear_response_queue(response_queue)
            
            # Send initial blacklist request
            initial_frame = with_dcu_invoke(frames.GET_BLACKLIST, dcu_k)
            print(f"📤 Sending GET_BLACKLIST to DCU {dcu_number}: {initial_frame}")
            is_last_frame = False
            frame_count = 1
            responses = []
            empty_blacklist = False
            await queue.put(bytes.fromhex(initial_frame))

            while not is_last_frame:
                response = await asyncio.wait_for(response_queue.get(), timeout=30)
                if not isinstance(response, bytes):
                    response = bytes(response)

                if len(response) == 14 and response[12:].hex() == "0100":
                    empty_blacklist = True
                    is_last_frame = True
                    break

                if len(response) in (45, 16):
                    continue

                print(f"📥 Blacklist frame {frame_count} from DCU {dcu_number}, length={len(response)}")
                if len(response) > 14 and response[0:6].hex() == "000100010050":
                    print(f"   block header bytes[11:16]={response[11:16].hex()}")

                is_last_block = len(response) <= 370
                if not is_last_block and len(response) > 14 and response[0:6].hex() == "000100010050":
                    if response[12:15].hex() != "000000" or response[11:12].hex() == "01":
                        is_last_block = True
                        print("   last block detected from DCU header flags")

                if len(response) > 370 and not is_last_block:
                    responses.append(response)
                    print("Blacklist block full, requesting next frame")
                    frame_count += 1
                    cont_frame = with_dcu_invoke(
                        next_frame_header + "40" + f"{frame_count:08x}", dcu_k
                    )
                    print(f"   continuation frame: {cont_frame}")
                    await queue.put(bytes.fromhex(cont_frame))
                    continue

                responses.append(response)
                is_last_frame = True
                print(f"   final block collected ({len(responses)} total frame(s))")

            if empty_blacklist:
                combined_hex = ""
                stitch_details = []
            else:
                combined_hex, stitch_details = stitch_blacklist_frames(responses)

            print(f"📊 Blacklist stitch summary: {len(responses)} frame(s)")
            for detail in stitch_details:
                print(
                    f"   frame {detail['frame']}: total={detail['total_bytes']} bytes, "
                    f"offset={detail['offset']}, payload={detail['payload_bytes']} bytes, "
                    f"starts_with={detail['starts_with']}, {detail['note']}"
                )

            expected_qty = peek_blacklist_array_qty(combined_hex) if combined_hex else None
            est_in_payload = estimate_entries_in_payload(combined_hex) if combined_hex else 0
            print(f"📊 Expected blacklist entries (array header): {expected_qty}")
            print(f"📊 Entries that fit in stitched payload: {est_in_payload}")
            print(f"📊 Combined payload length: {len(combined_hex) // 2} bytes ({len(combined_hex)} hex chars)")
            if combined_hex:
                print(f"📊 Full stitched payload hex:\n{combined_hex}")

            try: 
                parsed_data = parse_dlms_array(combined_hex) if combined_hex else []
            except Exception as e:
                print(f"❌ Error parsing DLMS array: {e}")
                import traceback
                traceback.print_exc()
                return JSONResponse(
                    status_code=500,
                    content={"success": False, "error": f"Failed to parse DLMS array: {str(e)}"}
                )
            # Map parsed data to format expected by frontend table
            if parsed_data:
                blacklist_data = []
                for idx, item in enumerate(parsed_data):
                    # Format dates for display
                    first_time_str = item['start_date'].strftime('%Y-%m-%d %H:%M:%S') if item['start_date'] else '—'
                    current_time_str = item['end_date'].strftime('%Y-%m-%d %H:%M:%S') if item['end_date'] else '—'
                    
                    # Use meter number or generate ID for checkbox
                    meter_id = item['meter'] if item['meter'] else f"item_{idx}"
                    comm_addr = item['meter'] if item['meter'] else '—'
                    
                    blacklist_data.append({
                        'comm_addr': comm_addr,
                        'count': item['connection_time'],
                        'first_time': first_time_str,
                        'current_time': current_time_str,
                        'current_dcu_no': dcu_number,
                        'old_dcu_no': "",  # This would need to be determined from the data
                        'id': meter_id  # Use meter number as ID for checkbox
                    })
        
                
                return JSONResponse(
                    content={
                        "success": True,
                        "blacklist_data": blacklist_data,
                        "dcu_number": dcu_number,
                        "total_count": len(blacklist_data),
                        "expected_count": expected_qty,
                        "parsed_count": len(blacklist_data),
                    }
                )
            else:
                return JSONResponse(
                    content={
                        "success": True,
                        "dcu_number": dcu_number,
                        "blacklist_data": [],
                        "total_count": 0,
                    }
                )
            
        except asyncio.TimeoutError:
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": "Timed out waiting for blacklist data from DCU"}
            )
        
    except ValueError as e:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": f"Invalid DCU number format: {str(e)}"}
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"Failed to read blacklist: {str(e)}"}
        )
    finally: 
        connected_clients[dcu_number_int]['pause_event'].set() 


@router.post("/read-dcu-communication-quality")
async def read_dcu_communication_quality(
    request: Request, user: dict = Depends(require_permission("Archive"))
):
    """
    Read DCU communication quality (PLC frame). Table rows are only what the
    response frame parses to — no extra rows from installed_meters.
    """
    dcu_number_int = None
    try:
        data = await request.json()
        dcu_number = data.get("dcu_number")
        if not dcu_number:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "DCU number is required"},
            )

        dcu_number_int = int(dcu_number) if str(dcu_number).isdigit() else None
        if not dcu_number_int or dcu_number_int not in connected_clients:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": f"DCU {dcu_number} is not connected",
                },
            )

        queue = connected_clients[dcu_number_int]["queue"]
        response_queue = connected_clients[dcu_number_int]["response_queue"]
        connected_clients[dcu_number_int]["pause_event"].clear()
        await clear_response_queue(response_queue)

        await queue.put(
            bytes.fromhex(
                with_dcu_invoke(frames.DCU_COMMUNICATION_QUALITY, str(dcu_number_int))
            )
        )
        response = await asyncio.wait_for(response_queue.get(), timeout=30)
        if not isinstance(response, bytes):
            response = bytes(response)

        parsed, parse_warn = parse_communication_quality_response(response)
        # Only rows from the frame; strip internal merge key
        quality_data = []
        for r in parsed:
            row = {k: v for k, v in r.items() if k != "comm_key"}
            quality_data.append(row)

        return JSONResponse(
            content={
                "success": True,
                "dcu_number": dcu_number,
                "quality_data": quality_data,
                "parse_warning": parse_warn,
                "response_length": len(response),
            }
        )
    except asyncio.TimeoutError:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": "Timed out waiting for communication quality from DCU",
            },
        )
    except Exception as e:
        import traceback

        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)},
        )
    finally:
        if dcu_number_int is not None and dcu_number_int in connected_clients:
            connected_clients[dcu_number_int]["pause_event"].set()


@router.post("/download-meters")
async def download_meters(request: Request, user: dict = Depends(require_permission("Archive"))):
    """
    Download selected meters. Sends built frames to the selected DCU.
    """
    print("called") 
    try:
        data = await request.json()
        meters = data.get("meters", [])  # List of dicts with meter_number and point_no
        dcu_number = data.get("dcu_number", "")  # DCU number
        dcu_id = int(dcu_number) 
        if not meters:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "No meters selected"}
            )
        
        if not dcu_number:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "DCU number is required"}
            )
        
        # Check if DCU is connected
        if dcu_id not in connected_clients:
            print(f"DCU {dcu_number} is not connected") 
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": f"DCU {dcu_number} is not connected"}
            )
        print("passed") 
        
        # Prepare meter data for batch frame building
        meter_list = []
        for meter_data in meters:
            meter_number = meter_data.get("meter_number")
            point_number = meter_data.get("point_no", 16)  # Use point_no from HTML, default to 16 if not provided
            
            if not meter_number:
                continue
            
            meter_list.append({
                "meter_number": meter_number,
                "point_number": point_number
            })
        
        if not meter_list:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "No valid meters to download"}
            )
        
        # Build frames for all meters (may return multiple frames if data is large)
        try:
            
            frames_to_send = build_dcu_download_frame(meter_list)
            print(frames_to_send) 
            print(f"Built {len(frames_to_send)} frame(s) for {len(meter_list)} meter(s)")
        except Exception as e:
            print(f"❌ Error building frames: {e}")
            import traceback
            traceback.print_exc()
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": f"Failed to build frames: {str(e)}"}
            )
        
        async def result_generator():
            result_queue = connected_clients[dcu_id]['response_queue']
            connected_clients[dcu_id]['pause_event'].clear()
            await clear_response_queue(result_queue) 
            
            all_frames_successful = True
            last_response_hex = None
            
            # Send all frames sequentially
            for frame_idx, frame in enumerate(frames_to_send):
                print(f"📤 Sending frame {frame_idx + 1}/{len(frames_to_send)}: {frame[:100]}...")
                
                try:
                    # Send frame to DCU
                    await connected_clients[dcu_id]['queue'].put(
                        bytes.fromhex(with_dcu_invoke(frame, str(dcu_id)))
                    )
                    print(f"📤 Sent frame {frame_idx + 1} to DCU {dcu_number}")
                    
                    # Wait for response
                    try:
                        response_data = await asyncio.wait_for(result_queue.get(), timeout=30)
                        response_hex = response_data.hex().upper() if isinstance(response_data, bytes) else str(response_data)
                        last_response_hex = response_hex
                        
                        # For multi-frame, we'll yield meter info after all frames are sent
                        # For now, just track success
                        print(f"✅ Received response for frame {frame_idx + 1}/{len(frames_to_send)}")
                        
                    except asyncio.TimeoutError:
                        print(f"❌ Timeout waiting for response from DCU {dcu_number} for frame {frame_idx + 1}")
                        all_frames_successful = False
                        # Yield error for all meters
                        for meter_info in meter_list:
                            yield json.dumps({
                                "meter_number": meter_info["meter_number"],
                                "point_number": meter_info["point_number"],
                                "result": "Error: Timed out waiting for DCU response",
                                "frame_index": frame_idx + 1,
                                "total_frames": len(frames_to_send)
                            }) + "\n"
                        break  # Stop sending remaining frames on timeout
                    
                except Exception as e:
                    print(f"❌ Error sending frame {frame_idx + 1}: {e}")
                    all_frames_successful = False
                    # Yield error for all meters
                    for meter_info in meter_list:
                        yield json.dumps({
                            "meter_number": meter_info["meter_number"],
                            "point_number": meter_info["point_number"],
                            "result": f"Error: {str(e)}",
                            "frame_index": frame_idx + 1,
                            "total_frames": len(frames_to_send)
                        }) + "\n"
                    break  # Stop sending remaining frames on error
            
            # After all frames are sent, yield results for all meters
            if all_frames_successful:
                # Update database: mark meters as downloaded
                conn = get_db_connection()
                try:
                    meter_numbers_to_update = [m["meter_number"] for m in meter_list]
                    placeholders = ','.join(['?'] * len(meter_numbers_to_update))
                    update_query = f"UPDATE installed_meters SET downloaded_to_dcu = 1 WHERE meter_number IN ({placeholders})"
                    cursor = conn.cursor()
                    cursor.execute(update_query, meter_numbers_to_update)
                    conn.commit()
                    print(f"✅ Marked {cursor.rowcount} meter(s) as downloaded in database")
                except Exception as db_error:
                    print(f"❌ Database update error: {db_error}")
                    import traceback
                    traceback.print_exc()
                finally:
                    conn.close()
                
                for meter_info in meter_list:
                    yield json.dumps({
                        "meter_number": meter_info["meter_number"],
                        "point_number": meter_info["point_number"],
                        "result": "successful",
                        "response": last_response_hex,
                        "total_frames": len(frames_to_send)
                    }) + "\n"
        
        return StreamingResponse(result_generator(), media_type="application/json")
    
    except Exception as e:
        print(f"Error in download_meters: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"Failed to download meters: {str(e)}"}
        )


@router.post("/assign-point-numbers")
async def assign_point_numbers(request: Request, user: dict = Depends(require_permission("Archive"))):
    """
    Assign point numbers to meters with point_number = 0 or NULL.
    Point numbers start from 2, and fill gaps in existing numbers.
    """
    try:
        data = await request.json()
        dcu_number = data.get("dcu_number", "")
        meter_number = data.get("meter_number", "")
        print( "dcu_number: ", dcu_number)
        conn = get_db_connection()
        conn.row_factory = sqlite3.Row
        
        # Build the same query as in meter_download to get filtered meters
        meters_query = "SELECT meter_number, point_number FROM installed_meters WHERE 1=1"
        params: List[str] = []
        
        if meter_number:
            meters_query += " AND meter_number LIKE ?"
            params.append(f"%{meter_number}%")
        if dcu_number:
            meters_query += " AND DCU_number = ?"
            params.append(dcu_number)
        
        # Get all meters matching the filters
        all_meters = conn.execute(meters_query, params).fetchall()
        
        print( "all_meters: ", all_meters)  
        # Get existing point numbers (non-zero, non-null)
        existing_point_numbers = set()
        meters_to_update = []
        
        for row in all_meters:
            point_no = row["point_number"]
            if point_no is not None and point_no != 0:
                existing_point_numbers.add(point_no)
            else:
                # This meter needs a point number assigned
                meters_to_update.append(row["meter_number"])
        print( "meters_to_update: ", meters_to_update)
        print( "existing_point_numbers: ", existing_point_numbers)  
        
        if not meters_to_update:
            print("No meters with point_number 0 found")  
            conn.close()
            return JSONResponse(
                content={"success": True, "message": "No meters with point_number 0 found", "updated_count": 0}
            )
        
        # Find gaps in the sequence and use them first
        all_numbers = sorted(existing_point_numbers)
        gaps = []
        
        # Check for gaps starting from 2
        if all_numbers:
            # Check gap before the first number (from 2 to first number)
            if all_numbers[0] > 2:
                for gap_num in range(2, all_numbers[0]):
                    gaps.append(gap_num)
            
            # Check gaps between numbers
            for i in range(1, len(all_numbers)):
                if all_numbers[i] - all_numbers[i-1] > 1:
                    # There's a gap between all_numbers[i-1] and all_numbers[i]
                    for gap_num in range(all_numbers[i-1] + 1, all_numbers[i]):
                        gaps.append(gap_num)
        else:
            # No existing numbers, so we'll start from 2
            pass
        
        # Sort gaps
        gaps.sort()
        
        # Find the maximum existing point number to know where to continue after gaps
        max_existing = max(existing_point_numbers) if existing_point_numbers else 1  # Start from 1 so next is 2
        
        # Start assigning from max(2, max_existing + 1) after gaps are filled
        next_point_number = max(2, max_existing + 1)
        
        # Assign point numbers
        updated_count = 0
        gap_index = 0
        
        for meter_num in meters_to_update:
            # Use gap if available, otherwise use next_point_number
            if gap_index < len(gaps):
                assigned_point = gaps[gap_index]
                gap_index += 1
            else:
                assigned_point = next_point_number
                next_point_number += 1
            
            # Update the database
            conn.execute(
                "UPDATE installed_meters SET point_number = ? WHERE meter_number = ?",
                (assigned_point, meter_num)
            )
            updated_count += 1
        
        conn.commit()
        conn.close()
        
        return JSONResponse(
            content={
                "success": True,
                "message": f"Successfully assigned point numbers to {updated_count} meter(s)",
                "updated_count": updated_count
            }
        )
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"Failed to assign point numbers: {str(e)}"}
        )


@router.post("/clear-point-numbers")
async def clear_point_numbers(request: Request, user: dict = Depends(require_permission("Archive"))):
    """
    Clear point numbers (set to NULL) for all meters matching the filters.
    Communicates with DCU using specified frame sequence before clearing database.
    """
    try:
        data = await request.json()
        dcu_number = data.get("dcu_number", "")
        zone = data.get("zone", "")
        power_grid = data.get("power_grid", "")
        meter_number = data.get("meter_number", "")
        
        if not dcu_number:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "DCU number is required"}
            )
        
        # Check if DCU is connected
        dcu_number_int = int(dcu_number) if str(dcu_number).isdigit() else None
        if not dcu_number_int or dcu_number_int not in connected_clients:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": f"DCU {dcu_number} is not connected"}
            )
        
        # Exchange frames with DCU
        try:
            queue = connected_clients[dcu_number_int]['queue']
            response_queue = connected_clients[dcu_number_int]['response_queue']
            
            # Clear pause event to allow communication
            connected_clients[dcu_number_int]['pause_event'].clear()
            
            # Frame 1: Server sends first frame
            frame1_server = "00010050000100386036a1090607608574050801018a0207808b0760857405080201ac0a8008554245444e444355be10040e01000000065f1f0400ffffff2800"
            print(f"📤 Sending frame 1 to DCU {dcu_number}: {frame1_server}")
            await queue.put(
                bytes.fromhex(with_dcu_invoke(frame1_server, str(dcu_number_int)))
            )
            
            # Wait for DCU response to frame 1
            response1 = await asyncio.wait_for(response_queue.get(), timeout=30)
            response1_hex = response1.hex().upper() if isinstance(response1, bytes) else str(response1)
            print(f"📥 Received response 1 from DCU {dcu_number}: {response1_hex}")
            
            # Frame 2: Server sends second frame
            frame2_server = "000100500001000fc1014b00010100828300ff02001102"
            print(f"📤 Sending frame 2 to DCU {dcu_number}: {frame2_server}")
            await queue.put(
                bytes.fromhex(with_dcu_invoke(frame2_server, str(dcu_number_int)))
            )
            
            # Wait for DCU response to frame 2
            response2 = await asyncio.wait_for(response_queue.get(), timeout=30)
            response2_hex = response2.hex().upper() if isinstance(response2, bytes) else str(response2)
            print(f"📥 Received response 2 from DCU {dcu_number}: {response2_hex}")
            
            # Set pause event back
            connected_clients[dcu_number_int]['pause_event'].set()
            
        except asyncio.TimeoutError:
            connected_clients[dcu_number_int]['pause_event'].set()
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": "Timed out waiting for DCU response"}
            )
        except Exception as comm_error:
            if dcu_number_int in connected_clients:
                connected_clients[dcu_number_int]['pause_event'].set()
            print(f"❌ Error communicating with DCU: {comm_error}")
            import traceback
            traceback.print_exc()
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": f"Failed to communicate with DCU: {str(comm_error)}"}
            )
        
        # After successful communication, update database
        conn = get_db_connection()
        conn.row_factory = sqlite3.Row
        
        # Build the same query as in meter_download to get filtered meters
        meters_query = "UPDATE installed_meters SET point_number = NULL, downloaded_to_dcu = 0 WHERE 1=1"
        params: List[str] = []
        
        if meter_number:
            meters_query += " AND meter_number LIKE ?"
            params.append(f"%{meter_number}%")
        if dcu_number:
            meters_query += " AND DCU_number = ?"
            params.append(dcu_number)
        if zone:
            meters_query += " AND (Zone LIKE ?)"
            params.append(f"%{zone}%")
        if power_grid:
            meters_query += " AND (station LIKE ?)"
            params.append(f"%{power_grid}%")
        
        # Execute the update
        cursor = conn.cursor()
        cursor.execute(meters_query, params)
        cleared_count = cursor.rowcount
        
        conn.commit()
        conn.close()
        
        return JSONResponse(
            content={
                "success": True,
                "message": f"Successfully cleared point numbers for {cleared_count} meter(s)",
                "cleared_count": cleared_count
            }
        )
        
    except ValueError as e:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": f"Invalid DCU number format: {str(e)}"}
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"Failed to clear point numbers: {str(e)}"}
        )


@router.post("/save-blacklist-meters")
async def save_blacklist_meters(request: Request, user: dict = Depends(require_permission("Archive"))):
    """
    Save selected meters from blacklist to registered_meters and installed_meters tables.
    """
    try:
        data = await request.json()
        meters = data.get("meters", [])  # List of meter dictionaries
        
        if not meters:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "No meters provided"}
            )
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        saved_count = 0
        errors = []
        
        for meter in meters:
            try:
                meter_number = meter.get("meter_number")
                comm_address = meter.get("comm_address")
                device_type = meter.get("device_type", "PLC Meter")
                modem_type = meter.get("modem_type", "DDSY283")
                password = meter.get("password", "")
                CT_ratio = int(meter.get("CT_ratio", 1)) if meter.get("CT_ratio") else 1
                VT_ratio = int(meter.get("VT_ratio", 1)) if meter.get("VT_ratio") else 1
                remarks = meter.get("remarks", "")
                line = meter.get("line", "")
                dcu_number = meter.get("dcu_number", "")
                Zone = meter.get("Zone", "")
                station = meter.get("station", "")
                
                if not meter_number:
                    errors.append(f"Missing meter number: {meter}")
                    continue
                
                if not comm_address:
                    comm_address = meter_number
                
                status = 'installed'
                
                # Determine if PLC meter
                meter_type_normalized = device_type.strip().lower()
                is_plc_meter = "plc" in meter_type_normalized
                dcu_value = dcu_number.strip() if dcu_number else None
                
                # Insert or update registered_meters
                cursor.execute("""
                    INSERT OR REPLACE INTO registered_meters
                    (meter_number, com_address, password, device_type, type, remarks, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    meter_number,
                    comm_address,
                    password,
                    device_type,
                    modem_type,
                    remarks,
                    status
                ))
                
                # Insert or update installed_meters
                cursor.execute("""
                    INSERT OR REPLACE INTO installed_meters
                    (meter_number, com_address, password, device_type, type, status, remarks, 
                     line, CT_ratio, VT_ratio, DCU_number, Zone, station)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    meter_number,
                    comm_address,
                    password,
                    device_type,
                    modem_type,
                    status,
                    remarks,
                    line,
                    CT_ratio,
                    VT_ratio,
                    dcu_value,
                    Zone,
                    station
                ))
                print("device type") 
                print(device_type) 

                saved_count += 1
                
            except Exception as e:
                errors.append(f"Error saving meter {meter.get('meter_number', 'unknown')}: {str(e)}")
                import traceback
                traceback.print_exc()
        
        conn.commit()
        conn.close()
        
        if errors:
            return JSONResponse(
                content={
                    "success": True,
                    "saved_count": saved_count,
                    "total_count": len(meters),
                    "errors": errors,
                    "message": f"Saved {saved_count} of {len(meters)} meter(s)"
                }
            )
        else:
            return JSONResponse(
                content={
                    "success": True,
                    "saved_count": saved_count,
                    "total_count": len(meters),
                    "message": f"Successfully saved {saved_count} meter(s)"
                }
            )
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"Failed to save meters: {str(e)}"}
        )


@router.post("/clear-selected-point-numbers")
async def clear_selected_point_numbers(request: Request, user: dict = Depends(require_permission("Archive"))):
    """
    Send clear frame to DCU for selected meters and clear point numbers (set to NULL) in database.
    """
    print("clear-selected-point-numbers called")
    try:
        data = await request.json()
        meters = data.get("meters", [])  # List of dicts with meter_number and point_no
        dcu_number = data.get("dcu_number", "")  # DCU number
        dcu_id = int(dcu_number) if dcu_number else None
        
        if not meters:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "No meters selected"}
            )
        
        if not dcu_number:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "DCU number is required"}
            )
        
        # Check if DCU is connected
        if dcu_id not in connected_clients:
            print(f"DCU {dcu_number} is not connected")
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": f"DCU {dcu_number} is not connected"}
            )
        print("DCU connection check passed")
        print(f"Received meters data: {meters}, type: {type(meters)}")
        
        # Prepare meter data for batch frame building
        meter_list = []
        for meter_data in meters:
            # Handle both string format (legacy) and object format (new)
            if isinstance(meter_data, str):
                # Legacy format: just a string meter number
                meter_number = meter_data
                point_number = 16  # Default point number
            elif isinstance(meter_data, dict):
                # New format: object with meter_number and point_no
                meter_number = meter_data.get("meter_number")
                point_number = meter_data.get("point_no", 16)  # Use point_no from HTML, default to 16 if not provided
            else:
                print(f"Warning: Unexpected meter_data type: {type(meter_data)}, value: {meter_data}")
                continue
            
            if not meter_number:
                continue
            
            meter_list.append({
                "meter_number": meter_number,
                "point_number": point_number
            })
        
        if not meter_list:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "No valid meters to clear"}
            )
        
        # Build frames for all meters (may return multiple frames if data is large)
        try:
            frames_to_send = build_dcu_clear_frame(meter_list)
            print(frames_to_send)
            print(f"Built {len(frames_to_send)} frame(s) for {len(meter_list)} meter(s)")
        except Exception as e:
            print(f"❌ Error building clear frames: {e}")
            import traceback
            traceback.print_exc()
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": f"Failed to build clear frames: {str(e)}"}
            )
        
        async def result_generator():
            result_queue = connected_clients[dcu_id]['response_queue']
            clear_response_queue(result_queue) 
            connected_clients[dcu_id]['pause_event'].clear()
            
            try:
                all_frames_successful = True
                last_response_hex = None
                
                # Send all frames sequentially
                for frame_idx, frame in enumerate(frames_to_send):
                    print(f"📤 Sending clear frame {frame_idx + 1}/{len(frames_to_send)}: {frame[:100]}...")
                    
                    try:
                        # Send frame to DCU
                        await connected_clients[dcu_id]['queue'].put(
                            bytes.fromhex(with_dcu_invoke(frame, str(dcu_id)))
                        )
                        print(f"📤 Sent clear frame {frame_idx + 1} to DCU {dcu_number}")
                        
                        # Wait for response
                        try:
                            response_data = await asyncio.wait_for(result_queue.get(), timeout=30)
                            response_hex = response_data.hex().upper() if isinstance(response_data, bytes) else str(response_data)
                            last_response_hex = response_hex
                            
                            # For multi-frame, we'll yield meter info after all frames are sent
                            # For now, just track success
                            print(f"✅ Received response for clear frame {frame_idx + 1}/{len(frames_to_send)}")
                            
                        except asyncio.TimeoutError:
                            print(f"❌ Timeout waiting for response from DCU {dcu_number} for clear frame {frame_idx + 1}")
                            all_frames_successful = False
                            # Yield error for all meters
                            for meter_info in meter_list:
                                yield json.dumps({
                                    "meter_number": meter_info["meter_number"],
                                    "point_number": meter_info["point_number"],
                                    "result": "Error: Timed out waiting for DCU response",
                                    "frame_index": frame_idx + 1,
                                    "total_frames": len(frames_to_send)
                                }) + "\n"
                            break  # Stop sending remaining frames on timeout
                        
                    except Exception as e:
                        print(f"❌ Error sending clear frame {frame_idx + 1}: {e}")
                        all_frames_successful = False
                        # Yield error for all meters
                        for meter_info in meter_list:
                            yield json.dumps({
                                "meter_number": meter_info["meter_number"],
                                "point_number": meter_info["point_number"],
                                "result": f"Error: {str(e)}",
                                "frame_index": frame_idx + 1,
                                "total_frames": len(frames_to_send)
                            }) + "\n"
                        break  # Stop sending remaining frames on error
                
                # After all frames are sent, update database and yield results
                if all_frames_successful:
                    # Update database: clear point numbers and mark as not downloaded for successfully sent meters
                    conn = get_db_connection()
                    try:
                        meter_numbers_to_clear = [m["meter_number"] for m in meter_list]
                        placeholders = ','.join(['?'] * len(meter_numbers_to_clear))
                        meters_query = f"UPDATE installed_meters SET point_number = NULL, downloaded_to_dcu = 0 WHERE meter_number IN ({placeholders})"
                        cursor = conn.cursor()
                        cursor.execute(meters_query, meter_numbers_to_clear)
                        cleared_count = cursor.rowcount
                        conn.commit()
                        print(f"Cleared point numbers and marked as not downloaded for {cleared_count} meter(s) in database")
                    except Exception as db_error:
                        print(f"Database update error: {db_error}")
                    finally:
                        conn.close()
                    
                    # Yield success results
                    for meter_info in meter_list:
                        yield json.dumps({
                            "meter_number": meter_info["meter_number"],
                            "point_number": meter_info["point_number"],
                            "result": "successful",
                            "response": last_response_hex,
                            "total_frames": len(frames_to_send)
                        }) + "\n"
            finally:
                connected_clients[dcu_id]['pause_event'].set()
        
        return StreamingResponse(result_generator(), media_type="application/json")
    
    except Exception as e:
        print(f"Error in clear_selected_point_numbers: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"Failed to clear point numbers: {str(e)}"}
        )



