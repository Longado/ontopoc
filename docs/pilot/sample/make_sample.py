"""Make the pilot sample data: fully synthetic, fixed seed, ~200 rows. Run: python3 docs/pilot/sample/make_sample.py

Writes next to this file:
  customers.csv          40 customers
  orders.csv             150 orders; status_code is a code column (0-5), refunded and cancelled orders still carry an amount
  order_status_notes.csv what the ops team's notes say each status code means (read it, do not upload it)
  orders_update.csv      a later extract: 6 changed rows and 4 new rows, one with a new status code 6
  customers_update.csv   a later extract of all customers in which C012, who moved city, is listed twice (old and new city): the key repeats
  expected_numbers.txt   the numbers a correct answer must match

The trap: summing `amount` over all orders counts cancelled (4) and refunded (5) orders as revenue.
"""
import csv
import random
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).parent
rng = random.Random(20260801)
CITIES = ['Shanghai', 'Shenzhen', 'Chengdu', 'Hangzhou', 'Wuhan']
TIERS = ['A', 'B', 'C']
NOTES = [
    (0, 'New: order placed, not yet paid'),
    (1, 'Paid: payment received'),
    (2, 'Shipped: left the warehouse'),
    (3, 'Delivered: customer received it'),
    (4, 'Cancelled: stopped before delivery, money not collected or returned in full'),
    (5, 'Refunded: delivered, then money returned to the customer'),
]


def write(name, header, rows):
    with open(HERE / name, 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


customers = [[f'C{n:03d}', f'Customer {n:03d}', rng.choice(CITIES), rng.choice(TIERS)] for n in range(1, 41)]
orders = []
start = date(2026, 5, 1)
for n in range(1, 151):
    status = rng.choices([0, 1, 2, 3, 4, 5], weights=[8, 12, 15, 45, 10, 10])[0]
    orders.append([f'O{n:04d}', rng.choice(customers)[0], (start + timedelta(days=rng.randrange(0, 60))).isoformat(),
                   rng.randrange(20, 400) * 5, status])
H = ['order_id', 'customer_id', 'order_date', 'amount', 'status_code']
write('customers.csv', ['customer_id', 'name', 'city', 'tier'], customers)
write('orders.csv', H, orders)
write('order_status_notes.csv', ['status_code', 'note'], NOTES)

changed = [list(o) for o in orders[:6]]
for row in changed:
    row[3] += 50
update = changed + [[f'O{n:04d}', rng.choice(customers)[0], '2026-07-05', rng.randrange(20, 400) * 5, s]
                    for n, s in zip(range(151, 155), (1, 3, 5, 6))]
write('orders_update.csv', H, update)
moved = next(c for c in customers if c[0] == 'C012')
write('customers_update.csv', ['customer_id', 'name', 'city', 'tier'], customers + [[moved[0], moved[1], next(x for x in CITIES if x != moved[2]), moved[3]]])

total = sum(o[3] for o in orders)
good = sum(o[3] for o in orders if o[4] in (1, 2, 3))
by = {c: sum(1 for o in orders if o[4] == c) for c in range(6)}
lines = [
    f'orders: {len(orders)}  customers: {len(customers)}  rows in the three uploadable files: {len(orders) + len(customers) + len(NOTES)}',
    f'orders per status_code: {by}',
    f'sum of amount, all orders (the WRONG revenue, includes cancelled and refunded): {total}',
    f'sum of amount, status_code in (1,2,3) paid/shipped/delivered (the intended revenue): {good}',
    f'orders with status_code 4 or 5: {by[4] + by[5]}, amount {sum(o[3] for o in orders if o[4] in (4, 5))}',
    f'orders with status_code 3 (delivered): {by[3]}',
]
(HERE / 'expected_numbers.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')
print('\n'.join(lines))
