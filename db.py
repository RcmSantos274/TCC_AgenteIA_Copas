import os

import psycopg2
from dotenv import load_dotenv

load_dotenv()


def get_connection(env_var='DATABASE_URL'):
    return psycopg2.connect(
        os.environ[env_var],
        connect_timeout=10,
        keepalives=1,
        keepalives_idle=15,
        keepalives_interval=5,
        keepalives_count=3,
    )
