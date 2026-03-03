#!/usr/bin/python
# -*- coding:utf-8 -*-

import RPi.GPIO as GPIO
import serial
import time
from datetime import datetime
import paho.mqtt.client as mqtt
import json

# -------------------------
# CONFIGURATION
# -------------------------
USB_PORT = '/dev/ttyUSB2'
BAUD_RATE = 115200
POWER_KEY = 6
VEHICLE_ID = "123"  # Fixed Dummy Data for Vehicle ID

# MQTT SETTINGS
SERVER_BROKER = "2001:d18:b:103:f816:3eff:fe4a:fdfb"
MQTT_TOPIC = "test/gps"

# -------------------------
# MQTT SETUP
# -------------------------
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"✅ Connected to Broker! Vehicle ID: {VEHICLE_ID}")
    else:
        print(f"❌ Connection failed. Code: {rc}")

mqtt_client = mqtt.Client()
mqtt_client.on_connect = on_connect

# -------------------------
# HELPERS
# -------------------------
def nmea_to_decimal(coord, direction):
    """Converts GPS NMEA to Decimal and returns as a rounded string."""
    if not coord or coord == '': return None
    coord = float(coord)
    degrees = int(coord / 100)
    minutes = coord - (degrees * 100)
    decimal = degrees + (minutes / 60)
    if direction in ['S', 'W']: decimal = -decimal
    return str(round(decimal, 6)) 

def power_on():
    """Operation: Powering on the SIM7600 module (Total: 22s)"""
    print("--- Powering ON SIM7600 ---")
    isConnected = False
    while not isConnected:
        try:
            GPIO.setup(POWER_KEY, GPIO.OUT)
            GPIO.output(POWER_KEY, GPIO.HIGH)
            time.sleep(2)  # Step 1: Physical pulse (2s)
            GPIO.output(POWER_KEY, GPIO.LOW)
            print("Waiting 20s for USB device to register...")
            time.sleep(20) # Step 2: Boot & OS registration (20s)
            isConnected = True
        except Exception:
            print("Hardware not ready, retrying...")

def send_at(ser, command):
    """Operation: Sending AT command and waiting for response (0.5s)"""
    try:
        ser.reset_input_buffer()
        ser.write((command + '\r\n').encode())
        time.sleep(0.5) 
        return ser.read(ser.in_waiting).decode(errors='ignore')
    except Exception:
        return "ERROR"

# -------------------------
# MAIN EXECUTION
# -------------------------
if __name__ == "__main__":
    try:
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)

        power_on()
        
        # Open Serial Connection
        ser = serial.Serial(USB_PORT, BAUD_RATE, timeout=1)
        
        # Connect to MQTT
        print(f"Connecting to {SERVER_BROKER}...")
        mqtt_client.connect(SERVER_BROKER, 1883, 60)
        mqtt_client.loop_start() 

        # Start GPS Engine
        send_at(ser, "AT+CGPS=1,1")
        print("GPS Started. Searching for satellites...\n")

        while True:
            # Operation: Request GPS Data (0.5s)
            response = send_at(ser, "AT+CGPSINFO")

            if "+CGPSINFO:" in response and ",,,," not in response:
                try:
                    gps_line = response.split("+CGPSINFO:")[1].strip()
                    parts = gps_line.split(",")

                    latitude_val = nmea_to_decimal(parts[0], parts[1])
                    longitude_val = nmea_to_decimal(parts[2], parts[3])

                    if latitude_val and longitude_val:
                        payload = {
                            "vehicleID": VEHICLE_ID,
                            "longitude": f" {longitude_val}",
                            "latitude": f" {latitude_val}"
                        }
                        
                        json_payload = json.dumps(payload)
                        mqtt_client.publish(MQTT_TOPIC, json_payload)
                        
                        print(f"📡 Sent: {json_payload}")

                except Exception as e:
                    print(f"Data Error: {e}")
            else:
                print("Waiting for satellite fix (No coordinates yet)...", end="\r")

            # Operation: Loop Interval (5s)
            time.sleep(5) 

    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        if 'ser' in locals() and ser:
            ser.close()
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
        GPIO.cleanup()