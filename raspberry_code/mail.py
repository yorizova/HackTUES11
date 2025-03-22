import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os

sender_email = "smartshoppingcart11@gmail.com"
receiver_email = "cvetoda@gmail.com"
password = os.environ.get("APP_PASSWORD")
subject = "Test Email from Raspberry Pi"
body = "This is a test email sent from a Raspberry Pi using Python."

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
