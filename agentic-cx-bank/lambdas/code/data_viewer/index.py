"""
lambdas/code/data_viewer/index.py — demo data viewer.

Renders the three banking DynamoDB tables (accounts, products, cards) as a
single styled HTML page. Invoked through a CloudFront behavior (path /datos*)
backed by a Lambda Function URL with OAC (AWS_IAM auth — not publicly
reachable).

Read-only: the function is granted dynamodb:Scan on the three tables only. The
table names arrive via environment variables (set from config in the
webhosting construct).
"""

import decimal
import html
import json
import os

import boto3

_ddb = boto3.resource("dynamodb")

# (display title, env var holding the table name)
_TABLES = [
    ("Cuentas (accounts)", "ACCOUNTS_TABLE"),
    ("Productos (products)", "PLANS_TABLE"),
    ("Tarjetas (cards)", "LINES_TABLE"),
]


def _scan_all(table_name):
    """Scan a table fully, following pagination."""
    table = _ddb.Table(table_name)
    items = []
    resp = table.scan()
    items.extend(resp.get("Items", []))
    while "LastEvaluatedKey" in resp:
        resp = table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"])
        items.extend(resp.get("Items", []))
    return items


def _fmt(value):
    """Render a single attribute value as an HTML-safe string."""
    if value is None:
        return ""
    if isinstance(value, decimal.Decimal):
        if value == value.to_integral_value():
            return str(int(value))
        return str(value)
    if isinstance(value, bool):
        return "sí" if value else "no"
    if isinstance(value, (dict, list, set)):
        if isinstance(value, set):
            value = list(value)
        return html.escape(json.dumps(value, ensure_ascii=False, default=str))
    return html.escape(str(value))


def _ordered_columns(items):
    """Union of keys across items, preserving first-seen order."""
    cols = []
    for item in items:
        for key in item.keys():
            if key not in cols:
                cols.append(key)
    return cols


def _table_section(title, items):
    if not items:
        return (
            f"<section class='tbl'><h2>{html.escape(title)}</h2>"
            f"<p class='empty'>Sin registros.</p></section>"
        )
    cols = _ordered_columns(items)
    head = "".join(f"<th>{html.escape(c)}</th>" for c in cols)
    rows = []
    for item in items:
        cells = "".join(f"<td>{_fmt(item.get(c))}</td>" for c in cols)
        rows.append(f"<tr>{cells}</tr>")
    return (
        f"<section class='tbl'>"
        f"<h2>{html.escape(title)}<span class='count'>{len(items)}</span></h2>"
        f"<div class='wrap'><table><thead><tr>{head}</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div></section>"
    )


_PAGE = """<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Latam Banco | Datos demo</title>
<style>
:root{--morado:#1a0052;--rosa:#e60050;--bg:#f5f4fb;--line:#e3e0ef;}
*{box-sizing:border-box;}
body{margin:0;font-family:Arial,Helvetica,sans-serif;background:var(--bg);color:#1c1c28;}
header.top{background:var(--morado);color:#fff;padding:20px 24px;}
header.top h1{margin:0;font-size:20px;}
header.top p{margin:6px 0 0;opacity:.8;font-size:13px;}
header.top a{color:#fff;text-decoration:underline;font-size:13px;}
main{padding:24px;max-width:1200px;margin:0 auto;}
.tbl{background:#fff;border:1px solid var(--line);border-radius:12px;margin:0 0 24px;
  overflow:hidden;box-shadow:0 1px 3px rgba(26,0,82,.06);}
.tbl h2{margin:0;padding:14px 18px;font-size:16px;background:linear-gradient(90deg,var(--morado),#3a1a8a);
  color:#fff;display:flex;align-items:center;gap:10px;}
.count{background:var(--rosa);color:#fff;border-radius:999px;padding:2px 10px;font-size:12px;font-weight:bold;}
.wrap{overflow-x:auto;}
table{border-collapse:collapse;width:100%;font-size:13px;}
th,td{padding:9px 14px;text-align:left;border-bottom:1px solid var(--line);white-space:nowrap;}
th{background:#efeaf9;color:var(--morado);font-weight:bold;position:sticky;top:0;}
tbody tr:nth-child(even){background:#faf9fe;}
tbody tr:hover{background:#fdeef4;}
.empty{padding:16px 18px;color:#8a8699;margin:0;}
footer{text-align:center;color:#8a8699;font-size:12px;padding:16px;}
</style></head>
<body>
<header class="top">
  <h1>Latam Banco — Datos demo</h1>
  <p>Contenido de las tablas DynamoDB del backend (solo lectura). <a href="/">Volver al sitio</a></p>
</header>
<main>{CONTENT}</main>
<footer>Datos de demostración · Latam Banco</footer>
</body></html>"""


def handler(event, context):
    try:
        sections = []
        for title, env_var in _TABLES:
            table_name = os.environ[env_var]
            sections.append(_table_section(title, _scan_all(table_name)))
        body = _PAGE.replace("{CONTENT}", "".join(sections))
        status = 200
    except Exception as exc:  # noqa: BLE001 - surface the error in the page
        body = _PAGE.replace(
            "{CONTENT}",
            f"<section class='tbl'><h2>Error</h2>"
            f"<p class='empty'>{html.escape(str(exc))}</p></section>",
        )
        status = 500
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "text/html; charset=utf-8",
            "Cache-Control": "no-store",
        },
        "body": body,
    }
