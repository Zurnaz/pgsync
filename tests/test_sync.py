"""Sync tests."""
from collections import namedtuple

import pytest
from mock import ANY, patch

from pgsync.exc import RDSError, SchemaError
from pgsync.settings import LOGICAL_SLOT_CHUNK_SIZE
from pgsync.sync import Sync

ROW = namedtuple("Row", ["data", "xid"])


@pytest.mark.usefixtures("table_creator")
class TestSync(object):
    """Sync tests."""

    def test_logical_slot_changes(self, sync):
        with patch("pgsync.sync.Sync.logical_slot_peek_changes") as mock_peek:
            mock_peek.side_effect = [
                [ROW("BEGIN: blah", 1234)],
                [],
            ]
            with patch("pgsync.sync.Sync.sync") as mock_sync:
                sync.logical_slot_changes()
                mock_peek.assert_any_call(
                    "testdb_testdb",
                    txmin=None,
                    txmax=None,
                    upto_nchanges=None,
                    limit=LOGICAL_SLOT_CHUNK_SIZE,
                    offset=0,
                )
                mock_sync.assert_not_called()

        with patch("pgsync.sync.Sync.logical_slot_peek_changes") as mock_peek:
            mock_peek.side_effect = [
                [ROW("COMMIT: blah", 1234)],
                [],
            ]
            with patch("pgsync.sync.Sync.sync") as mock_sync:
                sync.logical_slot_changes()
                mock_peek.assert_any_call(
                    "testdb_testdb",
                    txmin=None,
                    txmax=None,
                    upto_nchanges=None,
                    limit=LOGICAL_SLOT_CHUNK_SIZE,
                    offset=0,
                )
                mock_sync.assert_not_called()

        with patch("pgsync.sync.Sync.logical_slot_peek_changes") as mock_peek:
            mock_peek.side_effect = [
                [
                    ROW(
                        "table public.book: INSERT: id[integer]:10 isbn[character "  # noqa E501
                        "varying]:'888' title[character varying]:'My book title' "  # noqa E501
                        "description[character varying]:null copyright[character "  # noqa E501
                        "varying]:null tags[jsonb]:null publisher_id[integer]:null",  # noqa E501
                        1234,
                    ),
                ],
                [],
            ]

            with patch(
                "pgsync.sync.Sync.logical_slot_get_changes"
            ) as mock_get:
                with patch("pgsync.sync.Sync.sync") as mock_sync:
                    sync.logical_slot_changes()
                    mock_peek.assert_any_call(
                        "testdb_testdb",
                        txmin=None,
                        txmax=None,
                        upto_nchanges=None,
                        limit=LOGICAL_SLOT_CHUNK_SIZE,
                        offset=0,
                    )
                    mock_get.assert_called_once()
                    mock_sync.assert_called_once()
        sync.es.close()

    @patch("pgsync.sync.ElasticHelper")
    def test_sync_validate(self, mock_es):
        with pytest.raises(SchemaError) as excinfo:
            Sync(
                document={
                    "index": "testdb",
                    "nodes": ["foo"],
                },
                verbose=False,
                validate=True,
                repl_slots=False,
            )
        assert "Incompatible schema. Please run v2 schema migration" in str(
            excinfo.value
        )

        Sync(
            document={
                "index": "testdb",
                "nodes": {"table": "book"},
                "plugins": ["Hero"],
            },
            verbose=False,
            validate=True,
            repl_slots=False,
        )

        def _side_effect(*args, **kwargs):
            if args[0] == 0:
                return 0
            elif args[0] == "max_replication_slots":
                raise RuntimeError(
                    "Ensure there is at least one replication slot defined "
                    "by setting max_replication_slots=1"
                )

            elif args[0] == "wal_level":
                raise RuntimeError(
                    "Enable logical decoding by setting wal_level=logical"
                )
            elif args[0] == "rds_logical_replication":
                raise RDSError("rds.logical_replication is not enabled")
            else:
                return args[0]

        with pytest.raises(RuntimeError) as excinfo:
            with patch(
                "pgsync.base.Base.pg_settings",
                side_effects=_side_effect("max_replication_slots"),
            ):
                Sync(
                    document={
                        "index": "testdb",
                        "nodes": {"table": "book"},
                        "plugins": ["Hero"],
                    },
                )
        assert (
            "Ensure there is at least one replication slot defined "
            "by setting max_replication_slots=1" in str(excinfo.value)
        )

        with pytest.raises(RuntimeError) as excinfo:
            with patch(
                "pgsync.base.Base.pg_settings",
                side_effects=_side_effect("wal_level"),
            ):
                Sync(
                    document={
                        "index": "testdb",
                        "nodes": {"table": "book"},
                        "plugins": ["Hero"],
                    },
                )
        assert "Enable logical decoding by setting wal_level=logical" in str(
            excinfo.value
        )

        with pytest.raises(RDSError) as excinfo:
            with patch(
                "pgsync.base.Base.pg_settings",
                side_effects=_side_effect("rds_logical_replication"),
            ):
                Sync(
                    document={
                        "index": "testdb",
                        "nodes": {"table": "book"},
                        "plugins": ["Hero"],
                    },
                )
        assert "rds.logical_replication is not enabled" in str(excinfo.value)

    def test_status(self, sync):
        with patch("pgsync.sync.sys") as mock_sys:
            sync._status("mydb")
            mock_sys.stdout.write.assert_called_once_with(
                "mydb testdb "
                "Xlog: [0] => "
                "Db: [0] => "
                "Redis: [total = 0 "
                "pending = 0] => "
                "Elastic: [0] ...\n"
            )
        sync.es.close()

    @patch("pgsync.sync.logger")
    def test_truncate_slots(self, mock_logger, sync):
        with patch("pgsync.sync.Sync.logical_slot_get_changes") as mock_get:
            sync._truncate = True
            sync._truncate_slots()
            mock_get.assert_called_once_with(
                "testdb_testdb", upto_nchanges=None
            )
            mock_logger.debug.assert_called_once_with(
                "Truncating replication slot: testdb_testdb"
            )
        sync.es.close()

    @patch("pgsync.sync.ElasticHelper.bulk")
    @patch("pgsync.sync.logger")
    def test_pull(self, mock_logger, mock_es, sync):
        with patch("pgsync.sync.Sync.logical_slot_changes") as mock_get:
            sync.pull()
            txmin = None
            txmax = sync.txid_current - 1
            mock_get.assert_called_once_with(txmin=txmin, txmax=txmax)
            mock_logger.debug.assert_called_once_with(
                f"pull txmin: {txmin} - txmax: {txmax}"
            )
            assert sync.checkpoint == txmax
            assert sync._truncate is True
            mock_es.assert_called_once_with("testdb", ANY)
        sync.es.close()

    @patch("pgsync.sync.ElasticHelper.bulk")
    @patch("pgsync.sync.logger")
    def test_on_publish(self, mock_logger, mock_es, sync):
        payloads = [
            {
                "schema": "public",
                "tg_op": "INSERT",
                "table": "book",
                "old": {"isbn": "001"},
                "new": {"isbn": "0001"},
                "xmin": 1234,
            },
            {
                "schema": "public",
                "tg_op": "INSERT",
                "table": "book",
                "old": {"isbn": "002"},
                "new": {"isbn": "0002"},
                "xmin": 1234,
            },
            {
                "schema": "public",
                "tg_op": "INSERT",
                "table": "book",
                "old": {"isbn": "003"},
                "new": {"isbn": "0003"},
                "xmin": 1234,
            },
        ]
        sync._on_publish(payloads)
        mock_logger.debug.assert_any_call("on_publish len 3")
        assert sync.checkpoint == 1233
        mock_es.assert_called_once_with("testdb", ANY)
        sync.es.close()

    @patch("pgsync.sync.ElasticHelper.bulk")
    @patch("pgsync.sync.logger")
    def test_on_publish_mixed_ops(self, mock_logger, mock_es, sync):
        payloads = [
            {
                "schema": "public",
                "tg_op": "INSERT",
                "table": "book",
                "old": {"isbn": "001"},
                "new": {"isbn": "0001"},
                "xmin": 1234,
            },
            {
                "schema": "public",
                "tg_op": "UPDATE",
                "table": "book",
                "old": {"isbn": "002"},
                "new": {"isbn": "0002"},
                "xmin": 1234,
            },
            {
                "schema": "public",
                "tg_op": "DELETE",
                "table": "book",
                "old": {"isbn": "003"},
                "new": {"isbn": "0003"},
                "xmin": 1234,
            },
        ]
        sync._on_publish(payloads)
        mock_logger.debug.assert_any_call("on_publish len 3")
        assert sync.checkpoint == 1233
        mock_es.debug.call_count == 3
        mock_es.assert_any_call("testdb", ANY)
        sync.es.close()
