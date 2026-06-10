import asyncio
import os
import sys
from dotenv import load_dotenv

# Reconfigure stdout to use UTF-8
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')  # type: ignore
    except Exception:
        pass

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import database

load_dotenv()

async def main():
    print("Connecting to database...")
    try:
        await database.init_db()
        print("Database connected successfully!")
        
        print("\nChecking categories:")
        categories = await database.get_all_categories()
        print(f"Total categories: {len(categories)}")
        for cat in categories:
            icon = cat.get('icon', '')
            name = cat.get('name', '')
            slug = cat.get('slug', '')
            print(f" - {icon} {name} (slug: {slug})")

        print("\nChecking products:")
        products = await database.products_col.find({}).to_list(None)
        print(f"Total products: {len(products)}")
        for prod in products:
            name = prod.get('name', '')
            price = prod.get('price', 0)
            price_upi = prod.get('price_upi', 0.0)
            print(f" - Name: {name} (Price: {price} Stars / INR {price_upi})")

        print("\nChecking UPI pending payments:")
        pending = await database.upi_pending_col.find({}).to_list(None)
        print(f"Total pending UPI: {len(pending)}")
        for p in pending:
            print(f" - User: {p.get('user_id')}, Plan: {p.get('plan')}, Status: {p.get('status')}")

    except Exception as e:
        print(f"Database error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
