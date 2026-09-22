import sqlite3
import json
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from services.database import get_db_connection
from utils.utility_functions import require_permission, template_response

templates = Jinja2Templates(directory="templates")

router = APIRouter()


@router.get("/batch-upload-meter", response_class=HTMLResponse)
async def batch_upload_meter(
    request: Request,
    user: dict = Depends(require_permission("Archive"))
):
    """Initial batch upload page where user selects device type and uploads Excel file."""
    return template_response(request, "batch_upload.html", {"request": request})


@router.get("/batch-upload-device-type", response_class=HTMLResponse)
async def batch_upload_device_type(
    request: Request,
    user: dict = Depends(require_permission("Archive"))
):
    """Device type configuration page (step 2)."""
    return template_response(request, "batch_upload_device_type.html", {"request": request})


@router.get("/step2", response_class=HTMLResponse)
async def step2(
    request: Request,
    user: dict = Depends(require_permission("Archive"))
):
    """Result/confirmation page (step 3) showing which meters are already installed vs new."""
    # Get meter data from query params or use defaults
    # The actual data will be loaded from localStorage on the client side
    return template_response(
        request,
        "batch_upload_result.html",
        {
            "request": request,
            "add_success": 0,
            "update_success": 0,
            "failed": 0,
            "total": 0,
        }
    )


@router.post("/next_step")
async def next_step(
    request: Request,
    user: dict = Depends(require_permission("Archive"))
):
    """
    Process meter numbers and return which ones are already installed vs new.
    Expects JSON: {"meters": ["meter1", "meter2", ...]}
    """
    try:
        data = await request.json()
        meter_numbers = data.get("meters", [])
        
        if not meter_numbers:
            return JSONResponse(
                status_code=400,
                content={"error": "No meter numbers provided"}
            )
        
        conn = get_db_connection()
        conn.row_factory = sqlite3.Row
        
        # Get all installed meter numbers
        installed_rows = conn.execute(
            "SELECT meter_number FROM installed_meters"
        ).fetchall()
        installed_meter_numbers = {row["meter_number"] for row in installed_rows}
        
        # Separate into already installed and new meters
        already_installed = []
        new_meters = []
        
        for meter_num in meter_numbers:
            if meter_num in installed_meter_numbers:
                already_installed.append(meter_num)
            else:
                new_meters.append(meter_num)
        
        conn.close()
        
        return JSONResponse({
            "already_installed": already_installed,
            "new_meters": new_meters,
            "total_uploaded": len(meter_numbers)
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to process meters: {str(e)}"}
        )


@router.post("/install_meters")
async def install_meters(
    request: Request,
    user: dict = Depends(require_permission("Archive"))
):
    """
    Install meters from Excel data.
    Expects JSON: {
        "meters": [[row1], [row2], ...],  # Excel rows
        "device_type": "GPRS Meter" or "PLC Meter",
        "dcu_number": "123" (optional, required for PLC),
        "comm_address": "123" (optional)
    }
    """
    try:
        data = await request.json()
        excel_rows = data.get("meters", []) 
        print("excel_rows type:", type(excel_rows))
        print("excel_rows length:", len(excel_rows) if excel_rows else 0)
        
        # Check if excel_rows is a string that needs JSON parsing
        if isinstance(excel_rows, str):
            print("WARNING: excel_rows is a string, attempting to parse as JSON")
            try:
                import json
                excel_rows = json.loads(excel_rows)
                print("Parsed excel_rows type:", type(excel_rows))
                print("Parsed excel_rows length:", len(excel_rows) if excel_rows else 0)
            except Exception as e:
                print(f"Failed to parse JSON: {e}")
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "error": f"Invalid meters data format: {str(e)}"}
                )
        
        print("excel_rows", excel_rows) 
        print("excel_rows[0] type:", type(excel_rows[0]) if excel_rows else "N/A")
        print("excel_rows[0] repr:", repr(excel_rows[0]) if excel_rows else "N/A")
        print("headers (excel_rows[0]):", excel_rows[0] if excel_rows else "EMPTY") 
        device_type = data.get("device_type", "")
        dcu_number = data.get("dcu_number")
        comm_address = data.get("comm_address")
        
        if not excel_rows:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "No meter data provided"}
            )
        
        # Parse Excel rows (first row is headers, rest are data)
        if len(excel_rows) < 2:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "Invalid Excel data format"}
            )
             
        headers = excel_rows[0]
        print("headers (assigned variable):", headers)
        print("headers type:", type(headers))
        print("headers repr:", repr(headers))  
        data_rows = excel_rows[1:]
        
        # Find column indices (assuming standard format)
        # Typical columns: meter_number, com_address, device_type, type, password, etc.
        meter_number_idx = None
        comm_address_idx = None
        device_type_idx = None
        type_idx = None
        password_idx = None
        remarks_idx = None
        
        for i, header in enumerate(headers):
            header_lower = str(header).lower() if header else ""
            if "тоолуурын дугаар" in header_lower or "meter_number" in header_lower or "meter number" in header_lower:
                meter_number_idx = i
                print("meter_number_idx", meter_number_idx) 
            elif "ком" in header_lower or "comm_address" in header_lower or "comm address" in header_lower:
                comm_address_idx = i
            elif "тоолуурын төрөл" in header_lower or "device_type" in header_lower or "device type" in header_lower:
                type_idx = i 
            elif ("модулийн төрөл" in header_lower or "модуль" in header_lower or 
                  ("type" in header_lower and "device" not in header_lower and "тоолуурын" not in header_lower)):
                device_type_idx = i
            elif "password" in header_lower or "нууц үг" in header_lower:
                password_idx = i
            elif "тайлбар" in header_lower or "remarks" in header_lower or "тэмдэглэл" in header_lower:
                remarks_idx = i
        
        if meter_number_idx is None:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "Meter number column not found in Excel"}
            )
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        status = "installed"
        success_count = 0
        error_count = 0
        errors = []
        
        for row in data_rows:
            if len(row) <= meter_number_idx or not row[meter_number_idx]:
                continue  # Skip empty rows
            
            meter_number = str(row[meter_number_idx]).strip()
            if not meter_number:
                continue
            
            # Extract values from row
            meter_comm_address = (
                str(row[comm_address_idx]).strip()
                if comm_address_idx is not None and len(row) > comm_address_idx and row[comm_address_idx]
                else comm_address or ""
            )
            
            meter_device_type = (
                str(row[device_type_idx]).strip()
                if device_type_idx is not None and len(row) > device_type_idx and row[device_type_idx]
                else device_type or ""
            )
            
            meter_type = (
                str(row[type_idx]).strip()
                if type_idx is not None and len(row) > type_idx and row[type_idx]
                else meter_device_type
            )
            
            meter_password = (
                str(row[password_idx]).strip()
                if password_idx is not None and len(row) > password_idx and row[password_idx]
                else "00000000"  # Default password
            )
            
            meter_remarks = (
                str(row[remarks_idx]).strip()
                if remarks_idx is not None and len(row) > remarks_idx and row[remarks_idx]
                else None
            )
            
            # Determine if PLC meter and validate DCU
            meter_type_normalized = meter_device_type.strip().lower() if meter_device_type else ""
            is_plc_meter = "plc" in meter_type_normalized
            dcu_value = dcu_number.strip() if dcu_number else None
            
            if is_plc_meter and not dcu_value:
                error_count += 1
                errors.append(f"Meter {meter_number}: DCU number required for PLC meters")
                continue
            
            # For PLC meters, set comm_address to DCU number
            if is_plc_meter and dcu_value:
                meter_comm_address = dcu_value
            
            try:
                # Insert into installed_meters
                cursor.execute(
                    """
                    INSERT INTO installed_meters
                    (meter_number, com_address, password, device_type, type, status, remarks, CT_ratio, VT_ratio, DCU_number)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        meter_number,
                        meter_comm_address,
                        meter_password,
                        meter_device_type,
                        meter_type,
                        status,
                        meter_remarks,
                        1,  # Default CT_ratio
                        1,  # Default VT_ratio
                        dcu_value,
                    ),
                )
                
                # Insert or update registered_meters (handles both existing and new meters)
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO registered_meters
                    (meter_number, com_address, password, device_type, type, remarks, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (meter_number, meter_comm_address, meter_password, meter_device_type, meter_type, meter_remarks, status)
                )
                
                success_count += 1
                
            except sqlite3.IntegrityError:
                # Meter already exists, try to update it
                try:
                    cursor.execute(
                        """
                        UPDATE installed_meters
                        SET com_address = ?, password = ?, device_type = ?, type = ?, 
                            remarks = ?, DCU_number = ?
                        WHERE meter_number = ?
                        """,
                        (
                            meter_comm_address,
                            meter_password,
                            meter_device_type,
                            meter_type,
                            meter_remarks,
                            dcu_value,
                            meter_number,
                        ),
                    )
                    success_count += 1
                except Exception as e:
                    error_count += 1
                    errors.append(f"Meter {meter_number}: {str(e)}")
            except Exception as e:
                error_count += 1
                errors.append(f"Meter {meter_number}: {str(e)}")
        
        conn.commit()
        conn.close()
        
        message = f"Successfully processed {success_count} meter(s)"
        if error_count > 0:
            message += f", {error_count} error(s)"
        
        return JSONResponse({
            "success": True,
            "message": message,
            "success_count": success_count,
            "error_count": error_count,
            "errors": errors[:10]  # Limit errors to first 10
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"Failed to install meters: {str(e)}"}
        )
