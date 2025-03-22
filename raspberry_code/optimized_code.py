import tkinter as tk
import firebase_admin
from firebase_admin import credentials, firestore
import serial
import threading
import time
import cv2
from ultralytics import YOLO
from PIL import Image, ImageTk
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Initialize Firebase
cred = credentials.Certificate("/home/rpi5/hacktues/HackTUES11/database.json")  # Update path
firebase_admin.initialize_app(cred)
db = firestore.client()

# Initialize Arduino
arduino1 = serial.Serial('/dev/ttyUSB0', 115200)  # Non-blocking mode
arduino2 = serial.Serial('/dev/ttyACM1', 115200)  # Non-blocking mode


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
        return 0
        
def mail(subject, body):
    sender_email = "zsmartshoppingcart11@gmail.com"
    receiver_email = "cvetoda@gmail.com"
    password = "###"

    message = MIMEMultipart()
    message["From"] = sender_email
    message["To"] = receiver_email
    message["Subject"] = subject

    message.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(sender_email, password)
            server.sendmail(sender_email, receiver_email, message.as_string())
        print("Email sent successfully!")
    except Exception as e:
        print(f"Error: {e}")


class DisplayApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Terminal List")

        self.window_width = 1200
        self.window_height = 800
        
        self.root.attributes('-fullscreen', True)
        
        self.item_counts = {}

        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        position_top = int(screen_height / 2 - self.window_height / 2)
        position_right = int(screen_width / 2 - self.window_width / 2)
        root.geometry(f'{self.window_width}x{self.window_height}+{position_right}+{position_top}')

        self.canvas = tk.Canvas(root, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)

        self.original_bg_image = Image.open("../image.png")
        self.bg_image_tk = None
        self.update_background()

        self.items_frame = tk.Frame(root, bg="white")
        self.items_frame.place(relx=0.3, rely=0.4, anchor="center")

        self.total_label = tk.Label(root, text="Total: 0.00 EUR", font=("Helvetica", 16), bg="white", fg="black")
        self.total_label.place(relx=0.5, rely=0.8, anchor="center")

        self.add_button = tk.Button(root, text="Add Item", command=self.add_item_from_camera, font=("Helvetica", 16), bg="#FF0000", fg="white", relief="flat", height=2, width=15)
        self.add_button.place(relx=0.4, rely=0.7, anchor="center")

        self.remove_button = tk.Button(root, text="Remove Selected", command=self.remove_item, font=("Helvetica", 16), bg="#FF0000", fg="white", relief="flat", height=2, width=15)
        self.remove_button.place(relx=0.6, rely=0.7, anchor="center")

        self.checkout_button = tk.Button(root, text="Check Out", command=self.checkout, font=("Helvetica", 16), bg="#008000", fg="white", relief="flat", height=2, width=15)
        self.checkout_button.place(relx=0.5, rely=0.9, anchor="center")

        root.bind("<Configure>", self.on_resize)

        self.item_quantities = {}
        self.item_price_labels = {}
        
        self.model = YOLO("my_model.pt", task='detect')


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
        """Adds an item to the items_frame with name, quantity, and price displayed horizontally."""
        price = get_product_price(item)
        
        item_frame = tk.Frame(self.items_frame, bg="white")
        item_frame.pack(fill="x", pady=2)

        item_label = tk.Label(item_frame, text=item, font=("Helvetica", 14), bg="white", fg="black", width=20)
        item_label.pack(side="left", padx=5)

        minus_button = tk.Button(item_frame, text="-", command=lambda: self.decrease_item(item), font=("Helvetica", 12), bg="#FF0000", fg="white", relief="flat", width=2)
        minus_button.pack(side="left", padx=2)

        quantity_label = tk.Label(item_frame, text="1", font=("Helvetica", 14), bg="white", fg="black", width=5)
        quantity_label.pack(side="left", padx=2)

        plus_button = tk.Button(item_frame, text="+", command=lambda: self.increase_item(item, price), font=("Helvetica", 12), bg="#008000", fg="white", relief="flat", width=2)
        plus_button.pack(side="left", padx=2)

        price_label = tk.Label(item_frame, text=f"{price:.2f} EUR", font=("Helvetica", 14), bg="white", fg="black", width=10)
        price_label.pack(side="left", padx=5)

        self.item_quantities[item] = quantity_label
        self.item_price_labels[item] = price_label

        self.update_total()

    def remove_item(self):
        """Removes the selected item from the items_frame and updates the total price."""
        for child in self.items_frame.winfo_children():
            child.destroy()
        self.item_quantities.clear()
        self.item_price_labels.clear()
        self.update_total()

    def update_total(self):
        """Calculates and updates the total price."""
        total = 0.0
        for item, price_label in self.item_price_labels.items():
            quantity = int(self.item_quantities[item].cget("text"))
            price = float(price_label.cget("text").split()[0])
            total += quantity * price
        self.total_label.config(text=f"Total: {total:.2f} EUR")


    def add_item_from_camera(self):
        """Load YOLO model and use the camera to detect items when 'Add Item' is clicked."""

        labels = self.model.names

        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            print("Error: Could not open camera.")
            return

        print("Camera opened. Detecting items...")

        while True:
            read_from_arduino(arduino2)
            ret, frame = cap.read()
            if not ret:
                print("Failed to capture frame.")
                break

            results = self.model(frame, verbose=False)
            detections = results[0].boxes

            for i in range(len(detections)):
                xyxy_tensor = detections[i].xyxy.cpu()
                xyxy = xyxy_tensor.numpy().squeeze()
                xmin, ymin, xmax, ymax = xyxy.astype(int)
                classidx = int(detections[i].cls.item())
                classname = labels[classidx]
                conf = detections[i].conf.item()

                if conf > 0.5:
                    print(f"Detected: {classname}")
                    self.add_item(classname)
                    cap.release()
                    return

        cap.release()
        cv2.destroyAllWindows()

    def checkout(self):
        """Handle the checkout process (e.g., calculate total, confirm order, send email)."""
        total = 0.0
        product_details = []

        for item, price_label in self.item_price_labels.items():
            quantity = int(self.item_quantities[item].cget("text"))
            price = float(price_label.cget("text").split()[0])
            item_total = quantity * price
            total += item_total
            product_details.append(f"{item} x {quantity} = {item_total:.2f} EUR")

        email_body = "\n".join(product_details) + f"\n\nTotal: {total:.2f} EUR"

        try:
            read_from_arduino(arduino1)
            print(f"Checking out! Total: {total:.2f} EUR")
        except Exception as e:
            print(f"Error communicating with Arduino 1: {e}")

        mail(subject="Your Receipt", body=email_body)

        self.remove_item()

    def increase_item(self, item, price):
        """Increase the quantity of the selected item."""
        if item in self.item_quantities:
            current_quantity = int(self.item_quantities[item].cget("text"))
            self.item_quantities[item].config(text=str(current_quantity + 1))
            #variable = current_quantity + 1
            #item_cost = price * variable
            #self.item_price_labels[item].config(text=f"{item_cost} EUR")
            self.update_total()

    def decrease_item(self, item):
        """Decrease the quantity of the selected item."""
        if item in self.item_quantities:
            current_quantity = int(self.item_quantities[item].cget("text"))
            if current_quantity > 1:
                self.item_quantities[item].config(text=str(current_quantity - 1))
                
                self.update_total()

def read_from_arduino(arduino):
    """Read data from Arduino."""
    try:
        if arduino.in_waiting > 0:
            for i in range(14):
                data = arduino.readline().decode('utf-8').strip()
                print(data)
    except Exception as e:  
        print(f"Error reading from Arduino: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = DisplayApp(root)

    # Start a thread to periodically read from Arduino
  #  def arduino_read_loop():
   #     while True:
   #         read_from_arduino(arduino1)
    #        time.sleep(0.1)  # Adjust sleep time as needed

    #arduino_thread = threading.Thread(target=arduino_read_loop, daemon=True)
  #  arduino_thread.start()

    root.mainloop()
