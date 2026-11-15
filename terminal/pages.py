"""The HPC Terminal's pages, in the suite's look (static/trellis/), filled in by static/terminal.js."""
from html import escape


def _page(title: str, prefix: str, body: str, notebook: str = '', user: str = '', script: bool = True,
          extra_head: str = '') -> str:
    p = escape(prefix)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title) if title == 'HPC Terminal' else escape(title) + ' · HPC Terminal'}</title>
  <link rel="icon" href="{p}/static/trellis/terminal.svg" type="image/svg+xml">
  <link rel="stylesheet" href="{p}/static/trellis/trellis.css">
  <link rel="stylesheet" href="{p}/static/terminal.css">
  {extra_head}
</head>
<body class="tt" data-prefix="{p}" data-notebook="{escape(notebook)}" data-user="{escape(user)}">
  <header class="tt-bar">
    <a class="tt-home" href="/" title="All of Trellis Tools"><img src="{p}/static/trellis/trellis.svg" alt=""><span>Trellis Tools</span></a>
    <a class="tt-module" href="{p}/"><img src="{p}/static/trellis/terminal.svg" alt="">HPC Terminal</a>
    <nav class="tt-links">
      <a href="{p}/help">Help</a>
      <a href="{p}/about">About</a>
    </nav>
  </header>
{body}
  <script src="{p}/static/trellis/modules.js" defer></script>
  {f'<script src="{p}/static/terminal.js" defer></script>' if script else ''}
</body>
</html>
"""


def home(prefix: str, notebook: str, user: str, admin: bool) -> str:
    machines = """
    <section class="term-card" id="machines-card">
      <h2>The lab's machines</h2>
      <p class="term-hint">The HPC machines members can open a terminal on. Only these can be reached. Each is checked
        against the host key it was added with; compare the fingerprint with the one the machine's administrators give.</p>
      <table class="term-table" id="machines"><thead><tr><th>Name</th><th>Address</th><th>Host key (SHA256)</th><th></th></tr></thead><tbody></tbody></table>
      <form id="add-machine" class="term-form">
        <label>Name <input name="name" maxlength="80" required placeholder="Cluster login node"></label>
        <label>Host name or address <input name="hostname" required placeholder="hpc01.lab.local"></label>
        <label>SSH port <input name="port" type="number" min="1" max="65535" value="22"></label>
        <label>Note <input name="note" maxlength="300" placeholder="optional"></label>
        <button class="tt-btn" type="submit">Add the machine</button>
      </form>
      <p class="term-done" id="machine-done" role="status" hidden></p>
      <p class="term-error" id="machine-error" role="alert" hidden></p>
    </section>""" if admin else ''
    body = f"""
  <main class="term-main">
    <h1>HPC Terminal</h1>
    <p class="term-lead">A terminal on the lab's HPC machines, in the browser. Start long work, close the page, and come back
      to it from your connection's link. Save scripts and what a session did to your Lab Notebook, under the day it ran.
      <a href="{escape(prefix)}/help">How it works →</a></p>

    <section class="term-card">
      <h2>Your sessions</h2>
      <p class="term-hint" id="sessions-empty">None open.</p>
      <ul class="term-list" id="sessions"></ul>
    </section>

    <section class="term-card">
      <h2>Your connections</h2>
      <p class="term-hint">Who you log in as, on which machine. Your password, or one-time code, is asked in the terminal each
        time and never kept.</p>
      <ul class="term-list" id="connections"></ul>
      <form id="add-connection" class="term-form">
        <label>Machine <select name="host_id" required></select></label>
        <label>Your user name there <input name="username" required maxlength="64" autocomplete="off" spellcheck="false"></label>
        <label>Name it <input name="label" maxlength="80" placeholder="optional"></label>
        <label class="term-check"><input type="checkbox" name="tmux" checked> Keep my work in tmux on the machine</label>
        <label class="term-check"><input type="checkbox" name="record" checked> Record each session in my notebook when it ends</label>
        <button class="tt-btn" type="submit">Save the connection</button>
      </form>
      <p class="term-error" id="connection-error" role="alert" hidden></p>
    </section>
{machines}
  </main>"""
    return _page('HPC Terminal', prefix, body, notebook, user)


def terminal(prefix: str, notebook: str, user: str, idle: float = 300, login: str = '/account/login',
             logout: str = '/account/api/logout') -> str:
    p = escape(prefix)
    head = (f'<link rel="stylesheet" href="{p}/static/xterm/xterm.css">'
            f'<script src="{p}/static/xterm/xterm.js" defer></script>'
            f'<script src="{p}/static/xterm/addon-fit.js" defer></script>')
    body = """
  <div class="term-toolbar">
    <span class="term-title" id="term-title">Connecting…</span>
    <span class="term-state" id="term-state"></span>
    <span class="term-spacer"></span>
    <button class="tt-btn" type="button" id="save-script" disabled>Save a script to the notebook…</button>
    <button class="tt-btn" type="button" id="save-text" disabled>Save the session’s text…</button>
    <button class="tt-btn" type="button" id="copy-link">Copy link</button>
    <button class="tt-btn danger" type="button" id="close-session" disabled>End session</button>
  </div>
  <div class="term-warning" id="idle-warning" role="status" hidden></div>
  <div id="terminal" class="term-screen"></div>
  <div class="term-locked" id="locked" hidden>
    <div><h2>Locked</h2><p id="locked-text">Signing you out…</p></div>
  </div>

  <dialog id="save-dialog" class="term-dialog">
    <form method="dialog" id="save-form">
      <h2 id="save-title">Save to the notebook</h2>
      <div id="picker">
        <label>On the machine <input id="pick-path" spellcheck="false" autocomplete="off"></label>
        <div class="term-picker-actions"><button class="tt-btn" type="button" id="pick-go">Open</button>
          <button class="tt-btn" type="button" id="pick-up">Up a folder</button></div>
        <ul class="term-files" id="pick-list"></ul>
      </div>
      <pre class="term-preview" id="save-preview" hidden></pre>
      <label>Page title <input id="save-name" maxlength="200"></label>
      <label>Under the day <input id="save-day" type="date" required></label>
      <p class="term-hint" id="save-day-hint"></p>
      <label>A note <span class="term-hint">(optional)</span> <textarea id="save-note" rows="2"></textarea></label>
      <p class="term-error" id="save-error" role="alert" hidden></p>
      <p class="term-done" id="save-done" hidden></p>
      <div class="term-dialog-actions">
        <button class="tt-btn" type="button" id="save-cancel">Close</button>
        <button class="tt-btn primary" type="button" id="save-go" disabled>Save to the notebook</button>
      </div>
    </form>
  </dialog>"""
    return _page('Terminal', prefix, body, notebook, user, extra_head=head).replace(
        '<body class="tt"', f'<body class="tt term-page" data-idle="{int(idle)}" data-login="{escape(login)}" '
                            f'data-logout="{escape(logout)}"')


def help_page(prefix: str) -> str:
    p = escape(prefix)
    body = f"""
  <main class="term-main term-help">
    <h1>How to use the HPC Terminal</h1>
    <p class="term-lead">A terminal on the lab's HPC machines, from any browser signed in to the suite. The heavy work runs on
      the HPC machine; this server only carries the keystrokes and the output.</p>

    <h2 id="connect">Connecting</h2>
    <ol>
      <li><b>Save a connection</b> on the <a href="{p}/">HPC Terminal</a> page: choose one of the lab's machines and give
        the user name you have there.</li>
      <li><b>Open it</b>: click it, or its link. The link can be bookmarked or put on a notebook page; it opens the terminal
        and connects.</li>
      <li><b>Log in in the terminal</b>, as with any SSH client: type your password, and a one-time code if the machine asks
        for one. They go to the machine and are not kept. Ctrl-C gives up the login.</li>
    </ol>
    <p>Only machines an administrator has added can be reached. If one is missing, ask an administrator to add it (on the
      same page, under <i>The lab's machines</i>).</p>

    <h2 id="leave">Leaving work running, and coming back</h2>
    <p>Close the page: the session carries on. Open the connection's link again, from any computer, and you are back where
      you were: the terminal first shows what the session printed, while you were there and while you were away (its last
      12,000 lines or so), then carries on live. Your open sessions are listed on the HPC Terminal page.</p>
    <p>After a restart of the suite, that record is gone, but with tmux nothing on the machine is: you are put back in the
      same tmux session, as it was, and tmux's own history (Ctrl-b then [, to scroll; q to stop) holds what scrolled past.</p>
    <p>With <b>Keep my work in tmux</b> (on unless you turn it off), the terminal is a <code>tmux</code> session on the
      machine, called <code>trellis</code>. Then your work also outlives this service: after the suite is restarted or
      updated, opening the link logs you in again and puts you back in the same tmux session. Without tmux on the machine,
      you get an ordinary shell.</p>
    <p><b>The page locks after 5 minutes away; the session does not stop.</b> As a precaution, a terminal page with no key
      pressed and no mouse movement for 5 minutes lets go of the session, clears the screen and signs you out of the suite, so
      a computer left unattended is not a way onto the lab's machines. Thirty seconds before, it says so; press a key or move
      the mouse to stay. What runs in the session carries on regardless: sign in again, here or anywhere else, and the link
      takes you straight back to it.</p>
    <p>A session runs until you end it (<b>End session</b>), or it ends on the machine, however long you are away: leave it
      running at work and open the link at home. Only one browser shows it at a time; opening it somewhere else takes it
      over from the first. A restart of the suite (an update, say) does end the connection: that is what tmux is for. For
      work that takes hours or days, use the machine's job scheduler (for example <code>sbatch</code> with Slurm) rather than the login node: most
      HPC centres stop long work on login nodes.</p>

    <h2 id="notebook">Saving to the Lab Notebook</h2>
    <ul>
      <li><b>Save a script to the notebook</b>: choose a file on the machine (read over SFTP, up to 1 MB of text). It goes on a
        page with its text, and the file attached.</li>
      <li><b>Save the session’s text</b>: what is on the terminal and in its history, as a page, with the text attached.</li>
    </ul>
    <p>Either goes under the day the session started, unless you choose another day (for a script, the day it was last
      changed is offered too).</p>
    <p><b>Recorded for you</b>, with <i>Record each session in my notebook</i> (on unless you turn it off for a connection):
      when a session ends (you end it, it ends on the machine, or the suite restarts), what it showed is written to a page
      under today in your notebook, with the text attached. A session still running at midnight gets the day just past
      written under that day, and carries on; each day's page says where it continues. Passwords and codes typed at login
      are never shown in the terminal, so never in the record, but whatever the machine prints is. Full-screen programs (an
      editor, <code>top</code>) come out jumbled in it. Up to the last megabyte of output is kept for it.</p>

    <h2 id="safe">What is and is not kept</h2>
    <ul>
      <li>Kept: the lab's machines and their host keys; each member's connections (user name, machine, name). Each member sees
        only their own.</li>
      <li>Not kept: passwords, one-time codes, private keys. No SSH agent is used.</li>
      <li>A session's recent output is held in memory while it is open, for coming back to it, and is gone when it closes.</li>
      <li>Nothing runs on this server: the terminal only reaches the machine you connect to.</li>
      <li>If a machine answers with a different host key from the one it was added with, nothing is sent and the terminal
        says so: ask an administrator, who can read the key again and accept it after checking it.</li>
    </ul>
  </main>"""
    return _page('Help', prefix, body, script=False)


def about_page(prefix: str, version: str) -> str:
    body = f"""
  <main class="term-main term-help">
    <h1>About the HPC Terminal</h1>
    <p>Part of Trellis Tools, version {escape(version)}. A browser terminal on the lab's HPC machines over SSH, signed in by
      the suite. Sessions are held by this server so that work goes on with the browser closed; scripts and session text
      are saved to the Lab Notebook.</p>
    <p>The terminal is drawn by <a href="https://xtermjs.org" target="_blank" rel="noopener">xterm.js</a> (MIT licence); SSH is
      <a href="https://asyncssh.readthedocs.io" target="_blank" rel="noopener">AsyncSSH</a> (EPL 2.0).</p>
    <p>Its data (the lab's machines and members' connections) is in the <code>terminal-data</code> volume.</p>
  </main>"""
    return _page('About', prefix, body, script=False)
