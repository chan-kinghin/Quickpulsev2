# CVM Infrastructure — Aliyun ECS

> Mirrored from `/opt/ops/README.md` on the CVM. Last synced: 2026-02-11.

## Server Details

| Field | Value |
|-------|-------|
| **Host** | `121.41.81.36` |
| **User** | `root` |
| **Password** | *(stored in `.env` as `CVM_PASSWORD`)* |
| **OS** | Ubuntu 22.04.5 LTS |
| **CPU** | 4 cores |
| **RAM** | 7.1 GB |
| **Disk** | 59 GB (33% used) |
| **Provider** | Aliyun ECS |

### SSH Access

The password contains special characters that break `sshpass`. Use `expect` with `-o PubkeyAuthentication=no` (local SSH key has a passphrase). Password is stored in `.env` as `CVM_PASSWORD`:

```bash
# Interactive SSH (replace $CVM_PASSWORD with value from .env)
expect -c 'spawn ssh -o StrictHostKeyChecking=no -o PubkeyAuthentication=no root@121.41.81.36; expect "password:"; send "$CVM_PASSWORD\r"; interact'

# Run a remote command
expect -c 'spawn ssh -o StrictHostKeyChecking=no -o PubkeyAuthentication=no root@121.41.81.36 "<COMMAND>"; expect "password:"; send "$CVM_PASSWORD\r"; expect eof'
```

---

## Domain Names (HTTPS)

All services are accessible via custom subdomains with Let's Encrypt SSL certificates.

| Domain | Service | Internal Route |
|--------|---------|---------------|
| **https://fltpulse.szfluent.cn** | **QuickPulse Prod** | `quickpulse-prod:8000` |
| **https://dev.fltpulse.szfluent.cn** | **QuickPulse Dev** | `quickpulse-dev:8000` |
| **https://fltskills.szfluent.cn** | Fluent Skills Prod | `fluent-skills-prod:3000` |
| **https://dev.fltskills.szfluent.cn** | Fluent Skills Dev | `fluent-skills-dev:3000` |
| **https://water.jiejia1997.com** | jiejiawater Prod | `/` → admin:80, `/api/` → api:3000 |
| **https://dev.water.jiejia1997.com** | jiejiawater Dev | `/` → admin:80, `/api/` → api:3000 |
| **http://121.41.81.36:3100** | Grafana | IP-only (not exposed via subdomain) |

### SSL Certificates

| Certificate | Domains | Expiry |
|-------------|---------|--------|
| `szfluent` | fltskills.szfluent.cn, dev.fltskills.szfluent.cn, fltpulse.szfluent.cn, dev.fltpulse.szfluent.cn | 2026-05-12 |
| `jiejia1997` | water.jiejia1997.com, dev.water.jiejia1997.com | 2026-05-12 |

- **Issuer**: Let's Encrypt (certbot webroot)
- **Auto-renewal**: systemd timer (`certbot.timer`, twice daily)
- **Deploy hook**: `/etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh`
- **ACME webroot**: `/opt/ops/certbot/www/`
- **Cert paths**: `/etc/letsencrypt/live/{jiejia1997,szfluent}/`
- **Nginx config**: `/opt/ops/infra/nginx/conf.d/40-subdomains.conf`

### SSL Security

- TLS 1.2 and 1.3 only (no SSLv3, TLS 1.0, 1.1)
- Modern cipher suite (ECDHE + AES-GCM + CHACHA20-POLY1305)
- HSTS: `max-age=63072000; includeSubDomains` (2 years)
- HTTP/2 enabled
- DH parameters: 2048-bit (`/opt/ops/infra/nginx/ssl/dhparam.pem`)
- HTTP → HTTPS 301 permanent redirect on all subdomains

---

## Port Map (legacy, still active)

| Port | Service | Stack |
|------|---------|-------|
| **80** | HTTP → HTTPS redirect + ACME challenges | Infrastructure |
| **443** | HTTPS (all subdomains) | Infrastructure |
| **8001** | Fluent Skills **Prod** | Next.js 14 |
| **8002** | Fluent Skills **Dev** | Next.js 14 |
| **8003** | QuickPulse **Prod** | Python/FastAPI |
| **8004** | QuickPulse **Dev** | Python/FastAPI |
| **8010** | jiejiawater API **Prod** | NestJS |
| **8011** | jiejiawater Admin **Prod** | Vue 3 + Naive UI |
| **8020** | jiejiawater API **Dev** | NestJS |
| **8021** | jiejiawater Admin **Dev** | Vue 3 + Naive UI |
| **3100** | Grafana | Monitoring |

---

## Applications (21 containers)

### QuickPulse (Data sync & reporting)

| Container | Memory Limit | Health |
|-----------|-------------|--------|
| `quickpulse-prod` | 128 MB | `/health` |
| `quickpulse-dev` | 96 MB | `/health` |

- **Stack**: Python 3.11, FastAPI, uvicorn
- **Source**: `/opt/ops/apps/quickpulse/{dev,prod}/repo/`
- **Deploy**: `/opt/ops/scripts/deploy.sh quickpulse <prod|dev>`
- **Secrets**: `/opt/ops/secrets/quickpulse/{prod,dev}.env` (KINGDEE_* credentials)
- **Volumes**: `qp-{prod,dev}-data` → `/app/data`, `qp-{prod,dev}-reports` → `/app/reports`
- **Config**: `mto_config.json` lives at `/opt/ops/apps/quickpulse/{env}/repo/config/`

### Fluent Skills (AI-powered chat with dynamic skills)

| Container | Memory Limit | Health |
|-----------|-------------|--------|
| `fluent-skills-prod` | 400 MB | `/api/health` |
| `fluent-skills-dev` | 256 MB | `/api/health` |
| `redis-fluent-prod` | 128 MB (100mb maxmem) | `redis-cli ping` |
| `redis-fluent-dev` | 64 MB (50mb maxmem) | `redis-cli ping` |

- **Stack**: Next.js 14, TypeScript, SQLite (Drizzle), BullMQ, Redis
- **Source**: `/opt/ops/apps/fluent-skills/{dev,prod}/repo/`

### jiejiawater / 捷佳水域 (Aquatic facility management SaaS)

| Container | Memory Limit | Health |
|-----------|-------------|--------|
| `jiejia-api-prod` | 384 MB | `/api/health` |
| `jiejia-api-dev` | 256 MB | `/api/health` |
| `jiejia-admin-prod` | 64 MB | `wget /` |
| `jiejia-admin-dev` | 64 MB | `wget /` |
| `pg-jiejia-prod` | 512 MB | `pg_isready` |
| `pg-jiejia-dev` | 384 MB | `pg_isready` |
| `redis-jiejia-prod` | 192 MB (150mb maxmem) | `redis-cli ping` |
| `redis-jiejia-dev` | 128 MB (100mb maxmem) | `redis-cli ping` |

- **Stack**: NestJS, Prisma, PostgreSQL 16 + pgvector, Redis, Vue 3, Naive UI
- **Source**: `/opt/ops/apps/jiejiawater/{dev,prod}/repo/`
- **DB secrets**: Docker secrets at `/opt/ops/secrets/jiejiawater/pg_{dev,prod}_password.txt`

### Infrastructure

| Container | Memory Limit | Purpose |
|-----------|-------------|---------|
| `ops-nginx` | 32 MB | Reverse proxy (all traffic, HTTPS termination) |
| `ops-prometheus` | 64 MB | Metrics (7-day retention) |
| `ops-grafana` | 96 MB | Dashboards |
| `ops-loki` | 64 MB | Log aggregation |
| `ops-promtail` | 64 MB | Log shipping |
| `ops-node-exporter` | 16 MB | Host metrics |
| `ops-alertmanager` | 16 MB | Alert routing |

---

## Directory Structure

```
/opt/ops/
├── apps/                                ← Application deployments
│   ├── fluent-skills/{dev,prod}/
│   │   ├── docker-compose.yml
│   │   └── repo/                        ← Git clone
│   ├── quickpulse/{dev,prod}/
│   │   ├── docker-compose.yml
│   │   └── repo/
│   └── jiejiawater/{dev,prod}/
│       ├── docker-compose.yml
│       ├── nginx-admin.conf             ← Vue admin nginx config
│       └── repo/
├── certbot/                             ← Let's Encrypt ACME
│   └── www/                             ← Webroot for domain validation
├── infra/                               ← Shared infrastructure
│   ├── docker-compose.yml               ← ops-nginx (+certbot volumes)
│   └── nginx/
│       ├── nginx.conf
│       ├── conf.d/
│       │   ├── 00-status.conf           ← Ops portal + health endpoint
│       │   ├── 10-fluent-skills.conf    ← FS proxy (8001/8002)
│       │   ├── 20-quickpulse.conf       ← QP proxy (8003/8004)
│       │   ├── 30-jiejiawater.conf      ← JW proxy (8010-8021)
│       │   └── 40-subdomains.conf       ← Domain-based routing + SSL
│       └── ssl/
│           └── dhparam.pem              ← DH parameters (2048-bit)
├── monitoring/                          ← Observability stack
│   ├── docker-compose.yml
│   ├── prometheus/prometheus.yml
│   ├── prometheus/alert-rules.yml
│   ├── grafana/provisioning/
│   ├── loki/loki.yml
│   ├── promtail/promtail.yml
│   └── alertmanager/alertmanager.yml
├── secrets/                             ← Credentials (mode 700)
│   ├── fluent-skills/{dev,prod}.env
│   ├── quickpulse/{dev,prod}.env
│   └── jiejiawater/{dev,prod}.env + pg_*_password.txt
├── backups/
│   ├── scripts/backup.sh
│   ├── daily/                           ← Daily backups (3 AM)
│   └── weekly/                          ← Weekly backups (Sunday 4 AM)
├── scripts/deploy.sh                    ← Universal deploy script
├── deploy.log                           ← Deploy history
└── README.md                            ← Full CVM documentation
```

---

## Networking

All traffic enters through `ops-nginx` on ports 80 (HTTP redirect) and 443 (HTTPS), routing by domain name to containers via Docker DNS on `ops-infra`:

```
Internet
  │
  ├─ HTTPS (:443) — Domain-based routing
  │   ├─ fltpulse.szfluent.cn       → quickpulse-prod:8000
  │   ├─ dev.fltpulse.szfluent.cn   → quickpulse-dev:8000
  │   ├─ fltskills.szfluent.cn      → fluent-skills-prod:3000
  │   ├─ dev.fltskills.szfluent.cn  → fluent-skills-dev:3000
  │   ├─ water.jiejia1997.com
  │   │   ├─ /api/*  → jiejia-api-prod:3000
  │   │   └─ /*      → jiejia-admin-prod:80
  │   └─ dev.water.jiejia1997.com
  │       ├─ /api/*  → jiejia-api-dev:3000
  │       └─ /*      → jiejia-admin-dev:80
  │
  ├─ HTTP (:80) — Redirects to HTTPS (+ ACME challenges)
  │
  └─ Port-based routing (legacy, still active)
      ├─ :8001-8004, :8010-8011, :8020-8021
```

### Docker Networks

| Network | Purpose |
|---------|---------|
| `ops-infra` | Nginx → App routing (all apps + nginx) |
| `ops-monitoring` | Monitoring internal (Prometheus, Grafana, Loki) |
| `fluent-{prod,dev}-net` | FS isolation (app + redis) |
| `quickpulse-{prod,dev}-net` | QP isolation |
| `jiejia-{prod,dev}-net` | JW isolation (api + admin + pg + redis) |

No container ports exposed directly — all traffic proxied through nginx.

---

## Deployment

### CI/CD (GitHub Actions)

Each app has a CD pipeline (`.github/workflows/cd.yml`) using `appleboy/ssh-action@v1`.

**GitHub Secrets**: `CVM_HOST`, `CVM_USER`, `CVM_SSH_KEY` (ed25519 at `/root/.ssh/id_cicd_ed25519`)

| Trigger | Action |
|---------|--------|
| Push to `develop` | Auto-deploy to dev |
| `workflow_dispatch` | Manual deploy (select prod/dev) |

### Manual Deploy

```bash
/opt/ops/scripts/deploy.sh <app> <env>

# Examples:
/opt/ops/scripts/deploy.sh quickpulse prod
/opt/ops/scripts/deploy.sh fluent-skills dev
/opt/ops/scripts/deploy.sh jiejiawater dev
```

The deploy script:
1. Saves current images for rollback
2. Runs pre-deploy backup (prod only)
3. `git fetch && git reset --hard origin/<branch>`
4. `docker compose build --no-cache`
5. `docker compose up -d`
6. Health checks (5 retries x 30s timeout)
7. Auto-rollback on failure
8. Old image cleanup

### View Logs

```bash
# QuickPulse
ssh root@121.41.81.36 'cd /opt/ops/apps/quickpulse/prod && docker compose logs --tail 50'

# Other apps
ssh root@121.41.81.36 'cd /opt/ops/apps/fluent-skills/prod && docker compose logs --tail 50'
ssh root@121.41.81.36 'cd /opt/ops/apps/jiejiawater/prod && docker compose logs --tail 50'
```

---

## Automated Operations (Cron)

| Schedule | Command | Purpose |
|----------|---------|---------|
| Daily 3 AM | `backup.sh daily` | Daily database + config backups |
| Sunday 4 AM | `backup.sh weekly` | Weekly full backups |
| Twice daily | `certbot renew` (systemd timer) | SSL certificate auto-renewal |

## Monitoring & Backups

- **Grafana**: `http://121.41.81.36:3100` (IP-only, not exposed via subdomain)
- **Daily backups**: 3 AM → `/opt/ops/backups/daily/`
- **Weekly backups**: Sunday 4 AM → `/opt/ops/backups/weekly/`
- **Deploy log**: `/opt/ops/deploy.log`

## Security

- Secrets stored in `/opt/ops/secrets/` (mode 700, root only)
- jiejiawater uses Docker secrets for PG passwords (not env vars)
- All containers run with memory limits and log rotation
- Nginx rate limiting on production endpoints (`limit_req zone=general/api`)
- No container ports exposed directly — all proxied through nginx
- SSH key-based CI/CD (ed25519 at `/root/.ssh/id_cicd_ed25519`)
- SSL: TLS 1.2/1.3 only, modern cipher suite, HSTS (2 years), 2048-bit DH params
- Certbot auto-renewal with nginx reload deploy hook
- HTTP → HTTPS redirect enforced on all subdomains

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| 502 Bad Gateway | Container not on `ops-infra` network | `docker network connect ops-infra <container>` |
| Container unhealthy | App crash or missing env vars | Check `docker compose logs` in app dir |
| Deploy fails at health check | Slow startup or port conflict | Check deploy log, increase `start_period` |
| Nginx can't resolve container | Container name mismatch | Verify `container_name` matches nginx `$upstream_*` |
| SSH passphrase prompt | Local key has passphrase | Use `-o PubkeyAuthentication=no` flag |
| SSL cert expired | Certbot renewal failed | `certbot renew --dry-run`, check `certbot.timer` |
| Mixed content warnings | HTTP assets on HTTPS page | Ensure all URLs use `https://` or `//` |
