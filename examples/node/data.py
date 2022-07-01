import json
from typing import List

import click
import sqlalchemy as sa
from schema import Node
from sqlalchemy.orm import sessionmaker

from pgsync.base import pg_engine, subtransactions
from pgsync.helper import teardown
from pgsync.utils import get_config


@click.command()
@click.option(
    "--config",
    "-c",
    help="Schema config",
    type=click.Path(exists=True),
)
def main(config):

    config: str = get_config(config)
    teardown(drop_db=False, config=config)
    documents: List[dict] = json.load(open(config))
    engine: sa.engine.Engine = pg_engine(
        database=documents[0].get("database", documents[0]["index"])
    )

    Session = sessionmaker(bind=engine, autoflush=True)
    session = Session()

    nodes: List[Node] = [
        Node(id=1, name="Node A"),
        Node(id=2, name="Node B"),
        Node(id=3, name="Node C"),
        Node(id=4, name="Node A_A", node_id=1),
        Node(id=5, name="Node B_B", node_id=2),
        Node(id=6, name="Node C_C", node_id=3),
        Node(id=7, name="Node A_A_A", node_id=4),
        Node(id=8, name="Node B_B_B", node_id=5),
        Node(id=9, name="Node C_C_C", node_id=6),
    ]
    with subtransactions(session):
        session.add_all(nodes)


if __name__ == "__main__":
    main()
