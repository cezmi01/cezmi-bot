from flask import Flask, request, redirect, url_for, render_template_string, flash
import sqlite3, datetime
from decimal import Decimal, InvalidOperation

app = Flask(__name__)
app.secret_key = "change-me"
DB_PATH = "settings.db"

# ----------------- Seed data -----------------
# symbols_for_exchange[group][COIN] = {
#   "binance": "...",
#   "local": "...",
#   "multiplier": "...|None",
#   "pp": int,
#   "ap": int,
# }
from helpers import symbols_for_exchange

# Seed numeric defaults (global per coin row)
SEED_NUMERIC = {
    "amount": "10",  # now stored as TEXT (decimal-friendly)
    "buy_th": "0.05",
    "sell_th": "0.05",
    "cancel_th": "0.001",
}

GROUPS = ("paribu_binance", "paribu_btcturk", "btcturk_paribu", "btcturk_binance")


def group_label(group: str) -> str:
    return group.replace("_", " -> ").title()


def group_local_label(group: str) -> str:
    """
    In each group, "local" belongs to the left-side exchange.
    e.g. paribu_binance -> local is Paribu symbol
         btcturk_paribu -> local is BtcTurk symbol
    """
    left = group.split("_", 1)[0].lower()
    if left == "paribu":
        return "Paribu"
    if left == "btcturk":
        return "BtcTurk"
    return "Local"


# ----------------- HTML -----------------

LAYOUT = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Coin Config Dashboard</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    body { background-color: #f9fafc; }
    .navbar { background-color: #1a73e8; }
    .navbar-brand { color: #fff !important; font-weight: 600; }
    table td, table th { vertical-align: middle !important; }
    .btn-primary { background-color: #1a73e8; border-color: #1a73e8; }
    .btn-danger { background-color: #e84545; border-color: #e84545; }
    .card { border-radius: .5rem; box-shadow: 0 2px 6px rgba(0,0,0,0.05); }
    .flash { padding: .75rem 1rem; border-radius: .25rem; margin-bottom: 1rem; }
    .flash-success { background: #e7f5ee; border: 1px solid #b6e3c4; color: #1b6e42; }
    .small-muted { color: #6c757d; font-size: .9rem; }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; }
  </style>
</head>
<body>
  <nav class="navbar navbar-expand-lg mb-4">
    <div class="container-fluid">
      <a class="navbar-brand" href="{{ url_for('index') }}">Coin Config</a>
    </div>
  </nav>

  <div class="container">
    {% with messages = get_flashed_messages() %}
      {% if messages %}
        {% for m in messages %}
          <div class="flash flash-success">{{ m }}</div>
        {% endfor %}
      {% endif %}
    {% endwith %}
    {{ body|safe }}
  </div>

  <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

INDEX_HTML = """
<div class="d-flex justify-content-between align-items-center mb-3">
  <div>
    <h2 class="fw-bold mb-0">Coins</h2>
    <div class="small-muted">Groups: paribu_binance, paribu_btcturk, btcturk_paribu, btcturk_binance</div>
  </div>
  <div>
    <form method="post" action="{{ url_for('seed_defaults') }}" class="d-inline">
      <button class="btn btn-outline-secondary btn-sm">Seed defaults</button>
    </form>
  </div>
</div>

{% for group in groups %}
<div class="mb-4">
  <div class="d-flex justify-content-between align-items-center mb-2">
    <div>
      <h4 class="mb-0">{{ group_label(group) }}</h4>
      <div class="small-muted">Group key: <span class="mono">{{ group }}</span></div>
    </div>
    <form method="get" action="{{ url_for('add_coin') }}" class="d-inline">
      <input type="hidden" name="group" value="{{ group }}">
      <button class="btn btn-primary btn-sm">+ Add</button>
    </form>
  </div>

  <div class="card p-3">
    <div class="table-responsive">
      <table class="table table-hover align-middle">
        <thead class="table-light">
          <tr>
            <th>Coin</th>
            <th>Hedge</th>
            <th>{{ group_local_label(group) }}</th>
            <th>Multiplier</th>
            <th class="text-end">pp</th>
            <th class="text-end">ap</th>
            <th class="text-end">Amount</th>
            <th class="text-end">Buy&nbsp;th</th>
            <th class="text-end">Sell&nbsp;th</th>
            <th class="text-end">Cancel&nbsp;th</th>
            <th style="width: 170px;">Actions</th>
          </tr>
        </thead>
        <tbody>
          {% for r in rows_by_group[group] %}
          <tr>
            <td><strong>{{ r['coin'] }}</strong></td>
            <td>{{ r['binance_symbol'] or '-' }}</td>
            <td>{{ r['local_symbol'] or '-' }}</td>
            <td>{{ r['multiplier_symbol'] or '-' }}</td>
            <td class="text-end">{{ r['pp'] }}</td>
            <td class="text-end">{{ r['ap'] }}</td>
            <td class="text-end">{{ r['amount'] }}</td>
            <td class="text-end">{{ r['buy_th'] }}</td>
            <td class="text-end">{{ r['sell_th'] }}</td>
            <td class="text-end">{{ r['cancel_th'] }}</td>
            <td>
              <a href="{{ url_for('edit_coin', group=group, coin=r['coin']) }}" class="btn btn-sm btn-primary">Edit</a>
              <form method="post" action="{{ url_for('delete_coin') }}" class="d-inline"
                    onsubmit="return confirm('Delete {{ group }} coin {{ r['coin'] }}?')">
                <input type="hidden" name="group" value="{{ group }}">
                <input type="hidden" name="coin" value="{{ r['coin'] }}">
                <button class="btn btn-sm btn-danger">Delete</button>
              </form>
            </td>
          </tr>
          {% endfor %}
          {% if rows_by_group[group]|length == 0 %}
          <tr>
            <td colspan="11" class="text-center small-muted py-4">No coins yet.</td>
          </tr>
          {% endif %}
        </tbody>
      </table>
    </div>
  </div>
</div>
{% endfor %}
"""

ADD_HTML = """
<div class="card p-4">
  <div class="d-flex justify-content-between align-items-start">
    <div>
      <h2 class="fw-bold mb-1">Add Coin</h2>
      <div class="small-muted">Group: <span class="mono">{{ group }}</span> ({{ group_label(group) }})</div>
    </div>
  </div>

  <form method="post" action="{{ url_for('save_coin') }}" class="mt-3">
    <input type="hidden" name="group" value="{{ group }}">

    <div class="mb-3">
      <label class="form-label">Coin symbol</label>
      <input type="text" name="coin" class="form-control" required placeholder="e.g., ACM">
    </div>

    <h5 class="mt-4">Symbols</h5>
    <div class="row g-3">
      <div class="col-md-4">
        <label class="form-label">Hedge</label>
        <input type="text" name="binance_symbol" class="form-control" placeholder="e.g., W/USDT or acm_tl">
      </div>
      <div class="col-md-4">
        <label class="form-label">{{ group_local_label(group) }}</label>
        <input type="text" name="local_symbol" class="form-control" placeholder="e.g., ACMTRY or pengu_tl">
      </div>
      <div class="col-md-4">
        <label class="form-label">Multiplier</label>
        <input type="text" name="multiplier_symbol" class="form-control" placeholder="e.g., USDTTRY / usdt_tl (or empty)">
      </div>
    </div>

    <h5 class="mt-4">Precision</h5>
    <div class="row g-3">
      <div class="col-md-3"><label class="form-label">pp</label><input type="number" name="pp" class="form-control" value="2"></div>
      <div class="col-md-3"><label class="form-label">ap</label><input type="number" name="ap" class="form-control" value="0"></div>
    </div>

    <h5 class="mt-4">Config Values</h5>
    <div class="row g-3">
      <div class="col-md-3"><label class="form-label">Amount</label><input type="number" name="amount" class="form-control" value="10" step="any"></div>
      <div class="col-md-3"><label class="form-label">Buy Threshold</label><input type="number" name="buy_th" class="form-control" value="0.010" step="any"></div>
      <div class="col-md-3"><label class="form-label">Sell Threshold</label><input type="number" name="sell_th" class="form-control" value="0.010" step="any"></div>
      <div class="col-md-3"><label class="form-label">Cancel Threshold</label><input type="number" name="cancel_th" class="form-control" value="0.001" step="any"></div>
    </div>

    <div class="mt-4">
      <button class="btn btn-primary">Save</button>
      <a href="{{ url_for('index') }}" class="btn btn-outline-secondary">Cancel</a>
    </div>
  </form>
</div>
"""

EDIT_HTML = """
<div class="card p-4">
  <div class="d-flex justify-content-between align-items-start">
    <div>
      <h2 class="fw-bold mb-1">Edit Coin: {{ coin }}</h2>
      <div class="small-muted">Group: <span class="mono">{{ row['group_name'] }}</span> ({{ group_label(row['group_name']) }})</div>
    </div>
  </div>

  <form method="post" action="{{ url_for('save_coin') }}" class="mt-3">
    <input type="hidden" name="group" value="{{ row['group_name'] }}">
    <input type="hidden" name="coin" value="{{ coin }}">

    <h5>Symbols</h5>
    <div class="row g-3">
      <div class="col-md-4">
        <label class="form-label">Hedge</label>
        <input type="text" name="binance_symbol" class="form-control" value="{{ row['binance_symbol'] or '' }}">
      </div>
      <div class="col-md-4">
        <label class="form-label">{{ group_local_label(row['group_name']) }}</label>
        <input type="text" name="local_symbol" class="form-control" value="{{ row['local_symbol'] or '' }}">
      </div>
      <div class="col-md-4">
        <label class="form-label">Multiplier</label>
        <input type="text" name="multiplier_symbol" class="form-control" value="{{ row['multiplier_symbol'] or '' }}">
      </div>
    </div>

    <h5 class="mt-4">Precision</h5>
    <div class="row g-3">
      <div class="col-md-3"><label class="form-label">pp</label><input type="number" name="pp" class="form-control" value="{{ row['pp'] }}"></div>
      <div class="col-md-3"><label class="form-label">ap</label><input type="number" name="ap" class="form-control" value="{{ row['ap'] }}"></div>
    </div>

    <h5 class="mt-4">Config</h5>
    <div class="row g-3">
      <div class="col-md-3"><label class="form-label">Amount</label><input type="number" name="amount" class="form-control" value="{{ row['amount'] }}" step="any"></div>
      <div class="col-md-3"><label class="form-label">Buy Threshold</label><input type="number" name="buy_th" class="form-control" value="{{ row['buy_th'] }}" step="any"></div>
      <div class="col-md-3"><label class="form-label">Sell Threshold</label><input type="number" name="sell_th" class="form-control" value="{{ row['sell_th'] }}" step="any"></div>
      <div class="col-md-3"><label class="form-label">Cancel Threshold</label><input type="number" name="cancel_th" class="form-control" value="{{ row['cancel_th'] }}" step="any"></div>
    </div>

    <div class="mt-4">
      <button class="btn btn-primary">Save</button>
      <a href="{{ url_for('index') }}" class="btn btn-outline-secondary">Back</a>
    </div>
  </form>
</div>
"""

# ----------------- DB helpers -----------------


def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row

    # Create table (use amount TEXT so you can store 0.001 etc.)
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS coins(
            group_name TEXT NOT NULL,
            coin TEXT NOT NULL,

            amount TEXT NOT NULL,
            buy_th TEXT NOT NULL,
            sell_th TEXT NOT NULL,
            cancel_th TEXT NOT NULL,

            binance_symbol TEXT,
            local_symbol TEXT,
            multiplier_symbol TEXT,

            pp INTEGER NOT NULL DEFAULT 0,
            ap INTEGER NOT NULL DEFAULT 0,

            updated_at TEXT NOT NULL,

            PRIMARY KEY(group_name, coin)
        )
    """
    )

    _migrate_if_needed(con)
    return con


def _migrate_if_needed(con):
    """
    Best-effort migration:
      - Ensure new columns exist: multiplier_symbol, pp, ap, group_name
      - If old 'exchange' exists and group_name doesn't, copy exchange->group_name
      - If old amount was INTEGER, we KEEP the existing column as-is (SQLite cannot alter type easily).
        So we create a new table with amount TEXT and copy rows once (safe).
    """
    cols = con.execute("PRAGMA table_info(coins)").fetchall()
    names = {r["name"] for r in cols}

    # If this DB was created with amount INTEGER earlier, we need a one-time rebuild.
    amount_type = None
    for r in cols:
        if r["name"] == "amount":
            amount_type = (r["type"] or "").upper()
            break

    # Add missing columns on legacy tables
    if "multiplier_symbol" not in names:
        con.execute("ALTER TABLE coins ADD COLUMN multiplier_symbol TEXT")
    if "pp" not in names:
        con.execute("ALTER TABLE coins ADD COLUMN pp INTEGER NOT NULL DEFAULT 0")
    if "ap" not in names:
        con.execute("ALTER TABLE coins ADD COLUMN ap INTEGER NOT NULL DEFAULT 0")

    if "exchange" in names and "group_name" not in names:
        con.execute("ALTER TABLE coins ADD COLUMN group_name TEXT")
        con.execute("UPDATE coins SET group_name = exchange WHERE group_name IS NULL")

    con.commit()

    # Rebuild if amount column is INTEGER (or blank) rather than TEXT
    # This enables fractional amounts like 0.001.
    if amount_type and amount_type != "TEXT":
        con.execute("ALTER TABLE coins RENAME TO coins_old")

        con.execute(
            """
            CREATE TABLE coins(
                group_name TEXT NOT NULL,
                coin TEXT NOT NULL,

                amount TEXT NOT NULL,
                buy_th TEXT NOT NULL,
                sell_th TEXT NOT NULL,
                cancel_th TEXT NOT NULL,

                binance_symbol TEXT,
                local_symbol TEXT,
                multiplier_symbol TEXT,

                pp INTEGER NOT NULL DEFAULT 0,
                ap INTEGER NOT NULL DEFAULT 0,

                updated_at TEXT NOT NULL,

                PRIMARY KEY(group_name, coin)
            )
        """
        )

        # Copy data over; cast amount to text
        # If group_name is NULL for some legacy rows, try exchange, else set to
        # 'btcturk_binance' fallback.
        con.execute(
            """
            INSERT INTO coins(
              group_name, coin,
              amount, buy_th, sell_th, cancel_th,
              binance_symbol, local_symbol, multiplier_symbol,
              pp, ap,
              updated_at
            )
            SELECT
              COALESCE(group_name, exchange, 'btcturk_binance') as group_name,
              coin,
              CAST(amount AS TEXT) as amount,
              buy_th, sell_th, cancel_th,
              binance_symbol, local_symbol, multiplier_symbol,
              pp, ap,
              updated_at
            FROM coins_old
        """
        )

        con.execute("DROP TABLE coins_old")
        con.commit()


def upsert_coin_row(group_name, coin, data):
    with db() as con:
        con.execute(
            """
            INSERT INTO coins(
              group_name, coin,
              amount, buy_th, sell_th, cancel_th,
              binance_symbol, local_symbol, multiplier_symbol,
              pp, ap,
              updated_at
            )
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(group_name, coin) DO UPDATE SET
              amount=excluded.amount,
              buy_th=excluded.buy_th,
              sell_th=excluded.sell_th,
              cancel_th=excluded.cancel_th,
              binance_symbol=excluded.binance_symbol,
              local_symbol=excluded.local_symbol,
              multiplier_symbol=excluded.multiplier_symbol,
              pp=excluded.pp,
              ap=excluded.ap,
              updated_at=excluded.updated_at
        """,
            (
                group_name,
                coin,
                str(data.get("amount", "10")),
                str(data.get("buy_th", "0.010")),
                str(data.get("sell_th", "0.010")),
                str(data.get("cancel_th", "0.001")),
                (data.get("binance_symbol") or None),
                (data.get("local_symbol") or None),
                (data.get("multiplier_symbol") or None),
                int(data.get("pp", 0)),
                int(data.get("ap", 0)),
                datetime.datetime.utcnow().isoformat(),
            ),
        )


def validate_numeric(name, value, kind):
    if kind == "int":
        v = int(value)
        # allow negative pp/ap if you want; currently allow any int
        return v

    if kind == "decimal":
        try:
            d = Decimal(str(value))
        except InvalidOperation:
            raise ValueError(f"{name}: invalid decimal")
        # allow negative thresholds (no range restriction)
        return d

    raise ValueError("unknown kind")


# ----------------- Routes -----------------


@app.route("/")
def index():
    with db() as con:
        rows = con.execute(
            """
          SELECT
            group_name,
            coin,
            binance_symbol,
            local_symbol,
            multiplier_symbol,
            pp,
            ap,
            amount,
            buy_th,
            sell_th,
            cancel_th
          FROM coins
          ORDER BY group_name, coin
        """
        ).fetchall()

    rows_by_group = {g: [] for g in GROUPS}
    for r in rows:
        g = (r["group_name"] or "").lower()
        if g not in rows_by_group:
            rows_by_group[g] = []
        rows_by_group[g].append(r)

    body = render_template_string(
        INDEX_HTML,
        groups=GROUPS,
        rows_by_group=rows_by_group,
        group_label=group_label,
        group_local_label=group_local_label,
    )
    return render_template_string(LAYOUT, body=body)


@app.route("/add")
def add_coin():
    group = (request.args.get("group", "btcturk_binance") or "").lower()
    if group not in GROUPS:
        group = "btcturk_binance"
    body = render_template_string(
        ADD_HTML,
        group=group,
        group_label=group_label,
        group_local_label=group_local_label,
    )
    return render_template_string(LAYOUT, body=body)


@app.route("/edit/<group>/<coin>")
def edit_coin(group, coin):
    group = (group or "").lower()
    with db() as con:
        row = con.execute(
            "SELECT * FROM coins WHERE group_name=? AND coin=?",
            (group, coin.upper()),
        ).fetchone()
    if not row:
        flash(f"{group}:{coin} not found")
        return redirect(url_for("index"))
    body = render_template_string(
        EDIT_HTML,
        coin=coin.upper(),
        row=row,
        group_label=group_label,
        group_local_label=group_local_label,
    )
    return render_template_string(LAYOUT, body=body)


@app.route("/save-coin", methods=["POST"])
def save_coin():
    group = (request.form.get("group", "btcturk_binance") or "").lower()
    if group not in GROUPS:
        group = "btcturk_binance"

    coin = (request.form.get("coin") or "").strip().upper()
    if not coin:
        flash("Coin is required")
        return redirect(url_for("index"))

    try:
        amount = validate_numeric("amount", request.form.get("amount", "10"), "decimal")
        pp = validate_numeric("pp", request.form.get("pp", "0"), "int")
        ap = validate_numeric("ap", request.form.get("ap", "0"), "int")

        buy_th = validate_numeric("buy_th", request.form.get("buy_th", "0.010"), "decimal")
        sell_th = validate_numeric("sell_th", request.form.get("sell_th", "0.010"), "decimal")
        cancel_th = validate_numeric(
            "cancel_th", request.form.get("cancel_th", "0.001"), "decimal"
        )
    except Exception as e:
        flash(str(e))
        return redirect(url_for("edit_coin", group=group, coin=coin))

    data = {
        "amount": str(amount),
        "pp": int(pp),
        "ap": int(ap),
        "buy_th": str(buy_th),
        "sell_th": str(sell_th),
        "cancel_th": str(cancel_th),
        "binance_symbol": (request.form.get("binance_symbol", "") or "").strip()
        or None,
        "local_symbol": (request.form.get("local_symbol", "") or "").strip() or None,
        "multiplier_symbol": (request.form.get("multiplier_symbol", "") or "").strip()
        or None,
    }
    upsert_coin_row(group, coin, data)

    flash(f"Saved {group}:{coin}")
    return redirect(url_for("edit_coin", group=group, coin=coin))


@app.route("/delete-coin", methods=["POST"])
def delete_coin():
    group = (request.form.get("group") or "").lower()
    coin = (request.form.get("coin") or "").strip().upper()
    with db() as con:
        con.execute("DELETE FROM coins WHERE group_name=? AND coin=?", (group, coin))
    flash(f"Deleted {group} coin {coin}")
    return redirect(url_for("index"))


@app.route("/seed-defaults", methods=["POST"])
def seed_defaults():
    for group, coins in symbols_for_exchange.items():
        g = group.lower()
        for coin, sym in coins.items():
            payload = {
                **SEED_NUMERIC,
                "binance_symbol": sym.get("binance"),
                "local_symbol": sym.get("local"),
                "multiplier_symbol": sym.get("multiplier"),
                "pp": sym.get("pp", 0),
                "ap": sym.get("ap", 0),
            }
            upsert_coin_row(g, coin.upper(), payload)

    flash("Seeded defaults")
    return redirect(url_for("index"))


# ---------- Helpers for your trading code ----------


def load_coin_config(group_name, coin):
    """
    Return dict with typed values:
      amount (Decimal), buy_th/sell_th/cancel_th (Decimal),
      binance_symbol/local_symbol/multiplier_symbol (str or None),
      pp/ap (int)
    """
    group_name = (group_name or "").lower()
    coin = (coin or "").upper()
    with db() as con:
        row = con.execute(
            "SELECT * FROM coins WHERE group_name=? AND coin=?",
            (group_name, coin),
        ).fetchone()
    if not row:
        raise KeyError(f"{group_name} coin {coin} not found")

    return {
        "amount": Decimal(row["amount"]),
        "buy_th": Decimal(row["buy_th"]),
        "sell_th": Decimal(row["sell_th"]),
        "cancel_th": Decimal(row["cancel_th"]),
        "binance": row["binance_symbol"],
        "local": row["local_symbol"],
        "multiplier": row["multiplier_symbol"],
        "pp": int(row["pp"]),
        "ap": int(row["ap"]),
    }


def load_all_configs():
    """
    Return nested dict:
    {
        "paribu_binance": { "COIN": {...}, ... },
        "paribu_btcturk": { ... },
        ...
    }
    """
    cfg = {g: {} for g in GROUPS}
    with db() as con:
        rows = con.execute("SELECT group_name, coin FROM coins").fetchall()
    for r in rows:
        g = (r["group_name"] or "").lower()
        c = (r["coin"] or "").upper()
        if g not in cfg:
            cfg[g] = {}
        cfg[g][c] = load_coin_config(g, c)
    return cfg


def write_pid():
    import os

    pid = os.getpid()
    print("My PID:", pid)
    with open("allowed_pids.txt", "w") as f:
        f.write(str(pid) + "\n")
    print("PID written to allowed_pids.txt")


if __name__ == "__main__":
    try:
        # Ensure table exists; seed if empty
        with db() as con:
            have = con.execute("SELECT COUNT(*) c FROM coins").fetchone()["c"]
        if have == 0:
            for group, coins in symbols_for_exchange.items():
                for coin, sym in coins.items():
                    payload = {
                        **SEED_NUMERIC,
                        "binance_symbol": sym.get("binance"),
                        "local_symbol": sym.get("local"),
                        "multiplier_symbol": sym.get("multiplier"),
                        "pp": sym.get("pp", 0),
                        "ap": sym.get("ap", 0),
                    }
                    upsert_coin_row(group.lower(), coin.upper(), payload)

        write_pid()
        app.run(port=5000, debug=False, use_reloader=False)
    except Exception as e:
        print("Startup error:", e)
