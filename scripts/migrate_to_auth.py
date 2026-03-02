"""One-time migration: import existing file-based data into auth DB for admin user."""
import asyncio
import json
from pathlib import Path

from ghostfolio_agent.auth.db import AuthDB
from ghostfolio_agent.config import get_settings


async def migrate():
    settings = get_settings()
    if not settings.encryption_key:
        print("ERROR: ENCRYPTION_KEY not set in .env")
        return

    db = AuthDB("data/agent.db", settings.encryption_key)
    await db.init()

    # Create admin user with env token
    admin = await db.find_user_by_token(settings.ghostfolio_access_token)
    if not admin:
        admin = await db.create_user(
            ghostfolio_token=settings.ghostfolio_access_token, role="admin"
        )
        print(f"Created admin user: {admin['id']}")
    else:
        print(f"Admin user already exists: {admin['id']}")
    admin_id = admin["id"]

    # Migrate paper portfolio
    paper_file = Path("data/paper_portfolio.json")
    if paper_file.exists():
        data = json.loads(paper_file.read_text())
        await db.save_paper_portfolio(admin_id, data)
        pos_count = len(data.get("positions", {}))
        print(f"Migrated paper portfolio: ${data['cash']:.2f} cash, {pos_count} positions")
    else:
        print("No paper portfolio to migrate")

    # Migrate alert cooldowns
    cooldown_file = Path("data/alert_cooldowns.json")
    if cooldown_file.exists():
        cooldowns = json.loads(cooldown_file.read_text())
        for key, fired_at in cooldowns.items():
            await db.set_cooldown(admin_id, key, fired_at)
        print(f"Migrated {len(cooldowns)} alert cooldowns")
    else:
        print("No alert cooldowns to migrate")

    await db.close()
    print("Migration complete.")


if __name__ == "__main__":
    asyncio.run(migrate())
