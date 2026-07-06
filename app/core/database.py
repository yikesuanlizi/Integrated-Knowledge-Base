from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import declarative_base, sessionmaker

from app.conf.app_config import config

engine = create_async_engine(config.postgres_url, echo=False, poolclass=NullPool)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


async def init_database():
    # Import ORM models before create_all so SQLAlchemy metadata is populated.
    import app.models.documents  # noqa: F401
    import app.models.monitoring  # noqa: F401
    from sqlalchemy import text

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE chunks ADD COLUMN IF NOT EXISTS raw_content TEXT"))
        await conn.execute(text("ALTER TABLE chunks ADD COLUMN IF NOT EXISTS search_content TEXT DEFAULT ''"))
        await conn.execute(text("ALTER TABLE chunks ADD COLUMN IF NOT EXISTS embedding_content TEXT DEFAULT ''"))
        legacy_text_exists = (
            await conn.execute(
                text(
                    """
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'chunks'
                      AND column_name = 'text'
                    LIMIT 1
                    """
                )
            )
        ).scalar() is not None

        raw_content_exists = (
            await conn.execute(
                text(
                    """
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'chunks'
                      AND column_name = 'raw_content'
                    LIMIT 1
                    """
                )
            )
        ).scalar() is not None

        search_content_exists = (
            await conn.execute(
                text(
                    """
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'chunks'
                      AND column_name = 'search_content'
                    LIMIT 1
                    """
                )
            )
        ).scalar() is not None

        embedding_content_exists = (
            await conn.execute(
                text(
                    """
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'chunks'
                      AND column_name = 'embedding_content'
                    LIMIT 1
                    """
                )
            )
        ).scalar() is not None

        if legacy_text_exists:
            await conn.execute(text("UPDATE chunks SET raw_content = COALESCE(raw_content, text, '') WHERE raw_content IS NULL OR raw_content = ''"))
            await conn.execute(text("UPDATE chunks SET search_content = COALESCE(search_content, raw_content, text, '') WHERE search_content IS NULL OR search_content = ''"))
            await conn.execute(text("UPDATE chunks SET embedding_content = COALESCE(embedding_content, search_content, raw_content, text, '') WHERE embedding_content IS NULL OR embedding_content = ''"))
        else:
            if raw_content_exists:
                await conn.execute(text("UPDATE chunks SET raw_content = COALESCE(raw_content, '') WHERE raw_content IS NULL"))
            if search_content_exists and raw_content_exists:
                await conn.execute(text("UPDATE chunks SET search_content = COALESCE(search_content, raw_content, '') WHERE search_content IS NULL OR search_content = ''"))
            if embedding_content_exists and (search_content_exists or raw_content_exists):
                await conn.execute(text("UPDATE chunks SET embedding_content = COALESCE(embedding_content, search_content, raw_content, '') WHERE embedding_content IS NULL OR embedding_content = ''"))

        # 历史兼容：旧策略会把纯 warning 卡片错误地挂成 review。
        # 当前策略下 warning-only 应自动通过，因此在启动时回填历史状态。
        await conn.execute(
            text(
                """
                UPDATE wiki_reviews
                SET status = 'approved'
                WHERE status = 'review'
                  AND COALESCE(notes, '') <> ''
                  AND notes NOT LIKE '%[ERROR]%'
                """
            )
        )
        await conn.execute(
            text(
                """
                UPDATE wiki_cards wc
                SET status = 'approved'
                FROM wiki_reviews wr
                WHERE wc.card_id = wr.card_id
                  AND wc.status = 'review'
                  AND wr.status = 'approved'
                """
            )
        )
