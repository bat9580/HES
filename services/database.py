import sqlite3
import os
import sys 
DATABASE = "connection.db"
# Create database table if not exists
def init_db():
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))

    db_path = os.path.join(base_dir, 'connection.db')
    conn = sqlite3.connect(db_path)
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
            VT_ratio INT
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
            task TEXT  
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
        CREATE TABLE IF NOT EXISTS lines(  
            line_name TEXT PRIMARY KEY,
            line_level TEXT,  
            parent_node TEXT
        )
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
    conn.row_factory = sqlite3.Row
    return conn