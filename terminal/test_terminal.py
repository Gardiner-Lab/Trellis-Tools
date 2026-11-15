"""The HPC Terminal, against a real SSH server started here (AsyncSSH), through the web service."""
import asyncio
import json
import sqlite3
import time

import asyncssh
import pytest
from aiohttp.test_utils import TestClient, TestServer

import app as terminal_app
import sessions as sessions_module

PASSWORD = 'secret'


class Server(asyncssh.SSHServer):
    def begin_auth(self, username):
        return True

    def password_auth_supported(self):
        return True

    def validate_password(self, username, password):
        return password == PASSWORD


class TwoStepServer(Server):
    """A login of two questions, as with a one-time code: the password, then the code."""

    def password_auth_supported(self):
        return False

    def kbdint_auth_supported(self):
        return True

    def get_kbdint_challenge(self, username, lang, submethods):
        self.step = 1
        return '', 'Two-step login', '', [('Password: ', False)]

    def validate_kbdint_response(self, username, responses):
        if self.step == 1:
            if responses != [PASSWORD]:
                return False
            self.step = 2
            return '', '', '', [('Verification code: ', True)]
        return responses == ['123456']


async def shell(process):
    process.stdout.write('Welcome to the test HPC\r\n$ ')
    while True:
        try:
            data = await process.stdin.read(1024)
        except asyncssh.TerminalSizeChanged:
            continue                       # a resize, taken as a real shell takes it
        except asyncssh.BreakReceived:
            break
        if not data or 'exit' in data:
            break
        process.stdout.write(data.upper())
    process.exit(0)


class World:
    """An SSH server, the account directory (ada is an administrator, bob and cy are not) and the service."""

    def __init__(self, tmp_path, server=Server, idle=None):
        self.tmp = tmp_path
        self.server = server
        self.idle = idle

    async def __aenter__(self):
        users = self.tmp / 'moclo.db'
        conn = sqlite3.connect(users)
        conn.execute('CREATE TABLE users (username TEXT, is_admin INTEGER)')
        conn.executemany('INSERT INTO users VALUES (?, ?)', [('ada', 1), ('bob', 0), ('cy', 0)])
        conn.commit()
        conn.close()
        self.mp = pytest.MonkeyPatch()
        self.mp.setenv('MOCLO_DB', str(users))
        files = self.tmp / 'home'
        (files / 'jobs').mkdir(parents=True)
        (files / 'jobs' / 'align.sh').write_text('#!/bin/sh\n#SBATCH --mem=64G\nbwa mem ref.fa reads.fq > out.sam\n')
        (files / 'big.bin').write_bytes(b'\0' * 100)
        self.key = asyncssh.generate_private_key('ssh-ed25519')
        self.ssh = await asyncssh.create_server(
            self.server, '127.0.0.1', 0, server_host_keys=[self.key], process_factory=shell,
            sftp_factory=lambda chan: asyncssh.SFTPServer(chan, chroot=str(files).encode()))
        self.port = self.ssh.sockets[0].getsockname()[1]
        self.app = terminal_app.create_app(self.tmp / 'data', prefix='/terminal', keep_hours=1, idle_seconds=self.idle)
        self.client = TestClient(TestServer(self.app))
        await self.client.start_server()
        return self

    async def __aexit__(self, *exc):
        await self.client.close()
        self.ssh.close()
        self.mp.undo()

    def call(self, method, path, user='bob', body=None, headers=None):
        h = {'X-Suite-User': user, **(headers or {})}
        return self.client.request(method, path, json=body, headers=h)

    async def machine(self):
        res = await self.call('POST', '/api/hosts', 'ada', {'name': 'Test HPC', 'hostname': '127.0.0.1', 'port': self.port})
        assert res.status == 201, await res.text()
        return await res.json()

    async def connection(self, user='bob', host=None, tmux=False):
        host = host or await self.machine()
        res = await self.call('POST', '/api/connections', user, {'host_id': host['id'], 'username': user, 'tmux': tmux})
        assert res.status == 201, await res.text()
        return await res.json()

    async def socket(self, user='bob', **query):
        return await self.client.ws_connect('/api/ws', params=query, headers={'X-Suite-User': user})


async def read_until(ws, text, timeout=10):
    """Terminal output until ``text`` appears; status messages along the way are kept too."""
    out, statuses = b'', []
    end = time.time() + timeout
    while text.encode() not in out:
        msg = await asyncio.wait_for(ws.receive(), timeout=max(0.1, end - time.time()))
        if msg.type.name == 'BINARY':
            out += msg.data
        elif msg.type.name == 'TEXT':
            statuses.append(json.loads(msg.data))
        else:
            raise AssertionError(f'closed before {text!r}: {out!r}')
    return out.decode(errors='replace'), statuses


async def send(ws, text):
    await ws.send_str(json.dumps({'t': 'in', 'd': text}))


def run(coro):
    asyncio.run(coro)


# --- machines and connections -------------------------------------------------------------------------

def test_only_administrators_add_machines_and_the_host_key_is_read(tmp_path):
    async def go():
        async with World(tmp_path) as w:
            res = await w.call('POST', '/api/hosts', 'bob', {'name': 'x', 'hostname': '127.0.0.1', 'port': w.port})
            assert res.status == 403
            host = await w.machine()
            assert host['fingerprint'] == w.key.get_fingerprint('sha256')
            assert (await w.call('POST', '/api/hosts', 'ada', {'name': 'x', 'hostname': '127.0.0.1',
                                                               'port': w.port})).status == 409
            assert (await w.call('POST', '/api/hosts', 'ada', {'name': 'x', 'hostname': 'bad host;rm',
                                                               'port': 22})).status == 400
            listed = await (await w.call('GET', '/api/hosts')).json()
            assert [h['name'] for h in listed] == ['Test HPC'] and 'host_key' not in listed[0]
            assert (await w.call('GET', '/api/hosts', '')).status == 401
    run(go())


def test_each_member_has_their_own_connections(tmp_path):
    async def go():
        async with World(tmp_path) as w:
            c = await w.connection('bob')
            assert c['link'] == f"/terminal/c/{c['id']}" and c['label'] == 'bob@Test HPC'
            assert await (await w.call('GET', '/api/connections', 'cy')).json() == []
            assert (await w.call('DELETE', f"/api/connections/{c['id']}", 'cy')).status == 404
            bad = await w.call('POST', '/api/connections', 'bob', {'host_id': 'nope', 'username': 'bob'})
            assert bad.status == 400                                 # only the lab's machines
            bad = await w.call('POST', '/api/connections', 'bob', {'host_id': c['host_id'], 'username': 'bob; ls'})
            assert bad.status == 400
            res = await w.call('PATCH', f"/api/connections/{c['id']}", 'bob', {'label': 'Cluster', 'tmux': True})
            assert (await res.json())['label'] == 'Cluster'
    run(go())


def test_changes_from_another_site_are_refused(tmp_path):
    async def go():
        async with World(tmp_path) as w:
            host = await w.machine()
            res = await w.call('POST', '/api/connections', 'bob', {'host_id': host['id'], 'username': 'bob'},
                               headers={'Origin': 'https://evil.example'})
            assert res.status == 403
            # The proxy passes the host without its port; the browser's Origin has it.
            res = await w.call('POST', '/api/connections', 'bob', {'host_id': host['id'], 'username': 'bob'},
                               headers={'Origin': 'https://127.0.0.1:8080', 'Host': '127.0.0.1'})
            assert res.status == 201
            with pytest.raises(Exception):
                await w.client.ws_connect('/api/ws', params={'connection': 'x'},
                                          headers={'X-Suite-User': 'bob', 'Origin': 'https://evil.example'})
    run(go())


# --- the terminal --------------------------------------------------------------------------------------

def test_log_in_type_leave_and_come_back(tmp_path):
    async def go():
        async with World(tmp_path) as w:
            c = await w.connection('bob')
            ws = await w.socket(connection=c['id'], cols=80, rows=24)
            out, statuses = await read_until(ws, 'assword:')
            assert 'Connecting to bob@127.0.0.1' in out and any(s.get('state') == 'login' for s in statuses)
            await send(ws, PASSWORD + '\r')
            out, statuses = await read_until(ws, 'Welcome to the test HPC')
            assert PASSWORD not in out                               # never echoed
            await send(ws, 'hello\r')
            await read_until(ws, 'HELLO')
            session = statuses[-1]['id'] if statuses else None
            await ws.close()
            await asyncio.sleep(0.2)

            listed = await (await w.call('GET', '/api/sessions')).json()
            assert listed[0]['state'] == 'open' and not listed[0]['attached']
            session = listed[0]['id']
            # Back by the connection's link: the same session, its output so far sent again.
            ws = await w.socket(connection=c['id'])
            out, statuses = await read_until(ws, 'HELLO')
            assert 'Welcome to the test HPC' in out and statuses[0]['id'] == session
            # Someone else cannot attach to it, nor see it.
            other = await w.socket('cy', session=session)
            msg = json.loads((await other.receive()).data)
            assert msg['t'] == 'error'
            assert await (await w.call('GET', '/api/sessions', 'cy')).json() == []
            assert (await w.call('POST', f'/api/sessions/{session}/close', 'cy', {})).status == 404

            # A script read from the machine, for the notebook.
            res = await w.call('GET', f'/api/sessions/{session}/files?path=jobs')
            files = await res.json()
            assert res.status == 200, files
            assert [e['name'] for e in files['entries']] == ['align.sh']
            f = await (await w.call('GET', f'/api/sessions/{session}/file?path=jobs/align.sh')).json()
            assert f['name'] == 'align.sh' and '#SBATCH --mem=64G' in f['text'] and len(f['modified_day']) == 10
            assert (await w.call('GET', f'/api/sessions/{session}/file?path=big.bin')).status == 400
            assert (await w.call('GET', f'/api/sessions/{session}/file?path=jobs/align.sh', 'cy')).status == 404

            # A second session on the same connection, asked for.
            ws2 = await w.socket(connection=c['id'], new='1')
            await read_until(ws2, 'assword:')
            await ws2.close()
            assert len(await (await w.call('GET', '/api/sessions')).json()) == 2

            res = await w.call('POST', f'/api/sessions/{session}/close', 'bob', {})
            assert (await res.json())['state'] == 'closed'
            await ws.close()
    run(go())


def test_a_wrong_password_is_refused(tmp_path):
    async def go():
        async with World(tmp_path) as w:
            c = await w.connection('bob')
            ws = await w.socket(connection=c['id'])
            for _ in range(sessions_module.MAX_TRIES):
                await read_until(ws, 'assword:')
                await send(ws, 'wrong\r')
            out, _ = await read_until(ws, 'Login refused')
            assert out.count('assword:') <= 1          # asked no more than the limit
            listed = await (await w.call('GET', '/api/sessions')).json()
            assert listed[0]['state'] == 'closed'
    run(go())


def test_a_machine_with_another_host_key_is_not_logged_in_to(tmp_path):
    async def go():
        async with World(tmp_path) as w:
            host = await w.machine()
            other = asyncssh.generate_private_key('ssh-ed25519')
            w.app['store'].set_host_key(host['id'], other.export_public_key('openssh').decode(),
                                        other.get_fingerprint('sha256'))
            c = await w.connection('bob', host)
            ws = await w.socket(connection=c['id'])
            out, _ = await read_until(ws, 'different host key')
            assert 'password' not in out
            # An administrator reads it again; accepted only with the fingerprint they were shown.
            now = await (await w.call('POST', f"/api/hosts/{host['id']}/rescan", 'ada', {})).json()
            assert now['changed'] and now['fingerprint'] == w.key.get_fingerprint('sha256')
            assert (await w.call('POST', f"/api/hosts/{host['id']}/rescan", 'bob', {})).status == 403
            done = await (await w.call('POST', f"/api/hosts/{host['id']}/rescan", 'ada',
                                       {'accept': now['fingerprint']})).json()
            assert done['fingerprint'] == now['fingerprint']
            ws = await w.socket(connection=c['id'], new='1')
            await read_until(ws, 'assword:')
            await ws.close()
    run(go())


def test_sessions_left_alone_are_closed_after_a_while(tmp_path):
    async def go():
        async with World(tmp_path) as w:
            c = await w.connection('bob')
            ws = await w.socket(connection=c['id'])
            await read_until(ws, 'assword:')
            await send(ws, PASSWORD + '\r')
            await read_until(ws, 'Welcome')
            await ws.close()
            await asyncio.sleep(0.2)
            sessions = w.app['sessions']
            await sessions.tidy(now=time.time() + 30)            # within the hour kept: still open
            assert [s.state for s in sessions.mine('bob')] == ['open']
            await sessions.tidy(now=time.time() + 2 * 3600)
            assert [s.state for s in sessions.mine('bob')] == ['closed']
            assert 'no browser attached' in sessions.mine('bob')[0].reason
    run(go())


def test_the_limit_of_sessions_per_member(tmp_path):
    async def go():
        async with World(tmp_path) as w:
            c = await w.connection('bob')
            w.app['sessions'].per_member = 2
            for _ in range(2):
                ws = await w.socket(connection=c['id'], new='1')
                await read_until(ws, 'assword:')
            ws = await w.socket(connection=c['id'], new='1')
            msg = json.loads((await ws.receive()).data)
            assert msg['t'] == 'error' and 'sessions open' in msg['message']
    run(go())


def test_pages_and_health(tmp_path):
    async def go():
        async with World(tmp_path) as w:
            health = await (await w.call('GET', '/health', '')).json()
            assert health['status'] == 'healthy' and health['version'] == terminal_app.APP_VERSION
            home = await (await w.call('GET', '/', 'ada')).text()
            assert 'id="machines-card"' in home and 'data-notebook="/notebook"' in home
            assert 'id="machines-card"' not in await (await w.call('GET', '/', 'bob')).text()
            page = await (await w.call('GET', '/c/anything', 'bob')).text()
            assert 'xterm.js' in page and 'id="terminal"' in page
            assert 'data-idle="300"' in page and 'data-login="/account/login"' in page   # 5 minutes, by default
            assert (await w.call('GET', '/', '')).status == 401
            assert 'tmux' in await (await w.call('GET', '/help', 'bob')).text()
    run(go())


def test_a_login_with_a_one_time_code(tmp_path):
    async def go():
        async with World(tmp_path, TwoStepServer) as w:
            c = await w.connection('bob')
            ws = await w.socket(connection=c['id'])
            out, _ = await read_until(ws, 'Password: ')
            assert 'Two-step login' in out
            await send(ws, PASSWORD + '\r')
            await read_until(ws, 'Verification code: ')
            await send(ws, '123456\r')
            out, statuses = await read_until(ws, 'Welcome to the test HPC')
            assert '123456' in out and PASSWORD not in out          # the code is shown as typed, the password not
            assert 'Permission denied' not in out                  # two questions, not two tries
    run(go())


def test_a_terminal_left_alone_is_locked_and_the_session_carries_on(tmp_path):
    async def go():
        async with World(tmp_path, idle=1.0) as w:
            c = await w.connection('bob')
            ws = await w.socket(connection=c['id'])
            await read_until(ws, 'assword:')
            await send(ws, PASSWORD + '\r')
            await read_until(ws, 'Welcome')
            # Kept open while something happens: typing, or the page saying the mouse moved.
            for _ in range(4):
                await asyncio.sleep(0.4)
                await ws.send_str(json.dumps({'t': 'active'}))
            assert not ws.closed
            # Then nothing: locked and let go of.
            locked = None
            end = time.time() + 5
            while locked is None and time.time() < end:
                msg = await asyncio.wait_for(ws.receive(), timeout=5)
                if msg.type.name == 'TEXT' and json.loads(msg.data).get('t') == 'locked':
                    locked = json.loads(msg.data)
            assert locked is not None
            msg = await asyncio.wait_for(ws.receive(), timeout=5)
            assert msg.type.name in ('CLOSE', 'CLOSING', 'CLOSED')
            listed = await (await w.call('GET', '/api/sessions')).json()
            assert listed[0]['state'] == 'open' and not listed[0]['attached']      # still running, waiting
    run(go())


def test_a_session_left_alone_runs_on_by_default(tmp_path):
    async def go():
        sessions = sessions_module.Sessions()                 # the service's default: never closed for being left
        s = sessions_module.Session('bob', {'id': 'c', 'label': 'x', 'username': 'bob', 'hostname': 'h', 'port': 22}, 80, 24)
        s.state, s.detached_at = 'open', time.time() - 30 * 24 * 3600   # a month with no browser
        sessions.all[s.id] = s
        await sessions.tidy()
        assert s.state == 'open' and s.id in sessions.all
    run(go())


def test_what_was_printed_while_away_is_shown_on_return(tmp_path):
    async def go():
        async with World(tmp_path) as w:
            c = await w.connection('bob')
            ws = await w.socket(connection=c['id'])
            await read_until(ws, 'assword:')
            await send(ws, PASSWORD + '\r')
            await read_until(ws, 'Welcome')
            await ws.close()
            await asyncio.sleep(0.2)
            # Output arrives with no browser attached, as from a job left running.
            [session] = w.app['sessions'].mine('bob')
            for i in range(200):
                await session.output(f'step {i} done\r\n'.encode())
            # Back, from "another computer": all of it, before anything new.
            ws = await w.socket(connection=c['id'])
            out, _ = await read_until(ws, 'step 199 done')
            assert 'Welcome to the test HPC' in out and 'step 0 done' in out
            await ws.close()
    run(go())
