"""Tenant-scoped SQLite persistence for the Oraviro MVP."""
import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path

DB_PATH = os.getenv("ORAVIRO_DB_PATH", str(Path(__file__).resolve().parent.parent / "oraviro.db"))
DEFAULT_BUSINESS_ID = os.getenv("ORAVIRO_DEFAULT_BUSINESS_ID", "business_oraviro_demo")
DEMO_BUSINESS = {
    "id": DEFAULT_BUSINESS_ID,
    "name": os.getenv("ORAVIRO_DEFAULT_BUSINESS_NAME", "Oraviro Demo Store"),
    "slug": os.getenv("ORAVIRO_DEFAULT_BUSINESS_SLUG", "oraviro-demo"),
    "currency": "DZD",
}


@contextmanager
def connect():
    db = sqlite3.connect(DB_PATH, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=15000")
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS businesses(
        id TEXT PRIMARY KEY, name TEXT NOT NULL, slug TEXT UNIQUE NOT NULL, description TEXT,
        phone TEXT, email TEXT, address TEXT, currency TEXT NOT NULL DEFAULT 'DZD',
        active INTEGER NOT NULL DEFAULT 1, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS users(
        id TEXT PRIMARY KEY, business_id TEXT NOT NULL REFERENCES businesses(id) ON DELETE RESTRICT,
        name TEXT, email TEXT NOT NULL, password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'staff',
        active INTEGER NOT NULL DEFAULT 1, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(business_id,email))""",
    """CREATE TABLE IF NOT EXISTS customers(
        id TEXT PRIMARY KEY, business_id TEXT NOT NULL REFERENCES businesses(id) ON DELETE RESTRICT,
        name TEXT, phone TEXT, email TEXT, address TEXT, city TEXT, country TEXT,
        preferred_language TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(business_id,id))""",
    """CREATE TABLE IF NOT EXISTS categories(
        id TEXT PRIMARY KEY, business_id TEXT NOT NULL REFERENCES businesses(id) ON DELETE RESTRICT,
        name TEXT NOT NULL, description TEXT, parent_id TEXT REFERENCES categories(id) ON DELETE SET NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(business_id,name))""",
    """CREATE TABLE IF NOT EXISTS products(
        id TEXT PRIMARY KEY, business_id TEXT NOT NULL REFERENCES businesses(id) ON DELETE RESTRICT,
        category_id TEXT REFERENCES categories(id) ON DELETE SET NULL, name TEXT NOT NULL, sku TEXT NOT NULL,
        brand TEXT, description TEXT, price REAL NOT NULL CHECK(price >= 0), compare_at_price REAL,
        cost_price REAL, active INTEGER NOT NULL DEFAULT 1, featured INTEGER NOT NULL DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(business_id,sku))""",
    """CREATE TABLE IF NOT EXISTS product_variants(
        id TEXT PRIMARY KEY, business_id TEXT NOT NULL REFERENCES businesses(id) ON DELETE RESTRICT,
        product_id TEXT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
        name TEXT, sku TEXT NOT NULL, price REAL CHECK(price IS NULL OR price >= 0), stock INTEGER NOT NULL DEFAULT 0 CHECK(stock >= 0),
        attributes TEXT NOT NULL DEFAULT '{}', created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(business_id,sku))""",
    """CREATE TABLE IF NOT EXISTS inventory(
        id TEXT PRIMARY KEY, business_id TEXT NOT NULL REFERENCES businesses(id) ON DELETE RESTRICT,
        product_id TEXT REFERENCES products(id) ON DELETE CASCADE,
        variant_id TEXT REFERENCES product_variants(id) ON DELETE CASCADE,
        quantity INTEGER NOT NULL DEFAULT 0 CHECK(quantity >= 0),
        reserved_quantity INTEGER NOT NULL DEFAULT 0 CHECK(reserved_quantity >= 0 AND reserved_quantity <= quantity),
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        CHECK((product_id IS NOT NULL AND variant_id IS NULL) OR (product_id IS NULL AND variant_id IS NOT NULL)))""",
    """CREATE TABLE IF NOT EXISTS carts(
        id TEXT PRIMARY KEY, business_id TEXT NOT NULL REFERENCES businesses(id) ON DELETE RESTRICT,
        customer_id TEXT NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
        status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','converted','abandoned')),
        created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS cart_items(
        id INTEGER PRIMARY KEY AUTOINCREMENT, cart_id TEXT NOT NULL REFERENCES carts(id) ON DELETE CASCADE,
        product_id TEXT NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
        variant_id TEXT REFERENCES product_variants(id) ON DELETE RESTRICT,
        quantity INTEGER NOT NULL CHECK(quantity > 0), unit_price REAL NOT NULL CHECK(unit_price >= 0))""",
    """CREATE TABLE IF NOT EXISTS orders(
        id TEXT PRIMARY KEY, business_id TEXT NOT NULL REFERENCES businesses(id) ON DELETE RESTRICT,
        customer_id TEXT NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
        status TEXT NOT NULL DEFAULT 'pending', payment_status TEXT NOT NULL DEFAULT 'pending',
        fulfillment_status TEXT NOT NULL DEFAULT 'unfulfilled', subtotal REAL NOT NULL CHECK(subtotal >= 0),
        shipping_cost REAL NOT NULL DEFAULT 0 CHECK(shipping_cost >= 0), discount REAL NOT NULL DEFAULT 0 CHECK(discount >= 0),
        total REAL NOT NULL CHECK(total >= 0), currency TEXT NOT NULL DEFAULT 'DZD',
        shipping_name TEXT, shipping_phone TEXT, shipping_address TEXT, shipping_city TEXT, notes TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS order_items(
        id INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
        product_id TEXT NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
        variant_id TEXT REFERENCES product_variants(id) ON DELETE RESTRICT,
        product_name TEXT NOT NULL, sku TEXT, quantity INTEGER NOT NULL CHECK(quantity > 0),
        unit_price REAL NOT NULL CHECK(unit_price >= 0), subtotal REAL NOT NULL CHECK(subtotal >= 0))""",
    """CREATE TABLE IF NOT EXISTS payments(
        id TEXT PRIMARY KEY, business_id TEXT NOT NULL REFERENCES businesses(id) ON DELETE RESTRICT,
        order_id TEXT NOT NULL REFERENCES orders(id) ON DELETE RESTRICT,
        method TEXT NOT NULL CHECK(method IN ('cash_on_delivery','bank_transfer','online','other')),
        status TEXT NOT NULL DEFAULT 'pending', amount REAL NOT NULL CHECK(amount >= 0), transaction_id TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS shipments(
        id TEXT PRIMARY KEY, business_id TEXT NOT NULL REFERENCES businesses(id) ON DELETE RESTRICT,
        order_id TEXT NOT NULL REFERENCES orders(id) ON DELETE RESTRICT, carrier TEXT, tracking_number TEXT,
        status TEXT NOT NULL DEFAULT 'pending', shipped_at TEXT, delivered_at TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS conversations(
        id TEXT PRIMARY KEY, business_id TEXT NOT NULL REFERENCES businesses(id) ON DELETE RESTRICT,
        customer_id TEXT NOT NULL REFERENCES customers(id) ON DELETE RESTRICT, channel TEXT NOT NULL,
        channel_user_id TEXT, status TEXT NOT NULL DEFAULT 'open', state TEXT NOT NULL DEFAULT '{}', language TEXT,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS messages(
        id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
        role TEXT NOT NULL CHECK(role IN ('user','assistant','system','tool')), content TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS subscriptions(
        id TEXT PRIMARY KEY, business_id TEXT NOT NULL REFERENCES businesses(id) ON DELETE RESTRICT,
        customer_id TEXT NOT NULL REFERENCES customers(id) ON DELETE RESTRICT, channel TEXT NOT NULL,
        channel_user_id TEXT NOT NULL, subscription_type TEXT NOT NULL DEFAULT 'new_product',
        active INTEGER NOT NULL DEFAULT 1, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(business_id,channel,channel_user_id,subscription_type))""",
    """CREATE TABLE IF NOT EXISTS leads(
        id TEXT PRIMARY KEY, business_id TEXT NOT NULL REFERENCES businesses(id) ON DELETE RESTRICT,
        customer_id TEXT NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
        conversation_id TEXT UNIQUE REFERENCES conversations(id) ON DELETE SET NULL,
        profile TEXT NOT NULL DEFAULT '{}', lead_score INTEGER NOT NULL DEFAULT 0,
        lead_status TEXT NOT NULL DEFAULT 'new', consented INTEGER NOT NULL DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS product_images(
        id TEXT PRIMARY KEY, product_id TEXT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
        url TEXT NOT NULL, alt_text TEXT, position INTEGER NOT NULL DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP)""",
]

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_customers_business ON customers(business_id)",
    "CREATE INDEX IF NOT EXISTS idx_users_business ON users(business_id)",
    "CREATE INDEX IF NOT EXISTS idx_products_business ON products(business_id)",
    "CREATE INDEX IF NOT EXISTS idx_products_category ON products(category_id)",
    "CREATE INDEX IF NOT EXISTS idx_products_sku ON products(business_id,sku)",
    "CREATE INDEX IF NOT EXISTS idx_variants_sku ON product_variants(business_id,sku)",
    "CREATE INDEX IF NOT EXISTS idx_inventory_business ON inventory(business_id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_inventory_product ON inventory(business_id,product_id) WHERE product_id IS NOT NULL",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_inventory_variant ON inventory(business_id,variant_id) WHERE variant_id IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_carts_customer ON carts(business_id,customer_id,status)",
    "CREATE INDEX IF NOT EXISTS idx_cart_items_cart ON cart_items(cart_id)",
    "CREATE INDEX IF NOT EXISTS idx_orders_business ON orders(business_id,created_at)",
    "CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(business_id,customer_id)",
    "CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items(order_id)",
    "CREATE INDEX IF NOT EXISTS idx_order_items_product ON order_items(product_id)",
    "CREATE INDEX IF NOT EXISTS idx_payments_order ON payments(business_id,order_id)",
    "CREATE INDEX IF NOT EXISTS idx_shipments_order ON shipments(business_id,order_id)",
    "CREATE INDEX IF NOT EXISTS idx_conversations_business ON conversations(business_id,customer_id)",
    "CREATE INDEX IF NOT EXISTS idx_conversations_channel_user ON conversations(business_id,channel,channel_user_id)",
    "CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id)",
    "CREATE INDEX IF NOT EXISTS idx_subscriptions_business ON subscriptions(business_id,channel_user_id)",
    "CREATE INDEX IF NOT EXISTS idx_leads_business ON leads(business_id,customer_id)",
    "CREATE INDEX IF NOT EXISTS idx_images_product ON product_images(product_id,position)",
]

_LEGACY_TABLES = ("customers", "products", "orders", "order_items", "conversations", "messages", "subscriptions", "leads")


def _table_exists(db, name):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def _columns(db, name):
    return {row["name"] for row in db.execute(f'PRAGMA table_info("{name}")')}


def _insert_business(db, business):
    db.execute("""INSERT OR IGNORE INTO businesses(id,name,slug,description,phone,email,address,currency,active)
        VALUES(:id,:name,:slug,:description,:phone,:email,:address,:currency,:active)""",
        {"id": business["id"], "name": business["name"], "slug": business["slug"],
         "description": business.get("description"), "phone": business.get("phone"),
         "email": business.get("email"), "address": business.get("address"),
         "currency": business.get("currency", "DZD"), "active": int(business.get("active", 1))})


def _migrate_legacy(db, legacy):
    """Copy the old single-store schema into the demo tenant without dropping data."""
    b = DEMO_BUSINESS["id"]
    if "customers" in legacy:
        cols = _columns(db, legacy["customers"])
        for row in db.execute(f'SELECT * FROM "{legacy["customers"]}"').fetchall():
            db.execute("""INSERT OR IGNORE INTO customers(id,business_id,name,phone,email,address,preferred_language,created_at)
                VALUES(?,?,?,?,?,?,?,?)""", (row["id"], b, row["name"] if "name" in cols else None,
                row["phone"] if "phone" in cols else None, row["email"] if "email" in cols else None,
                row["address"] if "address" in cols else None, row["preferred_language"] if "preferred_language" in cols else None,
                row["created_at"] if "created_at" in cols else None))
    category_map = {}
    if "products" in legacy:
        cols = _columns(db, legacy["products"])
        for row in db.execute(f'SELECT * FROM "{legacy["products"]}"').fetchall():
            category_name = row["category"] if "category" in cols else None
            category_id = None
            if category_name:
                key = str(category_name).strip().lower()
                if key not in category_map:
                    category_id = "cat_" + uuid.uuid5(uuid.NAMESPACE_URL, b + ":" + key).hex[:16]
                    db.execute("INSERT OR IGNORE INTO categories(id,business_id,name) VALUES(?,?,?)", (category_id,b,str(category_name).strip()))
                    category_map[key] = category_id
                category_id = category_map[key]
            db.execute("""INSERT OR IGNORE INTO products(id,business_id,category_id,name,sku,brand,description,price,created_at)
                VALUES(?,?,?,?,?,?,?,?,?)""", (row["id"],b,category_id,row["name"],row["sku"],
                row["brand"] if "brand" in cols else None,row["description"] if "description" in cols else None,
                row["price"],row["created_at"] if "created_at" in cols else None))
            if "stock" in cols:
                db.execute("INSERT OR IGNORE INTO inventory(id,business_id,product_id,quantity) VALUES(?,?,?,?)",
                    ("inv_"+uuid.uuid5(uuid.NAMESPACE_URL,b+":"+row["id"]).hex[:16],b,row["id"],max(0,int(row["stock"] or 0))))
    if "orders" in legacy:
        cols = _columns(db, legacy["orders"])
        for row in db.execute(f'SELECT * FROM "{legacy["orders"]}"').fetchall():
            customer_id = row["customer_id"]
            db.execute("INSERT OR IGNORE INTO customers(id,business_id) VALUES(?,?)", (customer_id,b))
            total = float(row["total"] or 0)
            db.execute("""INSERT OR IGNORE INTO orders(id,business_id,customer_id,status,subtotal,total,created_at)
                VALUES(?,?,?,?,?,?,?)""", (row["id"],b,customer_id,row["status"] if "status" in cols else "pending",total,total,
                row["created_at"] if "created_at" in cols else None))
    if "order_items" in legacy:
        for row in db.execute(f'SELECT * FROM "{legacy["order_items"]}"').fetchall():
            product = db.execute("SELECT name,sku FROM products WHERE id=? AND business_id=?", (row["product_id"],b)).fetchone()
            if not product: continue
            quantity, price = int(row["quantity"]), float(row["unit_price"])
            db.execute("""INSERT INTO order_items(order_id,product_id,product_name,sku,quantity,unit_price,subtotal)
                VALUES(?,?,?,?,?,?,?)""", (row["order_id"],row["product_id"],product["name"],product["sku"],quantity,price,quantity*price))
        if "orders" in legacy:
            for order in db.execute(f'SELECT id,status FROM "{legacy["orders"]}" WHERE status IN (\'pending\',\'confirmed\',\'processing\')').fetchall():
                for item in db.execute("SELECT product_id,SUM(quantity) AS quantity FROM order_items WHERE order_id=? GROUP BY product_id",(order["id"],)).fetchall():
                    # The previous MVP deducted stock at order creation. Restore
                    # pending units into on-hand quantity and mark them reserved.
                    db.execute("UPDATE inventory SET quantity=quantity+?,reserved_quantity=reserved_quantity+?,updated_at=CURRENT_TIMESTAMP WHERE business_id=? AND product_id=?",
                        (item["quantity"],item["quantity"],b,item["product_id"]))
    if "conversations" in legacy:
        cols = _columns(db, legacy["conversations"])
        for row in db.execute(f'SELECT * FROM "{legacy["conversations"]}"').fetchall():
            customer_id = row["customer_id"]
            db.execute("INSERT OR IGNORE INTO customers(id,business_id) VALUES(?,?)",(customer_id,b))
            user_channel = "telegram" if str(customer_id).startswith("telegram_") else "web"
            channel_user_id = str(customer_id).removeprefix("telegram_") if user_channel == "telegram" else customer_id
            db.execute("""INSERT OR IGNORE INTO conversations(id,business_id,customer_id,channel,channel_user_id,status,state,language,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?)""", (row["id"],b,customer_id,user_channel,channel_user_id,
                row["status"] if "status" in cols else "open",row["state"] if "state" in cols else "{}",
                row["language"] if "language" in cols else None,row["created_at"] if "created_at" in cols else None,
                row["updated_at"] if "updated_at" in cols else None))
    if "messages" in legacy:
        for row in db.execute(f'SELECT * FROM "{legacy["messages"]}"').fetchall():
            db.execute("INSERT INTO messages(id,conversation_id,role,content,created_at) VALUES(?,?,?,?,?)",
                (row["id"],row["conversation_id"],row["role"],row["content"],row["created_at"]))
    if "subscriptions" in legacy:
        cols = _columns(db, legacy["subscriptions"])
        for row in db.execute(f'SELECT * FROM "{legacy["subscriptions"]}"').fetchall():
            customer_id=row["customer_id"]
            db.execute("INSERT OR IGNORE INTO customers(id,business_id) VALUES(?,?)",(customer_id,b))
            db.execute("""INSERT OR IGNORE INTO subscriptions(id,business_id,customer_id,channel,channel_user_id,subscription_type,active,created_at)
                VALUES(?,?,?,?,?,?,?,?)""", (row["id"],b,customer_id,row["channel"],row["channel_user_id"],
                row["subscription_type"] if "subscription_type" in cols else "new_product",
                row["active"] if "active" in cols else 1,row["created_at"] if "created_at" in cols else None))
    if "leads" in legacy:
        cols = _columns(db, legacy["leads"])
        for row in db.execute(f'SELECT * FROM "{legacy["leads"]}"').fetchall():
            customer_id=row["customer_id"]
            db.execute("INSERT OR IGNORE INTO customers(id,business_id) VALUES(?,?)",(customer_id,b))
            conversation_id=row["conversation_id"] if "conversation_id" in cols else None
            if conversation_id and not db.execute("SELECT 1 FROM conversations WHERE id=?",(conversation_id,)).fetchone():
                conversation_id=None
            db.execute("""INSERT OR IGNORE INTO leads(id,business_id,customer_id,conversation_id,profile,lead_score,lead_status,consented,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?)""",(row["id"],b,customer_id,conversation_id,row["profile"] if "profile" in cols else "{}",
                row["lead_score"] if "lead_score" in cols else 0,row["lead_status"] if "lead_status" in cols else "new",
                row["consented"] if "consented" in cols else 0,row["created_at"] if "created_at" in cols else None,
                row["updated_at"] if "updated_at" in cols else None))


def initialize_database():
    """Create schema and atomically migrate the old single-business MVP when present."""
    db = sqlite3.connect(DB_PATH, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=OFF")
    legacy = {}
    try:
        db.execute("BEGIN IMMEDIATE")
        needs_migration = _table_exists(db,"products") and "business_id" not in _columns(db,"products")
        if needs_migration:
            for table in _LEGACY_TABLES:
                if _table_exists(db,table):
                    legacy_name = "legacy_" + table
                    if _table_exists(db,legacy_name):
                        raise RuntimeError(f"Cannot migrate: {legacy_name} already exists")
                    db.execute(f'ALTER TABLE "{table}" RENAME TO "{legacy_name}"')
                    legacy[table] = legacy_name
        for statement in _SCHEMA:
            db.execute(statement)
        _insert_business(db,DEMO_BUSINESS)
        if legacy:
            _migrate_legacy(db,legacy)
            for old_table in legacy.values():
                db.execute(f'DROP TABLE "{old_table}"')
        for statement in _INDEXES:
            db.execute(statement)
        violations=db.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(f"Database migration produced {len(violations)} foreign-key violation(s)")
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.execute("PRAGMA foreign_keys=ON")
        db.close()


def row_dict(row):
    return dict(row) if row is not None else None


def _id(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _customer_id(db, customer_id, business_id):
    row = db.execute("SELECT id FROM customers WHERE id=? AND business_id=?",(customer_id,business_id)).fetchone()
    if row:
        return row["id"]
    collision = db.execute("SELECT id FROM customers WHERE id=?",(customer_id,)).fetchone()
    if not collision:
        return customer_id
    scoped = "cus_" + uuid.uuid5(uuid.NAMESPACE_URL,f"{business_id}:{customer_id}").hex[:20]
    row = db.execute("SELECT id FROM customers WHERE id=? AND business_id=?",(scoped,business_id)).fetchone()
    return row["id"] if row else scoped


def create_business(name, slug, description=None, phone=None, email=None, address=None, currency="DZD", active=True, business_id=None):
    business_id = business_id or _id("biz")
    with connect() as db:
        db.execute("INSERT INTO businesses(id,name,slug,description,phone,email,address,currency,active) VALUES(?,?,?,?,?,?,?,?,?)",
            (business_id,name.strip(),slug.strip().lower(),description,phone,email,address,currency,int(active)))
    return get_business(business_id)


def get_business(business_id):
    with connect() as db: return row_dict(db.execute("SELECT * FROM businesses WHERE id=?",(business_id,)).fetchone())


def list_businesses(active_only=False):
    with connect() as db:
        sql="SELECT * FROM businesses" + (" WHERE active=1" if active_only else "") + " ORDER BY name"
        return [row_dict(r) for r in db.execute(sql).fetchall()]


def create_category(name, business_id=DEFAULT_BUSINESS_ID, description=None, parent_id=None, category_id=None):
    category_id=category_id or _id("cat")
    if parent_id and not get_category(parent_id,business_id): raise ValueError("Parent category not found for this business")
    with connect() as db:
        db.execute("INSERT INTO categories(id,business_id,name,description,parent_id) VALUES(?,?,?,?,?)",
            (category_id,business_id,name.strip(),description,parent_id))
    return get_category(category_id,business_id)


def get_category(category_id,business_id=DEFAULT_BUSINESS_ID):
    with connect() as db: return row_dict(db.execute("SELECT * FROM categories WHERE id=? AND business_id=?",(category_id,business_id)).fetchone())


def list_categories(business_id=DEFAULT_BUSINESS_ID):
    with connect() as db: return [row_dict(r) for r in db.execute("SELECT * FROM categories WHERE business_id=? ORDER BY name",(business_id,)).fetchall()]


def _category_id(db, category, business_id):
    if not category: return None
    row=db.execute("SELECT id FROM categories WHERE business_id=? AND (id=? OR lower(name)=lower(?)) LIMIT 1",(business_id,str(category),str(category))).fetchone()
    return row["id"] if row else None


def _product_row(db, product_id, business_id):
    row=db.execute("""SELECT p.*,c.name AS category,
        COALESCE((SELECT SUM(i.quantity-i.reserved_quantity) FROM inventory i WHERE i.business_id=p.business_id AND i.product_id=p.id),
                 (SELECT SUM(i.quantity-i.reserved_quantity) FROM inventory i JOIN product_variants v ON v.id=i.variant_id WHERE i.business_id=p.business_id AND v.business_id=p.business_id AND v.product_id=p.id),0) AS stock
        FROM products p LEFT JOIN categories c ON c.id=p.category_id
        WHERE p.id=? AND p.business_id=?""",(product_id,business_id)).fetchone()
    return row_dict(row)


def create_product(product=None, business_id=DEFAULT_BUSINESS_ID, **fields):
    data=dict(product or {}); data.update(fields)
    product_id=data.get("id") or _id("prod")
    category_id=data.get("category_id") or _category_id_from_value(data.get("category"),business_id)
    if data.get("category_id") and not get_category(data["category_id"],business_id): raise ValueError("Category not found for this business")
    with connect() as db:
        db.execute("""INSERT INTO products(id,business_id,category_id,name,sku,brand,description,price,compare_at_price,cost_price,active,featured)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",(product_id,business_id,category_id,data["name"].strip(),data["sku"].strip(),data.get("brand"),data.get("description"),float(data["price"]),
            data.get("compare_at_price"),data.get("cost_price"),int(data.get("active",1)),int(data.get("featured",0))))
        if data.get("stock") is not None:
            _set_inventory_tx(db,business_id,product_id,int(data["stock"]))
    return get_product(product_id,business_id)


def _category_id_from_value(value,business_id):
    if not value: return None
    with connect() as db: return _category_id(db,value,business_id)


def get_product(product_id,business_id=DEFAULT_BUSINESS_ID):
    with connect() as db: return _product_row(db,product_id,business_id)


def list_products(business_id=DEFAULT_BUSINESS_ID, active_only=False):
    with connect() as db:
        sql="SELECT id FROM products WHERE business_id=?" + (" AND active=1" if active_only else "") + " ORDER BY name"
        ids=[r["id"] for r in db.execute(sql,(business_id,)).fetchall()]
        return [_product_row(db,pid,business_id) for pid in ids]


def search_products(query="",business_id=DEFAULT_BUSINESS_ID,active_only=True):
    q=f"%{query.strip().lower()}%"
    sql="""SELECT DISTINCT p.id FROM products p LEFT JOIN categories c ON c.id=p.category_id
        WHERE p.business_id=? AND (?=0 OR p.active=1) AND
        (lower(p.name) LIKE ? OR lower(COALESCE(c.name,'')) LIKE ? OR lower(COALESCE(p.brand,'')) LIKE ? OR lower(COALESCE(p.description,'')) LIKE ? OR lower(p.sku) LIKE ? OR EXISTS(SELECT 1 FROM product_variants v WHERE v.product_id=p.id AND lower(v.sku) LIKE ?)) ORDER BY p.name"""
    with connect() as db:
        ids=[r["id"] for r in db.execute(sql,(business_id,int(active_only),q,q,q,q,q,q)).fetchall()]
        return [_product_row(db,pid,business_id) for pid in ids]


def update_product(product_id,business_id=DEFAULT_BUSINESS_ID,**fields):
    allowed={"name","sku","category_id","brand","description","price","compare_at_price","cost_price","active","featured"}
    updates={k:v for k,v in fields.items() if k in allowed and v is not None}
    if "category" in fields and "category_id" not in updates: updates["category_id"]=_category_id_from_value(fields["category"],business_id)
    with connect() as db:
        category_id=updates.get("category_id")
        if category_id and not db.execute("SELECT 1 FROM categories WHERE id=? AND business_id=?",(category_id,business_id)).fetchone():
            raise ValueError("Category not found for this business")
        if "stock" in fields and fields["stock"] is not None: _set_inventory_tx(db,business_id,product_id,int(fields["stock"]))
        if updates:
            updates["updated_at"]="CURRENT_TIMESTAMP"
            assignments=",".join(f"{key}=?" for key in updates)
            values=[v for k,v in updates.items() if k!="updated_at"]+[product_id,business_id]
            assignments=",".join(f"{key}=?" for key in updates if key!="updated_at")+",updated_at=CURRENT_TIMESTAMP"
            changed=db.execute(f"UPDATE products SET {assignments} WHERE id=? AND business_id=?",values).rowcount
        else: changed=db.execute("SELECT 1 FROM products WHERE id=? AND business_id=?",(product_id,business_id)).fetchone() is not None
        if not changed: return None
    return get_product(product_id,business_id)


def upsert_product(product,business_id=DEFAULT_BUSINESS_ID):
    data=dict(product)
    product_id=data.get("id")
    if product_id and get_product(product_id,business_id):
        data.pop("id",None)
        return update_product(product_id,business_id,**data)
    return create_product(data,business_id)


def delete_product(product_id,business_id=DEFAULT_BUSINESS_ID):
    with connect() as db: return db.execute("DELETE FROM products WHERE id=? AND business_id=?",(product_id,business_id)).rowcount>0


def create_product_variant(product_id,sku,name=None,price=None,stock=0,attributes=None,business_id=DEFAULT_BUSINESS_ID,variant_id=None):
    variant_id=variant_id or _id("var")
    stock=int(stock)
    if stock<0: raise ValueError("Variant stock cannot be negative")
    with connect() as db:
        if not db.execute("SELECT 1 FROM products WHERE id=? AND business_id=?",(product_id,business_id)).fetchone(): raise ValueError("Product not found for this business")
        db.execute("INSERT INTO product_variants(id,business_id,product_id,name,sku,price,stock,attributes) VALUES(?,?,?,?,?,?,?,?)",
            (variant_id,business_id,product_id,name,sku.strip(),price,stock,json.dumps(attributes or {},ensure_ascii=False)))
        db.execute("INSERT INTO inventory(id,business_id,variant_id,quantity) VALUES(?,?,?,?)",(_id("inv"),business_id,variant_id,stock))
    return get_product_variant(variant_id,business_id)


def get_product_variant(variant_id,business_id=DEFAULT_BUSINESS_ID):
    with connect() as db:
        row=db.execute("""SELECT v.*,COALESCE(i.quantity,0) AS inventory_quantity,
            COALESCE(i.reserved_quantity,0) AS reserved_quantity,
            COALESCE(i.quantity-i.reserved_quantity,0) AS available_quantity
            FROM product_variants v LEFT JOIN inventory i ON i.variant_id=v.id
            WHERE v.id=? AND v.business_id=?""",(variant_id,business_id)).fetchone()
        result=row_dict(row)
        if result: result["attributes"]=json.loads(result["attributes"] or "{}")
        return result


def list_product_variants(product_id,business_id=DEFAULT_BUSINESS_ID):
    with connect() as db:
        ids=[r["id"] for r in db.execute("SELECT v.id FROM product_variants v WHERE v.product_id=? AND v.business_id=? ORDER BY v.name",(product_id,business_id)).fetchall()]
        return [get_product_variant(variant_id,business_id) for variant_id in ids]


def update_product_variant(variant_id,business_id=DEFAULT_BUSINESS_ID,**fields):
    allowed={"name","sku","price","attributes"}
    updates={k:v for k,v in fields.items() if k in allowed and v is not None}
    if "attributes" in updates: updates["attributes"]=json.dumps(updates["attributes"],ensure_ascii=False)
    with connect() as db:
        row=db.execute("SELECT v.product_id FROM product_variants v WHERE v.id=? AND v.business_id=?",(variant_id,business_id)).fetchone()
        if not row: return None
        if "stock" in fields and fields["stock"] is not None:
            quantity=int(fields["stock"])
            inv=db.execute("SELECT reserved_quantity FROM inventory WHERE business_id=? AND variant_id=?",(business_id,variant_id)).fetchone()
            if quantity<0 or (inv and quantity<inv["reserved_quantity"]): raise ValueError("Variant stock cannot be below reserved inventory")
            db.execute("UPDATE inventory SET quantity=?,updated_at=CURRENT_TIMESTAMP WHERE business_id=? AND variant_id=?",(quantity,business_id,variant_id))
            db.execute("UPDATE product_variants SET stock=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",(quantity,variant_id))
        if updates:
            assignments=",".join(f"{k}=?" for k in updates)+",updated_at=CURRENT_TIMESTAMP"
            db.execute(f"UPDATE product_variants SET {assignments} WHERE id=?",(*updates.values(),variant_id))
    return get_product_variant(variant_id,business_id)


def delete_product_variant(variant_id,business_id=DEFAULT_BUSINESS_ID):
    with connect() as db:
        exists=db.execute("SELECT 1 FROM product_variants WHERE id=? AND business_id=?",(variant_id,business_id)).fetchone()
        if not exists: return False
        db.execute("DELETE FROM product_variants WHERE id=?",(variant_id,))
        return True


def add_product_image(product_id,url,alt_text=None,position=0,business_id=DEFAULT_BUSINESS_ID,image_id=None):
    image_id=image_id or _id("img")
    with connect() as db:
        if not db.execute("SELECT 1 FROM products WHERE id=? AND business_id=?",(product_id,business_id)).fetchone(): raise ValueError("Product not found for this business")
        db.execute("INSERT INTO product_images(id,product_id,url,alt_text,position) VALUES(?,?,?,?,?)",(image_id,product_id,url,alt_text,int(position)))
    return get_product_image(image_id,business_id)


def get_product_image(image_id,business_id=DEFAULT_BUSINESS_ID):
    with connect() as db:
        return row_dict(db.execute("SELECT i.* FROM product_images i JOIN products p ON p.id=i.product_id WHERE i.id=? AND p.business_id=?",(image_id,business_id)).fetchone())


def list_product_images(product_id,business_id=DEFAULT_BUSINESS_ID):
    with connect() as db:
        return [row_dict(r) for r in db.execute("SELECT i.* FROM product_images i JOIN products p ON p.id=i.product_id WHERE p.id=? AND p.business_id=? ORDER BY i.position",(product_id,business_id)).fetchall()]


def delete_product_image(image_id,business_id=DEFAULT_BUSINESS_ID):
    with connect() as db:
        return db.execute("DELETE FROM product_images WHERE id=? AND product_id IN (SELECT id FROM products WHERE business_id=?)",(image_id,business_id)).rowcount>0


def _set_inventory_tx(db,business_id,product_id,quantity,reserved_quantity=None):
    if quantity<0: raise ValueError("Inventory quantity cannot be negative")
    row=db.execute("SELECT id,reserved_quantity FROM inventory WHERE business_id=? AND product_id=?",(business_id,product_id)).fetchone()
    reserved=int(reserved_quantity if reserved_quantity is not None else (row["reserved_quantity"] if row else 0))
    if reserved>quantity: raise ValueError("Inventory quantity cannot be below the reserved quantity")
    if row:
        db.execute("UPDATE inventory SET quantity=?,reserved_quantity=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",(quantity,reserved,row["id"]))
    else:
        db.execute("INSERT INTO inventory(id,business_id,product_id,quantity,reserved_quantity) VALUES(?,?,?,?,?)",(_id("inv"),business_id,product_id,quantity,reserved))


def get_inventory(business_id=DEFAULT_BUSINESS_ID,product_id=None,variant_id=None):
    sql="SELECT * FROM inventory WHERE business_id=?"; args=[business_id]
    if product_id: sql+=" AND product_id=?"; args.append(product_id)
    if variant_id: sql+=" AND variant_id=?"; args.append(variant_id)
    with connect() as db:
        rows=db.execute(sql,args).fetchall()
        result=[row_dict(r) for r in rows]
        for item in result: item["available_quantity"]=item["quantity"]-item["reserved_quantity"]
        return result


def update_inventory(product_id=None,quantity=0,business_id=DEFAULT_BUSINESS_ID,variant_id=None,reserved_quantity=None):
    with connect() as db:
        if product_id and not db.execute("SELECT 1 FROM products WHERE id=? AND business_id=?",(product_id,business_id)).fetchone(): raise ValueError("Product not found for this business")
        if variant_id and not db.execute("SELECT 1 FROM product_variants WHERE id=? AND business_id=?",(variant_id,business_id)).fetchone(): raise ValueError("Variant not found for this business")
        if bool(product_id)==bool(variant_id): raise ValueError("Provide exactly one of product_id or variant_id")
        if product_id: _set_inventory_tx(db,business_id,product_id,int(quantity),reserved_quantity)
        else:
            row=db.execute("SELECT id,reserved_quantity FROM inventory WHERE business_id=? AND variant_id=?",(business_id,variant_id)).fetchone()
            reserved=int(reserved_quantity if reserved_quantity is not None else (row["reserved_quantity"] if row else 0))
            if int(quantity)<reserved: raise ValueError("Inventory quantity cannot be below the reserved quantity")
            if row: db.execute("UPDATE inventory SET quantity=?,reserved_quantity=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",(int(quantity),reserved,row["id"]))
            else: db.execute("INSERT INTO inventory(id,business_id,variant_id,quantity,reserved_quantity) VALUES(?,?,?,?,?)",(_id("inv"),business_id,variant_id,int(quantity),reserved))
    return get_inventory(business_id,product_id,variant_id)


def reserve_inventory(product_id,quantity,business_id=DEFAULT_BUSINESS_ID,variant_id=None):
    quantity=int(quantity)
    if quantity<=0: raise ValueError("Reservation quantity must be positive")
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        key="variant_id" if variant_id else "product_id"; value=variant_id or product_id
        row=db.execute(f"SELECT * FROM inventory WHERE business_id=? AND {key}=?",(business_id,value)).fetchone()
        if not row: raise ValueError("Inventory record not found")
        available=row["quantity"]-row["reserved_quantity"]
        if available<quantity: raise ValueError(f"Insufficient inventory: requested {quantity}, available {available}")
        db.execute("UPDATE inventory SET reserved_quantity=reserved_quantity+?,updated_at=CURRENT_TIMESTAMP WHERE id=?",(quantity,row["id"]))
    return get_inventory(business_id,product_id,variant_id)


def release_inventory(product_id,quantity,business_id=DEFAULT_BUSINESS_ID,variant_id=None):
    quantity=int(quantity)
    if quantity<=0: raise ValueError("Release quantity must be positive")
    with connect() as db:
        key="variant_id" if variant_id else "product_id"; value=variant_id or product_id
        row=db.execute(f"SELECT * FROM inventory WHERE business_id=? AND {key}=?",(business_id,value)).fetchone()
        if not row: raise ValueError("Inventory record not found")
        if row["reserved_quantity"]<quantity: raise ValueError("Cannot release more inventory than is reserved")
        db.execute("UPDATE inventory SET reserved_quantity=reserved_quantity-?,updated_at=CURRENT_TIMESTAMP WHERE id=?",(quantity,row["id"]))
    return get_inventory(business_id,product_id,variant_id)


def get_or_create_customer(customer_id=None,business_id=DEFAULT_BUSINESS_ID,**fields):
    customer_id=customer_id or _id("cus")
    with connect() as db:
        actual=_customer_id(db,customer_id,business_id)
        db.execute("INSERT OR IGNORE INTO customers(id,business_id,name,phone,email,address,city,country,preferred_language) VALUES(?,?,?,?,?,?,?,?,?)",
            (actual,business_id,fields.get("name"),fields.get("phone"),fields.get("email"),fields.get("address"),fields.get("city"),fields.get("country"),fields.get("preferred_language")))
        return row_dict(db.execute("SELECT * FROM customers WHERE id=? AND business_id=?",(actual,business_id)).fetchone())


def get_customer(customer_id,business_id=DEFAULT_BUSINESS_ID):
    with connect() as db:
        actual=_customer_id(db,customer_id,business_id)
        return row_dict(db.execute("SELECT * FROM customers WHERE id=? AND business_id=?",(actual,business_id)).fetchone())


def update_customer(customer_id,business_id=DEFAULT_BUSINESS_ID,**fields):
    customer=get_or_create_customer(customer_id,business_id)
    allowed={k:v for k,v in fields.items() if k in {"name","phone","email","address","city","country","preferred_language"} and v is not None}
    if allowed:
        with connect() as db:
            assignments=",".join(f"{key}=?" for key in allowed)+",updated_at=CURRENT_TIMESTAMP"
            db.execute(f"UPDATE customers SET {assignments} WHERE id=? AND business_id=?",(*allowed.values(),customer["id"],business_id))
    return get_customer(customer["id"],business_id)


def _resolve_customer_tx(db,customer_id,business_id,create=False,fields=None):
    actual=_customer_id(db,customer_id,business_id)
    row=db.execute("SELECT * FROM customers WHERE id=? AND business_id=?",(actual,business_id)).fetchone()
    if not row and create:
        fields=fields or {}
        db.execute("INSERT INTO customers(id,business_id,name,phone,email,address,city,country) VALUES(?,?,?,?,?,?,?,?)",
            (actual,business_id,fields.get("name"),fields.get("phone"),fields.get("email"),fields.get("address"),fields.get("city"),fields.get("country")))
        row=db.execute("SELECT * FROM customers WHERE id=? AND business_id=?",(actual,business_id)).fetchone()
    if not row: raise ValueError("Customer not found for this business")
    return row


def get_or_create_cart(customer_id,business_id=DEFAULT_BUSINESS_ID):
    customer=get_or_create_customer(customer_id,business_id)
    with connect() as db:
        row=db.execute("SELECT * FROM carts WHERE business_id=? AND customer_id=? AND status='active' ORDER BY created_at DESC LIMIT 1",(business_id,customer["id"])).fetchone()
        if row: return row_dict(row)
        cart_id=_id("cart")
        db.execute("INSERT INTO carts(id,business_id,customer_id) VALUES(?,?,?)",(cart_id,business_id,customer["id"]))
        return row_dict(db.execute("SELECT * FROM carts WHERE id=?",(cart_id,)).fetchone())


def add_to_cart(cart_id,product_id,quantity=1,variant_id=None,business_id=DEFAULT_BUSINESS_ID,unit_price=None):
    quantity=int(quantity)
    if quantity<=0: raise ValueError("Quantity must be positive")
    with connect() as db:
        cart=db.execute("SELECT id FROM carts WHERE id=? AND business_id=? AND status='active'",(cart_id,business_id)).fetchone()
        product=db.execute("SELECT * FROM products WHERE id=? AND business_id=? AND active=1",(product_id,business_id)).fetchone()
        if not cart or not product: raise ValueError("Active cart or product not found for this business")
        price=product["price"]
        if variant_id:
            variant=db.execute("SELECT * FROM product_variants WHERE id=? AND product_id=? AND business_id=?",(variant_id,product_id,business_id)).fetchone()
            if not variant: raise ValueError("Variant does not belong to this product")
            if variant["price"] is not None: price=variant["price"]
        existing=db.execute("SELECT id,quantity FROM cart_items WHERE cart_id=? AND product_id=? AND variant_id IS ?",(cart_id,product_id,variant_id)).fetchone()
        if existing:
            db.execute("UPDATE cart_items SET quantity=quantity+?,unit_price=? WHERE id=?",(quantity,float(price),existing["id"]))
        else:
            db.execute("INSERT INTO cart_items(cart_id,product_id,variant_id,quantity,unit_price) VALUES(?,?,?,?,?)",(cart_id,product_id,variant_id,quantity,float(price)))
        db.execute("UPDATE carts SET updated_at=CURRENT_TIMESTAMP WHERE id=?",(cart_id,))
    return get_cart(cart_id,business_id)


def remove_from_cart(cart_id,item_id,business_id=DEFAULT_BUSINESS_ID):
    with connect() as db:
        if not db.execute("SELECT 1 FROM carts WHERE id=? AND business_id=?",(cart_id,business_id)).fetchone(): return False
        return db.execute("DELETE FROM cart_items WHERE cart_id=? AND id=?",(cart_id,item_id)).rowcount>0


def update_cart_item(cart_id,item_id,quantity,business_id=DEFAULT_BUSINESS_ID):
    quantity=int(quantity)
    if quantity<=0: return remove_from_cart(cart_id,item_id,business_id)
    with connect() as db:
        if not db.execute("SELECT 1 FROM carts WHERE id=? AND business_id=?",(cart_id,business_id)).fetchone(): return None
        db.execute("UPDATE cart_items SET quantity=? WHERE cart_id=? AND id=?",(quantity,cart_id,item_id))
    return get_cart(cart_id,business_id)


def get_cart(cart_id,business_id=DEFAULT_BUSINESS_ID):
    with connect() as db:
        cart=row_dict(db.execute("SELECT * FROM carts WHERE id=? AND business_id=?",(cart_id,business_id)).fetchone())
        if cart:
            cart["items"]=[row_dict(r) for r in db.execute("SELECT ci.*,p.name AS current_product_name FROM cart_items ci JOIN products p ON p.id=ci.product_id WHERE ci.cart_id=?",(cart_id,)).fetchall()]
            cart["subtotal"]=sum(i["quantity"]*i["unit_price"] for i in cart["items"])
        return cart


def clear_cart(cart_id,business_id=DEFAULT_BUSINESS_ID):
    with connect() as db:
        cart=db.execute("SELECT id FROM carts WHERE id=? AND business_id=?",(cart_id,business_id)).fetchone()
        if not cart: return False
        db.execute("DELETE FROM cart_items WHERE cart_id=?",(cart_id,))
        db.execute("UPDATE carts SET updated_at=CURRENT_TIMESTAMP WHERE id=?",(cart_id,))
        return True


def _product_for_order(db,business_id,item):
    product=db.execute("SELECT * FROM products WHERE id=? AND business_id=? AND active=1",(item["product_id"],business_id)).fetchone()
    if not product: raise ValueError(f"Product {item.get('product_id')} not found for this business")
    variant_id=item.get("variant_id")
    variant=None
    if variant_id:
        variant=db.execute("SELECT * FROM product_variants WHERE id=? AND product_id=? AND business_id=?",(variant_id,product["id"],business_id)).fetchone()
        if not variant: raise ValueError("Product variant not found")
    price=float(variant["price"] if variant and variant["price"] is not None else product["price"])
    return product,variant,price


def create_order(customer_id,items,name=None,phone=None,address=None,*,business_id=DEFAULT_BUSINESS_ID,shipping_cost=0,discount=0,currency=None,payment_method=None,cart_id=None,shipping_city=None,notes=None,shipment=None):
    """Create an order and reserve all required stock atomically."""
    if not items: raise ValueError("At least one order item is required")
    if name is not None and not name.strip(): raise ValueError("Customer name cannot be empty")
    if phone is not None and not phone.strip(): raise ValueError("Customer phone cannot be empty")
    shipping_cost=float(shipping_cost); discount=float(discount)
    if shipping_cost<0 or discount<0: raise ValueError("Shipping and discount must be non-negative")
    order_id=_id("ord")
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        customer=_resolve_customer_tx(db,customer_id,business_id,create=True,fields={"name":name,"phone":phone,"address":address,"city":shipping_city})
        validated=[]; subtotal=0.0
        for item in items:
            quantity=int(item["quantity"])
            if quantity<=0: raise ValueError("Quantity must be positive")
            product,variant,price=_product_for_order(db,business_id,item)
            inventory_key="variant_id" if variant else "product_id"; inventory_value=variant["id"] if variant else product["id"]
            inv=db.execute(f"SELECT * FROM inventory WHERE business_id=? AND {inventory_key}=?",(business_id,inventory_value)).fetchone()
            if not inv: raise ValueError(f"Inventory is not configured for {product['name']}")
            available=inv["quantity"]-inv["reserved_quantity"]
            if available<quantity: raise ValueError(f"Insufficient inventory for {product['name']}: requested {quantity}, available {available}")
            line=price*quantity; subtotal+=line
            validated.append((product,variant,quantity,price,line,inv))
        if discount>subtotal+shipping_cost: raise ValueError("Discount cannot exceed the order subtotal and shipping")
        total=round(subtotal+shipping_cost-discount,2)
        biz=db.execute("SELECT currency FROM businesses WHERE id=?",(business_id,)).fetchone()
        if not biz: raise ValueError("Business not found")
        db.execute("UPDATE customers SET name=COALESCE(?,name),phone=COALESCE(?,phone),address=COALESCE(?,address),city=COALESCE(?,city),updated_at=CURRENT_TIMESTAMP WHERE id=? AND business_id=?",
            (name,phone,address,shipping_city,customer["id"],business_id))
        db.execute("""INSERT INTO orders(id,business_id,customer_id,subtotal,shipping_cost,discount,total,currency,shipping_name,shipping_phone,shipping_address,shipping_city,notes)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",(order_id,business_id,customer["id"],subtotal,shipping_cost,discount,total,currency or biz["currency"],name or customer["name"],phone or customer["phone"],address or customer["address"],shipping_city or customer["city"],notes))
        for product,variant,quantity,price,line,inv in validated:
            db.execute("INSERT INTO order_items(order_id,product_id,variant_id,product_name,sku,quantity,unit_price,subtotal) VALUES(?,?,?,?,?,?,?,?)",
                (order_id,product["id"],variant["id"] if variant else None,product["name"],variant["sku"] if variant else product["sku"],quantity,price,line))
            db.execute("UPDATE inventory SET reserved_quantity=reserved_quantity+?,updated_at=CURRENT_TIMESTAMP WHERE id=?",(quantity,inv["id"]))
        if payment_method:
            _create_payment_tx(db,business_id,order_id,payment_method,total)
            db.execute("UPDATE orders SET payment_status='pending' WHERE id=?",(order_id,))
        if shipment:
            _create_shipment_tx(db,business_id,order_id,shipment.get("carrier"),shipment.get("tracking_number"),shipment.get("status","pending"))
        if cart_id:
            cart=db.execute("SELECT id,status FROM carts WHERE id=? AND business_id=? AND customer_id=?",(cart_id,business_id,customer["id"])).fetchone()
            if not cart or cart["status"]!="active": raise ValueError("Active cart not found for this customer and business")
            ordered={}
            for product,variant,quantity,price,line,inv in validated:
                key=(product["id"],variant["id"] if variant else None)
                ordered[key]=ordered.get(key,0)+quantity
            cart_lines=db.execute("SELECT product_id,variant_id,quantity FROM cart_items WHERE cart_id=?",(cart_id,)).fetchall()
            cart_contents={(line["product_id"],line["variant_id"]):line["quantity"] for line in cart_lines}
            if ordered!=cart_contents: raise ValueError("Order items must match the active cart contents")
            db.execute("UPDATE carts SET status='converted',updated_at=CURRENT_TIMESTAMP WHERE id=?",(cart_id,))
    result=get_order(order_id,business_id=business_id)
    result["order_id"]=result["id"]
    result["success"]=True
    return result


def get_order(order_id,customer_id=None,business_id=DEFAULT_BUSINESS_ID):
    with connect() as db:
        sql="SELECT * FROM orders WHERE id=? AND business_id=?"; args=[order_id,business_id]
        if customer_id is not None:
            customer=_customer_id(db,customer_id,business_id); sql+=" AND customer_id=?"; args.append(customer)
        order=row_dict(db.execute(sql,args).fetchone())
        if order:
            order["items"]=[row_dict(r) for r in db.execute("SELECT * FROM order_items WHERE order_id=? ORDER BY id",(order_id,)).fetchall()]
            for item in order["items"]: item["name"]=item["product_name"]
            order["order_id"]=order["id"]
            order["payments"]=[row_dict(r) for r in db.execute("SELECT * FROM payments WHERE order_id=? AND business_id=?",(order_id,business_id)).fetchall()]
            order["shipments"]=[row_dict(r) for r in db.execute("SELECT * FROM shipments WHERE order_id=? AND business_id=?",(order_id,business_id)).fetchall()]
        return order


def list_orders(business_id=DEFAULT_BUSINESS_ID,customer_id=None,status=None):
    sql="SELECT * FROM orders WHERE business_id=?"; args=[business_id]
    if customer_id is not None: sql+=" AND customer_id=?"; args.append(_customer_id_for_scope(customer_id,business_id))
    if status: sql+=" AND status=?"; args.append(status)
    sql+=" ORDER BY created_at DESC"
    with connect() as db: return [row_dict(r) for r in db.execute(sql,args).fetchall()]


def _customer_id_for_scope(customer_id,business_id):
    with connect() as db: return _customer_id(db,customer_id,business_id)


def update_order_status(order_id,status,business_id=DEFAULT_BUSINESS_ID,payment_status=None,fulfillment_status=None):
    allowed={"pending","confirmed","processing","shipped","delivered","cancelled","refunded"}
    if status not in allowed: raise ValueError("Invalid order status")
    if status=="cancelled": return cancel_order(order_id,business_id)
    if status=="refunded" and payment_status is None: payment_status="refunded"
    if fulfillment_status is None:
        fulfillment_status={"shipped":"shipped","delivered":"delivered"}.get(status)
    with connect() as db:
        order=db.execute("SELECT status FROM orders WHERE id=? AND business_id=?",(order_id,business_id)).fetchone()
        if not order: return None
        current=order["status"]
        if current in {"cancelled","delivered","refunded"} and status!=current:
            raise ValueError(f"Cannot change an order in {current} status")
        if current=="shipped" and status not in {"shipped","delivered","refunded"}:
            raise ValueError("A shipped order cannot return to an earlier status")
        if status in {"shipped","delivered"} and order["status"] not in {"shipped","delivered"}:
            _fulfill_order_inventory_tx(db,order_id,business_id)
        db.execute("UPDATE orders SET status=?,payment_status=COALESCE(?,payment_status),fulfillment_status=COALESCE(?,fulfillment_status),updated_at=CURRENT_TIMESTAMP WHERE id=? AND business_id=?",
            (status,payment_status,fulfillment_status,order_id,business_id))
    return get_order(order_id,business_id=business_id)


def _fulfill_order_inventory_tx(db,order_id,business_id):
    items=db.execute("SELECT product_id,variant_id,quantity FROM order_items WHERE order_id=?",(order_id,)).fetchall()
    for item in items:
        key="variant_id" if item["variant_id"] else "product_id"; value=item["variant_id"] or item["product_id"]
        inventory=db.execute(f"SELECT id,quantity,reserved_quantity FROM inventory WHERE business_id=? AND {key}=?",(business_id,value)).fetchone()
        if not inventory or inventory["reserved_quantity"]<item["quantity"] or inventory["quantity"]<item["quantity"]:
            raise ValueError("Reserved inventory is insufficient to fulfill this order")
        db.execute("UPDATE inventory SET quantity=quantity-?,reserved_quantity=reserved_quantity-?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (item["quantity"],item["quantity"],inventory["id"]))
        if item["variant_id"]:
            db.execute("UPDATE product_variants SET stock=stock-?,updated_at=CURRENT_TIMESTAMP WHERE id=?",(item["quantity"],item["variant_id"]))


def cancel_order(order_id,business_id=DEFAULT_BUSINESS_ID):
    with connect() as db:
        order=db.execute("SELECT status FROM orders WHERE id=? AND business_id=?",(order_id,business_id)).fetchone()
        if not order: return None
        if order["status"] in {"cancelled","shipped","delivered","refunded"}: raise ValueError(f"Cannot cancel an order in {order['status']} status")
        rows=db.execute("SELECT product_id,variant_id,quantity FROM order_items WHERE order_id=?",(order_id,)).fetchall()
        for item in rows:
            key="variant_id" if item["variant_id"] else "product_id"; value=item["variant_id"] or item["product_id"]
            db.execute(f"UPDATE inventory SET reserved_quantity=MAX(0,reserved_quantity-?),updated_at=CURRENT_TIMESTAMP WHERE business_id=? AND {key}=?",(item["quantity"],business_id,value))
        db.execute("UPDATE orders SET status='cancelled',fulfillment_status='cancelled',updated_at=CURRENT_TIMESTAMP WHERE id=? AND business_id=?",(order_id,business_id))
    return get_order(order_id,business_id=business_id)


def _create_payment_tx(db,business_id,order_id,method,amount,transaction_id=None,status="pending"):
    payment_id=_id("pay")
    db.execute("INSERT INTO payments(id,business_id,order_id,method,status,amount,transaction_id) VALUES(?,?,?,?,?,?,?)",
        (payment_id,business_id,order_id,method,status,float(amount),transaction_id))
    return payment_id


def create_payment(business_id,order_id,method,amount,transaction_id=None,status="pending"):
    with connect() as db:
        if not db.execute("SELECT 1 FROM orders WHERE id=? AND business_id=?",(order_id,business_id)).fetchone(): raise ValueError("Order not found for this business")
        payment_id=_create_payment_tx(db,business_id,order_id,method,amount,transaction_id,status)
    return get_payment(payment_id,business_id)


def get_payment(payment_id,business_id=DEFAULT_BUSINESS_ID):
    with connect() as db: return row_dict(db.execute("SELECT * FROM payments WHERE id=? AND business_id=?",(payment_id,business_id)).fetchone())


def update_payment_status(payment_id,status,business_id=DEFAULT_BUSINESS_ID):
    if status not in {"pending","paid","failed","refunded","partially_refunded","cancelled"}:
        raise ValueError("Invalid payment status")
    with connect() as db:
        row=db.execute("SELECT order_id FROM payments WHERE id=? AND business_id=?",(payment_id,business_id)).fetchone()
        if not row: return None
        db.execute("UPDATE payments SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND business_id=?",(status,payment_id,business_id))
        paid_amount=db.execute("SELECT COALESCE(SUM(amount),0) FROM payments WHERE order_id=? AND business_id=? AND status='paid'",(row["order_id"],business_id)).fetchone()[0]
        order_total=db.execute("SELECT total FROM orders WHERE id=? AND business_id=?",(row["order_id"],business_id)).fetchone()["total"]
        payment_state="paid" if paid_amount>=order_total else "partial" if paid_amount>0 else "pending"
        db.execute("UPDATE orders SET payment_status=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND business_id=?",(payment_state,row["order_id"],business_id))
    return get_payment(payment_id,business_id)


def _create_shipment_tx(db,business_id,order_id,carrier=None,tracking_number=None,status="pending"):
    shipment_id=_id("ship")
    db.execute("INSERT INTO shipments(id,business_id,order_id,carrier,tracking_number,status) VALUES(?,?,?,?,?,?)",
        (shipment_id,business_id,order_id,carrier,tracking_number,status))
    return shipment_id


def create_shipment(business_id,order_id,carrier=None,tracking_number=None,status="pending"):
    with connect() as db:
        if not db.execute("SELECT 1 FROM orders WHERE id=? AND business_id=?",(order_id,business_id)).fetchone(): raise ValueError("Order not found for this business")
        shipment_id=_create_shipment_tx(db,business_id,order_id,carrier,tracking_number,status)
    return get_shipment(shipment_id,business_id)


def get_shipment(shipment_id,business_id=DEFAULT_BUSINESS_ID):
    with connect() as db: return row_dict(db.execute("SELECT * FROM shipments WHERE id=? AND business_id=?",(shipment_id,business_id)).fetchone())


def update_shipment_status(shipment_id,status,business_id=DEFAULT_BUSINESS_ID,tracking_number=None):
    with connect() as db:
        row=db.execute("SELECT s.order_id,o.status AS order_status FROM shipments s JOIN orders o ON o.id=s.order_id WHERE s.id=? AND s.business_id=? AND o.business_id=?",(shipment_id,business_id,business_id)).fetchone()
        if not row: return None
        if row["order_status"] in {"delivered","cancelled","refunded"} and status not in {"delivered","cancelled","refunded"}:
            raise ValueError(f"Cannot move a {row['order_status']} order back to an earlier shipment status")
        if status in {"shipped","in_transit","delivered"} and row["order_status"] not in {"shipped","delivered"}:
            _fulfill_order_inventory_tx(db,row["order_id"],business_id)
        shipped="CURRENT_TIMESTAMP" if status in {"shipped","in_transit"} else "shipped_at"
        delivered="CURRENT_TIMESTAMP" if status=="delivered" else "delivered_at"
        db.execute(f"UPDATE shipments SET status=?,tracking_number=COALESCE(?,tracking_number),shipped_at={shipped},delivered_at={delivered},updated_at=CURRENT_TIMESTAMP WHERE id=? AND business_id=?",
            (status,tracking_number,shipment_id,business_id))
        if status in {"shipped","in_transit"}: db.execute("UPDATE orders SET status='shipped',fulfillment_status='shipped' WHERE id=? AND business_id=?",(row["order_id"],business_id))
        elif status=="delivered": db.execute("UPDATE orders SET status='delivered',fulfillment_status='delivered' WHERE id=? AND business_id=?",(row["order_id"],business_id))
    return get_shipment(shipment_id,business_id)


def _conversation_row(db,conversation_id,customer_id=None,business_id=None):
    sql="SELECT * FROM conversations WHERE id=?"; args=[conversation_id]
    if business_id is not None: sql+=" AND business_id=?"; args.append(business_id)
    if customer_id is not None:
        if business_id is None:
            # Conversation IDs are globally unique; verify the owning customer as well.
            sql+=" AND customer_id=?"; args.append(customer_id)
        else: sql+=" AND customer_id=?"; args.append(_customer_id(db,customer_id,business_id))
    return db.execute(sql,args).fetchone()


def _ensure_conversation(db,conversation_id,customer_id,business_id=DEFAULT_BUSINESS_ID,channel=None,channel_user_id=None):
    customer=_resolve_customer_tx(db,customer_id,business_id,create=True)
    row=db.execute("SELECT * FROM conversations WHERE id=?",(conversation_id,)).fetchone()
    if row:
        if row["business_id"]!=business_id or row["customer_id"]!=customer["id"]: raise ValueError("Conversation does not belong to this customer and business")
        return row
    inferred_channel=channel or ("telegram" if str(customer_id).startswith("telegram_") else "web")
    inferred_user=channel_user_id or str(customer_id).removeprefix("telegram_")
    db.execute("INSERT INTO conversations(id,business_id,customer_id,channel,channel_user_id) VALUES(?,?,?,?,?)",
        (conversation_id,business_id,customer["id"],inferred_channel,inferred_user))
    return db.execute("SELECT * FROM conversations WHERE id=?",(conversation_id,)).fetchone()


def save_message(conversation_id,customer_id,role,content,business_id=DEFAULT_BUSINESS_ID,channel=None,channel_user_id=None):
    if role not in {"user","assistant","system","tool"}: raise ValueError("Invalid message role")
    with connect() as db:
        _ensure_conversation(db,conversation_id,customer_id,business_id,channel,channel_user_id)
        db.execute("INSERT INTO messages(conversation_id,role,content) VALUES(?,?,?)",(conversation_id,role,str(content)))


def get_messages(conversation_id,limit=16,business_id=DEFAULT_BUSINESS_ID,customer_id=None):
    with connect() as db:
        if not _conversation_row(db,conversation_id,customer_id,business_id): return []
        return [row_dict(r) for r in db.execute("SELECT role,content FROM messages WHERE conversation_id=? ORDER BY id DESC LIMIT ?",(conversation_id,int(limit))).fetchall()[::-1]]


def get_conversation_language(conversation_id,customer_id,business_id=DEFAULT_BUSINESS_ID):
    with connect() as db:
        row=_conversation_row(db,conversation_id,customer_id,business_id)
        return row["language"] if row else None


def set_conversation_language(conversation_id,customer_id,language,business_id=DEFAULT_BUSINESS_ID):
    with connect() as db:
        conversation=_ensure_conversation(db,conversation_id,customer_id,business_id)
        db.execute("UPDATE conversations SET language=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND business_id=?",(language,conversation_id,business_id))
        db.execute("UPDATE customers SET preferred_language=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND business_id=?",(language,conversation["customer_id"],business_id))


def get_customer_language(customer_id,business_id=DEFAULT_BUSINESS_ID):
    with connect() as db:
        actual=_customer_id(db,customer_id,business_id)
        row=db.execute("SELECT preferred_language FROM customers WHERE id=? AND business_id=?",(actual,business_id)).fetchone()
        return row["preferred_language"] if row else None


def get_conversation_state(conversation_id,customer_id,business_id=None):
    with connect() as db:
        row=_conversation_row(db,conversation_id,customer_id,business_id)
        return json.loads(row["state"] or "{}") if row else {}


def set_conversation_state(conversation_id,customer_id,state,business_id=None):
    with connect() as db:
        if business_id is None:
            current=_conversation_row(db,conversation_id,customer_id)
            business_id=current["business_id"] if current else DEFAULT_BUSINESS_ID
        _ensure_conversation(db,conversation_id,customer_id,business_id)
        db.execute("UPDATE conversations SET state=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND business_id=?",(json.dumps(state,ensure_ascii=False),conversation_id,business_id))


def set_conversation_status(conversation_id,customer_id,status,business_id=None):
    with connect() as db:
        if business_id is None:
            current=_conversation_row(db,conversation_id,customer_id)
            business_id=current["business_id"] if current else DEFAULT_BUSINESS_ID
        _ensure_conversation(db,conversation_id,customer_id,business_id)
        db.execute("UPDATE conversations SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND business_id=?",(status,conversation_id,business_id))


def save_lead_record(customer_id,conversation_id,profile,lead_score,lead_status,business_id=None):
    lead_id=_id("lead")
    with connect() as db:
        if business_id is None:
            current=_conversation_row(db,conversation_id,customer_id) if conversation_id else None
            business_id=current["business_id"] if current else DEFAULT_BUSINESS_ID
        customer=_resolve_customer_tx(db,customer_id,business_id,create=True)
        conversation=_conversation_row(db,conversation_id,customer["id"],business_id) if conversation_id else None
        if conversation_id and not conversation: raise ValueError("Conversation not found for this customer and business")
        if conversation:
            found=db.execute("SELECT id FROM leads WHERE conversation_id=? AND business_id=?",(conversation_id,business_id)).fetchone()
            if found: lead_id=found["id"]
        db.execute("""INSERT INTO leads(id,business_id,customer_id,conversation_id,profile,lead_score,lead_status,consented)
            VALUES(?,?,?,?,?,?,?,1) ON CONFLICT(id) DO UPDATE SET profile=excluded.profile,lead_score=excluded.lead_score,
            lead_status=excluded.lead_status,consented=1,updated_at=CURRENT_TIMESTAMP""",
            (lead_id,business_id,customer["id"],conversation_id,json.dumps(profile,ensure_ascii=False),int(lead_score),lead_status))
    return lead_id


def list_lead_records(business_id=DEFAULT_BUSINESS_ID):
    with connect() as db: rows=db.execute("SELECT * FROM leads WHERE business_id=? ORDER BY updated_at DESC",(business_id,)).fetchall()
    result=[]
    for row in rows:
        item=row_dict(row); item["profile"]=json.loads(item["profile"] or "{}"); item["consented"]=bool(item["consented"]); result.append(item)
    return result


def add_subscription(sub,business_id=None):
    business_id=business_id or sub.get("business_id",DEFAULT_BUSINESS_ID)
    customer=get_or_create_customer(sub.get("customer_id") or sub["channel_user_id"],business_id)
    subscription_id=sub.get("id") or _id("sub")
    with connect() as db:
        db.execute("""INSERT INTO subscriptions(id,business_id,customer_id,channel,channel_user_id,subscription_type,active)
            VALUES(?,?,?,?,?,?,?) ON CONFLICT(business_id,channel,channel_user_id,subscription_type)
            DO UPDATE SET active=excluded.active""",(subscription_id,business_id,customer["id"],sub["channel"],sub["channel_user_id"],sub.get("subscription_type","new_product"),int(sub.get("active",1))))
        row=db.execute("SELECT id FROM subscriptions WHERE business_id=? AND channel=? AND channel_user_id=? AND subscription_type=?",
            (business_id,sub["channel"],sub["channel_user_id"],sub.get("subscription_type","new_product"))).fetchone()
        return row["id"]


def subscribe_new_products(customer_id,channel,channel_user_id,business_id=DEFAULT_BUSINESS_ID):
    return add_subscription({"customer_id":customer_id,"channel":channel,"channel_user_id":channel_user_id,"subscription_type":"new_product","active":1},business_id)


def unsubscribe_from_new_products(channel_user_id,business_id=DEFAULT_BUSINESS_ID,channel="telegram"):
    with connect() as db:
        return db.execute("UPDATE subscriptions SET active=0 WHERE business_id=? AND channel=? AND channel_user_id=? AND subscription_type='new_product' AND active=1",
            (business_id,channel,channel_user_id)).rowcount>0


def active_subscriptions(business_id=DEFAULT_BUSINESS_ID):
    with connect() as db:
        return [row_dict(r) for r in db.execute("SELECT * FROM subscriptions WHERE business_id=? AND active=1 AND subscription_type='new_product'",(business_id,)).fetchall()]


def seed_products(business_id=DEFAULT_BUSINESS_ID):
    if not get_business(business_id):
        if business_id==DEFAULT_BUSINESS_ID: _insert_business_for_seed()
        else: raise ValueError("Business not found")
    products=[
        ("lipstick-red","Red Lipstick","BEA-LIP-001","Makeup","Belle","Long-lasting matte red lipstick",1200,42),
        ("hoodie-black","Black Hoodie","APP-HOD-014","Clothing","Northstar","Warm cotton pullover hoodie",4800,18),
        ("air-max","Nike Air Max","SHO-NIK-042","Shoes","Nike","Cushioned everyday running shoes",28000,7),
        ("earbuds-wireless","Wireless Earbuds","ELC-AUD-008","Electronics","SoundWave","Bluetooth earbuds with charging case",6500,31),
        ("backpack-leather","Leather Backpack","ACC-BAG-022","Accessories","Atelier","Full-grain leather everyday backpack",14500,9),
        ("running-shoes","Running Shoes","SHO-RUN-035","Shoes","Stride","Lightweight breathable running shoes",9200,24),
    ]
    with connect() as db:
        categories={}
        for name in ("Makeup","Clothing","Shoes","Electronics","Accessories"):
            cid="cat_"+uuid.uuid5(uuid.NAMESPACE_URL,f"{business_id}:{name.lower()}").hex[:16]
            db.execute("INSERT OR IGNORE INTO categories(id,business_id,name) VALUES(?,?,?)",(cid,business_id,name)); categories[name]=cid
        for pid,name,sku,category,brand,description,price,stock in products:
            if business_id!=DEFAULT_BUSINESS_ID:
                pid="prod_"+uuid.uuid5(uuid.NAMESPACE_URL,f"{business_id}:seed:{pid}").hex[:16]
            db.execute("""INSERT OR IGNORE INTO products(id,business_id,category_id,name,sku,brand,description,price)
                VALUES(?,?,?,?,?,?,?,?)""",(pid,business_id,categories[category],name,sku,brand,description,price))
            if not db.execute("SELECT 1 FROM inventory WHERE business_id=? AND product_id=?",(business_id,pid)).fetchone():
                db.execute("INSERT INTO inventory(id,business_id,product_id,quantity) VALUES(?,?,?,?)",(_id("inv"),business_id,pid,stock))


def _insert_business_for_seed():
    with connect() as db: _insert_business(db,DEMO_BUSINESS)
