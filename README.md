# web-health-check

A small **website health checker**: enter any URL and it tells you whether the site is up, checked **server-side** so it works regardless of browser CORS rules.

> Public overview of the project. It runs as one of the tools in my [homelab](https://github.com/xm0dx/homelab).

![Python](https://img.shields.io/badge/Python-0f1620?style=flat-square&logo=python&logoColor=5BC0EB)
![nginx](https://img.shields.io/badge/nginx-0f1620?style=flat-square&logo=nginx&logoColor=5BC0EB)
![HTML5](https://img.shields.io/badge/HTML5-0f1620?style=flat-square&logo=html5&logoColor=5BC0EB)

## What it does

- Type a URL into a simple page and get back whether it's reachable and responding.
- The fetch happens **on the server**, not in the browser, so it isn't blocked by CORS and can reach hosts the browser can't.
- Embedded as a live card in my homelab dashboard, and usable as a standalone page.

## How it's built

```text
Browser ──▶ nginx ──/check──▶ Python checker ──▶ requests target URL ──▶ status
```

- **Backend:** a small Python microservice that performs the upstream request with a timeout and reports the result.
- **Frontend:** a single static HTML page with a URL input.
- **Serving:** nginx proxies the check endpoint to the service so the page stays same-origin.

## Run it

```bash
docker compose up --build
# open http://localhost:8080
```

## Security

The checker resolves every target host and **refuses anything that isn't a
globally routable address** — loopback, private/RFC1918, link-local (incl. the
`169.254.169.254` cloud-metadata IP), CGNAT and reserved ranges are all blocked,
and each redirect hop is re-validated. That keeps it from being used as an SSRF
pivot into internal services.

## Structure

```text
.
├── app/index.html      the page with a URL input
├── server.py           the checker — stdlib only, with SSRF guards
├── nginx.conf          serves the page + proxies /webcheck/ on one origin
├── docker-compose.yml  backend + nginx
└── Dockerfile          backend image
```

## Tech

Python · nginx · HTML · Docker
