"""Insert 6 verified demo chefs (same people as the frontend mock data).
Usage: python -m scripts.seed_demo   (demo password for all: ChefPass123)"""
from sqlalchemy import select
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import ChefProfile, User, UserRole

DEMO = [
    ("Ravi Kumar", "Nellore", 12, ["South Indian", "Andhra"], 4.9, 212, 2500, True, "Authentic Andhra home-style cooking for family dinners and functions."),
    ("Ayesha Khan", "Hyderabad", 9, ["Mughlai", "Biryani"], 4.8, 340, 3500, True, "Dum biryani and Mughlai specialist for large gatherings."),
    ("Marco Rossi", "Bengaluru", 15, ["Italian", "Continental"], 4.7, 128, 5000, False, "Fine-dining Italian experiences in your own kitchen."),
    ("Lakshmi Devi", "Vijayawada", 20, ["Vegetarian", "South Indian"], 4.9, 175, 1800, True, "Pure vegetarian feasts for festivals, poojas and weddings."),
    ("Arjun Reddy", "Nellore", 7, ["BBQ", "Party Catering"], 4.6, 96, 3000, True, "Live grills and party menus that keep guests talking."),
    ("Meera Nair", "Bengaluru", 11, ["Kerala", "Seafood"], 4.8, 151, 3200, True, "Coastal Kerala flavours with fresh seafood and appams."),
]
with SessionLocal() as db:
    for i, (name, city, yrs, cuisines, rating, reviews, price, avail, bio) in enumerate(DEMO, 1):
        email = f"chef{i}@demo.com"
        if db.scalar(select(User).where(User.email == email)):
            continue
        db.add(User(email=email, full_name=name, hashed_password=hash_password("ChefPass123"), role=UserRole.chef,
                    chef_profile=ChefProfile(city=city, years_experience=yrs, cuisines=cuisines, rating_avg=rating,
                                             review_count=reviews, price_per_session=price, is_available=avail, bio=bio, is_verified=True)))
    db.commit()
    print("Demo chefs ready")
