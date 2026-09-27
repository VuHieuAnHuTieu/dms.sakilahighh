"""Export the Sakila MySQL database into a portable SQLite file (data/sakila.db).

Usage (requires a running MySQL/MariaDB with the official sakila schema+data loaded):
    python scripts/build_sqlite_from_mysql.py --host 127.0.0.1 --user root --password "" --database sakila

The SQLite copy is a 1:1 row copy of the analytical tables. Geometry (address.location)
and binary (staff.picture) columns are dropped because they are not used in any analysis.
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import pandas as pd
import pymysql

TABLES = {
    "actor": None, "address": "address_id, address, address2, district, city_id, postal_code, phone, last_update",
    "category": None, "city": None, "country": None, "customer": None, "film": None,
    "film_actor": None, "film_category": None, "inventory": None, "language": None,
    "payment": None, "rental": None,
    "staff": "staff_id, first_name, last_name, address_id, email, store_id, active, username, last_update",
    "store": None,
}
INDEXES = [
    "CREATE INDEX IF NOT EXISTS ix_rental_customer ON rental(customer_id, rental_date, rental_id)",
    "CREATE INDEX IF NOT EXISTS ix_rental_inventory ON rental(inventory_id)",
    "CREATE INDEX IF NOT EXISTS ix_inventory_film ON inventory(film_id)",
    "CREATE INDEX IF NOT EXISTS ix_film_category_film ON film_category(film_id)",
    "CREATE INDEX IF NOT EXISTS ix_payment_rental ON payment(rental_id)",
    "CREATE INDEX IF NOT EXISTS ix_payment_customer ON payment(customer_id)",
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=3306)
    ap.add_argument("--user", default="root")
    ap.add_argument("--password", default="")
    ap.add_argument("--database", default="sakila")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "data" / "sakila.db"))
    a = ap.parse_args()

    src = pymysql.connect(host=a.host, port=a.port, user=a.user, password=a.password, database=a.database)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    dst = sqlite3.connect(out)
    for table, cols in TABLES.items():
        df = pd.read_sql(f"SELECT {cols or '*'} FROM {table}", src)
        for c in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[c]):
                df[c] = df[c].dt.strftime("%Y-%m-%d %H:%M:%S")
            elif df[c].dtype == object:
                df[c] = df[c].map(lambda v: ",".join(sorted(v)) if isinstance(v, set) else v)
        df.to_sql(table, dst, index=False)
        print(f"{table:15s} {len(df):>6,} rows")
    for ix in INDEXES:
        dst.execute(ix)
    dst.commit()
    dst.close()
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
