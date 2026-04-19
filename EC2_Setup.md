# EC2 Setup Guide — LUDA Analytics Platform

## 아키텍처 개요

```
[인터넷]
    ├─ HTTPS 443 ──────────────────────────────────┐
    │                                               ↓
    │                                 [EC2 Analytics Server]
    │                                   t3.medium
    │                                   analytics.ludaresearch.org
    │                                   Nginx + Gunicorn
    │                                         ↓ Private IP (5432)
    │                                 [EC2 DB Server]
    │                                   t3.small
    │                                   PostgreSQL 16
    │                                         ↑ Private IP (5432)
    │                                 [EC2 Server 2 (미래)]
    │                                   추가 서비스 서버
    │
    └─ SSH 터널 (노트북) ──────────────→ [EC2 DB Server]
       외부 노트북 접속                  SSH → localhost:5432
       (pgAdmin / DBeaver / psql)
```

### 접속 방법 요약
| 클라이언트 | DB 접속 방식 | 포트 노출 여부 |
|------------|-------------|----------------|
| Analytics Server | Private IP 직접 연결 | 내부 VPC만 |
| Server 2 (추가) | Private IP 직접 연결 | 내부 VPC만 |
| 외부 노트북 | SSH 터널 경유 | 인터넷에 5432 미노출 |

---

## 1. 서브도메인 DNS 설정 (analytics.ludaresearch.org)

### 1-1. Analytics Server Elastic IP 할당 (필수)

EC2 Public IP는 재시작 시 바뀌므로 Elastic IP를 먼저 고정해야 함.

```
AWS 콘솔 → EC2 → Elastic IPs
→ [Allocate Elastic IP address] → Allocate
→ 생성된 IP 선택 → [Associate Elastic IP address]
→ Instance: Analytics Server 선택 → Associate
```

### 1-2. DNS A 레코드 추가

**방법 A — AWS Route 53 사용 시 (ludaresearch.org 호스팅 존이 Route 53에 있는 경우)**

```
AWS 콘솔 → Route 53 → Hosted zones → ludaresearch.org
→ [Create record]

레코드 타입:  A
레코드 이름:  analytics          ← analytics.ludaresearch.org 완성
값(Value):    ANALYTICS_ELASTIC_IP
TTL:          300
라우팅 정책:  Simple routing
→ [Create records]
```

**방법 B — 외부 도메인 등록업체 사용 시 (가비아, Namecheap 등)**

도메인 관리 패널 → DNS 관리 → 레코드 추가:
```
Type:   A
Host:   analytics          (또는 analytics.ludaresearch.org)
Value:  ANALYTICS_ELASTIC_IP
TTL:    300 (또는 Auto)
```

### 1-3. DNS 전파 확인

```bash
# 로컬 노트북에서 — 전파 완료까지 최대 30분 소요
nslookup analytics.ludaresearch.org
dig analytics.ludaresearch.org

# 기대 응답
# analytics.ludaresearch.org → ANALYTICS_ELASTIC_IP
```

### 1-4. SSL 인증서 발급 (Let's Encrypt)

DNS 전파 확인 후 Analytics Server에서 실행:

```bash
# Nginx가 실행 중이어야 함
sudo systemctl status nginx

# certbot으로 SSL 발급 (Nginx 플러그인 사용)
sudo certbot --nginx -d analytics.ludaresearch.org

# 이메일 입력, 약관 동의 → 자동으로 Nginx 설정에 SSL 추가됨
```

인증서 자동 갱신 확인:
```bash
sudo certbot renew --dry-run
# 오류 없으면 cron/systemd timer로 자동 갱신 설정 완료
```

### 1-5. 접속 테스트

```bash
# HTTP → HTTPS 리다이렉트 확인
curl -I http://analytics.ludaresearch.org
# 기대: 301 Moved Permanently → https://...

# HTTPS 접속 확인
curl -I https://analytics.ludaresearch.org
# 기대: 200 OK
```

브라우저에서 `https://analytics.ludaresearch.org` 접속 → 자물쇠 아이콘 확인.

---

## 3. Analytics Server (Flask + Gunicorn + Nginx)

### 1-1. EC2 인스턴스 설정
| 항목 | 값 |
|------|-----|
| AMI | Ubuntu Server 24.04 LTS (HVM) |
| 인스턴스 타입 | t3.medium (2 vCPU, 4 GB RAM) |
| 스토리지 | gp3 30 GB |
| 리전 | ap-northeast-2 (서울) |

### 1-2. 보안 그룹 (Analytics-SG)
| 포트 | 프로토콜 | 소스 | 용도 |
|------|----------|------|------|
| 22 | TCP | 내 IP | SSH |
| 80 | TCP | 0.0.0.0/0 | HTTP (SSL 리다이렉트) |
| 443 | TCP | 0.0.0.0/0 | HTTPS |

### 1-3. 서버 초기 설정
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv nginx certbot python3-certbot-nginx git
```

### 1-4. 앱 배포
```bash
cd /home/ubuntu
git clone https://github.com/luda-data-ai-lab/luda-analytics.git app
cd app
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 1-5. 환경 변수 (.env)
```ini
# /home/ubuntu/app/.env
DATABASE_URL=postgresql://luda_user:YOUR_PASSWORD@DB_PRIVATE_IP:5432/luda_analytics
SECRET_KEY=your-secret-key-here
FLASK_ENV=production
ANTHROPIC_API_KEY=sk-ant-...
```

### 1-6. Gunicorn systemd 서비스
```ini
# /etc/systemd/system/luda-analytics.service
[Unit]
Description=LUDA Analytics Flask App
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/app
EnvironmentFile=/home/ubuntu/app/.env
ExecStart=/home/ubuntu/app/venv/bin/gunicorn \
    --workers 3 \
    --bind 127.0.0.1:5000 \
    --timeout 120 \
    app:app
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable luda-analytics
sudo systemctl start luda-analytics
```

### 1-7. Nginx 설정
```nginx
# /etc/nginx/sites-available/luda-analytics
server {
    listen 80;
    server_name analytics.ludaresearch.org;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl;
    server_name analytics.ludaresearch.org;

    ssl_certificate     /etc/letsencrypt/live/analytics.ludaresearch.org/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/analytics.ludaresearch.org/privkey.pem;

    client_max_body_size 50M;

    location / {
        proxy_pass         http://127.0.0.1:5000;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/luda-analytics /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d analytics.ludaresearch.org
```

---

## 4. DB Server (PostgreSQL 전용)

### 2-1. EC2 인스턴스 설정
| 항목 | 값 |
|------|-----|
| AMI | Ubuntu Server 24.04 LTS (HVM) |
| 인스턴스 타입 | t3.small (2 vCPU, 2 GB RAM) |
| 스토리지 | gp3 20 GB |
| 리전 | ap-northeast-2 (서울) — Analytics Server와 동일 VPC |

### 2-2. 보안 그룹 (DB-SG)

5432 포트는 **인터넷에 절대 열지 않음** — 내부 서버는 Private IP, 외부 노트북은 SSH 터널로만 접근.

| 포트 | 프로토콜 | 소스 | 용도 |
|------|----------|------|------|
| 22 | TCP | 내 노트북 공인 IP | SSH (터널 포함) |
| 22 | TCP | Analytics Server Private IP | SSH (서버 간 관리용) |
| 5432 | TCP | Analytics-SG (보안 그룹 ID) | Analytics Server → DB |
| 5432 | TCP | Server2-SG (보안 그룹 ID) | Server 2 → DB (추가 시) |

> **5432는 0.0.0.0/0 절대 금지.** 외부 노트북은 SSH 터널로만 접근 (섹션 8 참조).

### 2-3. PostgreSQL 16 설치
```bash
sudo apt update && sudo apt upgrade -y

# PostgreSQL 16 공식 저장소 추가
sudo apt install -y curl ca-certificates
curl https://www.postgresql.org/media/keys/ACCC4CF8.asc | sudo apt-key add -
echo "deb http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" \
    | sudo tee /etc/apt/sources.list.d/pgdg.list

sudo apt update
sudo apt install -y postgresql-16 postgresql-client-16
```

### 2-4. PostgreSQL 서비스 시작
```bash
sudo systemctl enable postgresql
sudo systemctl start postgresql
sudo systemctl status postgresql
```

### 2-5. DB / 사용자 생성
```bash
sudo -u postgres psql
```

```sql
-- psql 내에서 실행
CREATE DATABASE luda_analytics;
CREATE USER luda_user WITH ENCRYPTED PASSWORD 'YOUR_STRONG_PASSWORD';
GRANT ALL PRIVILEGES ON DATABASE luda_analytics TO luda_user;
ALTER DATABASE luda_analytics OWNER TO luda_user;

-- PostgreSQL 15+ 추가 권한
\c luda_analytics
GRANT ALL ON SCHEMA public TO luda_user;

-- postgres 슈퍼유저 비밀번호도 변경
ALTER USER postgres PASSWORD 'YOUR_SUPER_PASSWORD';

\q
```

### 2-6. 원격 접속 허용 설정

#### postgresql.conf — listen_addresses 변경
```bash
sudo nano /etc/postgresql/16/main/postgresql.conf
```
```ini
# 변경 전
#listen_addresses = 'localhost'

# 변경 후 (모든 인터페이스 수신 — 실제 필터는 pg_hba.conf + 보안그룹에서)
listen_addresses = '*'
```

#### pg_hba.conf — 허용 클라이언트 등록

```bash
sudo nano /etc/postgresql/16/main/pg_hba.conf
```

파일 끝에 아래 내용 추가:
```
# Analytics Server (Private IP)
host    luda_analytics    luda_user    ANALYTICS_SERVER_PRIVATE_IP/32    scram-sha-256

# Server 2 (추가 서버 — Private IP, 연결 시 추가)
# host    luda_analytics    luda_user    SERVER2_PRIVATE_IP/32    scram-sha-256

# 외부 노트북 — SSH 터널 사용 시 localhost로 들어오므로 아래 줄 필요
host    luda_analytics    luda_user    127.0.0.1/32    scram-sha-256
```

> SSH 터널은 DB 서버의 `localhost:5432`로 포워딩되므로, 노트북 IP가 아닌 `127.0.0.1/32`로 등록.

#### PostgreSQL 재시작
```bash
sudo systemctl restart postgresql
```

### 2-7. 방화벽 설정 (UFW)
```bash
sudo ufw allow 22/tcp
sudo ufw allow from ANALYTICS_SERVER_PRIVATE_IP to any port 5432
# Server 2 추가 시:
# sudo ufw allow from SERVER2_PRIVATE_IP to any port 5432
sudo ufw enable
sudo ufw status
```

---

## 5. 연결 테스트 (서버 간)

### Analytics Server에서 DB 연결 확인
```bash
# Analytics Server SSH 접속 후
sudo apt install -y postgresql-client
psql -h DB_PRIVATE_IP -U luda_user -d luda_analytics -c "SELECT version();"
```

### Python 연결 테스트
```python
# test_db.py
import psycopg2
conn = psycopg2.connect(
    host="DB_PRIVATE_IP",
    database="luda_analytics",
    user="luda_user",
    password="YOUR_STRONG_PASSWORD"
)
print("DB 연결 성공:", conn.server_version)
conn.close()
```

---

## 6. Flask app.py DB 연결 설정

```python
# app.py
import os
from flask_sqlalchemy import SQLAlchemy

app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL',
    'postgresql://luda_user:YOUR_PASSWORD@DB_PRIVATE_IP:5432/luda_analytics'
)
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 300,
}
```

### DB 테이블 초기화
```bash
cd /home/ubuntu/app
source venv/bin/activate
python init_db.py  # 옵션 1 → 2 → 3 순서로 실행
```

---

## 7. 두 번째 서버 추가 시 절차

Server 2 (예: 추가 분석 서버, API 서버 등)를 DB에 연결할 때:

### 5-1. DB 보안 그룹에 규칙 추가 (AWS 콘솔)
```
인바운드 규칙 추가:
  유형: PostgreSQL (5432)
  소스: Server2-SG 보안그룹 ID  또는  Server2 Private IP/32
```

### 5-2. pg_hba.conf에 줄 추가
```bash
# DB Server에서
sudo nano /etc/postgresql/16/main/pg_hba.conf
```
```
# 주석 해제 또는 추가
host    luda_analytics    luda_user    SERVER2_PRIVATE_IP/32    scram-sha-256
```
```bash
sudo systemctl reload postgresql
```

### 5-3. UFW 규칙 추가
```bash
sudo ufw allow from SERVER2_PRIVATE_IP to any port 5432
sudo ufw status
```

### 5-4. Server 2의 .env
```ini
DATABASE_URL=postgresql://luda_user:YOUR_PASSWORD@DB_PRIVATE_IP:5432/luda_analytics
```

---

## 8. 외부 노트북에서 DB 접속 (SSH 터널)

5432 포트를 인터넷에 열지 않고 SSH 터널을 통해 안전하게 접속하는 방법.

### 6-1. 전제 조건
- DB Server의 `.pem` 키 파일이 노트북에 있어야 함
- DB Server 보안 그룹에 노트북 공인 IP로 22번 포트 허용

### 6-2. SSH 터널 생성

**Mac / Linux 노트북:**
```bash
ssh -i ~/keys/luda-db-key.pem \
    -L 5433:localhost:5432 \
    -N -f \
    ubuntu@DB_SERVER_PUBLIC_IP
```

**Windows 노트북 (PowerShell):**
```powershell
ssh -i C:\keys\luda-db-key.pem `
    -L 5433:localhost:5432 `
    -N -f `
    ubuntu@DB_SERVER_PUBLIC_IP
```

> `-L 5433:localhost:5432` → 노트북의 5433 포트를 DB서버 5432로 터널링  
> `-N` → 명령 실행 없이 터널만 유지  
> `-f` → 백그라운드 실행

### 6-3. 터널 통해 psql 접속
```bash
psql -h 127.0.0.1 -p 5433 -U luda_user -d luda_analytics
```

### 6-4. pgAdmin에서 접속 설정
```
Host:     127.0.0.1
Port:     5433          ← 터널 포트
Database: luda_analytics
Username: luda_user
Password: YOUR_STRONG_PASSWORD
```

### 6-5. DBeaver에서 접속 설정
```
Host:     localhost
Port:     5433
Database: luda_analytics
Username: luda_user
Password: YOUR_STRONG_PASSWORD
```
> DBeaver는 SSH 터널을 직접 내장 지원함 (Connection → SSH Tunnel 탭):
```
SSH Host:     DB_SERVER_PUBLIC_IP
SSH Port:     22
SSH User:     ubuntu
Auth Method:  Public Key
Private Key:  C:\keys\luda-db-key.pem
Local Port:   5433  →  Remote Host: localhost  Remote Port: 5432
```

### 6-6. 터널 종료
```bash
# 터널 프로세스 찾아 종료
ps aux | grep "5433:localhost"
kill <PID>
```

---

## 9. 예상 비용 (서울 리전, 월간)

| 항목 | 사양 | 월 비용 |
|------|------|---------|
| Analytics EC2 | t3.medium On-Demand | ~$30 |
| DB EC2 | t3.small On-Demand | ~$15 |
| EBS (Analytics) | gp3 30GB | ~$2.40 |
| EBS (DB) | gp3 20GB | ~$1.60 |
| 데이터 전송 | 100GB outbound | ~$9 |
| **합계** | | **~$58/월** |

> Reserved Instance (1년) 선택 시 약 30% 절감 → ~$40/월

---

## 10. 보안 체크리스트

- [ ] DB 보안 그룹: 5432 포트 0.0.0.0/0 절대 금지
- [ ] DB 보안 그룹: 22번 포트는 노트북 공인 IP만 허용 (유동 IP면 매번 업데이트)
- [ ] 외부 접속은 반드시 SSH 터널 경유
- [ ] `.pem` 키 파일 권한: `chmod 400 luda-db-key.pem`
- [ ] `.env` 파일 `.gitignore`에 추가
- [ ] PostgreSQL `luda_user` 비밀번호 20자 이상 복잡한 조합
- [ ] `postgres` 슈퍼유저 비밀번호 변경
- [ ] 정기 백업: `pg_dump` + S3 업로드 cron 설정
- [ ] CloudWatch 모니터링 또는 Datadog 에이전트 설치
- [ ] Server 2 추가 시: pg_hba.conf + 보안그룹 + UFW 3곳 모두 업데이트

---

## 11. PostgreSQL 백업 자동화 (선택)

```bash
# /home/ubuntu/backup_db.sh
#!/bin/bash
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/home/ubuntu/backups"
mkdir -p $BACKUP_DIR

PGPASSWORD=YOUR_PASSWORD pg_dump \
    -h localhost -U luda_user luda_analytics \
    | gzip > "$BACKUP_DIR/luda_analytics_$TIMESTAMP.sql.gz"

# 7일 이상 된 백업 삭제
find $BACKUP_DIR -name "*.sql.gz" -mtime +7 -delete
```

```bash
chmod +x /home/ubuntu/backup_db.sh
# crontab에 추가 (매일 새벽 2시)
(crontab -l 2>/dev/null; echo "0 2 * * * /home/ubuntu/backup_db.sh") | crontab -
```

---

*작성일: 2026-04-19 | LUDA Analytics Platform*
