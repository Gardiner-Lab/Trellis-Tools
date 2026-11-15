/*
 * HPC Terminal in the browser: the list of connections and sessions (the home page), and the terminal
 * itself (/c/<connection> and /s/<session>), drawn with xterm.js over a websocket to this service.
 * Saving to the Lab Notebook goes through the notebook's own API, as the other tools do.
 */
(function () {
  'use strict';

  var PREFIX = document.body.getAttribute('data-prefix') || '';
  var NOTEBOOK = (document.body.getAttribute('data-notebook') || '').replace(/\/$/, '');
  var API = PREFIX + '/api';

  function el(id) { return document.getElementById(id); }

  function make(tag, attrs, children) {
    var node = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (k === 'text') { node.textContent = attrs[k]; }
      else if (k === 'class') { node.className = attrs[k]; }
      else if (k.slice(0, 2) === 'on') { node.addEventListener(k.slice(2), attrs[k]); }
      else { node.setAttribute(k, attrs[k]); }
    });
    (children || []).forEach(function (c) { if (c) { node.appendChild(typeof c === 'string' ? document.createTextNode(c) : c); } });
    return node;
  }

  function call(method, url, body) {
    return fetch(url, {
      method: method, credentials: 'same-origin',
      headers: body !== undefined ? { 'Content-Type': 'application/json', 'Accept': 'application/json' } : { 'Accept': 'application/json' },
      body: body !== undefined ? JSON.stringify(body) : undefined
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (data) {
        if (!r.ok) { throw new Error(data.error || ('HTTP ' + r.status)); }
        return data;
      });
    });
  }

  function showError(id, err) {
    var box = el(id);
    if (!box) { return; }
    box.textContent = err ? (err.message || String(err)) : '';
    box.hidden = !err;
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function absolute(link) { return new URL(link, window.location.href).href; }

  function copy(text, button) {
    var done = function () { var t = button.textContent; button.textContent = 'Copied'; setTimeout(function () { button.textContent = t; }, 1500); };
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(done, function () { window.prompt('Copy the link:', text); });
    } else {
      window.prompt('Copy the link:', text);
    }
  }

  // ------------------------------------------------------------------ the home page

  function home() {
    var hosts = [];

    function loadSessions() {
      return call('GET', API + '/sessions').then(function (list) {
        var ul = el('sessions');
        el('sessions-empty').hidden = list.length > 0;
        ul.replaceChildren.apply(ul, list.map(function (s) {
          var open = make('a', { class: 'tt-btn', href: PREFIX + '/s/' + s.id, text: s.state === 'closed' ? 'See it' : 'Open' });
          var end = s.state === 'closed' ? null : make('button', { class: 'tt-btn danger', type: 'button', text: 'End', onclick: function () {
            if (!window.confirm('End the session “' + s.label + '”? What runs in tmux on the machine carries on.')) { return; }
            call('POST', API + '/sessions/' + s.id + '/close', {}).then(loadSessions);
          } });
          return make('li', {}, [
            make('span', { class: 'term-name', text: s.label }), make('span', { class: 'term-target', text: s.target }),
            make('span', { class: 'term-badge ' + s.state, text: { open: 'open', login: 'logging in', connecting: 'connecting', closed: 'ended' }[s.state] || s.state }),
            make('span', { class: 'term-hint', text: 'since ' + s.started.replace('T', ' ').slice(0, 16) + (s.attached ? ' · open in a browser' : '') }),
            make('span', { class: 'term-spacer' }), open, end]);
        }));
      });
    }

    function loadConnections() {
      return call('GET', API + '/connections').then(function (list) {
        var ul = el('connections');
        ul.replaceChildren.apply(ul, list.length ? list.map(function (c) {
          var copyBtn = make('button', { class: 'tt-btn', type: 'button', text: 'Copy link' });
          copyBtn.addEventListener('click', function () { copy(absolute(c.link), copyBtn); });
          return make('li', {}, [
            make('a', { class: 'term-name', href: c.link, text: c.label }),
            make('span', { class: 'term-target', text: c.username + '@' + c.hostname + (c.port !== 22 ? ':' + c.port : '') }),
            c.tmux ? make('span', { class: 'term-badge', text: 'tmux' }) : null,
            make('span', { class: 'term-spacer' }),
            make('a', { class: 'tt-btn primary', href: c.link, text: 'Open' }), copyBtn,
            make('button', { class: 'tt-btn danger', type: 'button', text: 'Remove', onclick: function () {
              if (!window.confirm('Remove the connection “' + c.label + '”? Its link stops working.')) { return; }
              call('DELETE', API + '/connections/' + c.id).then(loadConnections);
            } })]);
        }) : [make('li', { class: 'term-hint', text: hosts.length ? 'None yet: save one below.' : 'No machines have been added yet: ask an administrator.' })]);
      });
    }

    function loadHosts() {
      return call('GET', API + '/hosts').then(function (list) {
        hosts = list;
        var select = document.querySelector('#add-connection select[name=host_id]');
        select.replaceChildren.apply(select, list.map(function (h) {
          return make('option', { value: h.id, text: h.name + ' (' + h.hostname + (h.port !== 22 ? ':' + h.port : '') + ')' });
        }));
        el('add-connection').querySelector('button').disabled = !list.length;
        var table = el('machines');
        if (!table) { return; }
        var body = table.querySelector('tbody');
        body.replaceChildren.apply(body, list.map(function (h) {
          var check = make('button', { class: 'tt-btn', type: 'button', text: 'Read its key again' });
          check.addEventListener('click', function () { rescan(h); });
          return make('tr', {}, [
            make('td', {}, [make('b', { text: h.name }), h.note ? make('div', { class: 'term-hint', text: h.note }) : null]),
            make('td', {}, [make('code', { text: h.hostname + ':' + h.port })]),
            make('td', {}, [make('code', { text: h.fingerprint }), make('div', { class: 'term-hint', text: 'added by ' + h.added_by + ', ' + h.added_at.slice(0, 10) })]),
            make('td', {}, [check, make('button', { class: 'tt-btn danger', type: 'button', text: 'Remove', onclick: function () {
              if (!window.confirm('Remove “' + h.name + '”? Every member’s connections to it go too.')) { return; }
              call('DELETE', API + '/hosts/' + h.id).then(function () { loadHosts().then(loadConnections); });
            } })])]);
        }));
      });
    }

    // What happened to a machine, said on the page (not in a pop-up).
    function notice(text) {
      var box = el('machine-done');
      box.textContent = text;
      box.hidden = false;
    }

    function rescan(h) {
      showError('machine-error', null);
      call('POST', API + '/hosts/' + h.id + '/rescan', {}).then(function (now) {
        if (!now.changed) { notice('“' + h.name + '” gives the same host key as when it was added: ' + now.fingerprint + '.'); return; }
        var ok = window.confirm('“' + h.name + '” now gives a DIFFERENT host key.\n\nWas: ' + now.was + '\nNow: ' + now.fingerprint +
          '\n\nAccept it only if you know the machine was reinstalled or its keys changed, and this matches the fingerprint its ' +
          'administrators give. Accept the new key?');
        if (!ok) { return; }
        return call('POST', API + '/hosts/' + h.id + '/rescan', { accept: now.fingerprint }).then(function () {
          notice('Accepted the new host key of “' + h.name + '”: ' + now.fingerprint + '.');
          return loadHosts();
        });
      }).catch(function (err) { showError('machine-error', err); });
    }

    el('add-connection').addEventListener('submit', function (e) {
      e.preventDefault();
      var f = e.target;
      showError('connection-error', null);
      call('POST', API + '/connections', { host_id: f.host_id.value, username: f.username.value.trim(), label: f.label.value.trim(),
        tmux: f.tmux.checked }).then(function () { f.username.value = ''; f.label.value = ''; return loadConnections(); })
        .catch(function (err) { showError('connection-error', err); });
    });

    var addMachine = el('add-machine');
    if (addMachine) {
      addMachine.addEventListener('submit', function (e) {
        e.preventDefault();
        var f = e.target, button = f.querySelector('button');
        showError('machine-error', null);
        button.disabled = true;
        button.textContent = 'Reading its host key…';
        call('POST', API + '/hosts', { name: f.name.value.trim(), hostname: f.hostname.value.trim(), port: Number(f.port.value) || 22,
          note: f.note.value.trim() }).then(function (h) {
          notice('Added “' + h.name + '”. Its host key fingerprint is ' + h.fingerprint + '. Compare it with the one the ' +
            'machine’s administrators give (ssh-keygen -lf on its host key); if it differs, remove the machine.');
          f.reset();
          return loadHosts();
        }).catch(function (err) { showError('machine-error', err); })
          .then(function () { button.disabled = false; button.textContent = 'Add the machine'; });
      });
    }

    loadHosts().then(loadConnections).catch(function (err) { showError('connection-error', err); });
    loadSessions();
    setInterval(loadSessions, 15000);
  }

  // ------------------------------------------------------------------ the terminal page

  function terminalPage() {
    var parts = window.location.pathname.slice(PREFIX.length).split('/');   // ['', 'c'|'s', id]
    var byConnection = parts[1] === 'c', id = parts[2];
    var term = new window.Terminal({ cursorBlink: true, scrollback: 10000, fontSize: 14,
      fontFamily: 'ui-monospace, Menlo, Consolas, "DejaVu Sans Mono", monospace', convertEol: false });
    var fit = new window.FitAddon.FitAddon();
    term.loadAddon(fit);
    term.open(el('terminal'));
    fit.fit();
    term.focus();
    var socket = null, info = null, ended = false, retry = 0, taken = false, locked = false;

    function setState(s) {
      info = s;
      document.title = s.label + ' · HPC Terminal';
      el('term-title').textContent = s.label;
      el('term-state').textContent = s.target + ' · ' + ({ open: 'connected', login: 'logging in', connecting: 'connecting', closed: 'ended' }[s.state] || s.state);
      el('save-text').disabled = false;
      el('save-script').disabled = s.state !== 'open';
      el('close-session').disabled = s.state === 'closed';
      ended = s.state === 'closed';
      // Coming back by the session's own address keeps working after the connection's session changes.
      if (byConnection && s.id) { history.replaceState(null, '', PREFIX + '/s/' + s.id); byConnection = false; id = s.id; }
    }

    function connect() {
      var url = new URL(API + '/ws', window.location.href);
      url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
      url.searchParams.set(byConnection ? 'connection' : 'session', id);
      url.searchParams.set('cols', term.cols);
      url.searchParams.set('rows', term.rows);
      socket = new WebSocket(url.href);
      socket.binaryType = 'arraybuffer';
      var first = true;
      socket.onopen = function () { retry = 0; };
      socket.onmessage = function (ev) {
        if (typeof ev.data !== 'string') {
          if (first) { term.reset(); first = false; }       // the session's output from the start, again
          term.write(new Uint8Array(ev.data));
          return;
        }
        var m = JSON.parse(ev.data);
        if (m.t === 'status') { setState(m); }
        else if (m.t === 'error') { ended = true; term.write('\r\n\x1b[31m' + m.message + '\x1b[0m\r\n'); el('term-state').textContent = m.message; }
        else if (m.t === 'locked') { lock(); }
        else if (m.t === 'taken') { taken = true; term.write('\r\n\x1b[33m[Opened in another window: this one has let go of it. Reload to take it back.]\x1b[0m\r\n'); }
      };
      socket.onclose = function () {
        if (ended || taken || locked) { return; }
        // The network dropped, or the service restarted: try again, a little later each time.
        retry = Math.min(retry + 1, 6);
        el('term-state').textContent = 'reconnecting…';
        setTimeout(connect, 1000 * retry);
      };
    }

    term.onData(function (d) {
      if (locked) { return; }
      lastActive = Date.now();
      if (socket && socket.readyState === 1) { socket.send(JSON.stringify({ t: 'in', d: d })); }
    });

    // --- locked after a while away (data-idle seconds; the server holds to it as well) ---

    var IDLE = Number(document.body.getAttribute('data-idle') || 300) * 1000;
    var LOGIN = document.body.getAttribute('data-login') || '/account/login';
    var LOGOUT = document.body.getAttribute('data-logout') || '/account/api/logout';
    var lastActive = Date.now(), lastSent = 0;

    function active() {
      if (locked) { return; }
      lastActive = Date.now();
      el('idle-warning').hidden = true;
      // The server is told now and then, so that reading without typing does not lock it either.
      if (Date.now() - lastSent > 20000 && socket && socket.readyState === 1) {
        socket.send(JSON.stringify({ t: 'active' }));
        lastSent = Date.now();
      }
    }
    ['keydown', 'mousedown', 'mousemove', 'wheel', 'touchstart'].forEach(function (name) {
      document.addEventListener(name, active, { passive: true, capture: true });
    });

    function lock() {
      if (locked) { return; }
      locked = true;
      if (socket) { try { socket.close(); } catch (e) { /* already closed */ } }
      term.reset();                       // nothing of the session left on the screen
      if (el('save-dialog').open) { el('save-dialog').close(); }
      el('idle-warning').hidden = true;
      el('locked').hidden = false;
      var back = PREFIX + '/s/' + (info ? info.id : id);
      el('locked-text').textContent = 'No key was pressed and the mouse did not move for ' + Math.round(IDLE / 60000) +
        ' minutes. Your session is still running; signing you out, then back to it once you sign in again…';
      // Signed out of the suite, then to its sign-in page, which comes back here.
      fetch(LOGOUT, { method: 'POST', credentials: 'same-origin', headers: { 'Accept': 'application/json' } })
        .catch(function () { /* the sign-in page is next either way */ })
        .then(function () { window.location.assign(LOGIN + '?next=' + encodeURIComponent(back)); });
    }

    if (IDLE > 0) {
      setInterval(function () {
        if (locked) { return; }
        var left = IDLE - (Date.now() - lastActive);
        if (left <= 0) { lock(); return; }
        if (left <= 30000) {
          el('idle-warning').textContent = 'Locking in ' + Math.ceil(left / 1000) + ' s, as nothing has been typed for a ' +
            'while: press a key or move the mouse to stay. (The session carries on either way.)';
          el('idle-warning').hidden = false;
        }
      }, 1000);
    }
    function resize() {
      fit.fit();
      if (socket && socket.readyState === 1) { socket.send(JSON.stringify({ t: 'resize', cols: term.cols, rows: term.rows })); }
    }
    window.addEventListener('resize', function () { clearTimeout(resize.t); resize.t = setTimeout(resize, 100); });

    el('copy-link').addEventListener('click', function () {
      copy(absolute(info ? PREFIX + '/c/' + info.connection : window.location.href), el('copy-link'));
    });
    el('close-session').addEventListener('click', function () {
      if (!info || !window.confirm('End this session? What runs in tmux on the machine carries on.')) { return; }
      call('POST', API + '/sessions/' + info.id + '/close', {});
    });

    // --- saving to the notebook ---

    var pending = null;   // {kind, title, text, filename, path}

    function openSave(kind) {
      if (!NOTEBOOK) { window.alert('The Lab Notebook is not part of this suite.'); return; }
      pending = null;
      showError('save-error', null);
      el('save-done').hidden = true;
      el('save-go').disabled = kind === 'script';
      el('save-go').textContent = 'Save to the notebook';
      el('picker').hidden = kind !== 'script';
      el('save-preview').hidden = true;
      el('save-note').value = '';
      el('save-day').value = info.day;
      el('save-day-hint').textContent = 'The day this session started: ' + info.day + '.';
      if (kind === 'script') {
        el('save-title').textContent = 'Save a script to the notebook';
        el('save-name').value = '';
        listFolder(el('pick-path').value || '.');
      } else {
        var text = sessionText();
        pending = { kind: 'text', text: text, filename: 'session-' + info.day + '.txt' };
        el('save-title').textContent = 'Save the session’s text to the notebook';
        el('save-name').value = 'Terminal: ' + info.label + ', ' + info.started.replace('T', ' ').slice(0, 16);
        el('save-preview').textContent = text.split('\n').slice(-40).join('\n');
        el('save-preview').hidden = false;
        el('save-go').disabled = !text.trim();
      }
      el('save-dialog').showModal();
    }

    function sessionText() {
      var buf = term.buffer.active, lines = [];
      for (var i = 0; i < buf.length; i++) { lines.push(buf.getLine(i).translateToString(true)); }
      while (lines.length && !lines[lines.length - 1].trim()) { lines.pop(); }
      return lines.join('\n');
    }

    function listFolder(path) {
      var list = el('pick-list');
      list.replaceChildren(make('li', { class: 'term-hint', text: 'Reading…' }));
      call('GET', API + '/sessions/' + info.id + '/files?path=' + encodeURIComponent(path)).then(function (res) {
        el('pick-path').value = res.path;
        list.replaceChildren.apply(list, res.entries.map(function (e) {
          var li = make('li', { tabindex: '0', text: (e.dir ? '📁 ' : '📄 ') + e.name }, [
            e.dir ? null : make('span', { class: 'term-size', text: e.size < 1024 ? e.size + ' B' : Math.round(e.size / 1024) + ' kB' })]);
          var choose = function () {
            var full = res.path.replace(/\/$/, '') + '/' + e.name;
            if (e.dir) { listFolder(full); } else { chooseFile(full); }
          };
          li.addEventListener('click', choose);
          li.addEventListener('keydown', function (ev) { if (ev.key === 'Enter') { choose(); } });
          return li;
        }));
        if (!res.entries.length) { list.replaceChildren(make('li', { class: 'term-hint', text: 'Empty.' })); }
      }).catch(function (err) { list.replaceChildren(); showError('save-error', err); });
    }

    function chooseFile(path) {
      showError('save-error', null);
      call('GET', API + '/sessions/' + info.id + '/file?path=' + encodeURIComponent(path)).then(function (f) {
        pending = { kind: 'script', text: f.text, filename: f.name, path: f.path };
        el('pick-path').value = f.path;
        el('save-name').value = 'Script: ' + f.name;
        el('save-preview').textContent = f.text;
        el('save-preview').hidden = false;
        el('save-day-hint').textContent = 'The day this session started: ' + info.day + '. The file was last changed on ' +
          f.modified_day + '.';
        el('save-go').disabled = false;
      }).catch(function (err) { showError('save-error', err); });
    }

    function save() {
      if (!pending) { return; }
      var NB = NOTEBOOK + '/api', title = el('save-name').value.trim() || 'Terminal', day = el('save-day').value;
      var note = el('save-note').value.trim(), page;
      el('save-go').disabled = true;
      el('save-go').textContent = 'Saving…';
      showError('save-error', null);
      call('POST', NB + '/days', { date: day }).then(function (res) {
        return call('POST', NB + '/notes', { parent_id: res.note.id, title: title, type: 'page' });
      }).then(function (res) {
        page = res.note;
        var files = new FormData();
        files.append('file', new File([pending.text], pending.filename, { type: 'text/plain' }));
        return fetch(NB + '/notes/' + encodeURIComponent(page.id) + '/attachments', { method: 'POST', credentials: 'same-origin', body: files })
          .then(function (r) { return r.json().then(function (b) { if (!r.ok) { throw new Error(b.error || r.status); } return b.attachments[0]; }); });
      }).then(function (file) {
        var where = escapeHtml(info.target) + (pending.path ? ', <code>' + escapeHtml(pending.path) + '</code>' : '');
        var html = '<p><b>' + (pending.kind === 'script' ? 'A script from the HPC Terminal:' : 'A terminal session from the HPC Terminal:') +
          '</b> ' + where + '. Session started ' + escapeHtml(info.started.replace('T', ' ').slice(0, 16)) + '.</p>' +
          (note ? '<p>' + escapeHtml(note).replace(/\n/g, '<br>') + '</p>' : '') +
          '<pre><code>' + escapeHtml(pending.text) + '</code></pre>' +
          '<p>The file: <a data-attachment="' + escapeHtml(file.id) + '">' + escapeHtml(file.name || pending.filename) + '</a></p>';
        return call('PUT', NB + '/notes/' + encodeURIComponent(page.id),
          { title: title, content: [{ type: 'text', html: html }], base_version: page.version });
      }).then(function () {
        var done = el('save-done');
        done.replaceChildren('Saved to your Lab Notebook, under ' + day + ': “' + title + '”. ',
          make('a', { href: NOTEBOOK + '/#note=' + encodeURIComponent(page.id), target: '_blank', rel: 'noopener', text: 'Open the page →' }));
        done.hidden = false;
        el('save-go').textContent = 'Saved';
      }).catch(function (err) {
        showError('save-error', new Error('Could not save it: ' + err.message));
        el('save-go').disabled = false;
        el('save-go').textContent = 'Save to the notebook';
      });
    }

    el('save-text').addEventListener('click', function () { openSave('text'); });
    el('save-script').addEventListener('click', function () { openSave('script'); });
    el('save-go').addEventListener('click', save);
    el('save-cancel').addEventListener('click', function () { el('save-dialog').close(); term.focus(); });
    el('pick-go').addEventListener('click', function () { listFolder(el('pick-path').value || '.'); });
    el('pick-path').addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); listFolder(el('pick-path').value || '.'); } });
    el('pick-up').addEventListener('click', function () {
      var p = (el('pick-path').value || '.').replace(/\/+$/, '');
      listFolder(p.lastIndexOf('/') > 0 ? p.slice(0, p.lastIndexOf('/')) : '/');
    });

    connect();
  }

  if (el('terminal')) { terminalPage(); } else if (el('connections')) { home(); }
})();
