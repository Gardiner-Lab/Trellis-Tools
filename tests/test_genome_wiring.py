"""
How the Genome Browser is wired into the suite.

The tool itself lives in its own repository
(https://github.com/Gardiner-Lab/genome-browser) and is pinned here as
GENOME_VERSION, like every other tool. What stays the suite's business is how
its two containers are run and how requests reach them, and that is what these
assertions pin: the worker's CPU and memory caps, its concurrency of one, the
one published image both containers share, and the nginx block that streams a
large upload rather than spooling it.

They came from the tool's own ``test_smoke.py`` when it moved out, because they
read ``docker-compose.yml`` and ``nginx/default.conf``, which are files here.
The requirement numbers are the Genome Browser design's.

    python -m pytest tests/
"""

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPOSE_PATH = REPO_ROOT / 'docker-compose.yml'
NGINX_CONF_PATH = REPO_ROOT / 'nginx' / 'default.conf'


@pytest.fixture(scope='module')
def compose():
    """The parsed ``docker-compose.yml`` as a dict."""
    assert COMPOSE_PATH.is_file(), f'missing {COMPOSE_PATH}'
    with open(COMPOSE_PATH, encoding='utf-8') as handle:
        return yaml.safe_load(handle)


@pytest.fixture(scope='module')
def nginx_conf():
    """The raw text of ``nginx/default.conf``."""
    assert NGINX_CONF_PATH.is_file(), f'missing {NGINX_CONF_PATH}'
    return NGINX_CONF_PATH.read_text(encoding='utf-8')


def _genome_location_block(nginx_text):
    """
    Return the body of the ``location /genome/ { ... }`` block.

    A small brace-matching scan rather than a regex so the assertions are about
    the block that actually proxies the genome browser, not an incidental match
    elsewhere in the file.
    """
    marker = 'location /genome/'
    start = nginx_text.find(marker)
    assert start != -1, 'no `location /genome/` block in nginx/default.conf'
    brace = nginx_text.find('{', start)
    assert brace != -1, 'malformed `location /genome/` block (no opening brace)'
    depth = 0
    for i in range(brace, len(nginx_text)):
        char = nginx_text[i]
        if char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0:
                return nginx_text[brace + 1:i]
    raise AssertionError('unterminated `location /genome/` block')


def test_worker_has_cpu_and_memory_caps(compose):
    """genome-worker carries cpus: "2.0" and mem_limit: 6g (Req 13.16)."""
    worker = compose['services']['genome-worker']

    # cpus may parse as the string "2.0" or the float 2.0 depending on quoting;
    # accept either and compare numerically.
    cpus = worker['cpus']
    assert float(cpus) == 2.0, f'genome-worker cpus should be 2.0, got {cpus!r}'

    # mem_limit is a human-readable size string; accept 6g/6G and optional "b".
    mem = str(worker['mem_limit']).strip().lower()
    assert re.fullmatch(r'6\s*g(b)?', mem), \
        f'genome-worker mem_limit should be 6g, got {worker["mem_limit"]!r}'


def test_worker_runs_the_worker_command(compose):
    """genome-worker overrides the image command to run worker.py."""
    worker = compose['services']['genome-worker']
    command = worker['command']
    # Compose may hold the command as a list or a shell string; normalise.
    text = ' '.join(command) if isinstance(command, list) else str(command)
    assert 'worker.py' in text, \
        f'genome-worker should run worker.py, got {command!r}'
    assert text.strip().split()[0] in ('python', 'python3'), \
        f'genome-worker command should invoke python, got {command!r}'


def test_worker_concurrency_is_one(compose):
    """
    Worker concurrency is 1 — a structural property, not a tunable.

    There is exactly ONE genome-worker service and it is a single container
    (no ``deploy.replicas`` / ``scale`` fan-out). Concurrency-1 is then the
    product of that single container plus the serialized single-row claim in
    the tool's conversion queue, which its own tests cover. This test guards
    the container side of that invariant.
    """
    services = compose['services']
    worker_services = [name for name in services if name == 'genome-worker']
    assert worker_services == ['genome-worker'], \
        f'expected exactly one genome-worker service, found {worker_services}'

    worker = services['genome-worker']
    # No replica fan-out that would break concurrency-1.
    replicas = worker.get('deploy', {}).get('replicas')
    assert replicas in (None, 1), \
        f'genome-worker must not scale beyond one replica, got {replicas}'
    assert 'scale' not in worker, \
        'genome-worker must not set a scale > 1'


def test_browser_and_worker_use_published_image_and_mount_data(compose):
    """
    Both genome services use the published image and mount genome-data (13.16).

    The Genome Browser ships as the published genome-browser image, pinned with
    GENOME_VERSION like the other tools; the worker must use the SAME image (so
    the bundled conversion toolchain is present) and share the one genome-data
    volume that holds the SQLite queue, stored BigWigs, and the conversion
    scratch area. (The docker-compose.local.yml overlay builds the image from a
    checkout at GENOME_SRC instead.)
    """
    services = compose['services']
    images = {}
    for name in ('genome-browser', 'genome-worker'):
        service = services[name]
        image = service['image']
        assert 'genome-browser' in image, \
            f'{name} should use the genome-browser image, got {image!r}'
        assert 'GENOME_VERSION' in image, \
            f'{name} should be pinned with GENOME_VERSION, got {image!r}'
        images[name] = image

        mounts = service['volumes']
        assert any(
            str(m).startswith('genome-data:/genome') for m in mounts), \
            f'{name} should mount genome-data:/genome, got {mounts!r}'

    # Worker and browser must be the SAME image (the worker needs the toolchain).
    assert images['genome-browser'] == images['genome-worker'], \
        f'worker and browser must share one image, got {images!r}'

    # The shared named volume must be declared.
    assert 'genome-data' in compose['volumes'], \
        'genome-data named volume must be declared'


def test_nginx_genome_block_streams_large_bodies(nginx_conf):
    """
    The /genome/ block allows 51g bodies and disables request buffering (13.14).

    Large BAM uploads are streamed to disk, so the nginx block must raise the
    body ceiling well past MAX_BAM_GB and turn request buffering off so nginx
    does not spool the whole upload before proxying it.
    """
    block = _genome_location_block(nginx_conf)
    assert re.search(r'client_max_body_size\s+51g\s*;', block), \
        'nginx /genome/ block must set client_max_body_size 51g'
    assert re.search(r'proxy_request_buffering\s+off\s*;', block), \
        'nginx /genome/ block must set proxy_request_buffering off'
    assert 'proxy_pass' in block and 'genome-browser:5008' in block, \
        'nginx /genome/ block must proxy to genome-browser:5008'


def test_the_genome_route_is_stripped_before_proxying(nginx_conf):
    """
    The prefix is stripped, as the tool serves at its root.

    Passing /genome through made every request 404 in 2.33.0 and 2.34.0-2.34.1,
    which is what scripts/check.sh now catches at install time; this catches it
    before a release.
    """
    block = _genome_location_block(nginx_conf)
    assert re.search(r'rewrite\s+\^/genome/\?\(\.\*\)\$\s+/\$1\s+break\s*;', block), \
        'nginx /genome/ block must strip the /genome prefix before proxying'
