from __future__ import annotations

from typing import Any

from sqlalchemy import text

from app.clients.es_client import es_client_manager
from app.clients.llm_client import embedding_client
from app.clients.milvus_client import get_milvus_client
from app.conf.app_config import config
from app.core.database import engine
from app.core.log import logger
from app.nl2sql import sample_data


NL2SQL_COLUMN_COLLECTION = "nl2sql_columns"
NL2SQL_METRIC_COLLECTION = "nl2sql_metrics"
NL2SQL_VALUE_INDEX = "nl2sql_values"


class NL2SQLRepository:
    async def seed(self) -> tuple[dict[str, int], dict[str, int]]:
        async with engine.begin() as conn:
            for ddl in sample_data.TABLE_DDL:
                await conn.execute(text(ddl))

            await conn.execute(text("TRUNCATE nl2sql_table_info, nl2sql_column_info, nl2sql_metric_info, nl2sql_value_info"))

            await conn.execute(
                text("INSERT INTO nl2sql_table_info(table_name, description, aliases) VALUES (:table_name, :description, :aliases)"),
                [{"table_name": r[0], "description": r[1], "aliases": r[2]} for r in sample_data.TABLE_METADATA],
            )
            await conn.execute(
                text("""
                    INSERT INTO nl2sql_column_info(column_id, table_name, column_name, data_type, description, aliases, sample_values)
                    VALUES (:column_id, :table_name, :column_name, :data_type, :description, :aliases, :sample_values)
                """),
                [
                    {
                        "column_id": r[0],
                        "table_name": r[1],
                        "column_name": r[2],
                        "data_type": r[3],
                        "description": r[4],
                        "aliases": r[5],
                        "sample_values": r[6],
                    }
                    for r in sample_data.COLUMN_METADATA
                ],
            )
            await conn.execute(
                text("""
                    INSERT INTO nl2sql_metric_info(metric_id, metric_name, description, expression, dependencies, aliases)
                    VALUES (:metric_id, :metric_name, :description, :expression, :dependencies, :aliases)
                """),
                [
                    {
                        "metric_id": r[0],
                        "metric_name": r[1],
                        "description": r[2],
                        "expression": r[3],
                        "dependencies": r[4],
                        "aliases": r[5],
                    }
                    for r in sample_data.METRIC_METADATA
                ],
            )
            await conn.execute(
                text("""
                    INSERT INTO nl2sql_value_info(value_id, value_text, value_type, table_name, column_name, aliases)
                    VALUES (:value_id, :value_text, :value_type, :table_name, :column_name, :aliases)
                """),
                [
                    {
                        "value_id": r[0],
                        "value_text": r[1],
                        "value_type": r[2],
                        "table_name": r[3],
                        "column_name": r[4],
                        "aliases": r[5],
                    }
                    for r in sample_data.VALUE_METADATA
                ],
            )

        return await self.table_counts(), await self.metadata_counts()

    async def table_counts(self) -> dict[str, int]:
        return {}

    async def metadata_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        async with engine.connect() as conn:
            for table in ["nl2sql_table_info", "nl2sql_column_info", "nl2sql_metric_info", "nl2sql_value_info"]:
                try:
                    result = await conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                    counts[table] = int(result.scalar_one())
                except Exception:
                    counts[table] = 0
        return counts

    async def load_metadata(self) -> dict[str, list[dict[str, Any]]]:
        async with engine.connect() as conn:
            columns = (await conn.execute(text("SELECT * FROM nl2sql_column_info ORDER BY column_id"))).mappings().all()
            metrics = (await conn.execute(text("SELECT * FROM nl2sql_metric_info ORDER BY metric_id"))).mappings().all()
            values = (await conn.execute(text("SELECT * FROM nl2sql_value_info ORDER BY value_id"))).mappings().all()
        return {
            "columns": [dict(row) for row in columns],
            "metrics": [dict(row) for row in metrics],
            "values": [dict(row) for row in values],
        }

    async def explain_sql(self, sql: str) -> None:
        async with engine.connect() as conn:
            await conn.execute(text(f"EXPLAIN {sql}"))

    async def execute_sql(self, sql: str) -> tuple[list[str], list[dict[str, Any]]]:
        async with engine.connect() as conn:
            trans = await conn.begin()
            try:
                await conn.execute(text("SET TRANSACTION READ ONLY"))
                result = await conn.execute(text(sql))
                rows = [dict(row) for row in result.mappings().all()]
                columns = list(result.keys())
                await trans.commit()
                return columns, rows
            except Exception:
                await trans.rollback()
                raise

    async def seed_indexes(self) -> tuple[dict[str, Any], list[str]]:
        warnings: list[str] = []
        index_counts: dict[str, Any] = {}
        metadata = await self.load_metadata()

        try:
            index_counts.update(await self._seed_milvus(metadata["columns"], metadata["metrics"]))
        except Exception as exc:
            logger.warning(f"NL2SQL Milvus index seed failed: {exc}")
            warnings.append(f"Milvus 索引写入失败：{exc}")

        try:
            index_counts[NL2SQL_VALUE_INDEX] = await self._seed_es(metadata["values"])
        except Exception as exc:
            logger.warning(f"NL2SQL ES index seed failed: {exc}")
            warnings.append(f"Elasticsearch 枚举索引写入失败：{exc}")

        return index_counts, warnings

    async def _seed_milvus(self, columns: list[dict[str, Any]], metrics: list[dict[str, Any]]) -> dict[str, int]:
        client = get_milvus_client()
        payloads = {
            NL2SQL_COLUMN_COLLECTION: [
                {
                    "id": row["column_id"],
                    "text": f"{row['table_name']}.{row['column_name']} {row['description']} {' '.join(row.get('aliases') or [])} {' '.join(row.get('sample_values') or [])}",
                    "entity": row,
                }
                for row in columns
            ],
            NL2SQL_METRIC_COLLECTION: [
                {
                    "id": row["metric_id"],
                    "text": f"{row['metric_name']} {row['description']} {row['expression']} {' '.join(row.get('aliases') or [])}",
                    "entity": row,
                }
                for row in metrics
            ],
        }
        counts: dict[str, int] = {}
        for collection, items in payloads.items():
            if client.has_collection(collection):
                client.drop_collection(collection)
            client.create_collection(
                collection_name=collection,
                dimension=config.embedding_dimensions,
                metric_type="COSINE",
                primary_field_name="id",
                vector_field_name="embedding",
                id_type="string",
                max_length=256,
                enable_dynamic_field=True,
                consistency_level="Strong",
            )
            embeddings = await embedding_client.embed([item["text"] for item in items])
            data = []
            for item, embedding in zip(items, embeddings):
                record = {"id": item["id"], "text": item["text"], "embedding": embedding}
                record.update({k: v for k, v in item["entity"].items() if k != "id"})
                data.append(record)
            if data:
                client.insert(collection_name=collection, data=data)
            counts[collection] = len(data)
        return counts

    async def _seed_es(self, values: list[dict[str, Any]]) -> int:
        await es_client_manager.create_index(
            NL2SQL_VALUE_INDEX,
            mappings={
                "properties": {
                    "value_text": {"type": "text"},
                    "value_type": {"type": "keyword"},
                    "table_name": {"type": "keyword"},
                    "column_name": {"type": "keyword"},
                    "aliases": {"type": "text"},
                }
            },
        )
        try:
            await es_client_manager.delete_by_query(NL2SQL_VALUE_INDEX, {"match_all": {}})
        except Exception:
            pass
        for row in values:
            await es_client_manager.index_document(NL2SQL_VALUE_INDEX, row, doc_id=row["value_id"])
        return len(values)

    async def index_counts(self) -> dict[str, Any]:
        counts: dict[str, Any] = {}
        try:
            client = get_milvus_client()
            for collection in [NL2SQL_COLUMN_COLLECTION, NL2SQL_METRIC_COLLECTION]:
                if client.has_collection(collection):
                    stats = client.get_collection_stats(collection_name=collection)
                    counts[collection] = int(stats.get("row_count", 0))
                else:
                    counts[collection] = 0
        except Exception as exc:
            counts["milvus_error"] = str(exc)
        try:
            counts[NL2SQL_VALUE_INDEX] = await es_client_manager.count(NL2SQL_VALUE_INDEX)
        except Exception as exc:
            counts["elasticsearch_error"] = str(exc)
        return counts
