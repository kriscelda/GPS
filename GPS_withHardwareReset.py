#!/usr/bin/python
# -*- coding:utf-8 -*-
import RPi.GPIO as GPIO
import serial
import time

# -------------------------
# CONFIGURATION
# -------------------------
USB_PORT = '/dev/ttyUSB2'   # SIM7600 GPS port
BAUD_RATE = 115200
POWER_KEY = 6               # BCM pin to toggle SIM7600
GPS_TIMEOUT = 1             # AT command timeout
GPS_REQUEST_INTERVAL = 1.5  # seconds between GPS requests
MAX_NO_RESPONSE = 5         # consecutive failures before hardware reset

# -------------------------
# SERIAL AND GPIO SETUP
# -------------------------
ser = serial.Serial(USB_PORT, BAUD_RATE, timeout=1, exclusive=False)
ser.xonxoff = False
ser.rtscts = False
ser.dsrdtr = False
ser.dtr = None
ser.rts = None
ser.flushInput()

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
GPIO.setup(POWER_KEY, GPIO.OUT)

# -------------------------
# FUNCTIONS
# -------------------------
def send_at(command, expected_response, timeout=GPS_TIMEOUT):
    """Send AT command and return response if it contains expected_response"""
    ser.write((command + '\r\n').encode())
    time.sleep(timeout)
    rec_buff = b''
    if ser.inWaiting():
        rec_buff = ser.read(ser.inWaiting())
    if rec_buff:
        decoded = rec_buff.decode(errors='ignore')
        if expected_response not in decoded:
            print(f"{command} ERROR")
            print(f"Back:\t{decoded}")
            return None
        return decoded
    else:
        print(f"{command} - no response yet")
        return None

def power_on():
    """Turn on SIM7600 module via GPIO"""
    print('Powering on SIM7600...')
    GPIO.output(POWER_KEY, GPIO.HIGH)
    time.sleep(2)
    GPIO.output(POWER_KEY, GPIO.LOW)
    time.sleep(20)
    ser.flushInput()
    print('SIM7600 should be ready.')

def power_off():
    """Turn off SIM7600 module safely"""
    print('Powering down SIM7600...')
    GPIO.output(POWER_KEY, GPIO.HIGH)
    time.sleep(3)
    GPIO.output(POWER_KEY, GPIO.LOW)
    time.sleep(18)
    print('SIM7600 powered down.')

def hardware_reset():
    """Force SIM7600 to restart via POWER_KEY"""
    print("Hardware reset SIM7600...")
    # Force power off
    GPIO.output(POWER_KEY, GPIO.HIGH)
    time.sleep(3)
    GPIO.output(POWER_KEY, GPIO.LOW)
    time.sleep(5)
    # Power on
    GPIO.output(POWER_KEY, GPIO.HIGH)
    time.sleep(2)
    GPIO.output(POWER_KEY, GPIO.LOW)
    time.sleep(20)
    ser.flushInput()
    print("SIM7600 restarted.")

def parse_gps(raw):
    """Parse +CGPSINFO into decimal latitude and longitude"""
    try:
        cleaned = raw.replace('\n','').replace('\r','').replace('AT','').replace('+CGPSINFO:','').replace(': ','').strip()
        if ',,,,,,' in cleaned:
            return None

        parts = cleaned.split(',')
        lat, lat_dir = parts[0], parts[1]
        lon, lon_dir = parts[2], parts[3]

        # Convert to decimal degrees
        lat_deg = float(lat[:2])
        lat_min = float(lat[2:])
        latitude = lat_deg + (lat_min / 60)
        if lat_dir == 'S':
            latitude = -latitude

        lon_deg = float(lon[:3])
        lon_min = float(lon[3:])
        longitude = lon_deg + (lon_min / 60)
        if lon_dir == 'W':
            longitude = -longitude

        return latitude, longitude
    except Exception:
        return None

def get_gps_position_continuous():
    """Continuously display GPS coordinates with watchdog reset"""
    print('Starting GPS session...')
    if not send_at('AT+CGPS=1,1','OK',1):
        print('Failed to start GPS.')
        return
    time.sleep(2)

    fix_acquired = False
    no_response_counter = 0  # track consecutive failures

    print('Waiting for GPS fix...')
    while True:
        response = send_at('AT+CGPSINFO', '+CGPSINFO: ', 1)
        if response:
            gps = parse_gps(response)
            if gps:
                fix_acquired = True
                print(f"Latitude: {gps[0]:.6f}, Longitude: {gps[1]:.6f}")
                no_response_counter = 0  # reset counter on success
            else:
                if not fix_acquired:
                    print('GPS fix not yet available...')
                no_response_counter += 1
        else:
            no_response_counter += 1

        # Watchdog: reset module if no response for MAX_NO_RESPONSE consecutive attempts
        if no_response_counter >= MAX_NO_RESPONSE:
            print("No GPS response detected. Resetting module...")
            hardware_reset()
            no_response_counter = 0
            fix_acquired = False
            send_at('AT+CGPS=1,1','OK',1)
            time.sleep(2)

        time.sleep(GPS_REQUEST_INTERVAL)

# -------------------------
# MAIN SCRIPT
# -------------------------
try:
    power_on()
    get_gps_position_continuous()  # loop forever, printing coordinates
except KeyboardInterrupt:
    print("\nScript interrupted by user.")
finally:
    power_off()
    if ser is not None:
        ser.close()
    GPIO.cleanup()
