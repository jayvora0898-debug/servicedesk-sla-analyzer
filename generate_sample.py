"""Generate a fake ticket export (tickets.csv) so the analyzer can be demoed without real client data."""
import csv, random
from datetime import datetime, timedelta

random.seed(7)
NOW = datetime(2026, 9, 18, 16, 0)
TECHS = ["A. Rivera", "B. Chen", "C. Okafor", "D. Patel", ""]          # "" = unassigned
CLIENTS = ["Northfield Machining", "Lakeside Dental", "Apex Aero Parts", "Huron Logistics", "Birch CPA Group"]
ISSUES = ["Password reset", "VPN not connecting", "Printer offline", "New user onboarding", "Email delivery delay",
          "Backup job failed", "Workstation slow", "Firewall rule change", "MFA enrollment", "Server disk space alert"]
PRIORITIES = ["Critical", "High", "Medium", "Low"]

rows = []
for i in range(1, 181):
    created = NOW - timedelta(hours=random.uniform(1, 24 * 21))
    priority = random.choices(PRIORITIES, weights=[5, 20, 50, 25])[0]
    tech = random.choices(TECHS, weights=[30, 25, 20, 15, 10])[0]
    done = random.random() < 0.8 and tech != ""
    hours = random.expovariate(1 / {"Critical": 3, "High": 7, "Medium": 20, "Low": 50}[priority])
    completed = created + timedelta(hours=hours) if done else None
    if completed and completed > NOW:
        completed, done = None, False
    if not done:                                   # open tickets are recent, like a real queue
        created = NOW - timedelta(hours=random.uniform(0.5, 60))
    rows.append({
        "ticket_number": f"T2026{i:04d}", "client": random.choice(CLIENTS), "title": random.choice(ISSUES),
        "priority": priority, "status": "Complete" if done else random.choice(["New", "In Progress", "Waiting Customer"]),
        "assigned_to": tech, "created": created.strftime("%Y-%m-%d %H:%M"),
        "completed": completed.strftime("%Y-%m-%d %H:%M") if completed else "",
    })

with open("tickets.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
print(f"Wrote {len(rows)} tickets to tickets.csv")
