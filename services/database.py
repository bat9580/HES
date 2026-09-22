import sqlite3
import os
import sys
from datetime import datetime
DATABASE = "connection.db"
# Create database table if not exists
def init_db():
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))

    db_path = os.path.join(base_dir, 'connection.db')
    conn = sqlite3.connect(db_path)
    # Enable WAL - Write Ahead Logging (Хурдан бичихэд)  
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000") # Wait up to 5 sec if DB is locked - avoid deadlock
    cursor = conn.cursor() 
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS unregistered_dcu (
            dcu_number TEXT PRIMARY KEY,
            ip_address TEXT,
            first_connection TEXT,
            last_connection TEXT,
            access_time INTEGER
        )
    """)
    # cursor.execute("DROP TABLE IF EXISTS registered_dcus") 
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS registered_dcus(
            dcu_number TEXT PRIMARY KEY,
            com_address TEXT,
            remarks TEXT,
            status TEXT       
            ip_address TEXT,
            password TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS registered_meters( 
            meter_number TEXT PRIMARY KEY,
            com_address TEXT,
            password TEXT,
            device_type TEXT, 
            type TEXT,
            remarks TEXT,
            status TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS installed_meters( 
            meter_number TEXT PRIMARY KEY,
            com_address TEXT,
            password TEXT,
            device_type TEXT, 
            type TEXT, 
            remarks TEXT,
            status TEXT,
            DCU_number TEXT,  
            Zone TEXT, 
            station TEXT,
            POWER_grid TEXT, 
            task TEXT, 
            line TEXT, 
            CT_ratio INT, 
            VT_ratio INT, 
            point_number INT,
            downloaded_to_dcu INTEGER DEFAULT 0
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks( 
            task_name TEXT PRIMARY KEY,
            invoke_target TEXT,  
            cron_expression TEXT,
            remark TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS installed_meters( 
            meter_number TEXT PRIMARY KEY,
            com_address TEXT,
            password TEXT,
            device_type TEXT, 
            type TEXT, 
            remarks TEXT,
            status TEXT,
            DCU_number TEXT, 
            Zone TEXT, 
            station TEXT,
            POWER_grid TEXT, 
            task TEXT,
            downloaded_to_dcu INTEGER DEFAULT 0
        )
    """)
    cursor.execute("""
CREATE TABLE IF NOT EXISTS instantaneous_profile_readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    meter_number TEXT,
    timestamp DATETIME,
    voltage_A REAL,        -- 32.7.0
    voltage_B REAL,        -- 52.7.0
    voltage_C REAL,        -- 72.7.0
    current_A REAL,        -- 31.7.0
    current_B REAL,        -- 51.7.0
    current_C REAL,        -- 71.7.0
    total_active_power REAL,-- 15.7.0
    total_reactive_power REAL,-- 3.7.0
    total_apparent_power REAL,-- 9.7.0
    total_power_factor REAL,-- 13.7.0
    
    voltage_A_min REAL,        -- 32.7.0
    voltage_B_min REAL,        -- 52.7.0
    voltage_C_min REAL,        -- 72.7.0
    current_A_min REAL,        -- 31.7.0
    current_B_min REAL,        -- 51.7.0
    current_C_min REAL,        -- 71.7.0
    total_active_power_min REAL,-- 15.7.0
    total_reactive_power_min REAL,-- 3.7.0
    total_power_factor_min REAL,-- 13.7.0
    
    voltage_A_avg REAL,        -- 32.7.0
    voltage_B_avg REAL,        -- 52.7.0
    voltage_C_avg REAL,        -- 72.7.0
    current_A_avg REAL,        -- 31.7.0
    current_B_avg REAL,        -- 51.7.0
    current_C_avg REAL,        -- 71.7.0
    total_active_power_avg REAL,-- 15.7.0
    total_reactive_power_avg REAL,-- 3.7.0
    total_power_factor_avg REAL,-- 13.7.0 
    
    voltage_A_max REAL,        -- 32.7.0
    voltage_B_max REAL,        -- 52.7.0
    voltage_C_max REAL,        -- 72.7.0
    current_A_max REAL,        -- 31.7.0
    current_B_max REAL,        -- 51.7.0
    current_C_max REAL,        -- 71.7.0
    total_active_power_max REAL,-- 15.7.0
    total_reactive_power_max REAL,-- 3.7.0
    total_power_factor_max REAL,-- 13.7.0  

    energy_peak REAL,       -- 81.7.10
    energy_offpeak REAL,    -- 81.7.20
    energy_shoulder REAL,   -- 81.7.40
    energy_highpeak REAL,   -- 81.7.51
    energy_super_offpeak REAL, -- 81.7.62 
    total_active_power_A_avg REAL, -- 15.4.0
    total_reactive_power_A_avg REAL,    -- 23.4.0 
    total_reactive_power_B_avg REAL,     -- 9.4.0
    total_reactive_power_C_avg REAL,     -- 13.4.0                   
    FOREIGN KEY (meter_number) REFERENCES installed_meters(meter_number)
)
""")
    cursor.execute("""
CREATE TABLE IF NOT EXISTS instantaneous_profile_readings_calculated(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    meter_number TEXT,
    timestamp DATETIME,
    voltage_A REAL,        -- 32.7.0
    voltage_B REAL,        -- 52.7.0
    voltage_C REAL,        -- 72.7.0
    current_A REAL,        -- 31.7.0
    current_B REAL,        -- 51.7.0
    current_C REAL,        -- 71.7.0
    total_active_power REAL,-- 15.7.0
    total_reactive_power REAL,-- 3.7.0
    total_apparent_power REAL,-- 9.7.0
    total_power_factor REAL,-- 13.7.0
    energy_peak REAL,       -- 81.7.10
    energy_offpeak REAL,    -- 81.7.20
    energy_shoulder REAL,   -- 81.7.40
    energy_highpeak REAL,   -- 81.7.51
    energy_super_offpeak REAL, -- 81.7.62 
    total_active_power_A_avg REAL, -- 15.4.0
    total_reactive_power_A_avg REAL,    -- 23.4.0 
    total_reactive_power_B_avg REAL,     -- 9.4.0
    total_reactive_power_C_avg REAL,     -- 13.4.0                   
    FOREIGN KEY (meter_number) REFERENCES installed_meters(meter_number)
)
""")
    
    cursor.execute("""
CREATE TABLE IF NOT EXISTS energy_profile_readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    meter_number TEXT,
    timestamp DATETIME,
    import_total_active_energy REAL,        -- 1.8.0 
    import_active_energy_T1 REAL,        -- 1.8.1
    import_active_energy_T2 REAL,        -- 1.8.2
    import_active_energy_T3 REAL,        -- 1.8.3
    import_active_energy_T4 REAL,        -- 1.8.4
                   
    export_total_active_energy REAL,        -- 2.8.0 
    export_active_energy_T1 REAL,        -- 2.8.1
    export_active_energy_T2 REAL,        -- 2.8.2
    export_active_energy_T3 REAL,        -- 2.8.3
    export_active_energy_T4 REAL,        -- 2.8.4
                   
    import_total_reactive_energy REAL,        -- 3.8.0 
    import_reactive_energy_T1 REAL,        -- 3.8.1
    import_reactive_energy_T2 REAL,        -- 3.8.2
    import_reactive_energy_T3 REAL,        -- 3.8.3
    import_reactive_energy_T4 REAL,        -- 3.8.4 
                   
    export_total_reactive_energy REAL,        -- 4.8.0 
    export_reactive_energy_T1 REAL,        -- 4.8.1
    export_reactive_energy_T2 REAL,        -- 4.8.2
    export_reactive_energy_T3 REAL,        -- 4.8.3
    export_reactive_energy_T4 REAL,        -- 4.8.4        
    FOREIGN KEY (meter_number) REFERENCES installed_meters(meter_number)
)
""") 
    cursor.execute("""
CREATE TABLE IF NOT EXISTS energy_profile_readings_calculated(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    meter_number TEXT,
    timestamp DATETIME,
    import_total_active_energy REAL,        -- 1.8.0 
    import_active_energy_T1 REAL,        -- 1.8.1
    import_active_energy_T2 REAL,        -- 1.8.2
    import_active_energy_T3 REAL,        -- 1.8.3
    import_active_energy_T4 REAL,        -- 1.8.4
                   
    export_total_active_energy REAL,        -- 2.8.0 
    export_active_energy_T1 REAL,        -- 2.8.1
    export_active_energy_T2 REAL,        -- 2.8.2
    export_active_energy_T3 REAL,        -- 2.8.3
    export_active_energy_T4 REAL,        -- 2.8.4
                   
    import_total_reactive_energy REAL,        -- 3.8.0 
    import_reactive_energy_T1 REAL,        -- 3.8.1
    import_reactive_energy_T2 REAL,        -- 3.8.2
    import_reactive_energy_T3 REAL,        -- 3.8.3
    import_reactive_energy_T4 REAL,        -- 3.8.4 
                   
    export_total_reactive_energy REAL,        -- 4.8.0 
    export_reactive_energy_T1 REAL,        -- 4.8.1
    export_reactive_energy_T2 REAL,        -- 4.8.2
    export_reactive_energy_T3 REAL,        -- 4.8.3
    export_reactive_energy_T4 REAL,        -- 4.8.4        
    FOREIGN KEY (meter_number) REFERENCES installed_meters(meter_number)
)
""")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lines(  
            line_name TEXT PRIMARY KEY,
            line_level TEXT,  
            parent_node TEXT
        )
    """)

    cursor.execute("""
CREATE TABLE IF NOT EXISTS regular_task_readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    meter_number TEXT,
    timestamp DATETIME,
    voltage_A REAL,        -- 32.7.0
    voltage_B REAL,        -- 52.7.0
    voltage_C REAL,        -- 72.7.0
    current_A REAL,        -- 31.7.0
    current_B REAL,        -- 51.7.0
    current_C REAL,        -- 71.7.0
    total_active_power REAL,-- 15.7.0
    total_reactive_power REAL,-- 3.7.0
    total_apparent_power REAL,-- 9.7.0
    total_power_factor REAL,-- 13.7.0
    energy_peak REAL,       -- 81.7.10
    energy_offpeak REAL,    -- 81.7.20
    energy_shoulder REAL,   -- 81.7.40
    energy_highpeak REAL,   -- 81.7.51
    energy_super_offpeak REAL, -- 81.7.62 
    total_active_power_A_avg REAL, -- 15.4.0
    total_reactive_power_A_avg REAL,    -- 23.4.0 
    total_reactive_power_B_avg REAL,     -- 9.4.0
    total_reactive_power_C_avg REAL,     -- 13.4.0                   
    FOREIGN KEY (meter_number) REFERENCES installed_meters(meter_number)
)
""")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users( 
            user_name TEXT PRIMARY KEY, 
            nick_name TEXT,   
            password TEXT, 
            phone_number TEXT, 
            email TEXT, 
            role_name TEXT,
            status TEXT 
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS roles( 
            role_name TEXT PRIMARY KEY, 
            remark TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS permissions( 
            permission_name TEXT PRIMARY KEY
        )
    """) 
    cursor.execute("""    
        CREATE TABLE IF NOT EXISTS role_permissions(   
            role_name TEXT REFERENCES roles(role_name), 
            permission_name TEXT REFERENCES permissions(permission_name), 
            PRIMARY KEY (role_name, permission_name) 
        )
    """)
    
    # Add downloaded_to_dcu column if it doesn't exist (for existing databases)
    try:
        cursor.execute("ALTER TABLE installed_meters ADD COLUMN downloaded_to_dcu INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        # Column already exists, ignore
        pass

    # Add relay status tracking columns if they don't exist
    try:
        cursor.execute("ALTER TABLE installed_meters ADD COLUMN relay_status TEXT")
    except sqlite3.OperationalError:
        # Column already exists, ignore
        pass

    try:
        cursor.execute("ALTER TABLE installed_meters ADD COLUMN relay_status_updated_at TEXT")
    except sqlite3.OperationalError:
        # Column already exists, ignore
        pass

    # Add online status tracking columns if they don't exist
    try:
        cursor.execute("ALTER TABLE installed_meters ADD COLUMN online_status TEXT")
    except sqlite3.OperationalError:
        # Column already exists, ignore
        pass

    try:
        cursor.execute("ALTER TABLE installed_meters ADD COLUMN online_status_updated_at TEXT")
    except sqlite3.OperationalError:
        # Column already exists, ignore
        pass

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS relay_operation_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            meter_number TEXT NOT NULL,
            zone TEXT,
            power_grid TEXT,
            dcu_number TEXT,
            task_name TEXT NOT NULL,
            task_type TEXT NOT NULL DEFAULT 'Action',
            start_time TEXT NOT NULL,
            end_time TEXT,
            process TEXT NOT NULL DEFAULT 'Waiting Processing',
            try_times INTEGER NOT NULL DEFAULT 1,
            user_name TEXT,
            result TEXT,
            attempts_json TEXT DEFAULT '[]'
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_relay_operation_log_start_time
        ON relay_operation_log (start_time)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_relay_operation_log_meter_number
        ON relay_operation_log (meter_number)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_relay_operation_log_dcu_number
        ON relay_operation_log (dcu_number)
    """)

    conn.commit()
    conn.close()

def get_db_connection():
    if getattr(sys, 'frozen', False):
        # Running as compiled .exe
        base_dir = os.path.dirname(sys.executable)
    else:
        # Running from script
        base_dir = os.path.dirname(os.path.abspath(__file__))

    db_path = os.path.join(base_dir, 'connection.db')
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")      # Enable WAL - Write Ahead Logging (Хурдан бичихэд) 
    conn.execute("PRAGMA busy_timeout=5000")     # Wait up to 5 sec if DB is locked - avoid deadlock
    conn.row_factory = sqlite3.Row
    return conn


def update_online_status(meter_number: str | int, is_online: bool) -> None:
    """
    Persist the latest known online status for a meter.

    is_online=True  -> 'online'
    is_online=False -> 'offline'
    """
    status_value = "online" if is_online else "offline"
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE installed_meters
            SET online_status = ?, online_status_updated_at = ?
            WHERE meter_number = ?
            """,
            (status_value, datetime.utcnow().isoformat(), str(meter_number)),
        )
        conn.commit()
    except Exception as e:
        # Avoid breaking real-time operations if DB update fails
        print(f"Failed to update online status for meter {meter_number}: {e}")
    finally:
        try:
            conn.close()
        except Exception:
            pass