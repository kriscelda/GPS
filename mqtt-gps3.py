#!/usr/bin/python3
# -*- coding:utf-8 -*-

import RPi.GPIO as GPIO
import serial
import time
import json
import sys
from datetime import datetime
import paho.mqtt.client as mqtt

# -------------------------
# CONFIGURATION
# -------------------------
UART_PORT = "/dev/ttyUSB0" 
BAUD_RATE = 115200
POWER_KEY = 6
VEHICLE_ID = "123"
MQTT_TOPIC = "test/gps"
SERVER_BROKER = "2001:d18:b:103:f816:3eff:fe4a:fdfb"

# -------------------------
# MQTT SETUP
# -------------------------
mqtt_client = mqtt.Client()

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"✅ MQTT Connected to {SERVER_BROKER}")
    else:
        print(f"❌ MQTT Connection Failed (Code: {rc})")

mqtt_client.on_connect = on_connect

# -------------------------
# HELPER FUNCTIONS
# -------------------------

def format_duration(seconds):
    """Converts seconds into 1s, 2m 10s, etc."""
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    remaining_seconds = seconds % 60
    return f"{minutes}m {remaining_seconds}s"

def nmea_to_decimal(coord, direction):
    if not coord or not direction:
        return None
    try:
        coord = float(coord)
        degrees = int(coord / 100)
        minutes = coord - (degrees * 100)
        decimal = degrees + (minutes / 60)
        if direction in ['S', 'W']:
            decimal = -decimal
        return str(round(decimal, 6))
    except:
        return None

def send_at(ser, command, wait_time=1.0):
    try:
        ser.reset_input_buffer()
        ser.write((command + '\r\n').encode())
        time.sleep(wait_time)
        if ser.in_waiting:
            return ser.read(ser.in_waiting).decode(errors='ignore').strip()
    except Exception as e:
        print(f"\n🚨 Serial Error: {e}")
    return ""

def power_on():
    print("🔌 Pulsing Power Key...")
    GPIO.setup(POWER_KEY, GPIO.OUT)
    GPIO.output(POWER_KEY, GPIO.HIGH)
    time.sleep(2)
    GPIO.output(POWER_KEY, GPIO.LOW)
    print("⏳ Waiting for modem boot...")
    for i in range(21):
        percent = int((i / 20) * 100)
        bar = "█" * i + "-" * (20 - i)
        print(f"\r[{bar}] {percent}% ", end="", flush=True)
        time.sleep(1)
    print("\n✅ Initialization Complete.\n")

# -------------------------
# MAIN LOOP
# -------------------------

if __name__ == "__main__":
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)

    power_on()

    try:
        ser = serial.Serial(UART_PORT, BAUD_RATE, timeout=2)
        print(f"✅ Connected to CP210x Bridge on {UART_PORT}")
    except Exception as e:
        print(f"❌ Could not open {UART_PORT}: {e}")
        sys.exit(1)

    try:
        mqtt_client.connect(SERVER_BROKER, 1883, 60)
        mqtt_client.loop_start()
    except:
        print("⚠️ MQTT Offline mode.")

    print("🛰 Starting GPS...")
    send_at(ser, "AT+CGPS=1,1")
    
    # Initialize the search timer
    search_start_time = time.time()

    try:
        while True:
            response = send_at(ser, "AT+CGPSINFO")
            
            if "+CGPSINFO:" in response and ",,,," not in response:
                gps_data = response.split("+CGPSINFO:")[1].strip().split(",")
                
                lat = nmea_to_decimal(gps_data[0], gps_data[1])
                lon = nmea_to_decimal(gps_data[2], gps_data[3])
                
                if lat and lon:
                    # Get current timestamp
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    # Calculate how long it took to get this fix
                    fix_time = format_duration(time.time() - search_start_time)
                    
                    # Prepare the data dictionary
                    payload_dict = {
                        "vehicleID": VEHICLE_ID,
                        "longitude": lon,
                        "latitude": lat
                    }
                    
                    # Convert dictionary to JSON string
                    json_payload = json.dumps(payload_dict)
                    
                    # PRINT IN REQUESTED FORMAT
                    print(f"\n--- {timestamp} ---")
                    print(f"📍 FIX ACQUIRED IN: {fix_time}")
                    print(f"📤 SENT:{json_payload}")
                    
                    # Publish to MQTT
                    mqtt_client.publish(MQTT_TOPIC, json_payload)
                    
                    # Optional: Reset timer if you want to track the time between fixes
                    # search_start_time = time.time() 
            else:
                elapsed = format_duration(time.time() - search_start_time)
                print(f"📡 Searching Satellites... [Elapsed: {elapsed}]", end="\r")
            
            time.sleep(5)

    except KeyboardInterrupt:
        print("\n🛑 Stopping...")
    finally:
        if 'ser' in locals(): ser.close()
        mqtt_client.disconnect()
        GPIO.cleanup()