import os
from dotenv import load_dotenv
from sendgrid import SendGridAPIClient

load_dotenv()

sg = SendGridAPIClient(os.getenv("SENDGRID_API_KEY"))

response = sg.client.user.profile.get()

print("Status:", response.status_code)
print(response.body)