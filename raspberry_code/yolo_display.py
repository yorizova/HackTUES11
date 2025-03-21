import os
import sys
import argparse
import glob
import time
import cv2
import numpy as np
import tkinter as tk
from ultralytics import YOLO
from PIL import Image, ImageTk
import threading
import firebase_admin
from firebase_admin import credentials, firestore
import serial

# Initialize Firebase
cred = credentials.Certificate("/home/cplisplqs/yolo_display/database.json")  # Update path
cred.GOOGLE_PRIVATE_KEY_ID = os.environ.get("GOOGLE_PRIVATE_KEY_ID")
cred.GOOGLE_CLIENT_EMAIL = os.environ.get("GOOGLE_CLIENT_EMAIL")
cred.GOOGLE_PRIVATE_KET = os.environ.get("GOOGLE_PRIVATE_KEY")
firebase_admin.initialize_app(cred)
db = firestore.client()

def get_product_price(product_name):
    """Fetch the price of a product from Firebase."""
    try:
        product_ref = db.collection("Prices Store 1").document(product_name)
        product_doc = product_ref.get()

        if product_doc.exists:
            data = product_doc.to_dict()
            return float(data.get("price", 0))  # Return price as float, default to 0 if not found
        else:
            return 0  # Return 0 if product not found
    except Exception as e:
        print(f"Error fetching price for {product_name}: {e}")
        return 0  # Return 0 in case of error

# Define and parse user input arguments
parser = argparse.ArgumentParser()
parser.add_argument('--model', help='Path to YOLO model file (example: "runs/detect/train/weights/best.pt")', required=True)
parser.add_argument('--source', help='Image source, can be image file ("test.jpg"), image folder ("test_dir"), video file ("testvid.mp4"), or index of USB camera ("usb0")', required=True)
parser.add_argument('--thresh', help='Minimum confidence threshold for displaying detected objects (example: "0.4")', default=0.5)
parser.add_argument('--resolution', help='Resolution in WxH to display inference results at (example: "640x480"), otherwise, match source resolution', default=None)
parser.add_argument('--record', help='Record results from video or webcam and save it as "demo1.avi". Must specify --resolution argument to record.', action='store_true')
args = parser.parse_args()

# Parse user inputs
model_path = args.model
img_source = args.source
min_thresh = float(args.thresh)
user_res = args.resolution
record = args.record

# Check if model file exists and is valid
if not os.path.exists(model_path):
    print('ERROR: Model path is invalid or model was not found.')
    sys.exit(0)

# Load the YOLO model
model = YOLO(model_path, task='detect')
labels = model.names

# Determine source type (image, folder, video, or USB)
img_ext_list = ['.jpg', '.jpeg', '.png', '.bmp']
vid_ext_list = ['.avi', '.mp4', '.mkv']
if os.path.isdir(img_source):
    source_type = 'folder'
    imgs_list = glob.glob(os.path.join(img_source, '*'))
elif os.path.isfile(img_source):
    _, ext = os.path.splitext(img_source)
    if ext in img_ext_list:
        source_type = 'image'
        imgs_list = [img_source]
    elif ext in vid_ext_list:
        source_type = 'video'
    else:
        print(f'File extension {ext} not supported.')
        sys.exit(0)
elif 'usb' in img_source:
    source_type = 'usb'
    usb_idx = int(img_source[3:])
else:
    print(f'Input {img_source} is invalid.')
    sys.exit(0)

# Parse user-specified display resolution
resize = False
if user_res:
    resize = True
    resW, resH = map(int, user_res.split('x'))

# Initialize video capture
if source_type == 'video' or source_type == 'usb':
    cap = cv2.VideoCapture(img_source if source_type == 'video' else usb_idx)
    if resize:
        cap.set(3, resW)
        cap.set(4, resH)

# Set bounding box colors (using the Tableu 10 color scheme)
bbox_colors = [(164, 120, 87), (68, 148, 228), (93, 97, 209), (178, 182, 133), (88, 159, 106), 
               (96, 202, 231), (159, 124, 168), (169, 162, 241), (98, 118, 150), (172, 176, 184)]

# Initialize control and status variables
avg_frame_rate = 0
frame_rate_buffer = []
fps_avg_len = 200
img_count = 0


# Create a list to store the detection information
detections_list = []

arduino1 = serial.Serial('/dev/ttyUSB0', 115200)  
arduino2 = serial.Serial('/dev/ttyACM0', 115200)  

# Tkinter GUI setup
class DisplayApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Terminal List")

        self.window_width = 600
        self.window_height = 400
        
        self.root.attributes('-fullscreen', True)

        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        position_top = int(screen_height / 2 - self.window_height / 2)
        position_right = int(screen_width / 2 - self.window_width / 2)
        root.geometry(f'{self.window_width}x{self.window_height}+{position_right}+{position_top}')

        self.canvas = tk.Canvas(root, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)

        self.original_bg_image = Image.open("background.jpg")
        self.bg_image_tk = None
        self.update_background()

        self.items_listbox = tk.Listbox(root, width=25, height=8, font=("Helvetica", 14), justify="center", bg="white", fg="black", bd=0, highlightthickness=0, relief="flat")
        self.items_listbox.place(relx=0.3, rely=0.4, anchor="center")

        self.prices_listbox = tk.Listbox(root, width=20, height=8, font=("Helvetica", 14), justify="center", bg="white", fg="black", bd=0, highlightthickness=0, relief="flat")
        self.prices_listbox.place(relx=0.7, rely=0.4, anchor="center")

        self.total_label = tk.Label(root, text="Total: 0.00 EUR", font=("Helvetica", 16), bg="white", fg="black")
        self.total_label.place(relx=0.5, rely=0.8, anchor="center")

        self.add_button = tk.Button(root, text="Add Item", command=self.add_sample_item, font=("Helvetica", 16), bg="#FF0000", fg="white", relief="flat", height=2, width=15)
        self.add_button.place(relx=0.4, rely=0.7, anchor="center")

        self.remove_button = tk.Button(root, text="Remove Selected", command=self.remove_item, font=("Helvetica", 16), bg="#FF0000", fg="white", relief="flat", height=2, width=15)
        self.remove_button.place(relx=0.6, rely=0.7, anchor="center")

        self.checkout_button = tk.Button(root, text="Check Out", command=self.checkout, font=("Helvetica", 16), bg="#008000", fg="white", relief="flat", height=2, width=15)
        self.checkout_button.place(relx=0.5, rely=0.9, anchor="center")

        root.bind("<Configure>", self.on_resize)

    def update_background(self):
        """Resize and update the background image dynamically."""
        new_width = self.root.winfo_width()
        new_height = self.root.winfo_height()

        if new_width > 1 and new_height > 1:  
            resized_image = self.original_bg_image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            self.bg_image_tk = ImageTk.PhotoImage(resized_image)
            self.canvas.create_image(0, 0, anchor="nw", image=self.bg_image_tk)

    def on_resize(self, event):
        """Handles window resizing to update the background image dynamically."""
        self.update_background()

    def add_item(self, item):
        """Adds an item to the listbox and updates the total price."""
        price = get_product_price(item)
        self.items_listbox.insert(tk.END, item)
        self.prices_listbox.insert(tk.END, f"{price:.2f} EUR")
        self.update_total()

    def remove_item(self):
        """Removes the selected item from the listbox and updates the total price."""
        selected = self.items_listbox.curselection()
        for index in selected[::-1]:  
            self.items_listbox.delete(index)
            self.prices_listbox.delete(index)
        self.update_total()

    def update_total(self):
        """Calculates and updates the total price."""
        total = 0.0
        for price in self.prices_listbox.get(0, tk.END):
            total += float(price.split()[0])  # Extract the numeric value from "XX.XX EUR"
        self.total_label.config(text=f"Total: {total:.2f} EUR")

    def add_sample_item(self):
        """Add a sample item to the listbox (for testing)."""
        if detections_list:
            item_to_add = detections_list.pop(0)  # Add the first item in the list
            self.add_item(item_to_add)
        else:
            print("No products detected yet.")

    def checkout(self):
        """Handle the checkout process (e.g., calculate total, confirm order)."""
        total = 0.0
        for price in self.prices_listbox.get(0, tk.END):
            total += float(price.split()[0])  # Extract the numeric value from "XX.XX EUR"

        try:
            read_from_arduino(arduino1)
            print(f"Checking out! Total: {total:.2f} EUR")
        except Exception as e:
            print(f"Error communicating with Arduino 1: {e}")

        # Clear the lists after checkout
        self.items_listbox.delete(0, tk.END)
        self.prices_listbox.delete(0, tk.END)
        self.total_label.config(text="Total: 0.00 EUR")


def read_from_arduino(arduino):
    if arduino.in_waiting > 0:
        for i in range(14):
            data = arduino.readline().decode('utf-8').strip()
            print(data)
            
# Function to run YOLO detections and store products until "Add Item" is clicked
def detection_loop():
    global img_count, detections_list
    detected_products = set()  # A set to store detected product names

    while True:
        t_start = time.perf_counter()

        # Load frame from image source
        if source_type == 'image' or source_type == 'folder':
            if img_count >= len(imgs_list):
                print('All images have been processed. Exiting program.')
                sys.exit(0)
            img_filename = imgs_list[img_count]
            frame = cv2.imread(img_filename)
            img_count += 1

        elif source_type == 'video':
            ret, frame = cap.read()
            if not ret:
                print('Reached end of the video file. Exiting program.')
                break

        elif source_type == 'usb':
            ret, frame = cap.read()
            if (frame is None) or (not ret):
                print('Unable to read frames from the camera. This indicates the camera is disconnected or not working. Exiting program.')
                break

        # Ensure the frame is correctly loaded before proceeding
        if frame is None:
            print("Error: Failed to capture frame.")
            break

        # Resize frame to desired display resolution
        if resize:
            frame = cv2.resize(frame, (resW, resH))

        # Run inference on frame
        results = model(frame, verbose=False)
        detections = results[0].boxes

        for i in range(len(detections)):
            read_from_arduino(arduino2)
            xyxy_tensor = detections[i].xyxy.cpu()
            xyxy = xyxy_tensor.numpy().squeeze()
            xmin, ymin, xmax, ymax = xyxy.astype(int)
            classidx = int(detections[i].cls.item())
            classname = labels[classidx]
            conf = detections[i].conf.item()

            if conf > min_thresh:  # If confidence is above threshold
                if classname not in detected_products:  # If product hasn't been detected before
                    detected_products.add(classname)  # Mark it as detected
                    label = f'{classname}'
                    detections_list.append(label)  # Store product for later addition to the list
                    print(f"Detected: {label}")  # This will only store the item, not display
                


        # Calculate and update FPS
        t_stop = time.perf_counter()
        frame_rate_calc = float(1 / (t_stop - t_start))
        avg_frame_rate = np.mean(frame_rate_buffer) if len(frame_rate_buffer) > 0 else frame_rate_calc
        
        #thread_reading = threading.Thread(target=read_from_arduino, args=(arduino2,))
        #thread_reading.start()

        

# Start Tkinter loop and YOLO detection loop
if __name__ == "__main__":
    root = tk.Tk()
    app = DisplayApp(root)

    detection_thread = threading.Thread(target=detection_loop, daemon=True)
    detection_thread.start()

    root.mainloop()
