from __future__ import annotations

from datetime import datetime, timedelta
import secrets

from bot.storage.repositories import HealthRepository, ReviveRepository


class HealthService:
    def __init__(self, health_repository: HealthRepository, revive_repository: ReviveRepository):
        self.health_repository = health_repository
        self.revive_repository = revive_repository

    async def lose_heart(self, user_id: int) -> int:
        hearts = max(0, await self.health_repository.get_hearts(user_id) - 1)
        await self.health_repository.set_hearts(user_id, hearts)
        return hearts

    async def gain_heart(self, user_id: int, amount: int = 1) -> int:
        hearts = min(5, await self.health_repository.get_hearts(user_id) + amount)
        await self.health_repository.set_hearts(user_id, hearts)
        return hearts

    async def generate_revive(self, user_id: int, ttl_minutes: int = 30) -> str:
        token = secrets.token_urlsafe(8)
        expires_at = datetime.utcnow() + timedelta(minutes=ttl_minutes)
        await self.revive_repository.create_token(user_id, token, expires_at)
        return token

    async def use_revive(self, user_id: int) -> bool:
        token_row = await self.revive_repository.get_active_token(user_id)
        if not token_row:
            return False
        await self.revive_repository.mark_used(token_row["id"])
        await self.health_repository.set_hearts(user_id, 3)
        return True

    async def get_hearts(self, user_id: int) -> int:
        return await self.health_repository.get_hearts(user_id)
