import os
from dotenv import load_dotenv
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

load_dotenv()

message = Mail(
    from_email="contact@pm-travelagency.com",
    to_emails="chaimaaait2005@gmail.com",
    subject="Test PM Travel",
    html_content="<strong>SendGrid test</strong>"
)

sg = SendGridAPIClient(os.getenv("SENDGRID_API_KEY"))

response = sg.send(message)

print(response.status_code)
print(response.headers)