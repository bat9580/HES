from services.database import get_db_connection
import sqlite3 

def store_meter_reading_instant_profile(meter_number, reading_data):
    conn = get_db_connection()
    cursor = conn.cursor()
    for reading in reading_data:
        try:
            # First check if record exists
            cursor.execute("""
            SELECT 1 FROM instantaneous_profile_readings 
            WHERE meter_number = ? AND timestamp = ?
            """, (meter_number, reading['timestamp']))
            
            if cursor.fetchone():
                print(f"Duplicate reading skipped for meter {meter_number} at {reading['timestamp']}")
                return False
            
            # Insert new record
            cursor.execute(""" 
            INSERT INTO instantaneous_profile_readings(  
                meter_number,
                timestamp,
                voltage_A,
                voltage_B,       
                voltage_C,       
                current_A,       
                current_B,     
                current_C,
                total_active_power,
                total_reactive_power,
                total_apparent_power,
                total_power_factor,
                energy_peak,      
                energy_offpeak,   
                energy_shoulder,   
                energy_highpeak,   
                energy_super_offpeak, 
                total_active_power_A_avg, 
                total_reactive_power_A_avg,    
                total_reactive_power_B_avg,  
                total_reactive_power_C_avg
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) 
            """, (
                meter_number,
                reading['timestamp'],
                reading.get('32.7.0'),
                reading.get('52.7.0'),
                reading.get('72.7.0'),
                reading.get('31.7.0'),
                reading.get('51.7.0'),
                reading.get('71.7.0'),
                reading.get('15.7.0'),
                reading.get('3.7.0'),
                reading.get('9.7.0'),
                reading.get('13.7.0'),
                reading.get('81.7.10'),
                reading.get('81.7.20'),
                reading.get('81.7.40'),
                reading.get('81.7.51'),
                reading.get('81.7.62'), 
                reading.get('15.4.0'),
                reading.get('23.4.0'),
                reading.get('9.4.0'),
                reading.get('13.4.0'), 
            ))
            conn.commit()
            return True
        except sqlite3.IntegrityError as e:
            print(f"Duplicate entry prevented: {e}")
            return False
        finally:
            conn.close()

def store_meter_reading_energy_profile(meter_number, reading_data):
    conn = get_db_connection()
    cursor = conn.cursor()  
    for reading in reading_data:
        try:
            # First check if record exists
            cursor.execute("""
            SELECT 1 FROM energy_profile_readings 
            WHERE meter_number = ? AND timestamp = ?
            """, (meter_number, reading['timestamp']))
            
            if cursor.fetchone():
                print(f"Duplicate reading skipped for meter {meter_number} at {reading['timestamp']}")
                return False 
            cursor.execute("""
                INSERT INTO energy_profile_readings (
                    meter_number,
                    timestamp,
                    import_total_active_energy,
                    import_active_energy_T1,
                    import_active_energy_T2,
                    import_active_energy_T3,
                    import_active_energy_T4,
                    export_total_active_energy,
                    export_active_energy_T1,
                    export_active_energy_T2,
                    export_active_energy_T3,
                    export_active_energy_T4,
                    import_total_reactive_energy,
                    import_reactive_energy_T1,
                    import_reactive_energy_T2,
                    import_reactive_energy_T3,
                    import_reactive_energy_T4,
                    export_total_reactive_energy,
                    export_reactive_energy_T1,
                    export_reactive_energy_T2,
                    export_reactive_energy_T3,
                    export_reactive_energy_T4
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    meter_number,
                    reading.get('timestamp'),
                    reading.get('1.8.0'),  # import_total_active_energy
                    reading.get('1.8.1'),  # import_active_energy_T1
                    reading.get('1.8.2'),  # import_active_energy_T2
                    reading.get('1.8.3'),  # import_active_energy_T3
                    reading.get('1.8.4'),  # import_active_energy_T4
                    reading.get('2.8.0'),  # export_total_active_energy
                    reading.get('2.8.1'),  # export_active_energy_T1
                    reading.get('2.8.2'),  # export_active_energy_T2
                    reading.get('2.8.3'),  # export_active_energy_T3
                    reading.get('2.8.4'),  # export_active_energy_T4
                    reading.get('3.8.0'),  # import_total_reactive_energy
                    reading.get('3.8.1'),  # import_reactive_energy_T1
                    reading.get('3.8.2'),  # import_reactive_energy_T2
                    reading.get('3.8.3'),  # import_reactive_energy_T3
                    reading.get('3.8.4'),  # import_reactive_energy_T4
                    reading.get('4.8.0'),  # export_total_reactive_energy
                    reading.get('4.8.1'),  # export_reactive_energy_T1
                    reading.get('4.8.2'),  # export_reactive_energy_T2
                    reading.get('4.8.3'),  # export_reactive_energy_T3
                    reading.get('4.8.4')   # export_reactive_energy_T4
                ))
            conn.commit() 
            return True
        except sqlite3.IntegrityError as e:
            print(f"Duplicate entry prevented: {e}")
            return False 
        finally: 
            conn.close() 

