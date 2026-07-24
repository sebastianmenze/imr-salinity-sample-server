from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.config import settings

engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _add_missing_columns():
    """
    create_all() only creates tables that don't exist yet — it never adds columns
    to tables that already exist. When a model gains a new column, add it here so
    existing deployments don't need a full DB reset.
    """
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue
            existing_columns = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing_columns:
                    continue
                col_type = column.type.compile(dialect=engine.dialect)
                conn.execute(text(
                    f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}'
                ))


def create_tables():
    from app.models import sample  # noqa: F401 — ensures model is registered
    Base.metadata.create_all(bind=engine)
    _add_missing_columns()
