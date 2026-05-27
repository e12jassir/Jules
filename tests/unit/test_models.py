from datetime import datetime, timezone
import uuid

import pytest

from jules.memory.models import Base, Episode, EpisodeORM, SessionContext, SessionContextORM


def test_session_context_initialization():
    ctx = SessionContext(
        project="Jules",
        directory="/home/user/Jules",
        active_files=["README.md"],
        inferred_intent="testing",
        time_of_day="morning",
    )
    assert ctx.project == "Jules"
    assert ctx.active_files == ["README.md"]


def test_episode_initialization():
    ctx = SessionContext(
        project="Jules",
        directory="/home/user/Jules",
        active_files=[],
        inferred_intent=None,
        time_of_day="night",
    )
    ep_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    
    ep = Episode(
        id=ep_id,
        timestamp=now,
        context=ctx,
        problem="Test problem",
        process="Test process",
        solution="Test solution",
        duration_seconds=120,
        friction_score=0.5,
        tags=["test"],
    )
    
    assert ep.id == ep_id
    assert ep.context.project == "Jules"
    assert ep.importance == 0.0  # default
    assert ep.model_used == ""   # default
    assert ep.provider_used == "" # default
    assert ep.memory_schema_version == "1.2" # default


def test_session_context_orm_conversion():
    ctx = SessionContext(
        project="Jules",
        directory="/home/user/Jules",
        active_files=["models.py"],
        inferred_intent="debugging",
        time_of_day="afternoon",
    )

    orm_ctx = SessionContextORM.from_dataclass(ctx)

    assert orm_ctx.project == "Jules"
    assert orm_ctx.active_files == ["models.py"]
    assert orm_ctx.to_dataclass() == ctx



def test_episode_orm_conversion():
    ctx = SessionContext(
        project="Jules",
        directory="/home/user/Jules",
        active_files=["models.py"],
        inferred_intent="debugging",
        time_of_day="afternoon",
    )
    ep_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    
    original_ep = Episode(
        id=ep_id,
        timestamp=now,
        context=ctx,
        problem="DB error",
        process="Debugging ORM",
        solution="Fixed models.py",
        duration_seconds=300,
        friction_score=0.2,
        tags=["db", "orm"],
        importance=0.8,
        model_used="gpt-5.4",
        provider_used="antigravity",
    )
    
    # 1. Convert Dataclass -> ORM
    orm_ep = EpisodeORM.from_dataclass(original_ep)
    
    assert orm_ep.id == original_ep.id
    assert orm_ep.timestamp.tzinfo is None
    assert orm_ep.timestamp == original_ep.timestamp.replace(tzinfo=None)
    assert orm_ep.session_context.project == "Jules"
    assert orm_ep.session_context.active_files == ["models.py"]
    assert orm_ep.model_used == "gpt-5.4"
    assert orm_ep.tags == ["db", "orm"]
    
    # 2. Convert ORM -> Dataclass
    restored_ep = orm_ep.to_dataclass()
    
    assert restored_ep.id == original_ep.id
    assert restored_ep.timestamp == original_ep.timestamp
    assert restored_ep.context.project == "Jules"
    assert restored_ep.context.active_files == ["models.py"]
    assert restored_ep.problem == "DB error"
    assert restored_ep.tags == ["db", "orm"]
    assert restored_ep.importance == 0.8
    assert restored_ep.model_used == "gpt-5.4"
    assert restored_ep.memory_schema_version == "1.2"
    
    # Verify the restored dataclass matches the original perfectly
    assert restored_ep == original_ep


def test_episode_orm_sqlite_round_trip():
    sqlalchemy = pytest.importorskip("sqlalchemy")
    orm = pytest.importorskip("sqlalchemy.orm")

    engine = sqlalchemy.create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    ctx = SessionContext(
        project="Jules",
        directory="/home/user/Jules",
        active_files=["models.py", "test_models.py"],
        inferred_intent="implementation",
        time_of_day="evening",
    )
    original_ep = Episode(
        id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc),
        context=ctx,
        problem="Need canonical persistence",
        process="Persist through ORM session",
        solution="Round-trip succeeded",
        duration_seconds=42,
        friction_score=0.1,
        tags=["memory", "sqlite"],
        importance=0.6,
        model_used="gpt-5.4",
        provider_used="opencode",
    )

    with orm.Session(engine) as session:
        session.add(EpisodeORM.from_dataclass(original_ep))
        session.commit()
        stored = session.get(EpisodeORM, original_ep.id)
        assert stored is not None
        assert stored.session_context.directory == "/home/user/Jules"
        assert stored.session_context.active_files == ["models.py", "test_models.py"]

        restored = stored.to_dataclass()

    assert restored == original_ep
