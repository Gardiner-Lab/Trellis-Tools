"""
What the proxy lets through, against what the tools accept.

nginx refuses a body before the tool ever sees it, so a tool that accepts a
128 MB upload behind a block that allows 65m rejects the file with a bare 413
and no explanation from the tool. Worse, a block with no
``client_max_body_size`` of its own silently inherits the server-wide 64m,
which is how attaching a 50 MB photo to a notebook page failed while the
notebook itself was happy to take it.

So: every tool that takes file uploads must have its own block here, allowing
at least what the tool allows.

    python -m pytest tests/
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
NGINX_CONF_PATH = REPO_ROOT / 'nginx' / 'default.conf'

# route -> the smallest body the block must allow, in MB; this is the tool's own
# MAX_CONTENT_LENGTH (app/main.py in each tool's repository).
UPLOAD_ROUTES = {
    '/notebook/': 128,
    '/stocks/': 128,
    '/map/': 64,
    '/seeds/': 210,
}


@pytest.fixture(scope='module')
def nginx_conf():
    """The raw text of ``nginx/default.conf``."""
    assert NGINX_CONF_PATH.is_file(), f'missing {NGINX_CONF_PATH}'
    return NGINX_CONF_PATH.read_text(encoding='utf-8')


def _location_block(conf: str, route: str) -> str:
    """The body of ``location <route> { ... }``."""
    start = conf.find(f'location {route} {{')
    assert start != -1, f'nginx has no location block for {route}'
    depth, index = 0, conf.index('{', start)
    for position in range(index, len(conf)):
        if conf[position] == '{':
            depth += 1
        elif conf[position] == '}':
            depth -= 1
            if depth == 0:
                return conf[index:position]
    raise AssertionError(f'unclosed location block for {route}')


def _body_limit_mb(block: str, route: str) -> float:
    """The block's own ``client_max_body_size``, in MB."""
    match = re.search(r'client_max_body_size\s+(\d+)([kmg])\s*;', block, re.IGNORECASE)
    assert match, (
        f'the nginx block for {route} sets no client_max_body_size of its own, so it '
        f'inherits the server-wide one and silently refuses what the tool accepts'
    )
    size, unit = int(match.group(1)), match.group(2).lower()
    return size * {'k': 1 / 1024, 'm': 1, 'g': 1024}[unit]


@pytest.mark.parametrize('route,tool_limit_mb', sorted(UPLOAD_ROUTES.items()))
def test_the_proxy_allows_what_the_tool_accepts(nginx_conf, route, tool_limit_mb):
    """A tool's uploads reach it, instead of dying at the proxy as a bare 413."""
    allowed = _body_limit_mb(_location_block(nginx_conf, route), route)

    assert allowed >= tool_limit_mb, (
        f'nginx allows {allowed:g} MB on {route} but the tool accepts {tool_limit_mb} MB; '
        f'uploads between the two are refused by the proxy with no word from the tool'
    )
