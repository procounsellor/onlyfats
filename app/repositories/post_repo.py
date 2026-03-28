from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.post import Post


class PostRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_post_by_id(self, post_id: str):
        result = await self.db.execute(
            select(Post).where(Post.id == post_id)
        )
        return result.scalar_one_or_none()
