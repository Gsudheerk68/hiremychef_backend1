"""Chat as a customer.  Run: python -m scripts.chat_cli customer@email.com   (type 'exit' to quit)"""
import sys
import uuid

from langgraph.types import Command
from sqlalchemy import select

from app.ai.agent.graph import build_graph
from app.db.session import SessionLocal
from app.models import User, UserRole


def pick_customer() -> User:
    with SessionLocal() as db:
        if len(sys.argv) > 1:
            user = db.scalars(select(User).where(User.email == sys.argv[1].lower())).first()
        else:
            user = db.scalars(select(User).where(User.role == UserRole.customer)).first()
        if not user or user.role != UserRole.customer:
            raise SystemExit("No customer found. Register one at /docs (POST /api/v1/auth/register, role=customer) "
                             "and pass the email: python -m scripts.chat_cli you@example.com")
        db.expunge(user)
        return user


def run_turn(graph, payload, config):
    """Streams one run. Returns (final_text, interrupt_value_or_None)."""
    final, pending = None, None
    for update in graph.stream(payload, config, stream_mode="updates"):
        for node, data in update.items():
            if node == "__interrupt__":
                pending = data[0].value
                continue
            for m in data.get("messages", []):
                calls = getattr(m, "tool_calls", None) or []
                for call in calls:
                    print(f"  -> tool call: {call['name']} {call['args']}")
                if node == "agent" and not calls:
                    final = m.content
    return final, pending


customer = pick_customer()
graph = build_graph()
config = {"configurable": {"thread_id": str(uuid.uuid4()), "user_id": customer.id}}
print(f"Hire My Chef assistant (logged in as {customer.email}). Type 'exit' to quit.\n")

while True:
    text = input("You: ").strip()
    if text.lower() in {"exit", "quit"}:
        break
    if not text:
        continue
    print("  (thinking, this can take a minute on CPU...)")
    payload = {"messages": [("user", text)]}
    try:
        final, pending = run_turn(graph, payload, config)
        while pending:  # the graph paused to ask for confirmation
            print("\n=== CONFIRM BOOKING ===")
            print(f"  Chef:     {pending['chef_name']}")
            print(f"  When:     {pending['when']}")
            print(f"  Guests:   {pending['guests']}  ({pending['event_type']})")
            print(f"  Location: {pending['location']}")
            print(f"  Estimate: ₹{pending['estimated_price']:,}")
            yes = input("Book this? (yes/no): ").strip().lower() in {"y", "yes"}
            final, pending = run_turn(graph, Command(resume=yes), config)
    except Exception as e:
        print(f"\n[error] {type(e).__name__}: {e}\n")
        continue
    print(f"\nBot: {final or '(no reply)'}\n")
