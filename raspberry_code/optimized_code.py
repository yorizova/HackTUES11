import tkinter as tk
import firebase_admin
from firebase_admin import credentials, firestore
import time
import cv2
from ultralytics import YOLO
from PIL import Image, ImageTk
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
import qrcode
import io
import serial  

cred = credentials.Certificate("/home/cplisplqs/Desktop/HackTUES11/database.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

arduino1 = serial.Serial('/dev/ttyACM0', 115200)
time.sleep(2)  
def read_from_arduino(arduino, output_file="output.txt"):
    try:
        if arduino.in_waiting > 0:
            last_data = None
            for i in range(14):  
                data = arduino.readline().decode('utf-8').strip()
                last_data = data
            return last_data
    except Exception as e:
        print(f"Error reading from Arduino: {e}")
        return None


def get_product_price(product_name):
    try:
        doc = db.collection("Prices Store 1").document(product_name).get()
        return float(doc.to_dict().get("price", 0)) if doc.exists else 0
    except Exception as e:
        print(f"Error fetching price: {e}")
        return 0

def get_product_Fats(product_name):
    try:
        doc = db.collection("Prices Store 1").document(product_name).get()
        return float(doc.to_dict().get("Fats", 0)) if doc.exists else 0
    except Exception as e:
        print(f"Error fetching fats: {e}")
        return 0

def get_product_Proteins(product_name):
    try:
        doc = db.collection("Prices Store 1").document(product_name).get()
        return float(doc.to_dict().get("Proteins", 0)) if doc.exists else 0
    except Exception as e:
        print(f"Error fetching proteins: {e}")
        return 0

def get_product_Cabrohydrates(product_name): 
    try:
        doc = db.collection("Prices Store 1").document(product_name).get()
        return float(doc.to_dict().get("Carbohydrates", 0)) if doc.exists else 0
    except Exception as e:
        print(f"Error fetching carbs: {e}")
        return 0

def mail(subject, body):
    sender_email = "zwetoslaw@gmail.com"
    receiver_email = "cvetoda@gmail.com"
    password = "iivi myiy dbye ffmn" 
    message = MIMEMultipart("related")
    message["From"] = sender_email
    message["To"] = receiver_email
    message["Subject"] = subject

    msg_alternative = MIMEMultipart("alternative")
    message.attach(msg_alternative)

    text_part = MIMEText(body, "plain")
    msg_alternative.attach(text_part)

    qr_img = qrcode.make(body)
    img_byte_arr = io.BytesIO()
    qr_img.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)

    image_part = MIMEImage(img_byte_arr.read(), name="receipt_qr.png")
    image_part.add_header('Content-ID', '<qr_code>')
    image_part.add_header('Content-Disposition', 'inline', filename="receipt_qr.png")
    message.attach(image_part)

    html_part = MIMEText(f"<html><body><pre>{body}</pre><br><img src='cid:qr_code'></body></html>", "html")
    msg_alternative.attach(html_part)

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(sender_email, password)
            server.sendmail(sender_email, receiver_email, message.as_string())
        print("Email sent successfully!")
    except Exception as e:
        print(f"Email error: {e}")

class DisplayApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Terminal List")
        self.root.attributes('-fullscreen', True)
        self.window_width = 1200
        self.window_height = 800
        self.item_counts = {}
        self.selected_product = None
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        root.geometry(f'{self.window_width}x{self.window_height}')
        self.canvas = tk.Canvas(root, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self.original_bg_image = Image.open("background.png")
        self.bg_image_tk = None
        self.update_background()
        self.items_frame = tk.Frame(root, bg="white")
        self.items_frame.place(relx=0.3, rely=0.4, anchor="center")
        self.total_label = tk.Label(root, text="Total: 0.00 EUR", font=("Helvetica", 16), bg="white", fg="black")
        self.total_label.place(relx=0.5, rely=0.8, anchor="center")

        self.add_button = tk.Button(root, text="Add Item", command=self.add_item_from_camera, font=("Helvetica", 16), bg="#FF0000", fg="white", relief="flat", height=2, width=15)
        self.add_button.place(relx=0.4, rely=0.7, anchor="center")
        self.remove_button = tk.Button(root, text="Remove All", command=self.remove_item, font=("Helvetica", 16), bg="#FF0000", fg="white", relief="flat", height=2, width=15)
        self.remove_button.place(relx=0.6, rely=0.7, anchor="center")
        self.checkout_button = tk.Button(root, text="Check Out", command=self.checkout, font=("Helvetica", 16), bg="#008000", fg="white", relief="flat", height=2, width=15)
        self.checkout_button.place(relx=0.5, rely=0.9, anchor="center")
        self.info_button = tk.Button(root, text="Show More Info", command=self.show_more_info, font=("Helvetica", 16), bg="#0000FF", fg="white", relief="flat", height=2, width=15)
        self.info_button.place(relx=0.5, rely=0.6, anchor="center")

        root.bind("<Configure>", self.on_resize)
        self.item_quantities = {}
        self.item_price_labels = {}
        self.model = YOLO("my_model.pt", task='detect')
        self.last_added_product = None

    def update_background(self):
        new_width = self.root.winfo_width()
        new_height = self.root.winfo_height()
        if new_width > 1 and new_height > 1:
            resized_image = self.original_bg_image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            self.bg_image_tk = ImageTk.PhotoImage(resized_image)
            self.canvas.create_image(0, 0, anchor="nw", image=self.bg_image_tk)

    def on_resize(self, event):
        self.update_background()

    def add_item(self, item):
        price = get_product_price(item)
        self.last_added_product = item
        item_frame = tk.Frame(self.items_frame, bg="white")
        item_frame.pack(fill="x", pady=2, anchor="center")

        item_label = tk.Label(item_frame, text=item, font=("Helvetica", 14), bg="white", fg="black", width=20, cursor="hand2")
        item_label.grid(row=0, column=0, padx=5, pady=2, sticky="w")
        item_label.bind("<Button-1>", lambda e, name=item: self.select_item(name))

        minus_button = tk.Button(item_frame, text="-", command=lambda: self.decrease_item(item, item_frame), font=("Helvetica", 12), bg="#FF0000", fg="white", relief="flat", width=2)
        minus_button.grid(row=0, column=1, padx=2, pady=2)
        quantity_label = tk.Label(item_frame, text="1", font=("Helvetica", 14), bg="white", fg="black", width=5)
        quantity_label.grid(row=0, column=2, padx=2, pady=2)
        plus_button = tk.Button(item_frame, text="+", command=lambda: self.increase_item(item, price), font=("Helvetica", 12), bg="#008000", fg="white", relief="flat", width=2)
        plus_button.grid(row=0, column=3, padx=2, pady=2)
        price_label = tk.Label(item_frame, text=f"{price:.2f} EUR", font=("Helvetica", 14), bg="white", fg="black", width=10)
        price_label.grid(row=0, column=4, padx=50, pady=2)
        self.item_quantities[item] = quantity_label
        self.item_price_labels[item] = price_label
        self.update_total()

    def select_item(self, item_name):
        self.selected_product = item_name

    def remove_item(self):
        for child in self.items_frame.winfo_children():
            child.destroy()
        self.item_quantities.clear()
        self.item_price_labels.clear()
        self.update_total()

    def update_total(self):
        total = 0.0
        for item, quantity_label in self.item_quantities.items():
            quantity = int(quantity_label.cget("text"))
            unit_price = get_product_price(item)
            item_total = quantity * unit_price
            self.item_price_labels[item].config(text=f"{item_total:.2f} EUR")
            total += item_total
        self.total_label.config(text=f"Total: {total:.2f} EUR")

    def decrease_item(self, item, frame):
        if item in self.item_quantities:
            current_quantity = int(self.item_quantities[item].cget("text"))
            if current_quantity > 1:
                self.item_quantities[item].config(text=str(current_quantity - 1))
            else:
                frame.destroy()
                del self.item_quantities[item]
                del self.item_price_labels[item]
            self.update_total()

    def increase_item(self, item, price):
        if item in self.item_quantities:
            current_quantity = int(self.item_quantities[item].cget("text"))
            self.item_quantities[item].config(text=str(current_quantity + 1))
            self.update_total()

    def add_item_from_camera(self):
        labels = self.model.names
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            print("Camera error.")
            return

        print("Camera opened.")

        while True:
            last_line = read_from_arduino(arduino1)
            if last_line:
                print(f"Arduino: {last_line}")

            ret, frame = cap.read()
            if not ret:
                break

            results = self.model(frame, verbose=False)
            detections = results[0].boxes

            for i in range(len(detections)):
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
        total = 0.0
        product_details = []
        for item, price_label in self.item_price_labels.items():
            quantity = int(self.item_quantities[item].cget("text"))
            unit_price = get_product_price(item)
            item_total = quantity * unit_price
            total += item_total
            product_details.append(f"{item} x {quantity} = {item_total:.2f} EUR")

        email_body = "\n".join(product_details) + f"\n\nTotal: {total:.2f} EUR"

        try:
            arduino1.write(b"checkout\n") 
            print("Waiting for NFC approval...")

            start_time = time.time()
            approved = False
            while time.time() - start_time < 10:
                response = read_from_arduino(arduino1)
                if response:
                    print(f"Arduino Response: {response}")
                    if "APPROVED" in response.upper(): 
                        approved = True
                        break
                    elif "DENIED" in response.upper():
                        print("Payment was denied.")
                        return

            if approved:
                print(f"Payment approved. Sending receipt for {total:.2f} EUR")
                mail(subject="Your Receipt", body=email_body)
            else:
                print("NFC approval timed out.")
                return

        except Exception as e:
            print(f"Checkout error: {e}")
        
        self.remove_item()


    def show_more_info(self):
        item = self.selected_product
        if item:
            price = get_product_price(item)
            fats = get_product_Fats(item)
            proteins = get_product_Proteins(item)
            carbs = get_product_Cabrohydrates(item)
            info_window = tk.Toplevel(self.root)
            info_window.title("Product Info")
            info_window.geometry("400x250")
            tk.Label(info_window, text=f"Product: {item}", font=("Helvetica", 14)).pack(pady=5)
            tk.Label(info_window, text=f"Price: {price} EUR", font=("Helvetica", 14)).pack(pady=5)
            tk.Label(info_window, text=f"Fats: {fats}g", font=("Helvetica", 14)).pack(pady=5)
            tk.Label(info_window, text=f"Proteins: {proteins}g", font=("Helvetica", 14)).pack(pady=5)
            tk.Label(info_window, text=f"Carbohydrates: {carbs}g", font=("Helvetica", 14)).pack(pady=5)
        else:
            print("No item selected.")

if __name__ == "__main__":
    root = tk.Tk()
    app = DisplayApp(root)
    root.mainloop()
