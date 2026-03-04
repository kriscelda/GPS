#!/usr/bin/python3
# -*- coding:utf-8 -*-


import RPi.GPIO as GPIO
import serial
import time
import json
import os
import sys
import subprocess
from datetime import datetime
import paho.mqtt.client as mqtt


# -------------------------
# CONFIGURATION
# -------------------------
USB_PORT = '/dev/ttyUSB2'
BAUD_RATE = 115200
POWER_KEY = 6
VEHICLE_ID = "123"
LOG_FILE = "/home/naira-bantai/GPS_MODIFIED/gps_log.csv"


# MQTT SETTINGS
SERVER_BROKER = "2001:d18:b:103:f816:3eff:fe4a:fdfb"
MQTT_TOPIC = "test/gps"


# -------------------------
# MQTT SETUP
# -------------------------
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"✅ MQTT Connected! Vehicle ID: {VEHICLE_ID}")
    else:
        print(f"❌ MQTT Failed. Code: {rc}")


mqtt_client = mqtt.Client()
mqtt_client.on_connect = on_connect


# -------------------------
# HELPERS
# -------------------------
def nmea_to_decimal(coord, direction):
    """Converts NMEA strings to decimal degrees."""
    if not coord or coord == '': return None
    try:
        coord = float(coord)
        degrees = int(coord / 100)
        minutes = coord - (degrees * 100)
        decimal = degrees + (minutes / 60)
        if direction in ['S', 'W']: decimal = -decimal
        return str(round(decimal, 6))
    except:
        return None


def reset_usb_protocol():
    """Forces the Pi 5 kernel to re-initialize the USB bus to clear Errno 71."""
    print("🔄 Forcing USB bus reset to clear Protocol Errors...")
    try:
        subprocess.run(["sudo", "udevadm", "trigger", "--attr-match=subsystem=usb"], check=True)
        time.sleep(3)
    except Exception as e:
        print(f"Reset failed: {e}")


def power_on():
    """Handles SIM7600 boot-up and USB detection."""
    print("--- Powering ON SIM7600 ---")
    GPIO.setup(POWER_KEY, GPIO.OUT)
   
    if os.path.exists(USB_PORT):
        reset_usb_protocol()
        print("Device detected. Resetting protocol stack...")
    else:
        GPIO.output(POWER_KEY, GPIO.HIGH)
        time.sleep(1.5)
        GPIO.output(POWER_KEY, GPIO.LOW)
        print("Waiting for USB to enumerate...")
   
    for i in range(30):
        if os.path.exists(USB_PORT):
            print(f"\n[OK] {USB_PORT} is active.")
            time.sleep(5)
            return
        print(".", end="", flush=True)
        time.sleep(1)


def get_serial():
    """Bypasses high-level ioctl calls that cause Errno 71."""
    if not os.path.exists(USB_PORT):
        return None
    try:
        ser = serial.Serial(None)
        ser.port = USB_PORT
        ser.baudrate = BAUD_RATE
        ser.timeout = 2
        ser.rtscts = False
        ser.dsrdtr = False
        ser.open()
        try:
            ser.dtr = False
            ser.rts = False
        except:
            pass
        return ser
    except Exception as e:
        if "71" in str(e):
            print("⚠️ Protocol locked. Check USB cable/port.")
        return None


def send_at(ser, command, timeout=1):
    """Standard AT command communication."""
    try:
        ser.reset_input_buffer()
        ser.write((command + '\r\n').encode())
        time.sleep(timeout)
        if ser.in_waiting:
            return ser.read(ser.in_waiting).decode(errors='ignore').strip()
        return ""
    except:
        return "ERROR"


# -------------------------
# MAIN LOOP
# -------------------------
if __name__ == "__main__":
    ser = None
    try:
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
       
        power_on()


        print("🔍 Stabilizing Serial connection...")
        for attempt in range(5):
            ser = get_serial()
            if ser:
                print(f"✅ Serial Protocol Established on {USB_PORT}")
                break
            time.sleep(4)


        if not ser:
            print("❌ Failure: Could not stabilize USB.")
            sys.exit(1)


        print(f"📡 Connecting to MQTT: {SERVER_BROKER}...")
        try:
            mqtt_client.connect(SERVER_BROKER, 1883, 60)
            mqtt_client.loop_start()
        except:
            print("⚠️ MQTT unreachable. Retrying in background...")


        # Powering GPS engine AND the active antenna (1,1)
        send_at(ser, "AT+CGPS=1,1")
        print("GPS active. Hunting for satellites...\n")
       
        while True:
            response = send_at(ser, "AT+CGPSINFO")
           
            if "+CGPSINFO:" in response and ",,,," not in response:
                try:
                    gps_line = response.split("+CGPSINFO:")[1].strip()
                    parts = gps_line.split(",")
                   
                    lat_val = nmea_to_decimal(parts[0], parts[1])
                    lon_val = nmea_to_decimal(parts[2], parts[3])


                    if lat_val and lon_val:
                        # Construct the payload
                        payload = {
                            "vehicleID": VEHICLE_ID,
                            "longitude": f" {lon_val}",
                            "latitude": f" {lat_val}",
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }
                       
                        json_payload = json.dumps(payload)
                       
                        # PUBLISH TO MQTT
                        result = mqtt_client.publish(MQTT_TOPIC, json_payload)
                       
                        # INDICATE SUCCESSFUL SEND
                        if result.rc == 0:
                            print(f"📤 [SENT TO MQTT] {json_payload}")
                        else:
                            print(f"⚠️ [MQTT ERROR] {json_payload}")
                       
                except Exception as e:
                    print(f"Parse error: {e}")
            else:
                print(f"Searching... [{datetime.now().strftime('%H:%M:%S')}]", end="\r")
           
            time.sleep(5)


    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        if ser: ser.close()
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
        GPIO.cleanup()
