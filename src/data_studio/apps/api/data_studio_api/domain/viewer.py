import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import duckdb

from ..errors import ValidationError
from .layout import IMAGE_SUFFIXES, METADATA_NAMES
from .preview import _json_value


@dataclass(frozen=True)
class ViewerFilter:
    column: str
    operator: str
    expected: Any


@dataclass(frozen=True)
class ViewerPage:
    rows: list[dict[str, Any]]
    total_rows: int
    available_rows: int


def parse_viewer_filter(raw_filter: str | None, columns: set[str]) -> ViewerFilter | None:
    if not raw_filter:
        return None
    try:
        value = json.loads(raw_filter)
    except json.JSONDecodeError as exc:
        raise ValidationError("invalid_filter", "Filter must be valid JSON.") from exc
    if not isinstance(value, dict) or not {"column", "op", "value"} <= set(value):
        raise ValidationError("invalid_filter", "Filter requires column, op, and value fields.")

    column = value["column"]
    operator = value["op"]
    if not isinstance(column, str) or column not in columns:
        raise ValidationError("invalid_filter", f"Unknown filter column: {column}")
    if operator not in {"eq", "ne", "contains", "gt", "gte", "lt", "lte"}:
        raise ValidationError("invalid_filter", f"Unsupported filter operator: {operator}")
    return ViewerFilter(column, operator, value["value"])


def row_matches_filter(row: dict[str, Any], filter_: ViewerFilter | None) -> bool:
    if filter_ is None:
        return True
    actual = row.get(filter_.column)
    expected = filter_.expected
    if filter_.operator == "eq":
        return bool(actual == expected)
    if filter_.operator == "ne":
        return bool(actual != expected)
    if filter_.operator == "contains":
        return str(expected).lower() in str(actual).lower()
    if isinstance(actual, str) and isinstance(expected, str):
        if filter_.operator == "gt":
            return actual > expected
        if filter_.operator == "gte":
            return actual >= expected
        if filter_.operator == "lt":
            return actual < expected
        return actual <= expected
    if isinstance(actual, int | float) and isinstance(expected, int | float):
        if filter_.operator == "gt":
            return actual > expected
        if filter_.operator == "gte":
            return actual >= expected
        if filter_.operator == "lt":
            return actual < expected
        return actual <= expected
    return False


def page_rows(
    rows: list[dict[str, Any]],
    filter_: ViewerFilter | None,
    offset: int,
    limit: int,
) -> ViewerPage:
    filtered = [row for row in rows if row_matches_filter(row, filter_)]
    return ViewerPage(
        rows=filtered[offset : offset + limit],
        total_rows=len(rows),
        available_rows=len(filtered),
    )


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _source_query(path: Path) -> str:
    literal = _sql_literal(str(path))
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        return f"SELECT * FROM read_parquet({literal})"
    if suffix in {".csv", ".tsv"}:
        delimiter = "\t" if suffix == ".tsv" else ","
        return (
            f"SELECT * FROM read_csv_auto({literal}, "
            f"delim = {_sql_literal(delimiter)}, header = true)"
        )
    if suffix == ".jsonl":
        return (
            f"SELECT * FROM read_json_auto({literal}, "
            "format = 'newline_delimited', union_by_name = true)"
        )
    if suffix == ".json":
        return f"SELECT * FROM read_json_auto({literal}, union_by_name = true)"
    if suffix == ".txt":
        return (
            f"SELECT column0 AS text FROM read_csv({literal}, header = false, "
            "delim = '\x1f', quote = '', escape = '', columns = {'column0': 'VARCHAR'})"
        )
    raise ValidationError("unsupported_viewer_file", f"Cannot browse file type {suffix!r}.")


def _quoted_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _filter_sql(filter_: ViewerFilter | None) -> tuple[str, list[Any]]:
    if filter_ is None:
        return "", []
    column = _quoted_identifier(filter_.column)
    if filter_.operator == "contains":
        return f" WHERE CAST({column} AS VARCHAR) ILIKE ?", [f"%{filter_.expected}%"]
    if filter_.operator == "eq":
        return f" WHERE {column} IS NOT DISTINCT FROM ?", [filter_.expected]
    if filter_.operator == "ne":
        return f" WHERE {column} IS DISTINCT FROM ?", [filter_.expected]
    symbols = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
    return f" WHERE {column} {symbols[filter_.operator]} ?", [filter_.expected]


def query_tabular_page(
    files: list[Path],
    filter_: ViewerFilter | None,
    offset: int,
    limit: int,
) -> ViewerPage:
    if not files:
        return ViewerPage([], 0, 0)

    source = " UNION ALL BY NAME ".join(_source_query(path) for path in files)
    hidden_column = "__cognidoc_viewer_row"
    filter_sql, parameters = _filter_sql(filter_)
    with duckdb.connect() as connection:
        connection.execute(
            f"CREATE TEMP TABLE viewer_source AS "
            f"SELECT row_number() OVER () AS {hidden_column}, * FROM ({source})"
        )
        total_result = connection.execute("SELECT count(*) FROM viewer_source").fetchone()
        available_result = connection.execute(
            f"SELECT count(*) FROM viewer_source{filter_sql}",
            parameters,
        ).fetchone()
        if total_result is None or available_result is None:
            raise RuntimeError("Viewer row count query returned no result.")
        total_rows = int(total_result[0])
        available_rows = int(available_result[0])
        cursor = connection.execute(
            f"SELECT * EXCLUDE ({hidden_column}) FROM viewer_source"
            f"{filter_sql} ORDER BY {hidden_column} LIMIT ? OFFSET ?",
            [*parameters, limit, offset],
        )
        names = [item[0] for item in cursor.description]
        rows = [
            {name: _json_value(value) for name, value in zip(names, values, strict=True)}
            for values in cursor.fetchall()
        ]
    return ViewerPage(rows, total_rows, available_rows)


def imagefolder_page(
    repository_paths: list[str],
    metadata_path: str | None,
    metadata_page: ViewerPage | None,
    filter_: ViewerFilter | None,
    offset: int,
    limit: int,
) -> ViewerPage:
    if metadata_path is None:
        rows = [
            {
                "image": {"_type": "image", "path": path},
                "label": PurePosixPath(path).parent.name,
            }
            for path in repository_paths
            if PurePosixPath(path).suffix.lower() in IMAGE_SUFFIXES
        ]
        return page_rows(rows, filter_, offset, limit)

    if metadata_page is None:
        return ViewerPage([], 0, 0)
    image_column = next(
        (
            name
            for name in ("file_name", "image", "path")
            if any(name in row for row in metadata_page.rows)
        ),
        None,
    )
    if image_column:
        metadata_parent = PurePosixPath(metadata_path).parent
        available_paths = set(repository_paths)
        for row in metadata_page.rows:
            value = row.get(image_column)
            if isinstance(value, str):
                relative = (metadata_parent / value).as_posix()
                resolved = relative if relative in available_paths else value
                row[image_column] = {"_type": "image", "path": resolved}
    return metadata_page


def imagefolder_metadata_path(paths: list[str]) -> str | None:
    return next(
        (path for path in paths if PurePosixPath(path).name.lower() in METADATA_NAMES),
        None,
    )
