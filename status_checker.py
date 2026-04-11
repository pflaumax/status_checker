from datetime import datetime
from common import SERVICES, send_message, check_service, check_website

for service in SERVICES:
    if not check_service(service):
        send_message(f"⚠️ <b>{service}</b> is DOWN!\n🕐 {datetime.now().strftime('%H:%M')}")

if not check_website():
    send_message(f"⚠️ <b>pflaumax.dev</b> is not responding!\n🕐 {datetime.now().strftime('%H:%M')}")
