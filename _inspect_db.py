import sqlite3

c = sqlite3.connect(r"instance/family_budget.sqlite3")
c.row_factory = sqlite3.Row
print("TABLES:", [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")])
row = c.execute("SELECT sql FROM sqlite_master WHERE name='expenses'").fetchone()
print("SCHEMA:", row[0] if row else None)
print("COUNT:", c.execute("SELECT COUNT(*) FROM expenses").fetchone()[0])
cols = [d[0] for d in c.execute("SELECT * FROM expenses LIMIT 1").description] if c.execute("SELECT COUNT(*) FROM expenses").fetchone()[0] else []
print("COLUMNS:", cols)
for r in c.execute("SELECT * FROM expenses LIMIT 10"):
    print(dict(r))
c.close()
