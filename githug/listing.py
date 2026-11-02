"""Search and sort view rows without changing their underlying records."""
from datetime import datetime


def date_value(value):
    if not value:
        return '', float('-inf')
    try:
        date = datetime.fromisoformat(value).astimezone()
        return date.strftime('%Y/%m/%d %H:%M:%S'), date.timestamp()
    except (TypeError, ValueError):
        return str(value), float('-inf')


def visible_rows(rows, query, column, descending, pinned_first=False):
    query = query.strip().casefold()
    matched = [row for row in rows if not query or query in row['search'].casefold()]
    ordered = sorted(matched, key=lambda row: row['sort'][column], reverse=descending)
    if pinned_first:
        ordered.sort(key=lambda row: not row.get('pinned', False))
    return ordered
