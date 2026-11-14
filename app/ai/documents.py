"""Turn chef rows into searchable text documents (the "knowledge base" the retriever searches)."""
from dataclasses import dataclass, field
from sqlalchemy import select
from sqlalchemy.orm import Session, contains_eager
from app.models import ChefProfile, Review, User


@dataclass
class ChefDoc:
    chef_id: int
    text: str
    metadata: dict = field(default_factory=dict)  # used later for filtering and ranking


def chef_to_text(name: str, city: str | None, cuisines: list[str], certifications: list[str],
                 bio: str | None, review_comments: list[str]) -> str:
    """Cuisines are written twice on purpose: it gives them more weight than free-text words."""
    cuisines = [c for c in cuisines if c]
    parts = [f"Chef {name}."]
    if city:
        parts.append(f"Based in {city}.")
    if cuisines:
        parts.append("Cuisines: " + ", ".join(cuisines) + ".")
        parts.append("Specialises in " + " and ".join(cuisines) + " cooking.")
    if certifications:
        parts.append("Certifications: " + ", ".join(certifications) + ".")
    if bio:
        parts.append(bio.strip())
    if review_comments:
        parts.append("Customers say: " + " ".join(c.strip() for c in review_comments) )
    return " ".join(parts)


def build_documents(db: Session, review_snippets: int = 5) -> list[ChefDoc]:
    """One document per chef that is verified and active (nobody else may ever be recommended)."""
    chefs = db.scalars(
        select(ChefProfile).join(User, ChefProfile.user_id == User.id).options(contains_eager(ChefProfile.user))
        .where(ChefProfile.is_verified.is_(True), User.is_active.is_(True)).order_by(ChefProfile.id)
    ).all()
    if not chefs:
        return []
    comments: dict[int, list[str]] = {c.id: [] for c in chefs}
    rows = db.execute(select(Review.chef_id, Review.comment).where(Review.chef_id.in_(comments), Review.comment.is_not(None))
                      .order_by(Review.created_at.desc(), Review.id.desc()))
    for chef_id, comment in rows:
        if comment and comment.strip() and len(comments[chef_id]) < review_snippets:
            comments[chef_id].append(comment)
    docs = []
    for c in chefs:
        docs.append(ChefDoc(
            chef_id=c.id,
            text=chef_to_text(c.user.full_name, c.city, c.cuisines or [], c.certifications or [], c.bio, comments[c.id]),
            metadata={"chef_id": c.id, "name": c.user.full_name, "city": c.city, "cuisines": c.cuisines or [],
                      "price": float(c.price_per_session or 0), "rating": float(c.rating_avg or 0),
                      "years": c.years_experience, "reviews": c.review_count}))
    return docs
