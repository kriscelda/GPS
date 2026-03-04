#!/usr/bin/python
# -*- coding:utf-8 -*-
import RPi.GPIO as GPIO
import serial
import time

# -------------------------
# CONFIGURATION
# -------------------------
USB_PORT = '/dev/ttyUSB2'   # Use the USB port where your SIM7600 GPS works
BAUD_RATE = 115200
POWER_KEY = 6               # BCM pin used to toggle SIM7600 power
GPS_TIMEOUT = 1             # Timeout for AT command response

# -------------------------
# INITIALIZE SERIAL AND GPIO
# -------------------------
ser = serial.Serial("/dev/ttyUSB2", 115200, timeout=1, exclusive=False)
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
    """
    Sends an AT command and waits for expected response.
    Returns the response if successful, None if failed.
    """
    ser.write((command + '\r\n').encode())
    time.sleep(timeout)
    rec_buff = b''
    if ser.inWaiting():
        rec_buff = ser.read(ser.inWaiting())
    if rec_buff:
        rec_decoded = rec_buff.decode(errors='ignore')
        if expected_response not in rec_decoded:
            print(f"{command} ERROR")
            print(f"Back:\t{rec_decoded}")
            return None
        return rec_decoded
    else:
        print(f"{command} - no response yet")
        return None

def power_on():
    """Turns on the SIM7600 module via GPIO"""
    print('Powering on SIM7600...')
    GPIO.output(POWER_KEY, GPIO.HIGH)
    time.sleep(2)
    GPIO.output(POWER_KEY, GPIO.LOW)
    time.sleep(20)  # Wait for module to initialize
    ser.flushInput()
    print('SIM7600 should be ready.')

def power_off():
    """Turns off the SIM7600 module safely"""
    print('Powering down SIM7600...')
    GPIO.output(POWER_KEY, GPIO.HIGH)
    time.sleep(3)
    GPIO.output(POWER_KEY, GPIO.LOW)
    time.sleep(18)
    print('SIM7600 powered down.')

def get_gps_position():
    """Starts GPS and waits for a valid fix"""
    print('Starting GPS session...')
    if not send_at('AT+CGPS=1,1','OK',1):
        print('Failed to start GPS.')
        return
    time.sleep(2)

    print('Waiting for GPS fix...')
    while True:
        response = send_at('AT+CGPSINFO', '+CGPSINFO: ', 1)
        if response:
            if ',,,,,,' in response:
                print('GPS fix not yet available...')
            else:
                # GPS fix acquired
                print('GPS coordinates:', response.strip())
                break
        time.sleep(1.5)
    send_at('AT+CGPS=0','OK',1)  # Stop GPS after getting coordinates

# -------------------------
# MAIN SCRIPT
# -------------------------
try:
    power_on()
    get_gps_position()
finally:
    power_off()
    if ser is not None:
        ser.close()
    GPIO.cleanup()

