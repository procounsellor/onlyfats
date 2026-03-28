"""Seed the local dev database with realistic dummy data."""
import asyncio
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

DATABASE_URL = "postgresql+asyncpg://fansonly_dev:fansonly_dev@localhost:5433/fansonly_dev"
engine = create_async_engine(DATABASE_URL)
AsyncSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

from app.models.user import User
from app.models.creator import Creator
from app.models.post import Post
from app.models.post_media import PostMedia
from app.models.subscription import SubscriptionPlan
from app.models.creator_subscription import CreatorSubscription
from app.models.subscription_usage import SubscriptionUsage
from app.models.notification import Notification
from app.models.message import Conversation, Message
from app.models.like import Like
from app.models.comment import Comment
from app.models.follow import Follow
from app.core.security import hash_password

# ── Images ────────────────────────────────────────────────────────────────────
# Post cover images (fashion / lifestyle)
COVERS = [
    "https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?q=80&w=1200",
    "https://images.unsplash.com/photo-1483985988355-763728e1935b?q=80&w=1200",
    "https://images.unsplash.com/photo-1529139574466-a303027c1d8b?q=80&w=1200",
    "https://images.unsplash.com/photo-1469334031218-e382a71b716b?q=80&w=1200",
    "https://images.unsplash.com/photo-1496747611176-843222e1e57c?q=80&w=1200",
    "https://images.unsplash.com/photo-1508214751196-bcfd4ca60f91?q=80&w=1200",
    "https://images.unsplash.com/photo-1524504388940-b1c1722653e1?q=80&w=1200",
    "https://images.unsplash.com/photo-1519741497674-611481863552?q=80&w=1200",
    "https://images.unsplash.com/photo-1487222477894-8943e31ef7b2?q=80&w=1200",
    "https://images.unsplash.com/photo-1502823403499-6ccfcf4fb453?q=80&w=1200",
    "https://images.unsplash.com/photo-1504703395950-b89145a5425b?q=80&w=1200",
    "https://images.unsplash.com/photo-1545205597-3d9d02c29597?q=80&w=1200",
]

# Avatar portraits (square, face-forward)
AVATARS = [
    "https://images.unsplash.com/photo-1494790108377-be9c29b29330?q=80&w=400&h=400&fit=crop",
    "https://images.unsplash.com/photo-1438761681033-6461ffad8d80?q=80&w=400&h=400&fit=crop",
    "https://images.unsplash.com/photo-1544005313-94ddf0286df2?q=80&w=400&h=400&fit=crop",
    "https://images.unsplash.com/photo-1531746020798-e6953c6e8e04?q=80&w=400&h=400&fit=crop",
]

# Header / banner images (wide landscape)
HEADERS = [
    "https://images.unsplash.com/photo-1469334031218-e382a71b716b?q=80&w=1600&h=400&fit=crop",
    "https://images.unsplash.com/photo-1558618666-fcd25c85cd64?q=80&w=1600&h=400&fit=crop",
    "https://images.unsplash.com/photo-1506905925346-21bda4d32df4?q=80&w=1600&h=400&fit=crop",
    "https://images.unsplash.com/photo-1520209759809-a9bcb6cb3241?q=80&w=1600&h=400&fit=crop",
]

CAPTIONS = [
    "Just dropped my latest exclusive photo set 🔥 Subscribers get first access!",
    "Behind the scenes from yesterday's shoot. You won't believe what happened next 👀",
    "New vlog is LIVE 🎬 Subscribe for full access to all my content",
    "Morning vibes ✨ Premium set available for subscribers",
    "Thank you for 10K subscribers! Here's a special post just for you all 💕",
    "New week, new content. Locked post available for EXCLUSIVE tier 🔒",
    "Just a casual Tuesday 😊 Free for all my followers!",
    "Big announcement coming soon 👀 Stay tuned...",
    "Working on something really special for you all 💎 VIP members get early access",
    "Happy Monday! Public post — share it with your friends 🌟",
    "Throwback to last month's beach shoot 🏖️",
    "New collection just dropped 🎨 Exclusive subscribers only!",
]

# ─────────────────────────────────────────────────────────────────────────────

async def seed():
    async with AsyncSessionLocal() as db:
        # ── Users ─────────────────────────────────────────────────────────────
        nishant = User(
            email="nishant@example.com",
            password_hash=hash_password("password123"),
            display_name="Nishant Sagar",
            role="visitor",
            is_active=True,
            is_email_verified=True,
        )
        db.add(nishant)

        creator_data = [
            ("ava@example.com",   "Ava Monroe",   AVATARS[0], HEADERS[0],
             "Fashion model & lifestyle creator 🌸 Exclusive content for subscribers!", "Mumbai"),
            ("luna@example.com",  "Luna Blake",   AVATARS[1], HEADERS[1],
             "Fitness coach & wellness creator 💪 Join me on my journey!", "Delhi"),
            ("nina@example.com",  "Nina Ray",     AVATARS[2], HEADERS[2],
             "Travel & photography enthusiast 📸 Capturing life's beautiful moments", "Bangalore"),
            ("sofia@example.com", "Sofia Star",   AVATARS[3], HEADERS[3],
             "Artist & creative director 🎨 Behind-the-scenes of my creative process", "Pune"),
        ]

        creator_users = []
        creators = []
        for email, name, avatar, header, bio, city in creator_data:
            u = User(
                email=email,
                password_hash=hash_password("password123"),
                display_name=name,
                role="creator",
                is_active=True,
                is_email_verified=True,
            )
            db.add(u)
            creator_users.append((u, avatar, header, bio, city))

        await db.flush()

        for (u, avatar, header, bio, city) in creator_users:
            c = Creator(
                user_id=u.id,
                display_name=u.display_name,
                bio=bio,
                profile_image_url=avatar,
                header_image_url=header,
                subscriber_count=0,
                post_count=0,
                total_likes=0,
                location=city,
                is_active=True,
            )
            db.add(c)
            creators.append(c)

        await db.flush()

        # ── Subscription plans ────────────────────────────────────────────────
        # FREE:      unlimited FREE, 1 EXCLUSIVE preview/month, 0 VIP
        # EXCLUSIVE: unlimited FREE + EXCLUSIVE, 3 VIP previews/month
        # VIP:       unlimited everything
        for creator in creators:
            plans = [
                SubscriptionPlan(
                    creator_id=creator.id, code="FREE", name="Free",
                    description="Public posts + 1 exclusive preview per month",
                    price_in_paise=0, duration_days=30, currency="INR",
                    active=True,
                    unlimited_free_content=True,
                    unlimited_exclusive_content=False,
                    unlimited_vip_content=False,
                    exclusive_preview_quota=1,
                    vip_preview_quota=0,
                ),
                SubscriptionPlan(
                    creator_id=creator.id, code="EXCLUSIVE", name="Exclusive Fan",
                    description="All exclusive content + 3 VIP previews/month",
                    price_in_paise=49900, duration_days=30, currency="INR",
                    active=True,
                    unlimited_free_content=True,
                    unlimited_exclusive_content=True,
                    unlimited_vip_content=False,
                    exclusive_preview_quota=0,
                    vip_preview_quota=3,
                ),
                SubscriptionPlan(
                    creator_id=creator.id, code="VIP", name="VIP Member",
                    description="Full access to ALL content — FREE, Exclusive, and VIP",
                    price_in_paise=99900, duration_days=30, currency="INR",
                    active=True,
                    unlimited_free_content=True,
                    unlimited_exclusive_content=True,
                    unlimited_vip_content=True,
                    exclusive_preview_quota=0,
                    vip_preview_quota=0,
                ),
            ]
            for p in plans:
                db.add(p)

        await db.flush()

        # ── Posts: 2 FREE, 2 EXCLUSIVE, 2 VIP per creator ────────────────────
        all_posts = []
        post_configs = [
            ("public",           "FREE",      0),
            ("public",           "FREE",      6),
            ("subscribers_only", "EXCLUSIVE", 1),
            ("subscribers_only", "EXCLUSIVE", 5),
            ("subscribers_only", "VIP",       3),
            ("subscribers_only", "VIP",       8),
        ]
        for creator in creators:
            for i, (vis, tier, cap_i) in enumerate(post_configs):
                p = Post(
                    creator_id=creator.id,
                    caption=CAPTIONS[cap_i % len(CAPTIONS)],
                    visibility=vis,
                    media_type="image",
                    status="published",
                    moderation_status="approved",
                    access_tier=tier,
                    like_count=0,
                    comment_count=0,
                    published_at=datetime.utcnow() - timedelta(hours=i * 6 + 1),
                )
                db.add(p)
                all_posts.append(p)

            creator.post_count = len(post_configs)

        await db.flush()

        # ── Post media ────────────────────────────────────────────────────────
        for i, post in enumerate(all_posts):
            media = PostMedia(
                post_id=post.id,
                media_kind="photo",
                storage_provider="url",
                bucket_name="unsplash",
                object_path=COVERS[i % len(COVERS)],
                thumbnail_object_path=COVERS[i % len(COVERS)],
                mime_type="image/jpeg",
                sort_order=0,
                processing_status="ready",
            )
            db.add(media)

        await db.flush()

        # ── Subscriptions: nishant gets EXCLUSIVE to creator[0], VIP to creator[1],
        #                   FREE to creator[2], nothing for creator[3] ──────────
        now = datetime.utcnow()
        sub_plan_codes = ["EXCLUSIVE", "VIP", "FREE"]
        for idx, creator in enumerate(creators[:3]):
            plan_code = sub_plan_codes[idx]
            sub = CreatorSubscription(
                subscriber_user_id=nishant.id,
                creator_id=creator.id,
                status="ACTIVE",
                plan_code=plan_code,
                current_period_start=now,
                current_period_end=now + timedelta(days=30),
                auto_renew=False,
            )
            db.add(sub)
            creator.subscriber_count += 1

        await db.flush()

        # ── Usage rows for FREE subscriber (creator[2]) ───────────────────────
        # nishant has FREE sub to nina → track exclusive_preview quota
        cycle_key = f"{now.year}-{now.month:02d}"
        db.add(SubscriptionUsage(
            user_id=nishant.id,
            creator_id=creators[2].id,
            plan_code="FREE",
            usage_type="EXCLUSIVE_PREVIEW",
            allowed_count=1,
            used_count=0,
            cycle_key=cycle_key,
        ))
        # nishant has EXCLUSIVE sub to ava → track vip_preview quota
        db.add(SubscriptionUsage(
            user_id=nishant.id,
            creator_id=creators[0].id,
            plan_code="EXCLUSIVE",
            usage_type="VIP_PREVIEW",
            allowed_count=3,
            used_count=0,
            cycle_key=cycle_key,
        ))

        await db.flush()

        # ── Likes & comments ──────────────────────────────────────────────────
        for post in all_posts[:10]:
            like = Like(user_id=nishant.id, post_id=post.id)
            db.add(like)
            post.like_count += 1

        comments_text = [
            "This is amazing! 🔥",
            "Love your content!",
            "Can't wait for more!",
            "Absolutely stunning 😍",
            "Keep it up! 💕",
        ]
        for i, post in enumerate(all_posts[:5]):
            db.add(Comment(post_id=post.id, user_id=nishant.id, body=comments_text[i]))
            post.comment_count += 1

        await db.flush()

        # ── Notifications ─────────────────────────────────────────────────────
        notifs = [
            Notification(user_id=nishant.id, actor_id=creators[0].user_id,
                         type="new_post", title="Ava Monroe posted new content",
                         body="Just dropped my latest exclusive photo set 🔥",
                         entity_type="post", entity_id=all_posts[0].id),
            Notification(user_id=nishant.id, actor_id=creators[1].user_id,
                         type="new_post", title="Luna Blake posted new content",
                         body="Behind the scenes from yesterday's shoot",
                         entity_type="post", entity_id=all_posts[6].id),
            Notification(user_id=nishant.id, actor_id=creators[0].user_id,
                         type="new_subscriber", title="Welcome to Ava Monroe's fan club!",
                         body="You subscribed to Ava Monroe. Enjoy exclusive content!"),
            Notification(user_id=nishant.id, actor_id=creators[1].user_id,
                         type="new_subscriber", title="VIP access unlocked!",
                         body="You are now a VIP member of Luna Blake's page 💎"),
        ]
        for n in notifs:
            db.add(n)

        # ── Messages ──────────────────────────────────────────────────────────
        await db.flush()
        conv = Conversation(user_a_id=nishant.id, user_b_id=creators[0].user_id)
        db.add(conv)
        await db.flush()

        for sender_id, body in [
            (creators[0].user_id, "Hey! Thanks for subscribing 💕 Hope you enjoy my content!"),
            (nishant.id, "Love your content! When's the next post coming?"),
            (creators[0].user_id, "Working on something special for this weekend 🔥 Stay tuned!"),
            (nishant.id, "Can't wait! Your exclusive content is always worth it 🙌"),
        ]:
            db.add(Message(conversation_id=conv.id, sender_id=sender_id, body=body))

        await db.commit()
        print("✅ Seed data created successfully!")
        print("   Login: nishant@example.com / password123")
        print("   Subscriptions: EXCLUSIVE→Ava, VIP→Luna, FREE→Nina, none→Sofia")
        print("   Creators: ava / luna / nina / sofia @example.com, all password123")


if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))
    asyncio.run(seed())
