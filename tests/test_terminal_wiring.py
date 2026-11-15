"""The HPC Terminal in the stack: its service, its route through the proxy, and the landing page."""
import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _compose():
    return yaml.safe_load((ROOT / 'docker-compose.yml').read_text(encoding='utf-8'))


def _terminal_block():
    conf = (ROOT / 'nginx' / 'default.conf').read_text(encoding='utf-8')
    m = re.search(r'location /terminal/ \{(.*?)\n    \}', conf, re.S)
    assert m, 'nginx has a /terminal/ block'
    return conf, m.group(1)


def test_the_proxy_names_the_member_itself_in_the_terminal_block():
    # Any proxy_set_header in a location drops every inherited one: without this line, a browser's own
    # X-Suite-User would reach the terminal and it would take it as the member.
    _, block = _terminal_block()
    assert re.search(r'proxy_set_header\s+X-Suite-User\s+\$suite_user;', block)
    assert re.search(r'proxy_set_header\s+X-Suite-Session\s+\$suite_session;', block)
    assert re.search(r'proxy_set_header\s+Host\s+\$host;', block)
    assert 'auth_request off' not in block


def test_the_terminal_block_upgrades_to_a_websocket():
    conf, block = _terminal_block()
    assert re.search(r'proxy_set_header\s+Upgrade\s+\$http_upgrade;', block)
    assert re.search(r'proxy_set_header\s+Connection\s+\$terminal_connection;', block)
    assert re.search(r'map \$http_upgrade \$terminal_connection \{', conf)
    assert 'rewrite ^/terminal/?(.*)$ /$1 break;' in block
    # Above the MoClo catch-all, or it would never be reached.
    assert conf.index('location /terminal/') < conf.rindex('    location / {')


def test_the_service_uses_the_suites_image_and_its_own_volume():
    compose = _compose()
    svc = compose['services']['terminal']
    assert svc['image'].startswith('ghcr.io/gardiner-lab/hpc-terminal:${TERMINAL_VERSION:-')   # its own repository
    assert 'terminal-data:/terminal-data' in svc['volumes']
    assert 'moclo-data:/moclo:ro' in svc['volumes']           # who is an administrator, read only
    assert not any(str(v).startswith('/') or 'docker.sock' in str(v) for v in svc['volumes'])
    assert 'ports' not in svc                                 # only through the proxy
    assert svc['read_only'] is True and svc['cap_drop'] == ['ALL']
    assert 'no-new-privileges:true' in svc['security_opt']
    assert 'terminal-data' in compose['volumes']


def test_the_landing_page_lists_it():
    tools = json.loads((ROOT / 'landing' / 'tools.json').read_text(encoding='utf-8'))['tools']
    t = next(t for t in tools if t['id'] == 'terminal')
    assert t['href'] == '/terminal/' and t['health'] == '/terminal/health'
    assert (ROOT / 'portal' / 'pages' / 'icons' / 'terminal.svg').exists()


def test_its_volume_is_backed_up_and_restored_and_nobody_else_mounts_it():
    services = _compose()['services']
    mounted = {name: [str(v) for v in s.get('volumes', []) if str(v).startswith('terminal-data:')]
               for name, s in services.items()}
    mounted = {k: v for k, v in mounted.items() if v}
    assert mounted == {'terminal': ['terminal-data:/terminal-data'],
                       'backup': ['terminal-data:/terminal-data:ro'],          # the nightly job only reads
                       'backup-console': ['terminal-data:/terminal-data'],
                       'restore': ['terminal-data:/terminal-data']}
    for script, line in (('backup/backup.sh', 'TERMINAL_DB:-/terminal-data/terminal.db'),
                         ('backup/restore.sh', 'TERMINAL_DB:-/terminal-data/terminal.db')):
        assert line in (ROOT / script).read_text(encoding='utf-8')
