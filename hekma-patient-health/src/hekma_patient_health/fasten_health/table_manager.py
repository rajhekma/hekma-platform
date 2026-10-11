from ..awsutils.postgresql_utils import pg_transaction
from .db_schema import create_fasten_table

def ensure_fasten_tables(total_by_resource_type: dict):
    with pg_transaction(dict_cursor=False) as (_, cur):
        for resource_type in total_by_resource_type.keys():
            create_fasten_table(cur, resource_type)
