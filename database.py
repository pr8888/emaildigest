from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text, JSON, Boolean, text
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime, timezone, timedelta
import os

engine = create_engine(os.environ["DATABASE_URL"])
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class Article(Base):
    __tablename__ = "articles"
    id = Column(Integer, primary_key=True)
    received_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    subject = Column(String(500))
    sender = Column(String(200))
    raw_content = Column(Text)
    summary = Column(Text)
    tags = Column(JSON)
    must_read_score = Column(Float, default=0.0)
    is_paywalled = Column(Boolean, default=False)


class Digest(Base):
    __tablename__ = "digests"
    id = Column(Integer, primary_key=True)
    sent_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    article_ids = Column(JSON)
    week_start = Column(DateTime)


class Feedback(Base):
    __tablename__ = "feedback"
    id = Column(Integer, primary_key=True)
    digest_id = Column(Integer)
    type = Column(String(50))   # "length" or "must_read"
    value = Column(String(50))  # "short"/"good"/"long" or "1"-"5"
    submitted_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


def init_db():
    Base.metadata.create_all(engine)
    # Add is_paywalled column to existing tables if it doesn't exist yet
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE articles ADD COLUMN IF NOT EXISTS is_paywalled BOOLEAN DEFAULT FALSE"))
        conn.commit()


def save_article(subject, sender, raw_content, summary, tags, must_read_score, is_paywalled=False):
    with SessionLocal() as session:
        article = Article(
            subject=subject,
            sender=sender,
            raw_content=raw_content,
            summary=summary,
            tags=tags,
            must_read_score=must_read_score,
            is_paywalled=is_paywalled,
        )
        session.add(article)
        session.commit()
        return article.id


def get_weekly_articles():
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    with SessionLocal() as session:
        articles = session.query(Article).filter(Article.received_at >= week_ago).all()
        # Detach from session so they can be used outside
        session.expunge_all()
        return articles


def save_digest(article_ids, week_start):
    with SessionLocal() as session:
        digest = Digest(article_ids=article_ids, week_start=week_start)
        session.add(digest)
        session.commit()
        return digest.id


def save_feedback(digest_id, type, value):
    with SessionLocal() as session:
        feedback = Feedback(digest_id=digest_id, type=type, value=value)
        session.add(feedback)
        session.commit()


def get_article_count():
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    with SessionLocal() as session:
        total = session.query(Article).count()
        this_week = session.query(Article).filter(Article.received_at >= week_ago).count()
        return total, this_week


def get_feedback_history(weeks=8):
    cutoff = datetime.now(timezone.utc) - timedelta(weeks=weeks)
    with SessionLocal() as session:
        items = session.query(Feedback).filter(Feedback.submitted_at >= cutoff).all()
        session.expunge_all()
        return items
