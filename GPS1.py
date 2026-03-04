#!/usr/bin/python
# -*- coding:utf-8 -*-

import RPi.GPIO as GPIO
import serial
import time
import csv
import os
from datetime import datetime

# -------------------------
# CONFIGURATION
# -------------------------
USB_PORT = '/dev/ttyUSB2'
BAUD_RATE = 115200
POWER_KEY = 6
LOG_FILE = "gps_log.csv"

# -------------------------
# NMEA TO DECIMAL CONVERTER
# -------------------------
def nmea_to_decimal(coord, direction):
    if not coord or coord == '':
        return None

    coord = float(coord)

    degrees = int(coord / 100)
    minutes = coord - (degrees * 100)

    decimal = degrees + (minutes / 60)

    if direction in ['S', 'W']:
        decimal = -decimal

    return decimal

# -------------------------
# POWER ON SIM7600
# -------------------------
def power_on():
    print("--- Powering ON SIM7600 ---")
    GPIO.setup(POWER_KEY, GPIO.OUT)
    GPIO.output(POWER_KEY, GPIO.HIGH)
    time.sleep(2)
    GPIO.output(POWER_KEY, GPIO.LOW)
    print("Waiting 20s for USB device to register...")
    time.sleep(20)

# -------------------------
# SERIAL CONNECTION
# -------------------------
def get_serial():
    try:
        ser = serial.Serial(
            USB_PORT,
            BAUD_RATE,
            timeout=1,
            rtscts=False,
            dsrdtr=False
        )
        print(f"[SUCCESS] Connected to {USB_PORT}")
        return ser
    except Exception as e:
        print(f"[RETRY] Connection failed: {e}")
        return None

# -------------------------
# SEND AT COMMAND
# -------------------------
def send_at(ser, command):
    try:
        ser.reset_input_buffer()
        ser.write((command + '\r\n').encode())
        time.sleep(0.5)
        response = ser.read(ser.in_waiting).decode(errors='ignore')
        return response
    except Exception as e:
        print(f"Serial Error during {command}: {e}")
        return "ERROR"

# -------------------------
# LOG TO CSV
# -------------------------
def log_to_csv(lat, lon, maps_link):
    file_exists = os.path.isfile(LOG_FILE)

    with open(LOG_FILE, mode='a', newline='') as f:
        writer = csv.writer(f)

        if not file_exists:
            writer.writerow(['Timestamp', 'Latitude', 'Longitude', 'GoogleMapsLink'])

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        writer.writerow([timestamp, lat, lon, maps_link])

        print(f"Logged to CSV.")

# -------------------------
# MAIN LOOP
# -------------------------
if __name__ == "__main__":
    try:
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)

        power_on()

        ser = get_serial()
        if ser:
            send_at(ser, "AT")
            send_at(ser, "AT+CGPS=1,1")

            print("GPS Started. Waiting for fix...\n")

            while True:
                response = send_at(ser, "AT+CGPSINFO")

                if "ERROR" in response:
                    print("Attempting to reconnect...")
                    ser.close()
                    time.sleep(2)
                    ser = get_serial()
                    continue

                if "+CGPSINFO:" in response and ",,,," not in response:
                    try:
                        gps_line = response.split("+CGPSINFO:")[1].strip()
                        parts = gps_line.split(",")

                        lat = parts[0]
                        lat_dir = parts[1]
                        lon = parts[2]
                        lon_dir = parts[3]

                        lat_decimal = nmea_to_decimal(lat, lat_dir)
                        lon_decimal = nmea_to_decimal(lon, lon_dir)

                        if lat_decimal and lon_decimal:
                            lat_str = f"{lat_decimal:.6f}"
                            lon_str = f"{lon_decimal:.6f}"

                            maps_link = f"https://www.google.com/maps?q={lat_str},{lon_str}"

                            print(f"\nLatitude  : {lat_str}")
                            print(f"Longitude : {lon_str}")
                            print("Google Maps Link:")
                            print(maps_link)
                            print("--------------------------------")

                            log_to_csv(lat_str, lon_str, maps_link)

                    except Exception as e:
                        print(f"Parse Error: {e}")

                else:
                    print("Searching for satellites...", end="\r")

                time.sleep(5)

    except KeyboardInterrupt:
        print("\nManual stop.")

    finally:
        if 'ser' in locals() and ser:
            ser.close()
        GPIO.cleanup()
        