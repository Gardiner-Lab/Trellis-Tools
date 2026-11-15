# HPC Terminal for Trellis Tools: a browser terminal on the lab's HPC machines, over SSH.

# xterm.js, the terminal drawn in the browser, at pinned versions.
FROM node:20-alpine AS xterm
WORKDIR /x
RUN npm install --no-audit --no-fund --omit=dev @xterm/xterm@5.5.0 @xterm/addon-fit@0.10.0

FROM alpine:3.20
RUN apk add --no-cache python3 py3-aiohttp py3-asyncssh ca-certificates tzdata

# Its own volume only; it writes nothing elsewhere and reads the account directory (who is an administrator).
RUN adduser -D -u 1000 terminal && mkdir -p /terminal-data && chown terminal:terminal /terminal-data

COPY app.py pages.py sessions.py store.py /srv/terminal/
COPY static /srv/terminal/static
COPY --from=xterm /x/node_modules/@xterm/xterm/lib/xterm.js /srv/terminal/static/xterm/xterm.js
COPY --from=xterm /x/node_modules/@xterm/xterm/css/xterm.css /srv/terminal/static/xterm/xterm.css
COPY --from=xterm /x/node_modules/@xterm/addon-fit/lib/addon-fit.js /srv/terminal/static/xterm/addon-fit.js
COPY --from=xterm /x/node_modules/@xterm/xterm/LICENSE /srv/terminal/static/xterm/LICENSE
WORKDIR /srv/terminal
USER terminal

ENV TERMINAL_DATA=/terminal-data \
    MOCLO_DB=/moclo/moclo.db \
    URL_PREFIX=/terminal \
    NOTEBOOK_URL=/notebook \
    PORT=5009

EXPOSE 5009
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD wget -qO- http://127.0.0.1:5009/health > /dev/null || exit 1

# One process: sessions live in it, so they are kept while the browser is away.
CMD ["python3", "app.py"]
