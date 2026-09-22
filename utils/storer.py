from services.database import get_db_connection
import sqlite3 

def store_meter_reading_instant_profile(meter_number, reading_data, table_name = "instantaneous_profile_readings"): 
    conn = get_db_connection()
    cursor = conn.cursor()
    for reading in reading_data:
        try:
            # First check if record exists
            cursor.execute(f"""
            SELECT 1 FROM {table_name}  
            WHERE meter_number = ? AND timestamp = ?
            """, (meter_number, reading['timestamp']))
            
            if cursor.fetchone():
                print(f"Duplicate reading skipped for meter {meter_number} at {reading['timestamp']}")
                return False
            
            # Insert new record
            cursor.execute(f""" 
            INSERT INTO {table_name}(   
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

def store_meter_reading_energy_profile(meter_number, reading_data,table_name = "energy_profile_readings"): 
    conn = get_db_connection()
    cursor = conn.cursor()  
    print("storing_table:",table_name) 
    print("storing_data:",reading_data) 
    for reading in reading_data:
        try:
            # First check if record exists
            cursor.execute(f"""
            SELECT 1 FROM {table_name}  
            WHERE meter_number = ? AND timestamp = ?
            """, (meter_number, reading['timestamp']))
            
            if cursor.fetchone():
                print(f"Duplicate reading skipped for meter {meter_number} at {reading['timestamp']}")
                return False 
            cursor.execute(f"""
                INSERT INTO {table_name} (
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


def _dcu_profile_row_value(row: list, index: int):
    """UInt32 (or other numeric) from parse_dlms_profile_frame_from_DCU structure entry."""
    if index >= len(row):
        return None
    cell = row[index]
    if isinstance(cell, dict) and "value" in cell:
        return cell["value"]
    return None


def store_meter_reading_instant_profile_from_DCU(reading_data, table_name="instantaneous_profile_readings"):
    """
    Persist one DCU instantaneous profile row from parse_dlms_profile_frame_from_DCU.

    PDU ``data[0]`` order (36 numeric values, same physical order as DB columns):

    **Spot:** Voltage A, B, C; Current A, B, C; active power total; reactive power total;
    power factor total.

    **Min:** same nine quantities.

    **Avg:** same nine quantities.

    **Max:** same nine quantities.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        meter_number = reading_data["pdu"]["meter_number"]
        timestamp = reading_data["pdu"]["date"]
        rows = reading_data["pdu"]["data"]
        if not rows or not rows[0]:
            print("store_meter_reading_instant_profile_from_DCU: no data array")
            return False
        row0 = rows[0]
        if len(row0) < 36:
            print(
                f"store_meter_reading_instant_profile_from_DCU: expected 36 values, got {len(row0)}"
            )
            return False

        cursor.execute(
            f"""
            SELECT 1 FROM {table_name}
            WHERE meter_number = ? AND timestamp = ?
            """,
            (meter_number, timestamp),
        )
        if cursor.fetchone():
            print(f"Duplicate reading skipped for meter {meter_number} at {timestamp}")
            return False

        vals = [_dcu_profile_row_value(row0, i) for i in range(36)]
        cursor.execute(
            f"""
            INSERT INTO {table_name}(
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
                total_power_factor,
                voltage_A_min,
                voltage_B_min,
                voltage_C_min,
                current_A_min,
                current_B_min,
                current_C_min,
                total_active_power_min,
                total_reactive_power_min,
                total_power_factor_min,
                voltage_A_avg,
                voltage_B_avg,
                voltage_C_avg,
                current_A_avg,
                current_B_avg,
                current_C_avg,
                total_active_power_avg,
                total_reactive_power_avg,
                total_power_factor_avg,
                voltage_A_max,
                voltage_B_max,
                voltage_C_max,
                current_A_max,
                current_B_max,
                current_C_max,
                total_active_power_max,
                total_reactive_power_max,
                total_power_factor_max
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (meter_number, timestamp, *vals),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError as e:
        print(f"Duplicate entry prevented: {e}")
        return False
    finally:
        conn.close()


def store_meter_reading_load_profile_from_DCU(reading_data, table_name="energy_profile_readings"):
    """
    Persist one DCU load-profile row. PDU data[0] order (16 × uint32 Wh/varh):
    import active total, T1, T2, T3;
    export active total, T1, T2, T3;
    import reactive total, T1, T2, T3;
    export reactive total, T1, T2, T3.
    T4 columns in the table are left NULL (not present in this capture).
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        meter_number = reading_data["pdu"]["meter_number"]
        timestamp = reading_data["pdu"]["date"]
        rows = reading_data["pdu"]["data"]
        if not rows or not rows[0]:
            print("store_meter_reading_load_profile_from_DCU: no data array")
            return False
        row0 = rows[0]
        if len(row0) < 16:
            print(
                f"store_meter_reading_load_profile_from_DCU: expected 16 values, got {len(row0)}"
            )
            return False

        cursor.execute(
            f"""
            SELECT 1 FROM {table_name}
            WHERE meter_number = ? AND timestamp = ?
            """,
            (meter_number, timestamp),
        )
        if cursor.fetchone():
            print(f"Duplicate reading skipped for meter {meter_number} at {timestamp}")
            return False

        vals = [_dcu_profile_row_value(row0, i) for i in range(16)]
        cursor.execute(
            f"""
            INSERT INTO {table_name} (
                meter_number,
                timestamp,
                import_total_active_energy,
                import_active_energy_T1,
                import_active_energy_T2,
                import_active_energy_T3,
                export_total_active_energy,
                export_active_energy_T1,
                export_active_energy_T2,
                export_active_energy_T3,
                import_total_reactive_energy,
                import_reactive_energy_T1,
                import_reactive_energy_T2,
                import_reactive_energy_T3,
                export_total_reactive_energy,
                export_reactive_energy_T1,
                export_reactive_energy_T2,
                export_reactive_energy_T3
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (meter_number, timestamp, *vals),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError as e:
        print(f"Duplicate entry prevented: {e}")
        return False
    finally:
        conn.close()


def store_meter_reading_energy_profile_from_DCU(reading_data, table_name="energy_profile_readings"):
    """Alias for :func:`store_meter_reading_load_profile_from_DCU`."""
    return store_meter_reading_load_profile_from_DCU(reading_data, table_name)

