"""Service Desk SLA & Dispatch Analyzer

Reads a ticket export (CSV) and answers the questions a dispatcher / operations manager asks every day:
  1. Which open tickets are unassigned, breached, or about to breach SLA?
  2. How are we doing against SLA, by priority and by client?
  3. How is the workload spread across technicians?
  4. Which issue types keep coming back?

Usage:  python analyzer.py tickets.csv [--now "2026-09-18 16:00"] [--out report.html]
"""
import argparse, csv, html
from collections import Counter, defaultdict
from datetime import datetime

# Resolution targets in hours. Change these to match the real SLA contract.
SLA_HOURS = {"Critical": 4, "High": 8, "Medium": 24, "Low": 72}
AT_RISK_FRACTION = 0.75          # open ticket that has used 75%+ of its SLA window = "at risk"
FMT = "%Y-%m-%d %H:%M"


def load(path):
    tickets = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            r["created"] = datetime.strptime(r["created"], FMT)
            r["completed"] = datetime.strptime(r["completed"], FMT) if r["completed"] else None
            r["sla"] = SLA_HOURS.get(r["priority"], 24)
            tickets.append(r)
    return tickets


def analyze(tickets, now):
    open_t = [t for t in tickets if not t["completed"]]
    closed = [t for t in tickets if t["completed"]]

    for t in tickets:                                   # hours the ticket has been (or was) open
        end = t["completed"] or now
        t["age"] = (end - t["created"]).total_seconds() / 3600
        t["breached"] = t["age"] > t["sla"]

    queue = []                                          # the dispatcher's action list
    for t in open_t:
        if t["breached"]:
            flag = "BREACHED"
        elif t["age"] >= t["sla"] * AT_RISK_FRACTION:
            flag = "AT RISK"
        elif not t["assigned_to"]:
            flag = "UNASSIGNED"
        else:
            continue
        queue.append((flag, t))
    order = {"BREACHED": 0, "AT RISK": 1, "UNASSIGNED": 2}
    queue.sort(key=lambda x: (order[x[0]], list(SLA_HOURS).index(x[1]["priority"]), -x[1]["age"]))

    def sla_table(key):
        groups = defaultdict(list)
        for t in closed:
            groups[t[key]].append(t)
        out = []
        for name, ts in groups.items():
            met = sum(1 for t in ts if not t["breached"])
            out.append((name, len(ts), met, 100 * met / len(ts), sum(t["age"] for t in ts) / len(ts)))
        return out

    by_priority = sorted(sla_table("priority"), key=lambda r: list(SLA_HOURS).index(r[0]))
    by_client = sorted(sla_table("client"), key=lambda r: r[3])

    workload = defaultdict(lambda: {"open": 0, "breached": 0, "closed": 0})
    for t in tickets:
        w = workload[t["assigned_to"] or "(unassigned)"]
        if t["completed"]:
            w["closed"] += 1
        else:
            w["open"] += 1
            w["breached"] += t["breached"]

    met_all = sum(1 for t in closed if not t["breached"])
    return {
        "total": len(tickets), "open": len(open_t), "closed": len(closed),
        "sla_pct": 100 * met_all / len(closed) if closed else 0,
        "queue": queue, "by_priority": by_priority, "by_client": by_client,
        "workload": sorted(workload.items(), key=lambda kv: -kv[1]["open"]),
        "recurring": Counter(t["title"] for t in tickets).most_common(5),
    }


def print_report(r, now):
    print(f"\nSERVICE DESK REPORT  (as of {now:%Y-%m-%d %H:%M})")
    print(f"Tickets: {r['total']}  |  Open: {r['open']}  |  Closed: {r['closed']}  |  SLA met: {r['sla_pct']:.1f}%")
    print(f"\nACTION QUEUE ({len(r['queue'])} tickets need attention)")
    for flag, t in r["queue"][:15]:
        print(f"  {flag:<10} {t['ticket_number']}  {t['priority']:<8} {t['age']:6.1f}h / {t['sla']}h  "
              f"{(t['assigned_to'] or '(unassigned)'):<13} {t['client']} - {t['title']}")
    print("\nSLA BY PRIORITY")
    for n, c, m, p, a in r["by_priority"]:
        print(f"  {n:<9} {m}/{c} met ({p:.0f}%)  avg {a:.1f}h")
    print("\nSLA BY CLIENT (worst first)")
    for n, c, m, p, a in r["by_client"]:
        print(f"  {n:<22} {m}/{c} met ({p:.0f}%)")
    print("\nTECHNICIAN WORKLOAD")
    for n, w in r["workload"]:
        print(f"  {n:<14} open {w['open']:>3}  (breached {w['breached']})  closed {w['closed']}")
    print("\nTOP RECURRING ISSUES")
    for title, n in r["recurring"]:
        print(f"  {n:>3}  {title}")


def write_html(r, now, path):
    e = html.escape
    def table(head, rows):
        h = "".join(f"<th>{e(x)}</th>" for x in head)
        b = "".join("<tr>" + "".join(f"<td>{e(str(c))}</td>" for c in row) + "</tr>" for row in rows)
        return f"<table><tr>{h}</tr>{b}</table>"
    q = [(f, t["ticket_number"], t["priority"], f"{t['age']:.1f}h / {t['sla']}h", t["assigned_to"] or "(unassigned)",
          t["client"], t["title"]) for f, t in r["queue"]]
    page = f"""<!doctype html><meta charset="utf-8"><title>Service Desk Report</title>
<style>body{{font-family:Arial,sans-serif;margin:2rem;color:#1a1a1a}}h1,h2{{color:#1f3a5f}}
table{{border-collapse:collapse;margin-bottom:1.5rem}}td,th{{border:1px solid #ccc;padding:4px 10px;font-size:14px;text-align:left}}
th{{background:#eef2f7}}.k{{display:inline-block;margin-right:2rem;font-size:18px}}</style>
<h1>Service Desk Report</h1><p>As of {now:%Y-%m-%d %H:%M}</p>
<p><span class="k"><b>{r['total']}</b> tickets</span><span class="k"><b>{r['open']}</b> open</span>
<span class="k"><b>{r['sla_pct']:.1f}%</b> SLA met</span><span class="k"><b>{len(r['queue'])}</b> need attention</span></p>
<h2>Action queue</h2>{table(["Flag","Ticket","Priority","Age / SLA","Assigned","Client","Issue"], q)}
<h2>SLA by priority</h2>{table(["Priority","Closed","Met","% met","Avg hours"], [(n,c,m,f"{p:.0f}%",f"{a:.1f}") for n,c,m,p,a in r['by_priority']])}
<h2>SLA by client (worst first)</h2>{table(["Client","Closed","Met","% met"], [(n,c,m,f"{p:.0f}%") for n,c,m,p,a in r['by_client']])}
<h2>Technician workload</h2>{table(["Technician","Open","Open & breached","Closed"], [(n,w['open'],w['breached'],w['closed']) for n,w in r['workload']])}
<h2>Top recurring issues</h2>{table(["Issue","Tickets"], r['recurring'])}"""
    with open(path, "w") as f:
        f.write(page)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv_file")
    ap.add_argument("--now", help='Treat this as the current time, e.g. "2026-09-18 16:00" (default: real now)')
    ap.add_argument("--out", default="report.html")
    a = ap.parse_args()
    now = datetime.strptime(a.now, FMT) if a.now else datetime.now()
    result = analyze(load(a.csv_file), now)
    print_report(result, now)
    write_html(result, now, a.out)
    print(f"\nHTML report written to {a.out}")
