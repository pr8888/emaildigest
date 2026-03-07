import os
import sendgrid
from sendgrid.helpers.mail import Mail
from bs4 import BeautifulSoup


def parse_inbound_email(form_data) -> dict | None:
    """Parse SendGrid Inbound Parse webhook payload."""
    sender = form_data.get("from", "")
    subject = form_data.get("subject", "No Subject")
    text = form_data.get("text", "")
    html = form_data.get("html", "")

    # Prefer plain text; fall back to stripping HTML
    if not text and html:
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(separator="\n")

    if not text or len(text.strip()) < 100:
        return None  # Too short to be a real article

    return {
        "sender": sender,
        "subject": subject,
        "text": text.strip(),
    }


def send_digest_email(html: str, plain: str, subject: str):
    sg = sendgrid.SendGridAPIClient(api_key=os.environ["SENDGRID_API_KEY"])
    message = Mail(
        from_email=os.environ["SENDGRID_FROM_EMAIL"],
        to_emails=os.environ["DIGEST_TO_EMAIL"],
        subject=subject,
        html_content=html,
        plain_text_content=plain,
    )
    sg.send(message)
