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


class ScreenerRun(Base):
    __tablename__ = "screener_runs"
    id = Column(Integer, primary_key=True)
    run_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    stock_count = Column(Integer, default=0)
    cluster_count = Column(Integer, default=0)


class ScreenerStock(Base):
    __tablename__ = "screener_stocks"
    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, index=True)
    symbol = Column(String(20))
    name = Column(String(500))
    exchange = Column(String(20))
    country = Column(String(100))
    sector = Column(String(200))
    industry = Column(String(200))
    price = Column(Float)
    year_low = Column(Float)
    low_3m = Column(Float)
    pct_above_52w = Column(Float)
    pct_above_3m = Column(Float)
    vol_ratio = Column(Float)
    vol_flag = Column(String(5))
    signal = Column(String(20))  # Strong | Recovery | Breakout


class ScreenerCluster(Base):
    __tablename__ = "screener_clusters"
    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, index=True)
    sector = Column(String(200))
    country = Column(String(100))
    strong = Column(Integer, default=0)
    recovery = Column(Integer, default=0)
    breakout = Column(Integer, default=0)
    total = Column(Integer, default=0)
    delta = Column(Integer, default=0)  # change vs previous run


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
    with SessionLocal() as session:
        # Get all article IDs already sent in any previous digest
        sent_ids = set()
        for digest in session.query(Digest).all():
            if digest.article_ids:
                sent_ids.update(digest.article_ids)

        # Return all articles not yet sent
        query = session.query(Article)
        if sent_ids:
            query = query.filter(~Article.id.in_(sent_ids))
        articles = query.all()
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


def get_queued_articles():
    with SessionLocal() as session:
        sent_ids = set()
        for digest in session.query(Digest).all():
            if digest.article_ids:
                sent_ids.update(digest.article_ids)
        query = session.query(Article)
        if sent_ids:
            query = query.filter(~Article.id.in_(sent_ids))
        articles = query.order_by(Article.must_read_score.desc()).all()
        result = []
        for a in articles:
            result.append({
                "id": a.id,
                "subject": a.subject,
                "sender": a.sender,
                "must_read_score": a.must_read_score,
                "is_paywalled": a.is_paywalled,
                "received_at": a.received_at.isoformat() if a.received_at else None,
                "tags": a.tags or [],
            })
        return result


def get_article_count():
    with SessionLocal() as session:
        total = session.query(Article).count()

        # Count articles not yet sent in any digest
        sent_ids = set()
        for digest in session.query(Digest).all():
            if digest.article_ids:
                sent_ids.update(digest.article_ids)
        if sent_ids:
            queued = session.query(Article).filter(~Article.id.in_(sent_ids)).count()
        else:
            queued = total
        return total, queued


def get_feedback_history(weeks=8):
    cutoff = datetime.now(timezone.utc) - timedelta(weeks=weeks)
    with SessionLocal() as session:
        items = session.query(Feedback).filter(Feedback.submitted_at >= cutoff).all()
        session.expunge_all()
        return items


# ── Screener CRUD ────────────────────────────────────────────────────────────

def save_screener_run(stock_count, cluster_count):
    with SessionLocal() as session:
        run = ScreenerRun(stock_count=stock_count, cluster_count=cluster_count)
        session.add(run)
        session.commit()
        return run.id


def save_screener_stocks(run_id, stocks):
    with SessionLocal() as session:
        for s in stocks:
            session.add(ScreenerStock(
                run_id=run_id,
                symbol=s["symbol"],
                name=s["name"],
                exchange=s["exchange"],
                country=s["country"],
                sector=s["sector"],
                industry=s["industry"],
                price=s["price"],
                year_low=s["year_low"],
                low_3m=s["low_3m"],
                pct_above_52w=s["pct_above_52w"],
                pct_above_3m=s["pct_above_3m"],
                vol_ratio=s["vol_ratio"],
                vol_flag=s["vol_flag"],
                signal=s["signal"],
            ))
        session.commit()


def _get_prev_run_id():
    """Return the second-most-recent screener run id, or None if this is the first."""
    with SessionLocal() as session:
        runs = session.query(ScreenerRun).order_by(ScreenerRun.run_at.desc()).limit(2).all()
        return runs[1].id if len(runs) >= 2 else None


def save_screener_clusters(run_id, clusters):
    """Save clusters, computing delta against the previous run."""
    prev_run_id = _get_prev_run_id()

    # Build lookup of previous totals keyed by (sector, country)
    prev_totals = {}
    if prev_run_id:
        with SessionLocal() as session:
            prev = session.query(ScreenerCluster).filter(ScreenerCluster.run_id == prev_run_id).all()
            for c in prev:
                prev_totals[(c.sector, c.country)] = c.total

    with SessionLocal() as session:
        for c in clusters:
            prev_total = prev_totals.get((c["sector"], c["country"]), 0)
            delta = c["total"] - prev_total
            session.add(ScreenerCluster(
                run_id=run_id,
                sector=c["sector"],
                country=c["country"],
                strong=c["strong"],
                recovery=c["recovery"],
                breakout=c["breakout"],
                total=c["total"],
                delta=delta,
            ))
        session.commit()


def get_latest_screener_results():
    """Return (stocks, clusters) from the most recent screener run, or ([], []) if none."""
    with SessionLocal() as session:
        latest_run = session.query(ScreenerRun).order_by(ScreenerRun.run_at.desc()).first()
        if not latest_run:
            return [], []

        stocks = session.query(ScreenerStock).filter(ScreenerStock.run_id == latest_run.id).all()
        clusters = (
            session.query(ScreenerCluster)
            .filter(ScreenerCluster.run_id == latest_run.id)
            .order_by(ScreenerCluster.total.desc())
            .all()
        )

        stock_dicts = [{
            "symbol": s.symbol, "name": s.name, "exchange": s.exchange,
            "country": s.country, "sector": s.sector, "industry": s.industry,
            "price": s.price, "year_low": s.year_low, "low_3m": s.low_3m,
            "pct_above_52w": s.pct_above_52w, "pct_above_3m": s.pct_above_3m,
            "vol_ratio": s.vol_ratio, "vol_flag": s.vol_flag or "", "signal": s.signal,
        } for s in stocks]

        cluster_dicts = [{
            "sector": c.sector, "country": c.country,
            "strong": c.strong, "recovery": c.recovery, "breakout": c.breakout,
            "total": c.total, "delta": c.delta,
        } for c in clusters]

        return stock_dicts, cluster_dicts
