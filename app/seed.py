from app.database import initialize_database, seed_products

if __name__ == "__main__":
    initialize_database()
    seed_products()
    print("Oraviro SQLite database initialized and demo catalog seeded.")
