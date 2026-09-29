"""migrations/ 리비전이 현재 모델 스키마와 일치하는지 검증."""

import os
import subprocess
import sys
import tempfile

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

import config


def test_upgrade_matches_model_metadata():
    from models import db

    db_fd, db_path = tempfile.mkstemp(suffix='.sqlite')
    os.close(db_fd)
    env = dict(os.environ, DATABASE_URL=f'sqlite:///{db_path}', FLASK_APP='app.py')

    try:
        subprocess.run([sys.executable, '-m', 'flask', 'db', 'upgrade'],
                       cwd=config.BASE_DIR, env=env, check=True, capture_output=True)

        engine = create_engine(f'sqlite:///{db_path}')
        with engine.connect() as connection:
            diff = compare_metadata(MigrationContext.configure(connection), db.metadata)
        engine.dispose()
    finally:
        os.remove(db_path)

    assert diff == []
