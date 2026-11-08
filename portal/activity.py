"""
What someone did in the suite: a report of their work in every tool, for the lab
lead or lab admin who archives them when they leave (and for administrators).

Each tool keeps its own database; this reads them read-only, as the tools read
each other's (the portal mounts their volumes :ro), and changes nothing. A tool
whose database is not there (not installed, or an older schema without a table
or column) is reported as such, not as an error.

What counts as someone's: what they made or own, by the column each tool keeps
for it (created_by, owner, contributor, booked_by, ...). Older records name the
person by their account id in MoClo or the editor instead of their username, so
both are matched. Deleted records are left out.

Archiving keeps a copy of the report as it was that day, in suite-data/reports
(backed up with the rest of the suite).
"""

import csv
import html
import io
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

# Where each tool's database is, as mounted in the portal (docker-compose.yml).
DATABASES = {
    'notebook': ('NOTEBOOK_DATABASE_PATH', '/notebook/notebook.db'),
    'editor': ('EDITOR_DB', '/data/plasmid_editor.db'),
    'moclo': ('MOCLO_DB', '/moclo/moclo.db'),
    'parts': ('PARTS_DB', '/moclo/parts.db'),
    'seeds': ('SEEDS_DATABASE_PATH', '/seeds/seeds.db'),
    'stocks': ('STOCKS_DATABASE_PATH', '/stocks/stocks.db'),
    'booking': ('BOOKING_DATABASE_PATH', '/booking/booking.db'),
    'genome': ('GENOME_DATABASE_PATH', '/genome/genome.db'),
}

TOOLS = ('Lab Notebook', 'Sequence Editor', 'MoClo', 'Seed Bank', 'Lab Stocks', 'Booking', 'Genome Browser')

# What is listed: (tool, what, database, table, the column naming whose it is, the columns shown as
# code, name, lab, made, changed, status; and an extra condition). None leaves a column out.
NOT_DELETED = 'deleted_at IS NULL'
SOURCES = [
    ('Lab Notebook', 'Notebook pages', 'notebook', 'notes', 'owner', None, 'title', None, 'created_at', 'updated_at', 'type',
     "space = 'notebook' AND type NOT IN ('notebook', 'year', 'month') AND deleted_at IS NULL"),
    ('Lab Notebook', 'Protocols and library pages', 'notebook', 'notes', 'created_by', None, 'title', None, 'created_at',
     'updated_at', 'type', "space = 'library' AND type <> 'library' AND deleted_at IS NULL"),
    ('Lab Notebook', 'Files attached', 'notebook', 'attachments', 'created_by', None, 'filename', None, 'created_at', None,
     'mime', NOT_DELETED),
    ('Sequence Editor', 'Sequences', 'editor', 'sequences', 'owner_id', None, 'name', None, 'created_at', 'updated_at',
     'confirmed_at', None),
    ('Sequence Editor', 'Sequencing reads', 'editor', 'reads', 'uploaded_by', None, 'name', None, 'created_at', None,
     'verdict', None),
    ('Sequence Editor', 'Gel ladders', 'editor', 'ladders', 'owner_id', None, 'name', None, 'created_at', 'updated_at',
     None, None),
    ('Sequence Editor', 'Enzyme lists', 'editor', 'enzyme_lists', 'owner_id', None, 'name', None, 'created_at',
     'updated_at', None, None),
    ('MoClo', 'Parts', 'parts', 'parts', 'contributor', None, 'name', 'lab_source', 'upload_date', None, 'part_type', None),
    ('MoClo', 'Backbones', 'moclo', 'backbones', 'owner_id', None, 'name', 'lab_source', 'created_at', None, None, None),
    ('MoClo', 'Transcription units', 'moclo', 'cassettes', 'owner_id', None, 'name', None, 'created_at', None, 'level',
     None),
    ('MoClo', 'Assembled plasmids', 'moclo', 'final_plasmids', 'owner_id', None, 'name', None, 'created_at', None, None,
     None),
    ('MoClo', 'Saved constructs', 'moclo', 'saved_items', 'user_id', None, 'title', None, 'created_at', None,
     'item_type', None),
    ('Seed Bank', 'Lines', 'seeds', 'lines', 'created_by', 'code', 'name', 'lab', 'created_at', 'updated_at', 'kind',
     NOT_DELETED),
    ('Seed Bank', 'Seed lots', 'seeds', 'lots', 'created_by', 'code', 'generation', 'lab', 'created_at', 'updated_at',
     'location', NOT_DELETED),
    ('Seed Bank', 'Plants', 'seeds', 'plants', 'created_by', 'code', 'location', 'lab', 'created_at', 'updated_at',
     'status', NOT_DELETED),
    ('Seed Bank', 'Places', 'seeds', 'places', 'created_by', None, 'name', 'lab', 'created_at', None, 'kind', NOT_DELETED),
    ('Seed Bank', 'Segregation tests', 'seeds', 'seg_tests', 'created_by', None, 'selection', None, 'created_at', None,
     None, NOT_DELETED),
    ('Lab Stocks', 'Glycerol stocks', 'stocks', 'glycerol', 'created_by', 'code', 'plasmid_name', 'lab', 'created_at',
     'updated_at', 'status', NOT_DELETED),
    ('Lab Stocks', 'Primers', 'stocks', 'primers', 'created_by', 'code', 'name', 'lab', 'created_at', 'updated_at',
     'status', NOT_DELETED),
    ('Lab Stocks', 'Chemicals', 'stocks', 'chemicals', 'created_by', 'code', 'name', 'lab', 'created_at', 'updated_at',
     'status', NOT_DELETED),
    ('Lab Stocks', 'Antibodies', 'stocks', 'antibodies', 'created_by', 'code', 'description', 'lab', 'created_at',
     'updated_at', 'status', NOT_DELETED),
    ('Lab Stocks', 'Plant material', 'stocks', 'material', 'created_by', 'code', 'name', 'lab', 'created_at',
     'updated_at', 'status', NOT_DELETED),
    ('Lab Stocks', 'Orders asked for', 'stocks', 'orders', 'requested_by', None, 'item', 'lab', 'requested_at',
     'updated_at', 'status', None),
    ('Booking', 'Bookings', 'booking', 'bookings', 'booked_by', None, 'title', None, 'starts_at', 'ends_at', 'status',
     None),
    ('Booking', 'Rooms and equipment added', 'booking', 'resources', 'created_by', None, 'name', 'owner_lab',
     'created_at', 'retired_at', 'kind', None),
    ('Genome Browser', 'Genomes', 'genome', 'reference_genomes', 'created_by', None, 'name', 'owner_lab', 'created_at',
     None, 'assembly_id', None),
    ('Genome Browser', 'Tracks', 'genome', 'tracks', 'created_by', None, 'name', 'owner_lab', 'created_at', None,
     'type', None),
]

# Counted rather than listed: many small records.
COUNTS = [
    ('Seed Bank', 'Observations scored', 'seeds', 'observations', 'created_by', NOT_DELETED),
    ('Seed Bank', 'Changes to records', 'seeds', 'changes', 'changed_by', None),
    ('Lab Stocks', 'Changes to records', 'stocks', 'changes', 'changed_by', None),
    ('Lab Notebook', 'Page revisions saved', 'notebook', 'revisions', 'changed_by', None),
    ('Sequence Editor', 'Sequence revisions saved', 'editor', 'sequence_revisions', 'changed_by', None),
]


def _path(key: str) -> str:
    env, default = DATABASES[key]
    return os.environ.get(env, default)


def _open(key: str) -> Optional[sqlite3.Connection]:
    path = _path(key)
    if not os.path.exists(path):
        return None
    try:
        conn = sqlite3.connect(f'file:{path}?mode=ro', uri=True, timeout=5)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error:
        return None


def _columns(conn, table: str) -> set:
    try:
        return {r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')}
    except sqlite3.Error:
        return set()


def _ids(conn, username: str) -> List[str]:
    """Their username, and their account id in this database's users table if it has one."""
    names = [username]
    if 'username' in _columns(conn, 'users'):
        names += [r[0] for r in conn.execute('SELECT id FROM users WHERE username = ?', (username,)) if r[0]]
    return names


def _ids_for(key: str, username: str, conns: Dict) -> List[str]:
    # Parts name their contributor by MoClo's account id when not by username.
    conn = conns.get('moclo' if key == 'parts' else key)
    return _ids(conn, username) if conn is not None else [username]


def _text(value) -> str:
    return '' if value is None else str(value)


def collect(username: str) -> Dict:
    """Everything this person made or owns, tool by tool: {'tools': [...], 'missing': [...], 'last': ...}."""
    conns = {key: _open(key) for key in DATABASES}
    try:
        tools: Dict[str, dict] = {t: {'tool': t, 'lists': [], 'counts': []} for t in TOOLS}
        seen_dbs = {key for key, conn in conns.items() if conn is not None}
        last = ''
        for tool, what, key, table, who, code, name, lab, made, changed, status, where in SOURCES:
            conn = conns.get(key)
            cols = _columns(conn, table) if conn is not None else set()
            if who not in cols:
                continue
            ids = _ids_for(key, username, conns)
            pick = {k: c if c in cols else None for k, c in
                    (('code', code), ('name', name), ('lab', lab), ('made', made), ('changed', changed), ('status', status))}
            select = ', '.join(f'"{c}" AS {k}' if c else f'NULL AS {k}' for k, c in pick.items())
            clause = f'"{who}" IN ({", ".join("?" * len(ids))})'
            if where and all(c in cols for c in re.findall(r'\b(deleted_at|space|type)\b', where)):
                clause += f' AND ({where})'
            order = f'"{pick["made"]}"' if pick['made'] else 'rowid'
            try:
                rows = conn.execute(f'SELECT {select} FROM "{table}" WHERE {clause} ORDER BY {order}', ids).fetchall()
            except sqlite3.Error:
                continue
            items = []
            for r in rows:
                item = {k: _text(r[k]) for k in pick}
                if table == 'sequences':
                    item['status'] = 'confirmed' if item['status'] else ''
                items.append(item)
                if table != 'bookings':      # a booking's times are when it is for, not when work was done
                    last = max(last, item['changed'], item['made'])
            if items:
                tools[tool]['lists'].append({'what': what, 'count': len(items), 'items': items})
        for tool, what, key, table, who, where in COUNTS:
            conn = conns.get(key)
            cols = _columns(conn, table) if conn is not None else set()
            if who not in cols:
                continue
            ids = _ids_for(key, username, conns)
            clause = f'"{who}" IN ({", ".join("?" * len(ids))})' + (f' AND ({where})' if where and 'deleted_at' in cols else '')
            try:
                n = conn.execute(f'SELECT count(*) FROM "{table}" WHERE {clause}', ids).fetchone()[0]
            except sqlite3.Error:
                continue
            if n:
                tools[tool]['counts'].append({'what': what, 'count': n})
        missing = sorted({tool for tool, _, key, *_ in SOURCES if key not in seen_dbs})
        return {'tools': [tools[t] for t in TOOLS], 'missing': missing, 'last': last}
    finally:
        for conn in conns.values():
            if conn is not None:
                conn.close()


def report(username: str, person: Dict, by: str) -> Dict:
    """The report: who they are (person: labs, archived), what they did, and when and by whom it was made."""
    found = collect(username)
    found.update({'username': username, 'person': person, 'made_by': by,
                  'made_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                  'total': sum(x['count'] for t in found['tools'] for x in t['lists'])})
    return found


# --- as a page and as a spreadsheet ---------------------------------------------------

def _day(value: str) -> str:
    return (value or '')[:10]


def as_csv(rep: Dict) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(['tool', 'what', 'code', 'name', 'lab', 'made', 'changed', 'status'])
    for tool in rep['tools']:
        for x in tool['lists']:
            for i in x['items']:
                w.writerow([tool['tool'], x['what'], i['code'], i['name'], i['lab'], i['made'], i['changed'], i['status']])
        for c in tool['counts']:
            w.writerow([tool['tool'], c['what'], '', f"{c['count']} in all", '', '', '', ''])
    return out.getvalue()


def _copies_html(rep: Dict) -> str:
    """Links to the copies kept when they were archived (only on the live report)."""
    names = rep.get('copies') or []
    if not names:
        return ''
    def when(n):
        return f'{n[0:4]}-{n[4:6]}-{n[6:8]} {n[9:11]}:{n[11:13]} UTC'
    links = ', '.join(f'<a href="?copy={html.escape(n)}">{when(n)}</a> (<a href="?copy={html.escape(n)}&amp;format=csv">CSV</a>)'
                      for n in names)
    return f'<p class="print-hide">Kept when they were archived: {links}</p>'


def as_html(rep: Dict) -> str:
    e = html.escape
    p = rep['person']
    labs = ', '.join(f"{m['lab']} ({m['role'].replace('_', ' ')})" for m in p.get('labs', [])) or 'none'
    gone = p.get('archived')
    parts = [f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Work of {e(rep['username'])}</title>
<style>
 body {{ font: 14px/1.45 system-ui, sans-serif; color: #1d2421; background: #fff; margin: 2rem auto; max-width: 960px; padding: 0 16px; }}
 h1 {{ font-size: 1.5rem; margin: 0 0 .25rem; }} h2 {{ font-size: 1.15rem; margin: 2rem 0 .5rem; border-bottom: 2px solid #3d7a55; padding-bottom: .2rem; }}
 h3 {{ font-size: 1rem; margin: 1.2rem 0 .3rem; }} .meta {{ color: #55615b; }} .none {{ color: #55615b; font-style: italic; }}
 table {{ border-collapse: collapse; width: 100%; font-size: 13px; }} th, td {{ text-align: left; padding: .25rem .5rem; border-bottom: 1px solid #dde3df; vertical-align: top; }}
 th {{ background: #f1f5f2; }} .tbl {{ overflow-x: auto; }} ul.sum {{ columns: 2; padding-left: 1.2rem; }}
 .print {{ float: right; }} @media print {{ .print, .print-hide {{ display: none; }} body {{ margin: 0; }} }}
</style></head><body>
<button class="print" onclick="print()">Print or save as PDF</button>
<h1>Work of {e(rep['username'])}</h1>
<p class="meta">Labs: {e(labs)}<br>
{('Archived ' + e(_day(gone.get('archived_at', ''))) + (' by ' + e(gone['archived_by']) if gone.get('archived_by') else '') + '<br>') if gone else ''}
Last recorded work: {e(_day(rep['last'])) or 'none found'}<br>
Report made {e(rep['made_at'].replace('T', ' ').replace('Z', ' UTC'))} by {e(rep['made_by'])}. {rep['total']} records in all.</p>
<p class="meta">Everything they made or own in each tool, as the tools record it; deleted records are left out.
Their work stays in the tools for their labs either way: this is a record of it, not a copy.</p>
<p class="print-hide"><a href="?format=csv">Download as CSV</a> (one row per record, for a spreadsheet)</p>
""" + _copies_html(rep) + """<h2>Summary</h2><ul class="sum">"""]
    for tool in rep['tools']:
        bits = [f"{x['what']} ({x['count']})" for x in tool['lists']] + \
               [f"{c['what']} ({c['count']})" for c in tool['counts']]
        parts.append(f"<li><b>{e(tool['tool'])}</b>: {e(', '.join(bits)) if bits else 'nothing'}</li>")
    parts.append('</ul>')
    if rep['missing']:
        parts.append(f"<p class=\"none\">Not found on this server, so not in the report: {e(', '.join(rep['missing']))}.</p>")
    for tool in rep['tools']:
        if not tool['lists'] and not tool['counts']:
            continue
        parts.append(f"<h2>{e(tool['tool'])}</h2>")
        for c in tool['counts']:
            parts.append(f"<p>{e(c['what'])}: <b>{c['count']}</b></p>")
        for x in tool['lists']:
            cols = [k for k in ('code', 'name', 'lab', 'made', 'changed', 'status') if any(i[k] for i in x['items'])]
            head = {'code': 'Code', 'name': 'Name', 'lab': 'Lab', 'made': 'Made', 'changed': 'Changed', 'status': 'Kind / status'}
            if x['what'] == 'Bookings':
                head.update(made='Starts', changed='Ends')
            parts.append(f"<h3>{e(x['what'])} ({x['count']})</h3><div class=\"tbl\"><table><thead><tr>"
                         + ''.join(f'<th>{head[k]}</th>' for k in cols) + '</tr></thead><tbody>')
            for i in x['items']:
                parts.append('<tr>' + ''.join(
                    f"<td>{e(_day(i[k]) if k in ('made', 'changed') and x['what'] != 'Bookings' else i[k].replace('T', ' ')[:16] if k in ('made', 'changed') else i[k])}</td>"
                    for k in cols) + '</tr>')
            parts.append('</tbody></table></div>')
    if not rep['total'] and not any(t['counts'] for t in rep['tools']):
        parts.append('<p class="none">No work of theirs was found in any tool.</p>')
    parts.append('</body></html>')
    return '\n'.join(parts)


# --- copies kept when someone is archived ---------------------------------------------

def _copies_dir(suite_db: Path, username: str) -> Path:
    return suite_db.parent / 'reports' / re.sub(r'[^A-Za-z0-9._-]', '_', username)


def keep_copy(suite_db: Path, rep: Dict) -> str:
    """Save the report as made now (HTML and CSV); returns its name, the time it was made."""
    folder = _copies_dir(suite_db, rep['username'])
    folder.mkdir(parents=True, exist_ok=True)
    name = rep['made_at'].replace(':', '').replace('-', '')
    (folder / f'{name}.html').write_text(as_html(rep), encoding='utf-8')
    (folder / f'{name}.csv').write_text(as_csv(rep), encoding='utf-8')
    return name


def copies(suite_db: Path, username: str) -> List[str]:
    folder = _copies_dir(suite_db, username)
    return sorted((p.stem for p in folder.glob('*.html')), reverse=True) if folder.exists() else []


def copy_file(suite_db: Path, username: str, name: str, fmt: str) -> Optional[Path]:
    if not re.fullmatch(r'[0-9TZ]+', name or '') or fmt not in ('html', 'csv'):
        return None
    path = _copies_dir(suite_db, username) / f'{name}.{fmt}'
    return path if path.exists() else None
