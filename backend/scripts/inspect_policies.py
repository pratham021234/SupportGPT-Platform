import asyncio
from app.db.session import async_session_factory
from app.models.policy_rule import PolicyRule
from sqlalchemy import select, text

async def check():
    async with async_session_factory() as session:
        await session.execute(text("SELECT set_config('app.is_system_admin', 'true', true)"))
        policies = (await session.execute(select(PolicyRule))).scalars().all()
        print(f"Policies count: {len(policies)}")
        for p in policies:
            print(f"  Policy: {p.policy_code} | {p.name} | Action: {p.action_on_violation} | Enabled: {p.is_enabled}")

if __name__ == "__main__":
    asyncio.run(check())
