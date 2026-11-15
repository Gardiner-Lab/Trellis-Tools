"""
Terminal sessions on the lab's HPC machines, held by the server so that work goes on with the
browser closed, and the browser can come back to it.

A session is one SSH connection to an allowed machine, with a terminal (a pty) on it. Its output is
kept (the last ``SCROLLBACK`` bytes) and sent again when a browser attaches, so reopening the page
shows where things stand. One browser at a time is attached; a second takes over from the first.

Logging in happens in the terminal, as in any SSH client: the password, or each question of a
keyboard-interactive login (a one-time code, for example), is asked there, typed by the member,
passed to the machine and not kept. No private key is used or stored, and no SSH agent.

Nothing here starts a process on this server: the only thing a member's keystrokes reach is the
remote machine. With ``tmux`` on (the default), the work is started inside tmux on the machine, so it
outlives this session as well (a restart of this service, say); attaching again reattaches it.
"""
import asyncio
import json
import time
import uuid
from typing import Dict, List, Optional

import asyncssh

SCROLLBACK = 256 * 1024                 # bytes of output kept for a browser that attaches later
ASK_TIMEOUT = 300                       # seconds to type a password or code before giving up
MAX_TRIES = 3                           # wrong answers before the login is given up

# On the machine: tmux when it has it (one session per connection, attached again when it exists),
# otherwise the login shell.
TMUX_COMMAND = ('if command -v tmux >/dev/null 2>&1; then exec tmux new-session -A -s {name}; '
                'else exec "${{SHELL:-/bin/sh}}" -l; fi')


class SessionError(Exception):
    """What the member is told when a session cannot be opened."""


class Session:
    def __init__(self, owner: str, connection: dict, cols: int, rows: int):
        self.id = uuid.uuid4().hex
        self.owner = owner
        self.connection = connection
        self.label = connection['label']
        self.target = f"{connection['username']}@{connection['hostname']}" + \
            (f":{connection['port']}" if int(connection['port']) != 22 else '')
        self.started = time.time()
        self.detached_at: Optional[float] = time.time()
        self.state = 'connecting'       # connecting, login, open, closed
        self.reason = ''
        self.cols, self.rows = cols, rows
        self.buffer = bytearray()
        self.socket = None              # the attached browser's websocket, if any
        self.keys: 'asyncio.Queue[str]' = asyncio.Queue()
        self.conn: Optional[asyncssh.SSHClientConnection] = None
        self.process = None
        self.task: Optional[asyncio.Task] = None

    # --- what the browser sees ---

    def info(self) -> dict:
        return {'id': self.id, 'connection': self.connection['id'], 'label': self.label, 'target': self.target,
                'state': self.state, 'reason': self.reason, 'attached': self.socket is not None,
                'started': time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(self.started)),
                'day': time.strftime('%Y-%m-%d', time.localtime(self.started))}

    async def output(self, data: bytes) -> None:
        self.buffer += data
        if len(self.buffer) > SCROLLBACK:
            del self.buffer[:len(self.buffer) - SCROLLBACK]
        if self.socket is not None:
            try:
                await self.socket.send_bytes(data)
            except Exception:
                self.socket = None
                self.detached_at = time.time()

    async def say(self, text: str) -> None:
        await self.output(text.replace('\n', '\r\n').encode())

    async def status(self) -> None:
        if self.socket is not None:
            try:
                await self.socket.send_str(json.dumps({'t': 'status', **self.info()}))
            except Exception:
                pass

    async def attach(self, socket) -> None:
        old, self.socket = self.socket, socket
        self.detached_at = None
        if old is not None:
            try:
                await old.send_str(json.dumps({'t': 'taken', 'session': self.id}))
                await old.close()
            except Exception:
                pass
        await socket.send_str(json.dumps({'t': 'status', **self.info()}))
        if self.buffer:
            await socket.send_bytes(bytes(self.buffer))

    def detach(self, socket) -> None:
        if self.socket is socket:
            self.socket = None
            self.detached_at = time.time()

    # --- what the browser sends ---

    async def typed(self, text: str) -> None:
        if self.state == 'open' and self.process is not None:
            self.process.stdin.write(text.encode())
        elif self.state == 'login':
            for ch in text:
                self.keys.put_nowait(ch)

    def resize(self, cols: int, rows: int) -> None:
        self.cols, self.rows = max(10, min(cols, 1000)), max(2, min(rows, 500))
        if self.process is not None:
            try:
                self.process.change_terminal_size(self.cols, self.rows)
            except Exception:
                pass

    async def ask(self, prompt: str, echo: bool) -> str:
        """A line typed in the terminal, shown or not as the machine asks, for the login only."""
        self.state = 'login'
        await self.status()
        while not self.keys.empty():
            self.keys.get_nowait()
        await self.say(prompt)
        line = ''
        while True:
            try:
                ch = await asyncio.wait_for(self.keys.get(), timeout=ASK_TIMEOUT)
            except asyncio.TimeoutError:
                raise SessionError('Nothing was typed for five minutes: try again.')
            if ch in ('\r', '\n'):
                await self.say('\n')
                return line
            if ch in ('\x7f', '\b'):
                if line:
                    line = line[:-1]
                    if echo:
                        await self.output(b'\b \b')
                continue
            if ch == '\x03':                   # Ctrl-C: give up the login
                raise SessionError('Login cancelled.')
            if ch == '\x15':                   # Ctrl-U: start the line again
                if echo:
                    await self.output(b'\b \b' * len(line))
                line = ''
                continue
            if ch.isprintable():
                line += ch
                if echo:
                    await self.output(ch.encode())

    # --- the connection ---

    async def run(self) -> None:
        c = self.connection
        try:
            await self.say(f'Connecting to {self.target} ...\n')
            try:
                key = asyncssh.import_public_key(c['host_key'])
            except Exception:
                raise SessionError('The machine’s host key is not readable: ask an administrator to look at it again.')
            session = self
            # A question asked again means the last answer was wrong. A login of several steps (a
            # password, then a one-time code) asks different questions, which are not counted.
            asked: set = set()
            wrong = [0]

            def again(question) -> bool:
                """Whether to answer this question: False once MAX_TRIES answers were wrong."""
                if wrong[0] >= MAX_TRIES:
                    return False
                if question in asked:
                    wrong[0] += 1
                    if wrong[0] >= MAX_TRIES:
                        return False
                    asyncio.ensure_future(session.say('Permission denied, please try again.\n'))
                asked.add(question)
                return True

            class Client(asyncssh.SSHClient):
                def auth_banner_received(self, msg, lang):
                    asyncio.ensure_future(session.say(msg))

                def kbdint_auth_requested(self):
                    return ''

                async def kbdint_challenge_received(self, name, instructions, lang, prompts):
                    if not prompts:
                        return []
                    if not again(tuple(p for p, _ in prompts)):
                        return None
                    if instructions:
                        await session.say(instructions + '\n')
                    return [await session.ask(prompt, echo) for prompt, echo in prompts]

                async def password_auth_requested(self):
                    if not again('password'):
                        return None
                    return await session.ask(f"{c['username']}@{c['hostname']}'s password: ", False)

            try:
                self.conn, _ = await asyncssh.create_connection(
                    Client, c['hostname'], int(c['port']), username=c['username'],
                    known_hosts=([key], [], []), client_keys=[], agent_path=None, password=None,
                    preferred_auth='keyboard-interactive,password', connect_timeout=20, login_timeout=600,
                    keepalive_interval=60, config=[])
            except asyncssh.HostKeyNotVerifiable:
                raise SessionError('The machine answered with a different host key from the one it was added with. '
                                   'This can mean it was reinstalled, or that something is in between: nothing was '
                                   'sent. Ask an administrator to check it (HPC Terminal, Machines).')
            except asyncssh.PermissionDenied:
                raise SessionError('Login refused.')
            except (OSError, asyncio.TimeoutError) as exc:
                raise SessionError(f'Could not reach {c["hostname"]}:{c["port"]}: {exc}')
            except asyncssh.Error as exc:
                raise SessionError(f'The machine closed the connection: {exc.reason}')
            command = TMUX_COMMAND.format(name='trellis') if c.get('tmux') else None
            self.process = await self.conn.create_process(command, term_type='xterm-256color',
                                                          term_size=(self.cols, self.rows), encoding=None)
            self.state = 'open'
            await self.status()

            async def pump(stream):
                while True:
                    data = await stream.read(65536)
                    if not data:
                        return
                    await self.output(data)

            await asyncio.gather(pump(self.process.stdout), pump(self.process.stderr))
            await self.process.wait_closed()
            self.reason = 'The session ended on the machine.'
        except SessionError as exc:
            self.reason = str(exc)
        except asyncio.CancelledError:
            self.reason = self.reason or 'Closed.'
        except Exception as exc:     # never the service's end: the member is told
            self.reason = f'The connection failed: {exc}'
        finally:
            if self.conn is not None:
                self.conn.close()
            self.state = 'closed'
            self.detached_at = self.detached_at or time.time()
            try:
                await self.say(f'\n[{self.reason}]\n')
            except Exception:
                pass
            await self.status()

    async def close(self, reason: str = 'Closed from the browser.') -> None:
        self.reason = reason
        if self.task is not None and not self.task.done():
            self.task.cancel()
            try:
                await self.task
            except (asyncio.CancelledError, Exception):
                pass

    # --- files on the machine, for saving a script to the notebook ---

    async def sftp(self):
        if self.state != 'open' or self.conn is None:
            raise SessionError('The session is not open.')
        return await self.conn.start_sftp_client()


class Sessions:
    """Every open session, by id; each member sees only their own."""

    def __init__(self, keep_hours: float = 12, per_member: int = 6, total: int = 100):
        self.all: Dict[str, Session] = {}
        self.keep = keep_hours * 3600
        self.per_member = per_member
        self.total = total

    def mine(self, owner: str) -> List[Session]:
        return [s for s in self.all.values() if s.owner == owner]

    def get(self, session_id: str, owner: str) -> Optional[Session]:
        s = self.all.get(session_id)
        return s if s is not None and s.owner == owner else None

    def live_for(self, owner: str, connection_id: str) -> Optional[Session]:
        """The member's session on a connection still going, the newest: a link opens it again."""
        live = [s for s in self.mine(owner) if s.connection['id'] == connection_id and s.state != 'closed']
        return max(live, key=lambda s: s.started) if live else None

    def open(self, owner: str, connection: dict, cols: int, rows: int) -> Session:
        if len([s for s in self.mine(owner) if s.state != 'closed']) >= self.per_member:
            raise SessionError(f'You have {self.per_member} sessions open: close one first.')
        if len([s for s in self.all.values() if s.state != 'closed']) >= self.total:
            raise SessionError('The terminal is at its limit of open sessions: try again later.')
        s = Session(owner, connection, cols, rows)
        self.all[s.id] = s
        s.task = asyncio.ensure_future(s.run())
        return s

    async def tidy(self, now: Optional[float] = None) -> None:
        """Close sessions nobody has looked at for ``keep`` hours, and forget closed ones after an hour."""
        now = now or time.time()
        for s in list(self.all.values()):
            if s.socket is not None or s.detached_at is None:
                continue
            idle = now - s.detached_at
            if s.state != 'closed' and idle > self.keep:
                await s.close(f'Closed after {self.keep / 3600:g} hours with no browser attached.')
            elif s.state == 'closed' and idle > 3600:
                self.all.pop(s.id, None)

    async def close_all(self) -> None:
        for s in list(self.all.values()):
            await s.close('The terminal service stopped.')

