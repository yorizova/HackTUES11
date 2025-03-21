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

# Define and parse user input arguments
parser = argparse.ArgumentParser()
parser.add_argument('--model', help='Path to YOLO model file (example: "runs/detect/train/weights/best.pt")',
                    required=True)
parser.add_argument('--source', help='Image source, can be image file ("test.jpg"), \
                    image folder ("test_dir"), video file ("testvid.mp4"), or index of USB camera ("usb0")', 
                    required=True)
parser.add_argument('--thresh', help='Minimum confidence threshold for displaying detected objects (example: "0.4")',
                    default=0.5)
parser.add_argument('--resolution', help='Resolution in WxH to display inference results at (example: "640x480"), \
                    otherwise, match source resolution',
                    default=None)
parser.add_argument('--record', help='Record results from video or webcam and save it as "demo1.avi". Must specify --resolution argument to record.',
                    action='store_true')
args = parser.parse_args()

# Parse user inputs
model_path = args.model
img_source = args.source
min_thresh = args.thresh
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
elif os.path.isfile(img_source):
    _, ext = os.path.splitext(img_source)
    if ext in img_ext_list:
        source_type = 'image'
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

# Open the log file to append the detection data after the process
log_file = 'detections.txt'

# Create a list to store the detection information
detections_list = []

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

        self.add_button = tk.Button(root, text="Add Item", command=self.add_sample_item, font=("Helvetica", 16), bg="#FF0000", fg="white", relief="flat", height=2, width=15)
        self.add_button.place(relx=0.4, rely=0.7, anchor="center")

        self.remove_button = tk.Button(root, text="Remove Selected", command=self.remove_item, font=("Helvetica", 16), bg="#FF0000", fg="white", relief="flat", height=2, width=15)
        self.remove_button.place(relx=0.6, rely=0.7, anchor="center")

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
        """Adds an item to the listbox."""
        self.items_listbox.insert(tk.END, item)

    def remove_item(self):
        """Removes the selected item from the listbox."""
        selected = self.items_listbox.curselection()
        for index in selected[::-1]:  
            self.items_listbox.delete(index)

    def add_sample_item(self):
        """Add a sample item to the listbox (for testing)."""
        self.add_item("Sample Item")

# Redirect stdout to display in the Tkinter listbox
class StdOutRedirector:
    def __init__(self, listbox):
        self.listbox = listbox

    def write(self, text):
        if text != '\n':  # Avoid empty lines
            self.listbox.add_item(text)
        sys.__stdout__.write(text)  # Print to terminal as well

    def flush(self):
        sys.__stdout__.flush()

# Function to run YOLO detections and display results
def detection_loop():
    global img_count, detections_list
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

        elif source_type == 'picamera':
            frame_bgra = cap.capture_array()
            frame = cv2.cvtColor(np.copy(frame_bgra), cv2.COLOR_BGRA2BGR)
            if frame is None:
                print('Unable to read frames from the Picamera. This indicates the camera is disconnected or not working. Exiting program.')
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
            xyxy_tensor = detections[i].xyxy.cpu()
            xyxy = xyxy_tensor.numpy().squeeze()
            xmin, ymin, xmax, ymax = xyxy.astype(int)
            classidx = int(detections[i].cls.item())
            classname = labels[classidx]
            conf = detections[i].conf.item()

            if conf > min_thresh:  # If confidence is above threshold
                label = f'{classname}    '
                detections_list.append(label)
                print(f"Detected: {label}")  # This will also update the listbox via redirect

        # Display frame with detections
        #cv2.imshow('YOLO Detection Results', frame)

        # Calculate and update FPS
        t_stop = time.perf_counter()
        frame_rate_calc = float(1 / (t_stop - t_start))
        avg_frame_rate = np.mean(frame_rate_buffer) if len(frame_rate_buffer) > 0 else frame_rate_calc

        key = cv2.waitKey(1)
        if key == ord('q'):  # Press 'q' to quit
            break
        if key == ord('p'):  # Press 'p' to save image
            cv2.imwrite('capture.png', frame)


# Start Tkinter loop and YOLO detection loop
if __name__ == "__main__":
    root = tk.Tk()
    app = DisplayApp(root)

    sys.stdout = StdOutRedirector(app)

    detection_thread = threading.Thread(target=detection_loop, daemon=True)
    detection_thread.start()

    root.mainloop()
