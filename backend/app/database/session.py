"""
Database Engine & Session Management for SQL Server
Dual Database Setup:
- System DB (Claude): RBAC, RLS, Audit, Table Metadata
- Data DB (Rep_data): Business data, dynamic tables, allocations
"""
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, Session, DeclarativeBase
from sqlalchemy.pool import QueuePool
from typing import Generator
from loguru import logger

from app.core.config import get_settings

settings = get_settings()


# ============================================================================
# System Database Engine (Claude) - RBAC, RLS, Audit
# ============================================================================
system_engine = create_engine(
    settings.DATABASE_URL,
    poolclass=QueuePool,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    pool_recycle=settings.DB_POOL_RECYCLE,
    pool_pre_ping=settings.DB_POOL_PRE_PING,
    echo=settings.DEBUG,
    fast_executemany=True,
)

# Alias for backward compatibility
engine = system_engine


# ============================================================================
# Data Database Engine (Rep_data) - Business Data
# ============================================================================
data_engine = create_engine(
    settings.DATA_DATABASE_URL,
    poolclass=QueuePool,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    pool_recycle=settings.DB_POOL_RECYCLE,
    pool_pre_ping=settings.DB_POOL_PRE_PING,
    echo=settings.DEBUG,
    fast_executemany=True,
)


# ============================================================================
# Session Factories
# ============================================================================
SystemSessionLocal = sessionmaker(
    bind=system_engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)

DataSessionLocal = sessionmaker(
    bind=data_engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)

# Alias for backward compatibility
SessionLocal = SystemSessionLocal


# ============================================================================
# Declarative Bases
# ============================================================================
class Base(DeclarativeBase):
    """Base for system tables (RBAC, RLS, Audit)."""
    pass


class DataBase(DeclarativeBase):
    """Base for data tables (business data)."""
    pass


# ============================================================================
# Dependencies: Get DB Sessions (for FastAPI)
# ============================================================================
def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency for System DB (RBAC, RLS, Audit)."""
    db = SystemSessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_data_db() -> Generator[Session, None, None]:
    """FastAPI dependency for Data DB (business data, dynamic tables)."""
    db = DataSessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ============================================================================
# Raw Connection Helpers (for Pandas / bulk ops)
# ============================================================================
def get_raw_connection():
    """Get a raw DBAPI connection for System DB."""
    return system_engine.raw_connection()


def get_data_raw_connection():
    """Get a raw DBAPI connection for Data DB."""
    return data_engine.raw_connection()


def get_engine():
    """Get the System DB SQLAlchemy engine."""
    return system_engine


def get_system_engine():
    """Get the System DB SQLAlchemy engine (alias for get_engine)."""
    return system_engine


def get_data_engine():
    """Get the Data DB SQLAlchemy engine."""
    return data_engine


def get_system_db_url() -> str:
    """Get the System DB connection URL string (for background tasks)."""
    return str(settings.DATABASE_URL)


def get_data_db_url() -> str:
    """Get the Data DB connection URL string (for background tasks)."""
    return str(settings.DATA_DATABASE_URL)


# ============================================================================
# Enable Read Committed Snapshot Isolation (RCSI)
# ============================================================================
def enable_rcsi():
    """
    Enable READ_COMMITTED_SNAPSHOT on both databases.
    This is the #1 fix for 'DB locked during upsert' — readers use row versioning
    instead of shared locks, so they NEVER block writers and vice versa.
    This is a one-time DB setting that persists across restarts.
    """
    for label, eng in [("System", system_engine), ("Data", data_engine)]:
        try:
            db_name = None
            with eng.connect() as conn:
                db_name = conn.execute(text("SELECT DB_NAME()")).scalar()
                is_rcsi = conn.execute(text(
                    "SELECT is_read_committed_snapshot_on FROM sys.databases WHERE name = DB_NAME()"
                )).scalar()
                if is_rcsi:
                    logger.info(f"{label} DB [{db_name}]: RCSI already enabled")
                    continue

            # Must run ALTER DATABASE outside of a transaction on a separate connection
            # using autocommit mode
            raw = eng.raw_connection()
            raw.autocommit = True
            try:
                cursor = raw.cursor()
                cursor.execute(f"ALTER DATABASE [{db_name}] SET READ_COMMITTED_SNAPSHOT ON")
                cursor.close()
                logger.info(f"{label} DB [{db_name}]: RCSI enabled successfully")
            except Exception as e:
                logger.debug(f"{label} DB [{db_name}]: RCSI not set (OK on Azure SQL — usually pre-enabled): {e}")
            finally:
                raw.close()

        except Exception as e:
            logger.debug(f"{label} DB: RCSI check skipped: {e}")


# ============================================================================
# Health Checks
# ============================================================================
def check_db_connection() -> bool:
    """Verify System DB connectivity."""
    try:
        with system_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"System DB connection failed: {e}")
        return False


def check_data_db_connection() -> bool:
    """Verify Data DB connectivity."""
    try:
        with data_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Data DB connection failed: {e}")
        return False


# ============================================================================
# Event Listeners
# ============================================================================
@event.listens_for(system_engine, "connect")
def set_system_connection_options(dbapi_connection, connection_record):
    """Set connection-level options for system DB."""
    pass


@event.listens_for(data_engine, "connect")
def set_data_connection_options(dbapi_connection, connection_record):
    """Set connection-level options for data DB.
    Use READ COMMITTED SNAPSHOT so readers never block writers and vice versa."""
    try:
        cursor = dbapi_connection.cursor()
        cursor.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
        cursor.close()
    except Exception:
        pass


# ============================================================================
# Hot-Reload (used by Settings UI when DB credentials change)
# ============================================================================
def reload_db_engines() -> dict:
    """Re-point the running app at a new database without restarting.

    Why this works despite many modules doing `from app.database.session import
    data_engine` at import time:

    SQLAlchemy's Engine object holds a connection pool, a dialect, and a URL.
    `engine.connect()` calls `engine.pool.connect()`, which in turn calls a
    *creator* closure built from the URL. By swapping `engine.pool` with a
    pool built from the NEW URL, every existing reference to `data_engine`
    starts producing connections to the new server — without changing the
    Engine object's identity. Direct imports keep working.

    Steps:
      1. Bust the lru_cache on get_settings() so it re-reads .env.
      2. Build new pools from the new URLs (via temporary engines).
      3. Swap the live engines' .pool and .url attributes in place.
      4. Dispose the old pools (closes their checked-in connections).
      5. Re-bind the sessionmaker factories so future sessions use the
         updated engines (no-op if they're already bound to the same object).

    Returns a small status dict for logging.
    """
    from app.core.config import get_settings as _gs

    # 1) Refresh the cached Settings instance so .env changes take effect
    _gs.cache_clear()
    new_settings = _gs()

    sys_url = new_settings.DATABASE_URL
    data_url = new_settings.DATA_DATABASE_URL

    # 2) Build new engines temporarily — only their pools/urls will be used
    new_sys_engine = create_engine(
        sys_url,
        poolclass=QueuePool,
        pool_size=new_settings.DB_POOL_SIZE,
        max_overflow=new_settings.DB_MAX_OVERFLOW,
        pool_timeout=new_settings.DB_POOL_TIMEOUT,
        pool_recycle=new_settings.DB_POOL_RECYCLE,
        pool_pre_ping=new_settings.DB_POOL_PRE_PING,
        echo=new_settings.DEBUG,
        fast_executemany=True,
    )
    new_data_engine = create_engine(
        data_url,
        poolclass=QueuePool,
        pool_size=new_settings.DB_POOL_SIZE,
        max_overflow=new_settings.DB_MAX_OVERFLOW,
        pool_timeout=new_settings.DB_POOL_TIMEOUT,
        pool_recycle=new_settings.DB_POOL_RECYCLE,
        pool_pre_ping=new_settings.DB_POOL_PRE_PING,
        echo=new_settings.DEBUG,
        fast_executemany=True,
    )

    # 3) Swap pools/url onto the live engine objects (preserve identity)
    old_sys_pool = system_engine.pool
    old_data_pool = data_engine.pool
    system_engine.pool = new_sys_engine.pool
    data_engine.pool = new_data_engine.pool
    try:
        system_engine.url = new_sys_engine.url
        data_engine.url = new_data_engine.url
    except AttributeError:
        # Older SQLAlchemy treats .url as read-only — that's fine, .pool is
        # what actually drives connection creation.
        pass

    # 4) Dispose the old pools to release their connections
    try:
        old_sys_pool.dispose()
    except Exception as e:
        logger.warning(f"Old system pool dispose failed: {e}")
    try:
        old_data_pool.dispose()
    except Exception as e:
        logger.warning(f"Old data pool dispose failed: {e}")

    # 5) Re-bind sessionmaker factories — same engine object, but force a
    #    re-validation so any cached state inside the factory is refreshed.
    SystemSessionLocal.configure(bind=system_engine)
    DataSessionLocal.configure(bind=data_engine)

    # 6) Probe both engines with a trivial query against the new pool. If the
    #    swap left the engine in a bad state (or the new credentials cannot
    #    open a session even though the up-front probe passed), fail loudly
    #    here instead of letting downstream API endpoints return mystery 500s.
    sys_db_name = None
    data_db_name = None
    try:
        with system_engine.connect() as conn:
            sys_db_name = conn.execute(text("SELECT DB_NAME()")).scalar()
    except Exception as e:
        logger.error(f"Post-reload probe FAILED for system engine: {e}")
        raise
    try:
        with data_engine.connect() as conn:
            data_db_name = conn.execute(text("SELECT DB_NAME()")).scalar()
    except Exception as e:
        logger.error(f"Post-reload probe FAILED for data engine: {e}")
        raise

    db_cfg = new_settings._db()
    logger.info(
        f"DB engines reloaded → server={db_cfg['server']} "
        f"system_db={sys_db_name} data_db={data_db_name} "
        f"user={db_cfg['username']}"
    )
    return {
        "server": db_cfg["server"],
        "system_database": sys_db_name,
        "data_database": data_db_name,
        "username": db_cfg["username"],
    }


