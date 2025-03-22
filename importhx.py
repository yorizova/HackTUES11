import os
os.environ["BCM2835_PERI_BASE"] = "0xFE000000"  # For Raspberry Pi 4/5 (RPi 4/5 has this address)
import time
import RPi.GPIO as GPIO
from hx711 import HX711  # Ensure this is the correct import for your HX711 class

# Set up GPIO mode before creating HX711 instance
GPIO.setmode(GPIO.BCM)

# Define GPIO pins for HX711
HX711_DOUT = 5  # Data output pin
HX711_SCK = 6   # Clock pin

# Create HX711 instance
hx = HX711(dout_pin=HX711_DOUT, pd_sck_pin=HX711_SCK, gain=128, channel='A')

# Calibration factor (adjust this based on your calibration process)
calibration_factor = 696.0  # Same as Arduino sketch

# Offset for tare functionality
offset = 0

def tare():
    """
    Tare the scale by setting the current reading as the offset.
    """
    global offset
    print("Taring...")
    raw_data = hx.get_raw_data(times=5)  # Take 5 readings for averaging
    if raw_data:
        offset = sum(raw_data) / len(raw_data)  # Calculate the average
    print("Tare complete. Offset:", offset)

def clean_and_exit():
    print("Cleaning up...")
    GPIO.cleanup()
    print("Bye!")
    exit()

# Initialize the HX711 module
try:
    print("Starting...")

    # Reset the HX711 and prepare it for reading
    hx.reset()
    hx.power_up()

    # Tare the scale to zero
    tare()

    print("Startup complete")

    while True:
        try:
            # Read the load cell value
            raw_data = hx.get_raw_data(times=5)  # Read 5 samples for smoothing
            if raw_data:
                # Calculate the average of the raw data
                avg_raw_data = sum(raw_data) / len(raw_data)
                # Subtract the offset and convert raw data to weight using the calibration factor
                weight = (avg_raw_data - offset) / calibration_factor
                print(f"Load cell output val: {weight:.2f}")

            # Check for user input to tare
            user_input = input("Press 't' to tare (or ENTER to continue): ").strip().lower()
            if user_input == 't':
                tare()

            time.sleep(0.1)  # Reduce CPU load

        except KeyboardInterrupt:
            clean_and_exit()

except Exception as e:
    print(f"Error: {e}")
    clean_and_exit()