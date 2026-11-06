# Ubuntu 24.04 + GitHub + Docker + independent Cloudflare Tunnel

This deploy version uses the existing `team-task.py` as the actual parser. The web application calls `web_backend.legacy_adapter.LegacyCrawler`, which calls the original `get_page`, `parse_job_list`, and `parse_job_detail`. No crawler logic was replaced. `web_backend.collector` remains for shared helpers and historical tests, **not** the production parser. No runtime database is required: task metadata and CSV/JSON records live in the Docker named volume `recruitment_data`.

## 1. Create a PRIVATE GitHub repository

Create a new private repository on GitHub named `recruitment-crawler`; do not initialize it with a README. Then, in the **extracted deployment folder** on your Mac:

```bash
git init
git branch -M main
git add .
git status --short
git commit -m "deploy: original team-task crawler with Docker and Cloudflare"
git remote add origin https://github.com/YOUR_LOGIN/recruitment-crawler.git
git push -u origin main
```

The `.gitignore` prevents `.env`, collected records, and local runtime from being uploaded. Do not paste Cloudflare token into GitHub files, issue comments, or chats.

## 2. On Ubuntu server (Docker Compose plugin already installed)

```bash
cd ~
git clone https://github.com/YOUR_LOGIN/recruitment-crawler.git
cd recruitment-crawler
cp .env.example .env
nano .env
```

Set `PUBLIC_HOSTNAME` to your actual Cloudflare hostname, e.g. `jobs.example.com`, `LOCAL_PORT` to a free port (e.g. 18083), and `CF_TUNNEL_TOKEN` to the new tunnel token. Secure the secret file:

```bash
chmod 600 .env
sudo ss -lntp | grep ':18083 ' || true
docker compose config --quiet
docker compose up -d --build
docker compose ps
curl -sS http://127.0.0.1:18083/api/health
```

`web` runs as a non-root user (UID 10001), and stores durable task history in a Docker named volume. Docker manages this volume's directory permissions automatically. The web container binds only to 127.0.0.1:18083, not the Internet; `cloudflared` connects over the private Compose network.

## 3. Create a separate Cloudflare Tunnel

Cloudflare Dashboard -> **Networking > Tunnels > Create Tunnel**. Name it `recruitment-crawler` and select the Docker installation option. Copy **only the token** from the Docker command; place it in Ubuntu `.env` as `CF_TUNNEL_TOKEN`, without quotes. **Do not** execute the `docker run` command from the dashboard: Compose starts the connector.

In the tunnel's Routes -> **Add route > Published application** set:
- Hostname: the same `PUBLIC_HOSTNAME` as in `.env`
- Service type: `HTTP`
- Service URL: **`http://web:8000`** (not `localhost:18083`, because cloudflared is a separate container)

Enable **Cloudflare Access** before publishing the route (Zero Trust -> Access controls -> Applications -> Self-hosted); use an allow policy for your own and teacher's email identities. The crawler API is not authenticated itself, so do not open it without Access. Under the tunnel route configuration, turn on `Protect with Access`/JWT validation when available.

## 4. Logs, updates, backups

```bash
docker compose ps
docker compose logs --tail 100 web
docker compose logs --tail 100 tunnel
# Upgrade after new GitHub commit:
git pull --ff-only
docker compose up -d --build
# Make a backup of all run records from named volume:
docker compose run --rm --no-deps -v "$PWD/backups:/backup" --user 0:0 --entrypoint sh web -c 'cp -a /app/web_backend/data/. /backup/'
```

If you want the archived example task history in the original ZIP, do not commit the data into GitHub. Restore it separately (and only while services are stopped); current deploy starts with a clean history. History is not required to run the crawler, but requires actual network access to get live results.

## 5. Verification

- Local unit/integration tests use offline HTML fixtures, not the live Wayback network.
- Published `/api/health` should return JSON after Cloudflare Access authentication.
- Start a sample scrape only once, then inspect `/api/tasks`, task status, and CSV download.
- If `/` or `/api/health` gives HTTP 400: confirm `PUBLIC_HOSTNAME` matches the incoming hostname and recreate the web container.
- If the POST `/api/tasks` gives 403: confirm the tunnel is configured with the public HTTPS hostname and UVicorn is honoring forwarded proxy headers; do not disable same-origin checking.
- If Wayback returns 404, timeout, or SSL error, check the upstream site separately. This does not mean the Docker deployment failed.

**Important:** `team-task.py` uses a historic snapshot and is for academic demonstration, not for representing up-to-date job postings. Do not assume original Wayback URLs are always reachable.
