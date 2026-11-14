"""Adds 14 more verified chefs with rich bios plus customer reviews, so retrieval has realistic data.
Safe to run twice. Usage: python -m scripts.seed_ai_demo   (chef password ChefPass123, customer CustPass123)"""
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import Booking, BookingStatus, ChefProfile, Review, User, UserRole

# name, city, years, cuisines, certifications, price, rating, bio, review comments
CHEFS = [
    ("Venkat Rao", "Guntur", 14, ["Andhra", "Telugu Meals"], ["FSSAI Certified"], 2200, 4.8, "Guntur-style spicy Andhra meals, gongura mutton and pulusu for family functions and festivals.", ["Gongura chicken was fiery and authentic.", "Perfect for our housewarming lunch."]),
    ("Sunitha Reddy", "Nellore", 10, ["Nellore", "Seafood"], [], 2600, 4.7, "Nellore chepala pulusu, prawn fry and coastal seafood feasts cooked fresh at your home.", ["The fish curry tasted like my grandmother's."]),
    ("Imran Sheikh", "Hyderabad", 16, ["Hyderabadi", "Biryani", "Mughlai"], ["Culinary Institute Diploma"], 4200, 4.9, "Hyderabadi dum biryani, haleem and kebabs for weddings, Eid and large parties of 50 or more guests.", ["Best dum biryani we have ever had.", "Handled 80 guests without any stress."]),
    ("Padma Iyer", "Chennai", 18, ["Tamil", "South Indian", "Vegetarian"], ["Temple Cuisine Training"], 2000, 4.9, "Traditional Tamil vegetarian sadya, pongal and temple-style prasadam for poojas and festivals.", ["Pooja lunch was pure and delicious."]),
    ("Chef Daniel D'Souza", "Bengaluru", 13, ["Continental", "Italian", "Desserts"], ["Le Cordon Bleu Short Course"], 5500, 4.7, "Fine-dining continental menus, handmade pasta and plated desserts for anniversaries and corporate dinners.", ["Elegant anniversary dinner, beautiful plating."]),
    ("Farah Siddiqui", "Hyderabad", 8, ["Mughlai", "North Indian"], [], 3300, 4.6, "Rich Mughlai curries, butter naan and North Indian thalis for family dinners.", []),
    ("Gopal Krishna", "Vijayawada", 22, ["Vegetarian", "Andhra", "Wedding Catering"], ["Master Caterer Award"], 3800, 4.8, "Pure vegetarian Andhra wedding catering, sweets and traditional banana-leaf meals for 100+ guests.", ["Our wedding feast was flawless."]),
    ("Anita Menon", "Kochi", 12, ["Kerala", "Seafood"], [], 3000, 4.8, "Kerala fish curry, appam with stew and coconut-based seafood dishes.", ["Karimeen pollichathu was outstanding."]),
    ("Rahul Verma", "Delhi", 9, ["Punjabi", "North Indian", "BBQ"], [], 3200, 4.5, "Punjabi dhaba-style food, tandoori platters and live BBQ counters for parties.", ["Tandoori platter disappeared in minutes."]),
    ("Shalini Gupta", "Bengaluru", 6, ["Healthy", "Vegan", "Vegetarian"], ["Nutrition Coach"], 2800, 4.6, "Healthy vegan and low-oil vegetarian meal plans, salads and millet dishes for weekly home meals.", ["Great weekly meal prep, light and tasty."]),
    ("Mohan Das", "Visakhapatnam", 15, ["Andhra", "Seafood", "Party Catering"], [], 3100, 4.6, "Vizag-style seafood, prawn biryani and cocktail party catering for birthdays and corporate gatherings.", ["Prawn biryani was the highlight of the party."]),
    ("Lakshmi Prasad", "Tirupati", 17, ["South Indian", "Vegetarian", "Temple Food"], [], 1900, 4.8, "Tirupati-style vegetarian meals, pulihora, sweet pongal and satvik food without onion or garlic.", ["Satvik food exactly as we asked."]),
    ("Zoya Ali", "Mumbai", 7, ["Desserts", "Bakery", "Continental"], ["Pastry Diploma"], 3600, 4.7, "Custom cakes, brownies and dessert tables for birthday parties and baby showers.", ["The dessert table made the party."]),
    ("Chef Pradeep", "Nellore", 11, ["BBQ", "Andhra", "Party Catering"], [], 3400, 4.5, "Live tandoor and BBQ with Andhra-style starters for birthday and corporate parties.", []),
]

with SessionLocal() as db:
    cust = db.scalar(select(User).where(User.email == "demo.customer@demo.com"))
    if not cust:
        cust = User(email="demo.customer@demo.com", full_name="Demo Customer", hashed_password=hash_password("CustPass123"), role=UserRole.customer)
        db.add(cust); db.flush()
    added = 0
    for i, (name, city, yrs, cuisines, certs, price, rating, bio, comments) in enumerate(CHEFS, 101):
        email = f"chef{i}@demo.com"
        if db.scalar(select(User).where(User.email == email)):
            continue
        profile = ChefProfile(city=city, years_experience=yrs, cuisines=cuisines, certifications=certs, rating_avg=rating,
                              review_count=len(comments) + 20, price_per_session=price, bio=bio, is_verified=True)
        db.add(User(email=email, full_name=name, hashed_password=hash_password("ChefPass123"), role=UserRole.chef, chef_profile=profile))
        db.flush()
        for k, text in enumerate(comments):
            when = datetime.now(timezone.utc) - timedelta(days=30 + k * 7)
            b = Booking(customer_id=cust.id, chef_id=profile.id, service_type="Family dinner", event_date=when, event_day=when.date(),
                        guests=6, location="Demo address", status=BookingStatus.completed)
            db.add(b); db.flush()
            db.add(Review(booking_id=b.id, customer_id=cust.id, chef_id=profile.id, rating=5, comment=text))
        added += 1
    db.commit()
    print(f"Added {added} demo chefs (skipped existing)")
