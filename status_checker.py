from datetime import datetime
from common import SERVICES, send_message, check_service, check_website, get_system_alerts

now = datetime.now().strftime("%H:%M")

for service in SERVICES:
    if not check_service(service):
        send_message(f"⚠️ <b>{service}</b> is DOWN!\n🕐 {now}")

if not check_website():
    send_message(f"⚠️ <b>pflaumax.dev</b> is not responding!\n🕐 {now}")

alerts = get_system_alerts()
if alerts:
    send_message(f"🚨 <b>Critical Raspberry Pi state!</b>\n\n" + "\n".join(alerts) + f"\n\n🕐 {now}")
