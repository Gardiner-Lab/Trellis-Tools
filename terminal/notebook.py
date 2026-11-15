"""
A session's transcript, written to its member's Lab Notebook: a page under the day, with the text on it
and attached as a .txt file.

Written when a session ends, and for a session still running at midnight, the day's part under that
day, so each day's notebook shows what was done that day. A member can turn it off per connection, and
can always save by hand from the terminal page as well.

The service writes as the session's member, to the notebook's own API inside the suite's network
(NOTEBOOK_INTERNAL), naming them in X-Suite-User as the suite's proxy does. Only ever for the member's
own session, and only what their terminal showed: passwords and one-time codes typed at login are never
echoed, so never in it.
"""
import html
import os
import re
import time
from typing import Optional

import aiohttp

MAX_ON_PAGE = 3000          # lines shown on the page; all of them are in the attached file

# Terminal control sequences: colours, cursor moves, titles, character sets.
_ESCAPES = re.compile(rb'\x1b\[[0-?]*[ -/]*[@-~]'          # CSI
                      rb'|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)'  # OSC (window titles)
                      rb'|\x1b[()][0-9A-Za-z]'               # character sets
                      rb'|\x1b[@-Z\\-_=>]')                  # other two-byte escapes


def plain_text(data: bytes) -> str:
    """
    What a terminal's output says, as text: control sequences dropped, a carriage return overwriting
    the line from its start (progress bars end as their last state), backspaces taken back. Full-screen
    programs (an editor, top) come out jumbled: their screens are drawn by moving the cursor about.
    """
    text = _ESCAPES.sub(b'', data).decode('utf-8', errors='replace')
    lines = []
    for raw in text.split('\n'):
        line = ''
        for part in raw.split('\r'):
            if part:
                line = part + line[len(part):]
        out = []
        for ch in line:
            if ch == '\b':
                if out:
                    out.pop()
            elif ch == '\t' or ord(ch) >= 32:
                out.append(ch)
        lines.append(''.join(out).rstrip())
    # No more than one empty line in a row.
    kept = []
    for line in lines:
        if line or (kept and kept[-1]):
            kept.append(line)
    while kept and not kept[-1]:
        kept.pop()
    return '\n'.join(kept)


def base_url() -> str:
    return os.environ.get('NOTEBOOK_INTERNAL', '').rstrip('/')


async def write_page(member: str, day: str, title: str, intro_html: str, text: str, filename: str,
                     base: Optional[str] = None, timeout: float = 30) -> str:
    """A page under ``day`` in ``member``'s notebook; returns its id. Raises on failure."""
    base = (base if base is not None else base_url()) + '/api'
    headers = {'X-Suite-User': member, 'Accept': 'application/json'}
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout), headers=headers) as http:
        async def call(method, path, **kw):
            async with http.request(method, base + path, **kw) as r:
                body = await r.json(content_type=None)
                if r.status >= 400:
                    raise RuntimeError((body or {}).get('error') or f'the notebook said {r.status}')
                return body

        day_note = (await call('POST', '/days', json={'date': day}))['note']
        page = (await call('POST', '/notes', json={'parent_id': day_note['id'], 'title': title, 'type': 'page'}))['note']
        form = aiohttp.FormData()
        form.add_field('file', text.encode('utf-8'), filename=filename, content_type='text/plain')
        attached = (await call('POST', f"/notes/{page['id']}/attachments", data=form))['attachments'][0]
        lines = text.split('\n')
        shown = text if len(lines) <= MAX_ON_PAGE else \
            f'… (the first {len(lines) - MAX_ON_PAGE:,} lines are in the file)\n' + '\n'.join(lines[-MAX_ON_PAGE:])
        body = (intro_html + f'<pre><code>{html.escape(shown)}</code></pre>' +
                f'<p>All of it: <a data-attachment="{html.escape(attached["id"])}">'
                f'{html.escape(attached.get("name") or filename)}</a></p>')
        await call('PUT', f"/notes/{page['id']}",
                   json={'title': title, 'content': [{'type': 'text', 'html': body}], 'base_version': page['version']})
        return page['id']


async def record(session, final: bool, day: Optional[str] = None, base: Optional[str] = None) -> Optional[dict]:
    """
    The part of ``session``'s transcript not yet recorded, as a page under ``day`` (today when left out):
    at the session's end (``final``), or at midnight for the day just past. Returns what was written
    ({'day', 'note'} or {'day', 'error'}), or None when there was nothing to write.
    """
    data, cut = session.unrecorded()
    text = plain_text(data)
    if not text.strip():
        session.mark_recorded()
        return None
    day = day or time.strftime('%Y-%m-%d')
    started = time.strftime('%H:%M', time.localtime(session.started))
    when = (f'Session started {time.strftime("%Y-%m-%d %H:%M", time.localtime(session.started))}' +
            (f', ended {time.strftime("%Y-%m-%d %H:%M")}' if final else ', still running at the end of the day'))
    reason = f' {session.reason}' if final and session.reason else ''
    intro = (f'<p><b>{"A terminal session" if final else "A terminal session, still running"} from the HPC Terminal:</b> '
             f'{html.escape(session.label)} ({html.escape(session.target)}). {html.escape(when)}.{html.escape(reason)}</p>')
    if session.recorded:
        intro += '<p>Continued from the page of ' + html.escape(session.recorded[-1]['day']) + '.</p>'
    if cut:
        intro += '<p>Its earliest output was no longer kept (only the last megabyte is), so the record starts partway.</p>'
    title = f'Terminal: {session.label}, {day} ' + (f'from {started}' if not session.recorded else '(continued)')
    filename = re.sub(r'[^A-Za-z0-9._-]+', '_', f'terminal_{session.label}_{day}') + '.txt'
    try:
        note = await write_page(session.owner, day, title, intro, text, filename, base=base)
        out = {'day': day, 'note': note}
    except Exception as exc:   # the session's end is never held up by the notebook: it is said, and kept
        out = {'day': day, 'error': str(exc)}
    session.mark_recorded(out)
    return out
