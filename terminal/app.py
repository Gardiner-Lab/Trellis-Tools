"""
HPC Terminal: a terminal in the browser on the lab's HPC machines, over SSH.

Members save connections (who they log in as, on which machine) and open them from a link; the
session runs on the server and carries on with the browser closed, so long work can be started and
come back to. Scripts and session text can be saved to the Lab Notebook, under the day they ran
(done in the browser, through the notebook's own API, as the other tools do).

Only machines an administrator has added can be reached, each checked against the host key it was
added with: this is not a way into anything else on the network, and nothing runs on this server.
No password, code or private key is kept (sessions.py).

Signed in by the suite: nginx asks the sign-in service and passes the member as X-Suite-User.
"""
import asyncio
import json
import os
import re
import sqlite3
import stat as stat_module
import time
from pathlib import Path
from typing import Optional

import asyncssh
from aiohttp import WSMsgType, web

import notebook
import pages
from sessions import SessionError, Sessions
from store import Store

APP_VERSION = '2.53.0'
HERE = Path(__file__).parent
MAX_SCRIPT_BYTES = 1024 * 1024
HOSTNAME = re.compile(r'^[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$|^\[?[0-9A-Fa-f:.]+\]?$')
USERNAME = re.compile(r'^[A-Za-z0-9._][A-Za-z0-9._-]{0,63}$')


# --- who is asking ----------------------------------------------------------------------------------

def member(request) -> str:
    user = (request.headers.get('X-Suite-User') or '').strip()
    if not user:
        raise web.HTTPUnauthorized(text=json.dumps({'error': 'Sign-in required.'}), content_type='application/json')
    return user


def is_admin(username: str) -> bool:
    """A suite administrator, from MoClo's account directory (users.is_admin), read-only."""
    path = os.environ.get('MOCLO_DB', '/moclo/moclo.db')
    try:
        conn = sqlite3.connect(f'file:{path}?mode=ro', uri=True, timeout=5)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        return False
    return bool(row is not None and 'is_admin' in row.keys() and row['is_admin'])


def same_origin(request) -> None:
    """A change, or a terminal, only from this site's own pages: a page elsewhere cannot use the member's sign-in."""
    origin = request.headers.get('Origin')
    if origin is None:
        return

    def name(value: str) -> str:
        # The proxy passes the host name without its port ($host); the browser's Origin has the port.
        value = re.sub(r'^[a-z]+://', '', value.strip().lower()).split('/')[0]
        return value[1:value.index(']')] if value.startswith('[') and ']' in value else value.split(':')[0]
    if name(origin) != name(request.headers.get('Host') or ''):
        raise web.HTTPForbidden(text=json.dumps({'error': 'Not from this site.'}), content_type='application/json')


def fail(status: int, message: str):
    return web.json_response({'error': message}, status=status)


def _body(request) -> dict:
    return request['body'] if 'body' in request else {}


# --- machines (administrators) -----------------------------------------------------------------------

async def scan_host_key(hostname: str, port: int):
    """The machine's host key, as it gives it now: (OpenSSH line, SHA256 fingerprint)."""
    key = await asyncio.wait_for(asyncssh.get_server_host_key(hostname, port), timeout=20)
    if key is None:
        raise SessionError('The machine gave no host key.')
    return key.export_public_key('openssh').decode().strip(), key.get_fingerprint('sha256')


def host_view(h: dict) -> dict:
    return {k: h[k] for k in ('id', 'name', 'hostname', 'port', 'fingerprint', 'note', 'added_by', 'added_at')}


def connection_view(c: dict, request) -> dict:
    prefix = request.app['prefix']
    return {'id': c['id'], 'label': c['label'], 'username': c['username'], 'host_id': c['host_id'],
            'host_name': c['host_name'], 'hostname': c['hostname'], 'port': c['port'], 'tmux': bool(c['tmux']),
            'record': bool(c.get('record', 1)),
            'created_at': c['created_at'], 'last_used': c['last_used'], 'link': f'{prefix}/c/{c["id"]}'}


# --- the application ---------------------------------------------------------------------------------

def create_app(data_dir: Optional[Path] = None, prefix: Optional[str] = None, keep_hours: Optional[float] = None,
               idle_seconds: Optional[float] = None) -> web.Application:
    app = web.Application(middlewares=[_json_body])
    app['prefix'] = (prefix if prefix is not None else os.environ.get('URL_PREFIX', '/terminal')).rstrip('/')
    app['store'] = Store(Path(data_dir or os.environ.get('TERMINAL_DATA', '/terminal-data')) / 'terminal.db')
    app['sessions'] = Sessions(keep_hours=float(keep_hours if keep_hours is not None else
                                                os.environ.get('KEEP_HOURS', '0')),
                               per_member=int(os.environ.get('SESSIONS_PER_MEMBER', '6')))
    app['notebook'] = os.environ.get('NOTEBOOK_URL', '/notebook').rstrip('/')
    # A terminal left without a key pressed or the mouse moved this long is locked: the page lets go of
    # the session (which carries on) and signs out, so a computer walked away from is not a way onto
    # the lab's machines. 0 turns it off.
    app['idle'] = float(idle_seconds if idle_seconds is not None else
                        float(os.environ.get('IDLE_MINUTES', '5')) * 60)
    # Each session's transcript, to its member's notebook when it ends, and at midnight while it runs.
    async def at_end(session):
        if session.was_open and session.connection.get('record'):
            return await notebook.record(session, final=True)
    app['sessions'].on_end = at_end
    app['sessions'].daily = lambda session, day: notebook.record(session, final=False, day=day)
    app['login'] = os.environ.get('SUITE_LOGIN_URL', '/account/login')
    app['logout'] = os.environ.get('SUITE_LOGOUT_API', '/account/api/logout')

    r = app.router
    r.add_get('/health', health)
    r.add_get('/', page_home)
    r.add_get('/c/{id}', page_terminal)
    r.add_get('/s/{id}', page_terminal)
    r.add_get('/help', page_help)
    r.add_get('/about', page_about)
    r.add_static('/static', HERE / 'static')
    r.add_get('/api/me', api_me)
    r.add_get('/api/hosts', api_hosts)
    r.add_post('/api/hosts', api_add_host)
    r.add_post('/api/hosts/{id}/rescan', api_rescan_host)
    r.add_delete('/api/hosts/{id}', api_remove_host)
    r.add_get('/api/connections', api_connections)
    r.add_post('/api/connections', api_add_connection)
    r.add_patch('/api/connections/{id}', api_update_connection)
    r.add_delete('/api/connections/{id}', api_remove_connection)
    r.add_get('/api/sessions', api_sessions)
    r.add_post('/api/sessions/{id}/close', api_close_session)
    r.add_get('/api/sessions/{id}/files', api_files)
    r.add_get('/api/sessions/{id}/file', api_file)
    r.add_get('/api/ws', websocket)
    app.on_startup.append(_start_tidying)
    app.on_shutdown.append(_stop)
    return app


@web.middleware
async def _json_body(request, handler):
    if request.method in ('POST', 'PATCH', 'DELETE'):
        same_origin(request)
        if request.can_read_body:
            try:
                body = await request.json()
            except (ValueError, UnicodeDecodeError):
                return fail(400, 'The request was not JSON.')
            request['body'] = body if isinstance(body, dict) else {}
    return await handler(request)


async def _start_tidying(app):
    async def loop():
        while True:
            await asyncio.sleep(60)
            await app['sessions'].record_days()
            await app['sessions'].tidy()
    app['tidier'] = asyncio.ensure_future(loop())


async def _stop(app):
    app['tidier'].cancel()
    await app['sessions'].close_all()


async def health(request):
    return web.json_response({'status': 'healthy', 'service': 'terminal', 'version': APP_VERSION})


# --- pages ---

def _page(request, html: str):
    return web.Response(text=html, content_type='text/html', headers={
        'Content-Security-Policy': "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
                                   "connect-src 'self'; frame-ancestors 'self'",
        'X-Content-Type-Options': 'nosniff'})


async def page_home(request):
    user = member(request)
    return _page(request, pages.home(request.app['prefix'], request.app['notebook'], user, is_admin(user)))


async def page_terminal(request):
    user = member(request)
    return _page(request, pages.terminal(request.app['prefix'], request.app['notebook'], user, request.app['idle'],
                                         request.app['login'], request.app['logout']))


async def page_help(request):
    member(request)
    return _page(request, pages.help_page(request.app['prefix']))


async def page_about(request):
    member(request)
    return _page(request, pages.about_page(request.app['prefix'], APP_VERSION))


# --- api: me and machines ---

async def api_me(request):
    user = member(request)
    return web.json_response({'user': user, 'admin': is_admin(user), 'notebook': request.app['notebook']})


async def api_hosts(request):
    member(request)
    return web.json_response([host_view(h) for h in request.app['store'].hosts()])


async def api_add_host(request):
    user = member(request)
    if not is_admin(user):
        return fail(403, 'Only an administrator can add a machine.')
    b = _body(request)
    name = str(b.get('name') or '').strip()[:80]
    hostname = str(b.get('hostname') or '').strip()
    try:
        port = int(b.get('port') or 22)
    except (TypeError, ValueError):
        port = 0
    if not name or not HOSTNAME.match(hostname) or not 0 < port < 65536:
        return fail(400, 'Give the machine a name, its host name or address, and its SSH port.')
    hostname = hostname.strip('[]')
    try:
        line, fingerprint = await scan_host_key(hostname, port)
    except (OSError, asyncio.TimeoutError, asyncssh.Error, SessionError) as exc:
        return fail(400, f'Could not read the host key of {hostname}:{port}: {exc}')
    try:
        host = request.app['store'].add_host(name, hostname, port, line, fingerprint, str(b.get('note') or '')[:300], user)
    except sqlite3.IntegrityError:
        return fail(409, 'That machine is added already.')
    return web.json_response(host_view(host), status=201)


async def api_rescan_host(request):
    """After the machine was reinstalled: its host key read again, to compare with its own and accept."""
    user = member(request)
    if not is_admin(user):
        return fail(403, 'Only an administrator can change a machine.')
    store = request.app['store']
    host = store.host(request.match_info['id'])
    if host is None:
        return fail(404, 'No such machine.')
    try:
        line, fingerprint = await scan_host_key(host['hostname'], host['port'])
    except (OSError, asyncio.TimeoutError, asyncssh.Error, SessionError) as exc:
        return fail(400, f'Could not read its host key: {exc}')
    if _body(request).get('accept') == fingerprint:
        store.set_host_key(host['id'], line, fingerprint)
        return web.json_response({**host_view(store.host(host['id'])), 'changed': fingerprint != host['fingerprint']})
    # Not yet accepted: what it gives now, to compare before accepting.
    return web.json_response({'fingerprint': fingerprint, 'was': host['fingerprint'],
                              'changed': fingerprint != host['fingerprint']})


async def api_remove_host(request):
    user = member(request)
    if not is_admin(user):
        return fail(403, 'Only an administrator can remove a machine.')
    if not request.app['store'].remove_host(request.match_info['id']):
        return fail(404, 'No such machine.')
    return web.json_response({'removed': True})


# --- api: each member's connections ---

async def api_connections(request):
    user = member(request)
    return web.json_response([connection_view(c, request) for c in request.app['store'].connections(user)])


def _connection_fields(b: dict, store: Store, partial: bool = False):
    out = {}
    if 'username' in b or not partial:
        username = str(b.get('username') or '').strip()
        if not USERNAME.match(username):
            raise ValueError('Give the user name you log in to the machine with.')
        out['username'] = username
    if 'label' in b or not partial:
        out['label'] = str(b.get('label') or '').strip()[:80]
    if 'tmux' in b or not partial:
        out['tmux'] = b.get('tmux') is not False
    if 'record' in b or not partial:
        out['record'] = b.get('record') is not False
    if not partial:
        if store.host(str(b.get('host_id') or '')) is None:
            raise ValueError('Choose one of the lab’s machines.')
        out['host_id'] = str(b['host_id'])
    return out


async def api_add_connection(request):
    user = member(request)
    store = request.app['store']
    try:
        f = _connection_fields(_body(request), store)
    except ValueError as exc:
        return fail(400, str(exc))
    host = store.host(f['host_id'])
    label = f['label'] or f"{f['username']}@{host['name']}"
    c = store.add_connection(user, f['host_id'], f['username'], label, f['tmux'], f['record'])
    return web.json_response(connection_view(c, request), status=201)


async def api_update_connection(request):
    user = member(request)
    store = request.app['store']
    try:
        f = _connection_fields(_body(request), store, partial=True)
    except ValueError as exc:
        return fail(400, str(exc))
    if 'label' in f and not f['label']:
        del f['label']
    c = store.update_connection(request.match_info['id'], user, **f)
    if c is None:
        return fail(404, 'No such connection.')
    return web.json_response(connection_view(c, request))


async def api_remove_connection(request):
    user = member(request)
    if not request.app['store'].remove_connection(request.match_info['id'], user):
        return fail(404, 'No such connection.')
    return web.json_response({'removed': True})


# --- api: sessions ---

async def api_sessions(request):
    user = member(request)
    mine = sorted(request.app['sessions'].mine(user), key=lambda s: s.started, reverse=True)
    return web.json_response([s.info() for s in mine])


def _own_session(request):
    user = member(request)
    s = request.app['sessions'].get(request.match_info['id'], user)
    if s is None:
        raise web.HTTPNotFound(text=json.dumps({'error': 'No such session.'}), content_type='application/json')
    return s


async def api_close_session(request):
    s = _own_session(request)
    await s.close('Closed from the browser.')
    return web.json_response(s.info())


async def api_files(request):
    """A folder on the machine, for choosing a script to save: folders first, then files."""
    s = _own_session(request)
    path = request.query.get('path') or '.'
    try:
        async with await s.sftp() as sftp:
            where = await sftp.realpath(path)
            entries = []
            for e in await sftp.readdir(where):
                if e.filename in ('.', '..'):
                    continue
                mode = e.attrs.permissions or 0
                entries.append({'name': e.filename, 'dir': stat_module.S_ISDIR(mode),
                                'size': e.attrs.size, 'modified': e.attrs.mtime})
    except SessionError as exc:
        return fail(409, str(exc))
    except (asyncssh.SFTPError, OSError) as exc:
        return fail(400, f'Could not read {path}: {getattr(exc, "reason", exc)}')
    entries.sort(key=lambda e: (not e['dir'], e['name'].lower()))
    return web.json_response({'path': where, 'entries': entries[:2000]})


async def api_file(request):
    """A script's text, read from the machine, for a notebook page."""
    s = _own_session(request)
    path = request.query.get('path') or ''
    if not path:
        return fail(400, 'Choose a file.')
    try:
        async with await s.sftp() as sftp:
            where = await sftp.realpath(path)
            attrs = await sftp.stat(where)
            if stat_module.S_ISDIR(attrs.permissions or 0):
                return fail(400, 'That is a folder.')
            if (attrs.size or 0) > MAX_SCRIPT_BYTES:
                return fail(400, 'Larger than 1 MB: not a script to put on a notebook page.')
            async with sftp.open(where, 'rb') as fh:
                data = await fh.read(MAX_SCRIPT_BYTES + 1)
    except SessionError as exc:
        return fail(409, str(exc))
    except (asyncssh.SFTPError, OSError) as exc:
        return fail(400, f'Could not read {path}: {getattr(exc, "reason", exc)}')
    if b'\0' in data[:8192]:
        return fail(400, 'Not a text file.')
    return web.json_response({'path': where, 'name': where.rsplit('/', 1)[-1],
                              'text': data.decode('utf-8', errors='replace'),
                              'modified': time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(attrs.mtime or 0)),
                              'modified_day': time.strftime('%Y-%m-%d', time.localtime(attrs.mtime or 0))})


# --- the terminal itself ---

async def websocket(request):
    """
    ?connection=ID opens that connection: the member's session on it that is still going, or a new one
    (&new=1 for a second). ?session=ID attaches to a session. Text frames are JSON: from the browser
    {"t":"in","d":text}, {"t":"resize","cols":n,"rows":n} and {"t":"active"} (the mouse moved, say);
    to it, {"t":"status",...}, {"t":"error","message":...} and {"t":"locked"}. Binary frames are the
    terminal's output.

    With nothing typed and no activity for the idle time, the browser is told it is locked and let go
    of; the session carries on. The page then signs out (static/terminal.js), but the server does not
    rely on it: a page that does not lock is let go of all the same.
    """
    user = member(request)
    same_origin(request)
    sessions = request.app['sessions']
    ws = web.WebSocketResponse(heartbeat=30, max_msg_size=1024 * 1024)
    await ws.prepare(request)
    try:
        cols, rows = int(request.query.get('cols', 100)), int(request.query.get('rows', 30))
    except ValueError:
        cols, rows = 100, 30
    session = None
    try:
        if request.query.get('session'):
            session = sessions.get(request.query['session'], user)
            if session is None:
                await ws.send_str(json.dumps({'t': 'error', 'message': 'That session is not yours, or has gone.'}))
                return ws
        else:
            c = request.app['store'].connection(request.query.get('connection', ''), user)
            if c is None:
                await ws.send_str(json.dumps({'t': 'error', 'message': 'That connection is not yours, or was removed.'}))
                return ws
            session = None if request.query.get('new') else sessions.live_for(user, c['id'])
            if session is None:
                try:
                    session = sessions.open(user, c, cols, rows)
                except SessionError as exc:
                    await ws.send_str(json.dumps({'t': 'error', 'message': str(exc)}))
                    return ws
                request.app['store'].used(c['id'])
        await session.attach(ws)
        session.resize(cols, rows)
        last = [time.monotonic()]
        idle = request.app['idle']

        async def watch():
            while not ws.closed:
                await asyncio.sleep(min(15.0, max(0.2, idle / 4)))
                if time.monotonic() - last[0] >= idle:
                    session.detach(ws)
                    await ws.send_str(json.dumps({'t': 'locked', 'minutes': round(idle / 60, 1)}))
                    await ws.close()
                    return
        watcher = asyncio.ensure_future(watch()) if idle > 0 else None
        try:
            async for msg in ws:
                if msg.type != WSMsgType.TEXT:
                    continue
                try:
                    m = json.loads(msg.data)
                except ValueError:
                    continue
                if m.get('t') == 'in' and isinstance(m.get('d'), str):
                    last[0] = time.monotonic()
                    await session.typed(m['d'])
                elif m.get('t') == 'active':
                    last[0] = time.monotonic()
                elif m.get('t') == 'resize':
                    try:
                        session.resize(int(m.get('cols')), int(m.get('rows')))
                    except (TypeError, ValueError):
                        pass
        finally:
            if watcher is not None:
                watcher.cancel()
    finally:
        if session is not None:
            session.detach(ws)
    return ws


def main() -> None:
    web.run_app(create_app(), host='0.0.0.0', port=int(os.environ.get('PORT', '5009')), access_log=None)


if __name__ == '__main__':
    main()
