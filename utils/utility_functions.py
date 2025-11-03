import asyncio
import sqlite3

from fastapi import HTTPException, Request, Depends, status 
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from services.database import get_db_connection
from services.state import connected_clients,scheduler 
import utils.meter_task_functions as task_functions
from apscheduler.triggers.cron import CronTrigger 
import os
from datetime import datetime 
templates = Jinja2Templates(directory="templates")  

PRIORITY_HIGH = 0     # e.g., on-demand read 
PRIORITY_MEDIUM = 5   # e.g., cron job 
PRIORITY_LOW = 10     # e.g., health check  


def is_meter_installed(meter_number):
    conn = get_db_connection()   
    result = conn.execute(
        "SELECT 1 FROM installed_meters WHERE meter_number = ?", (str(meter_number),)
    ).fetchone()
    conn.close()
    return result is not None

def is_heartbeat_frame(data):
    if len(data) == 26:
        return True 
    else:
        return False    

def add_meter_to_connected_clients(meter_number,addr, access_time,reader,writer): 
    connected_clients[meter_number] = { 
                'addr' : addr,  
                'access_time': access_time,
                'queue': asyncio.Queue(), 
                'response_queue': asyncio.Queue(),
                'keep_connection_queue': asyncio.Queue(), 
                'real_time_result': asyncio.Queue(), 
                'reader': reader, 
                'writer': writer,
                'scheduled_jobs': [],
                'pause_event': asyncio.Event(),
                'task_queue': asyncio.PriorityQueue(),
            } 
def add_cron_job(task_function, cronExpression, meter_number,ID):
    scheduler.add_job(
            task_function,   
            CronTrigger.from_crontab(cronExpression), 
            args=[meter_number], 
            id=ID, 
            replace_existing=True
            )
    connected_clients[meter_number]['scheduled_jobs'].append(ID)   # scheduled Jobuudiig hadgalah 
def add_job(cronExpression, meter_number,invoke_target): 
    if invoke_target == "Energy load profile":
        id = f"{invoke_target}_{cronExpression}_{meter_number}"  
        add_cron_job(task_functions.schedule_load_profile,cronExpression,meter_number,id) 
    elif invoke_target == "Instantanious load profile":
        id = f"{invoke_target}_{cronExpression}_{meter_number}" 
        add_cron_job(task_functions.schedule_instantanious_profile,cronExpression,meter_number, id)  
    elif invoke_target == "Voltage read": 
        id = f"{invoke_target}_{cronExpression}_{meter_number}"  
        add_cron_job(task_functions.schedule_voltage_read,cronExpression,meter_number,id)  
    elif invoke_target == "Active Power read":  
        id = f"{invoke_target}_{cronExpression}_{meter_number}"  
        add_cron_job(task_functions.schedule_active_power_read,cronExpression,meter_number,id)   
    else: 
        print(f"{invoke_target} not available") 
def add_system_task(meter_number): 
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row  # ✅ Enable access by column name

    tasks = conn.execute("SELECT * FROM tasks").fetchall()
    conn.close()
    for task in tasks:
        add_job(task["cron_expression"],meter_number,task["invoke_target"]) 
        print(f"✅ Scheduled {task['invoke_target']} for meter {meter_number} at {task["cron_expression"]}") 

def add_added_task_to_all_connected_meters(task):
    for meter_number in connected_clients:
        add_job(task["cron_expression"],meter_number,task["invoke_target"]) 
        print(f"✅ Scheduled {task['invoke_target']} for meter {meter_number} at {task["cron_expression"]}") 
def creat_meter_task(meter_number):
    
    print("beginning task") 
    connected_clients[meter_number]['tasks'] = [
        asyncio.create_task(task_functions.meter_writer(meter_number)),
        asyncio.create_task(task_functions.keep_connection(meter_number)),
        asyncio.create_task(task_functions.task_executor(meter_number)) 
    ]
    add_system_task(meter_number) 
async def clear_tasks(client): 
    try:
        tasks = client.get('tasks', [])
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    except Exception as e:
        print(f"⚠️ Error while clearing tasks: {e}") 
    
def clear_scheduled_jobs(meter_number):
    scheduled_jobs = connected_clients[meter_number]['scheduled_jobs']
    for job_ID in scheduled_jobs:    
        scheduler.remove_job(job_ID) 
    connected_clients[meter_number]['scheduled_jobs'].clear()   
    print(f"removed_scheduled_jobs {meter_number}")  

def remove_task_from_exsisting_meters(invoke_target,cron_expression): # Таск устгахад бүх online meter - ээс тухайн Таск ыг устгах  
    for meter_number in connected_clients:
        job_id = f"{invoke_target}_{cron_expression}_{meter_number}" 
        if job_id in connected_clients[meter_number]['scheduled_jobs']:
            scheduler.remove_job(job_id)  
            print(f"removed_scheduled_jobs {meter_number}") 
        else:
            print(f"job id not found {job_id} and {meter_number}")    
def add_task_to_existing_meters(invoke_target,cron_expression):  # шинээр таск нэмэгдэхэд тэр таскыг бүх online meter - д нэмэх 
    for meter_number in connected_clients:
        add_job(cron_expression, meter_number,invoke_target)  

def edit_tasks_on_existing_meters(invoke_target_old,cron_expression_old,invoke_target_new,cron_expression_new): # таск өөрчлөх үед байсан таскыг устгаж шинэ таск үүсгэх
    remove_task_from_exsisting_meters(invoke_target_old,cron_expression_old)  
    add_task_to_existing_meters(invoke_target_new,cron_expression_new) 
    print("task edited on all meters")
    
 
def get_ratios(meter_number):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT CT_ratio, VT_ratio 
        FROM installed_meters 
        WHERE meter_number = ?
    """, (meter_number,)) 

    row = cursor.fetchone()
    conn.close()  
    return row   



LOG_DIR = "meter_logs"  
def get_log_file_path(meter_number: str) -> str:
    """Return the current daily log file path for a given meter."""
    current_date_str = datetime.now().strftime("%m_%d")
    daily_log_dir = os.path.join(LOG_DIR, current_date_str)
    os.makedirs(daily_log_dir, exist_ok=True)
    return os.path.join(daily_log_dir, f"{meter_number}.log") 


def template_response(request: Request, template_name: str, context: dict = {}):
    user = request.session.get("user")
    default_context = {
        "request": request,
        "user": user,
        "permissions": user.get("permissions", []) if user else []
    }
    default_context.update(context)
    return templates.TemplateResponse(template_name, default_context)


def require_permission(permission: str):
    def checker(request: Request):
        user = request.session.get("user")
        if not user or permission not in user.get("permissions", []):
            print("🚨 No session or no permission — redirecting to login")
            # raise an HTTPException with special status
            raise HTTPException(
                status_code=status.HTTP_303_SEE_OTHER,
                detail="redirect_login"
            )
        return user
    return checker 

def get_meters_by_line(line): 
    query = "SELECT meter_number FROM installed_meters WHERE 1=1" 
    params = [] 

    if line:
        query += " AND line LIKE ?"
        params.append(f"%{line}%") 

    conn = get_db_connection() 
    cursor = conn.cursor()
    cursor.execute(query, params)
    rows = cursor.fetchall()   # returns list of Row objects

    # Extract just the meter_number values
    meter_numbers = [row[0] for row in rows]
    print(meter_numbers) 
    conn.close()
    return meter_numbers  