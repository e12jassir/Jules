"""roadmap_session_context_orm

Revision ID: 123f8dc39e81
Revises: db91a0ae1c2b
Create Date: 2026-05-27 13:28:52.985466

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

# revision identifiers, used by Alembic.
revision: str = '123f8dc39e81'
down_revision: Union[str, Sequence[str], None] = 'db91a0ae1c2b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'session_contexts',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('project', sa.String(), nullable=True),
        sa.Column('directory', sa.String(), nullable=False),
        sa.Column('active_files', sa.JSON(), nullable=False),
        sa.Column('inferred_intent', sa.String(), nullable=True),
        sa.Column('time_of_day', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_session_contexts')),
    )

    with op.batch_alter_table('episodes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('session_context_id', sa.Integer(), nullable=True))

    bind = op.get_bind()
    metadata = sa.MetaData()
    episodes = sa.Table(
        'episodes',
        metadata,
        sa.Column('id', sa.String()),
        sa.Column('context_json', sa.JSON()),
        sa.Column('session_context_id', sa.Integer()),
    )
    session_contexts = sa.Table(
        'session_contexts',
        metadata,
        sa.Column('id', sa.Integer()),
        sa.Column('project', sa.String()),
        sa.Column('directory', sa.String()),
        sa.Column('active_files', sa.JSON()),
        sa.Column('inferred_intent', sa.String()),
        sa.Column('time_of_day', sa.String()),
    )

    rows = bind.execute(sa.select(episodes.c.id, episodes.c.context_json)).mappings().all()
    for row in rows:
        context = row['context_json'] or {}
        inserted = bind.execute(
            session_contexts.insert().values(
                project=context.get('project'),
                directory=context.get('directory', ''),
                active_files=context.get('active_files', []),
                inferred_intent=context.get('inferred_intent'),
                time_of_day=context.get('time_of_day', ''),
            )
        )
        context_id = inserted.lastrowid
        if context_id is None:
            inserted_primary_key = inserted.inserted_primary_key
            if not inserted_primary_key or inserted_primary_key[0] is None:
                raise RuntimeError('failed to backfill session_contexts.id during upgrade')
            context_id = inserted_primary_key[0]
        bind.execute(
            episodes.update()
            .where(episodes.c.id == row['id'])
            .values(session_context_id=context_id)
        )

    with op.batch_alter_table('episodes', schema=None) as batch_op:
        batch_op.alter_column('session_context_id', nullable=False)
        batch_op.create_unique_constraint(batch_op.f('uq_episodes_session_context_id'), ['session_context_id'])
        batch_op.create_foreign_key(
            batch_op.f('fk_episodes_session_context_id_session_contexts'),
            'session_contexts',
            ['session_context_id'],
            ['id'],
        )
        batch_op.drop_column('context_json')


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('episodes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('context_json', sqlite.JSON(), nullable=True))

    bind = op.get_bind()
    metadata = sa.MetaData()
    episodes = sa.Table(
        'episodes',
        metadata,
        sa.Column('id', sa.String()),
        sa.Column('session_context_id', sa.Integer()),
        sa.Column('context_json', sqlite.JSON()),
    )
    session_contexts = sa.Table(
        'session_contexts',
        metadata,
        sa.Column('id', sa.Integer()),
        sa.Column('project', sa.String()),
        sa.Column('directory', sa.String()),
        sa.Column('active_files', sa.JSON()),
        sa.Column('inferred_intent', sa.String()),
        sa.Column('time_of_day', sa.String()),
    )

    rows = bind.execute(
        sa.select(
            episodes.c.id,
            episodes.c.session_context_id,
            session_contexts.c.project,
            session_contexts.c.directory,
            session_contexts.c.active_files,
            session_contexts.c.inferred_intent,
            session_contexts.c.time_of_day,
        ).join(session_contexts, episodes.c.session_context_id == session_contexts.c.id)
    ).mappings().all()
    for row in rows:
        bind.execute(
            episodes.update()
            .where(episodes.c.id == row['id'])
            .values(
                context_json={
                    'project': row['project'],
                    'directory': row['directory'],
                    'active_files': row['active_files'],
                    'inferred_intent': row['inferred_intent'],
                    'time_of_day': row['time_of_day'],
                }
            )
        )

    with op.batch_alter_table('episodes', schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f('fk_episodes_session_context_id_session_contexts'), type_='foreignkey')
        batch_op.drop_constraint(batch_op.f('uq_episodes_session_context_id'), type_='unique')
        batch_op.drop_column('session_context_id')
        batch_op.alter_column('context_json', nullable=False)

    op.drop_table('session_contexts')
