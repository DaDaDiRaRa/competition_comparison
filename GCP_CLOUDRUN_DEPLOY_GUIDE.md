# GCP Cloud Run 배포 가이드
> 이 앱(설계공모 경쟁분석)의 배포 경험을 바탕으로 정리한 범용 참고서.
> FastAPI + React 앱 기준이지만, 다른 앱에도 동일하게 적용 가능.

---

## 목차

1. [배포 구조 개요](#1-배포-구조-개요)
2. [기술 선택 이유](#2-기술-선택-이유)
3. [최초 GCP 셋업 (1회만)](#3-최초-gcp-셋업-1회만)
4. [Dockerfile 작성법](#4-dockerfile-작성법)
5. [GitHub Actions 워크플로우](#5-github-actions-워크플로우)
6. [배포 명령어 전체](#6-배포-명령어-전체)
7. [겪었던 오류 & 해결법](#7-겪었던-오류--해결법)
8. [운영 중 자주 하는 작업](#8-운영-중-자주-하는-작업)
9. [비용 구조](#9-비용-구조)
10. [다른 앱에 적용할 때 체크리스트](#10-다른-앱에-적용할-때-체크리스트)

---

## 1. 배포 구조 개요

```
개발자 PC
  │  git push → main 브랜치
  │
  ▼
GitHub Actions (ubuntu-latest)
  │  1. docker build  (멀티스테이지: Node.js → Python)
  │  2. docker push
  │
  ▼
Artifact Registry
  asia-northeast3-docker.pkg.dev/{프로젝트}/{레지스트리}/app
  │
  ▼
Cloud Run (gen2, asia-northeast3)
  │  - 요청 있을 때만 컨테이너 기동
  │  - 메모리 2Gi / CPU 2 / 타임아웃 3600s
  │  - max-instances 1 (JSON DB 동시성 충돌 방지)
  │
  ├── /data  ← GCS 버킷 마운트 (영구 데이터)
  │     kunwon-competition-db (gs://)
  │
  └── Secret Manager
        anthropic-api-key → 환경변수로 주입
```

**이 프로젝트의 실제 값:**

| 항목 | 값 |
|------|-----|
| GCP 프로젝트 ID | `arch-diagnose` |
| 리전 | `asia-northeast3` (서울) |
| Cloud Run 서비스명 | `competition-analyzer` |
| Artifact Registry 레지스트리명 | `competition-analyzer` |
| Docker 이미지 경로 | `asia-northeast3-docker.pkg.dev/arch-diagnose/competition-analyzer/app` |
| GCS 버킷 | `kunwon-competition-db` |
| 서비스 계정 | `30350777436-compute@developer.gserviceaccount.com` |
| 서비스 URL | `https://competition-analyzer-30350777436.asia-northeast3.run.app` |

---

## 2. 기술 선택 이유

### Cloud Run을 쓰는 이유
- **서버리스** — 트래픽 없으면 과금 없음 (회사 내부 툴에 적합)
- **컨테이너 기반** — 로컬 개발 환경과 동일하게 동작
- **GCS 볼륨 마운트** — JSON 파일 DB를 S3처럼 영구 보관 (별도 DB 서버 불필요)
- **gen2 실행환경** — GCS 볼륨 마운트, 긴 타임아웃(최대 3600s) 지원

### GCS를 DB로 쓰는 이유
- JSON 파일 기반 데이터 → 별도 DB 서버(PostgreSQL 등) 불필요
- Cloud Run 인스턴스가 죽어도 데이터 영구 보관
- `gsutil rsync`로 로컬 데이터와 동기화 가능

### Artifact Registry를 쓰는 이유
- GCP 네이티브 Docker 레지스트리 → Cloud Run과 인증 연동 자동
- Docker Hub 대비 private 이미지 관리 용이

### Secret Manager를 쓰는 이유
- API 키를 환경변수 평문으로 저장하면 `gcloud run describe`로 노출됨
- Secret Manager는 IAM으로 접근 제어, 버전 관리, 감사 로그 지원

---

## 3. 최초 GCP 셋업 (1회만)

### 3-1. GCP 프로젝트 생성 후 API 활성화

```bash
gcloud config set project {프로젝트-ID}

gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  storage.googleapis.com \
  cloudbuild.googleapis.com
```

### 3-2. Artifact Registry 레지스트리 생성

```bash
gcloud artifacts repositories create {레지스트리명} \
  --repository-format=docker \
  --location=asia-northeast3 \
  --description="앱 Docker 이미지"
```

### 3-3. GCS 버킷 생성 (영구 데이터용)

```bash
gsutil mb -l asia-northeast3 gs://{버킷명}
```

> 버킷명은 전 세계에서 유일해야 함. `{회사명}-{앱명}-db` 패턴 추천.

### 3-4. Secret Manager에 API 키 등록

```bash
# 시크릿 생성 (최초)
echo -n "sk-ant-실제키값" | gcloud secrets create anthropic-api-key \
  --data-file=- \
  --replication-policy=automatic

# 이후 키 교체 시
echo -n "sk-ant-새키값" | gcloud secrets versions add anthropic-api-key \
  --data-file=-
```

### 3-5. 서비스 계정 권한 설정

Cloud Run은 기본 Compute 서비스 계정(`{프로젝트번호}-compute@developer.gserviceaccount.com`)으로 실행됨.

```bash
SA="{프로젝트번호}-compute@developer.gserviceaccount.com"

# GCS 버킷 읽기/쓰기
gsutil iam ch serviceAccount:${SA}:roles/storage.objectAdmin gs://{버킷명}

# Secret Manager 읽기
gcloud secrets add-iam-policy-binding anthropic-api-key \
  --member="serviceAccount:${SA}" \
  --role=roles/secretmanager.secretAccessor
```

### 3-6. GitHub Actions용 서비스 계정 키 생성

```bash
# 배포 전용 서비스 계정 생성
gcloud iam service-accounts create github-deployer \
  --display-name="GitHub Actions Deployer"

# 필요한 역할 부여
DEPLOYER="github-deployer@{프로젝트-ID}.iam.gserviceaccount.com"
gcloud projects add-iam-policy-binding {프로젝트-ID} \
  --member="serviceAccount:${DEPLOYER}" \
  --role=roles/run.admin

gcloud projects add-iam-policy-binding {프로젝트-ID} \
  --member="serviceAccount:${DEPLOYER}" \
  --role=roles/artifactregistry.writer

gcloud projects add-iam-policy-binding {프로젝트-ID} \
  --member="serviceAccount:${DEPLOYER}" \
  --role=roles/iam.serviceAccountUser

# JSON 키 발급
gcloud iam service-accounts keys create key.json \
  --iam-account="${DEPLOYER}"
```

발급된 `key.json` 내용을 GitHub → Settings → Secrets → `GCP_SA_KEY`로 등록.

> ⚠️ `key.json`은 `.gitignore`에 반드시 추가. 절대 커밋 금지.

---

## 4. Dockerfile 작성법

### 이 프로젝트의 Dockerfile

```dockerfile
# Stage 1: React 프론트엔드 빌드
FROM node:20-slim AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Python 백엔드 (최종 이미지)
FROM python:3.12-slim
WORKDIR /app

# Stage 1에서 빌드된 정적 파일만 복사
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# 서버 전용 requirements (데스크톱 의존성 제외)
COPY backend/requirements-server.txt ./
RUN pip install --no-cache-dir -r requirements-server.txt

COPY backend/ ./backend/
WORKDIR /app/backend

ENV PYTHONUNBUFFERED=1
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
```

### 핵심 포인트

| 포인트 | 설명 |
|--------|------|
| **멀티스테이지 빌드** | Node.js 이미지(~500MB)가 최종 이미지에 포함되지 않음. Python slim만 사용 |
| **포트 8080** | Cloud Run은 기본적으로 8080 포트 수신. 다른 포트 사용 시 `--port` 환경변수 설정 필요 |
| **requirements-server.txt 분리** | `requirements.txt`에는 PyInstaller, PyWebView 등 데스크톱 전용 패키지 포함. 서버용은 별도 파일로 분리 |
| **`--no-cache-dir`** | pip 캐시 저장 안 함 → 이미지 크기 감소 |
| **`npm ci`** | `npm install` 대신 사용. lock 파일 기준으로 정확히 설치, CI 환경에 적합 |
| **PYTHONUNBUFFERED=1** | Python 출력 버퍼링 비활성화 → Cloud Run 로그에 즉시 표시 |

### requirements-server.txt 분리 방법

```
# requirements.txt (로컬 개발 + 데스크톱 빌드 전체)
fastapi
uvicorn[standard]
anthropic
PyMuPDF
pywebview       # ← 서버에서 불필요
pyinstaller     # ← 서버에서 불필요
...

# requirements-server.txt (서버 전용 — 불필요 패키지 제외)
fastapi
uvicorn[standard]
anthropic
PyMuPDF
...
```

---

## 5. GitHub Actions 워크플로우

### 이 프로젝트의 deploy.yml

```yaml
name: Deploy to Cloud Run

on:
  push:
    branches: [main]        # main 브랜치 push 시 자동 배포
  workflow_dispatch:         # 수동 트리거도 가능

env:
  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true   # Actions 환경 Node 버전 경고 억제
  IMAGE: asia-northeast3-docker.pkg.dev/arch-diagnose/competition-analyzer/app

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      # GCP 인증
      - uses: google-github-actions/auth@v2
        with:
          credentials_json: ${{ secrets.GCP_SA_KEY }}

      # gcloud CLI 셋업
      - uses: google-github-actions/setup-gcloud@v2

      # Artifact Registry에 Docker 인증
      - name: Configure Docker for Artifact Registry
        run: gcloud auth configure-docker asia-northeast3-docker.pkg.dev --quiet

      # 빌드 & 푸시
      - name: Build and push Docker image
        run: |
          docker build -t $IMAGE .
          docker push $IMAGE

      # Cloud Run 배포
      - name: Deploy to Cloud Run
        run: |
          gcloud run deploy competition-analyzer \
            --image $IMAGE \
            --region asia-northeast3 \
            --project arch-diagnose \
            --execution-environment gen2 \
            --add-volume name=db,type=cloud-storage,bucket=kunwon-competition-db \
            --add-volume-mount volume=db,mount-path=/data \
            --update-env-vars DB_PATH=/data,PYTHONUNBUFFERED=1 \
            --remove-env-vars ANTHROPIC_API_KEY \
            --memory 2Gi \
            --cpu 2 \
            --timeout 3600 \
            --max-instances 1 \
            --allow-unauthenticated
```

### 배포 명령어 옵션 설명

| 옵션 | 값 | 이유 |
|------|----|------|
| `--execution-environment gen2` | gen2 | GCS 볼륨 마운트는 gen2에서만 지원 |
| `--add-volume` / `--add-volume-mount` | GCS 버킷 | JSON DB 파일 영구 보관 |
| `--update-env-vars` | DB_PATH, PYTHONUNBUFFERED | 앱에서 읽는 환경변수 |
| `--remove-env-vars ANTHROPIC_API_KEY` | - | 이전 배포에서 실수로 평문 저장된 키 제거 |
| `--memory 2Gi` | 2GB | PDF 래스터라이즈(PyMuPDF) + LLM 응답 처리에 필요 |
| `--cpu 2` | 2코어 | PDF 처리 + uvicorn 동시 처리 |
| `--timeout 3600` | 1시간 | 대용량 PDF 처리 + LLM 연쇄 호출 시간 |
| `--max-instances 1` | 1개 | JSON 파일 DB → 동시 쓰기 충돌 방지 |
| `--allow-unauthenticated` | - | 사내 사용자가 Google 계정 없이 접근 가능 |

---

## 6. 배포 명령어 전체

### 수동 빌드 & 배포 (Actions 없이)

```bash
# 1. GCP 로그인
gcloud auth login
gcloud config set project arch-diagnose

# 2. Docker 인증
gcloud auth configure-docker asia-northeast3-docker.pkg.dev

# 3. 이미지 빌드 & 푸시
IMAGE="asia-northeast3-docker.pkg.dev/arch-diagnose/competition-analyzer/app"
docker build -t $IMAGE .
docker push $IMAGE

# 4. Cloud Run 배포
gcloud run deploy competition-analyzer \
  --image $IMAGE \
  --region asia-northeast3 \
  --execution-environment gen2 \
  --add-volume name=db,type=cloud-storage,bucket=kunwon-competition-db \
  --add-volume-mount volume=db,mount-path=/data \
  --update-env-vars DB_PATH=/data,PYTHONUNBUFFERED=1 \
  --remove-env-vars ANTHROPIC_API_KEY \
  --memory 2Gi --cpu 2 --timeout 3600 \
  --max-instances 1 --allow-unauthenticated
```

### gcloud builds를 쓰는 방법 (로컬 Docker 없이)

```bash
# Cloud Build로 빌드 + Artifact Registry 푸시를 GCP에서 실행
gcloud builds submit \
  --tag asia-northeast3-docker.pkg.dev/arch-diagnose/competition-analyzer/app .
```

> 로컬에 Docker가 없거나 이미지가 커서 업로드가 느릴 때 유리.
> Cloud Build 비용 별도 발생 (월 120분 무료).

---

## 7. 겪었던 오류 & 해결법

### 오류 1: GCS 볼륨 마운트 실패
```
Error: volume type cloud-storage is not supported in gen1 execution environment
```
**원인:** Cloud Run 기본 실행환경(gen1)은 GCS 볼륨 마운트 미지원.  
**해결:** `--execution-environment gen2` 옵션 추가.

---

### 오류 2: 서비스 계정 GCS 권한 없음
```
403 Forbidden: Access denied to bucket 'kunwon-competition-db'
```
**원인:** Cloud Run 서비스 계정에 GCS 버킷 권한 미부여.  
**해결:**
```bash
gsutil iam ch serviceAccount:{SA}:roles/storage.objectAdmin gs://kunwon-competition-db
```

---

### 오류 3: Docker 이미지에 PyWebView/PyInstaller가 포함되어 빌드 실패
```
ERROR: Failed building wheel for pywebview
```
**원인:** `requirements.txt`에 데스크톱 전용 패키지 포함. Linux 서버 환경에서 컴파일 실패.  
**해결:** `requirements-server.txt` 별도 파일로 서버 전용 패키지만 관리. Dockerfile에서 `-server.txt` 사용.

---

### 오류 4: 요청 타임아웃 (대용량 PDF)
```
503 Service Unavailable (deadline exceeded)
```
**원인:** Cloud Run 기본 타임아웃 300초. PDF 래스터라이즈 + 다중 LLM 호출이 초과.  
**해결:** `--timeout 3600` (최대 3600초).

---

### 오류 5: 메모리 초과 (OOM)
```
Container exceeded memory limit. Killed.
```
**원인:** 고해상도 PDF(100페이지+) 래스터라이즈 시 메모리 급증.  
**해결:** `--memory 2Gi`. (필요 시 4Gi까지 가능, 비용 비례 증가)

---

### 오류 6: API 키가 배포 후에도 평문 노출
```
gcloud run describe competition-analyzer
→ ANTHROPIC_API_KEY: sk-ant-...  ← 노출됨
```
**원인:** 초기 테스트 시 `--set-env-vars ANTHROPIC_API_KEY=...`로 직접 설정했던 값이 남음.  
**해결:** `--remove-env-vars ANTHROPIC_API_KEY`를 배포 명령에 항상 포함. Secret Manager로 분리.
```bash
# Secret Manager에서 주입하는 방식
--set-secrets ANTHROPIC_API_KEY=anthropic-api-key:latest
```

---

### 오류 7: GitHub Actions에서 gcloud 인증 실패
```
Error: google-github-actions/auth failed: ...credentials_json is not valid JSON
```
**원인:** GitHub Secret에 key.json을 등록할 때 파일 내용 복사 오류 (BOM, 줄바꿈 등).  
**해결:**
```bash
# key.json을 base64 인코딩 없이 그대로 복사해야 함
# Windows에서는 PowerShell로 확인
Get-Content key.json -Raw | clip  # 클립보드에 복사 후 GitHub Secret에 붙여넣기
```

---

### 오류 8: Cloud Run 콜드 스타트 후 첫 요청 5~10초 지연
**원인:** 인스턴스가 꺼진 상태(scale to zero)에서 첫 요청 시 컨테이너 기동 시간.  
**해결 옵션:**
- 방치: 내부 툴은 허용 가능
- 최소 인스턴스 1개 유지: `--min-instances 1` (월 ~$10 추가)
- Cloud Scheduler로 1분마다 워밍업 핑 (무료)

```bash
# 워밍업 핑 (Cloud Scheduler)
gcloud scheduler jobs create http warmup-competition-analyzer \
  --schedule="*/5 * * * *" \
  --uri="https://competition-analyzer-30350777436.asia-northeast3.run.app/api/health" \
  --time-zone="Asia/Seoul"
```

---

### 오류 9: `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24` 없어서 경고
```
Warning: Node.js 16 actions are deprecated...
```
**원인:** google-github-actions 구버전이 Node 16 사용.  
**해결:** workflow env에 `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true` 추가. 근본 해결은 actions 버전 업데이트.

---

### 오류 10: max-instances 없이 동시 요청 → JSON 파일 충돌
**원인:** Cloud Run은 기본적으로 여러 인스턴스를 동시에 띄움. JSON 파일 DB는 파일 잠금 없음.  
**해결:** `--max-instances 1`. (진짜 DB: PostgreSQL/Firestore 사용 시 불필요)

---

## 8. 운영 중 자주 하는 작업

### 로그 확인
```bash
# 최근 50줄
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=competition-analyzer" \
  --limit=50 --format="table(timestamp, textPayload)"

# 실시간 스트리밍
gcloud beta run services logs tail competition-analyzer --region=asia-northeast3
```

### API 키 교체
```bash
echo -n "sk-ant-새키" | gcloud secrets versions add anthropic-api-key --data-file=-
# Cloud Run은 재시작 시 자동으로 latest 버전 사용
# 즉시 적용하려면 트래픽 재배포
gcloud run services update competition-analyzer --region=asia-northeast3
```

### 로컬 데이터 → GCS 동기화
```bash
# 로컬 → GCS (덮어쓰기 동기화)
gsutil -m rsync -r -d "M:\KUNWON_COMPETITION_DB" gs://kunwon-competition-db

# GCS → 로컬 (백업)
gsutil -m rsync -r gs://kunwon-competition-db "C:\Backup\competition-db"
```

### 서비스 일시 중지 (비용 절감)
```bash
# 트래픽 차단 (이미지는 유지)
gcloud run services update-traffic competition-analyzer \
  --to-revisions=LATEST=0 --region=asia-northeast3

# 복구
gcloud run services update-traffic competition-analyzer \
  --to-revisions=LATEST=100 --region=asia-northeast3
```

### 특정 리비전으로 롤백
```bash
# 리비전 목록 확인
gcloud run revisions list --service=competition-analyzer --region=asia-northeast3

# 이전 버전으로 트래픽 전환
gcloud run services update-traffic competition-analyzer \
  --to-revisions={리비전명}=100 --region=asia-northeast3
```

---

## 9. 비용 구조

| 항목 | 요금 | 비고 |
|------|------|------|
| **Cloud Run** | 요청 기반 과금 | 월 200만 요청 무료. 내부 툴 수준이면 무료 범위 내 |
| Cloud Run CPU | $0.00002400/vCPU·초 | 요청 처리 중에만 과금 |
| Cloud Run 메모리 | $0.00000250/GiB·초 | 요청 처리 중에만 과금 |
| **Artifact Registry** | $0.10/GB·월 | 이미지 저장 (보통 1~2GB → $0.10~0.20) |
| **GCS 스토리지** | $0.023/GB·월 | JSON + HTML 파일 (수 GB 이하면 미미) |
| GCS 읽기 | 무료 | Cloud Run → GCS (같은 리전) |
| GCS 쓰기 | $0.05/만 작업 | |
| **Secret Manager** | $0.06/시크릿·월 | 활성 버전 1개당 |
| **Cloud Build** (선택) | 월 120분 무료 | 초과 시 $0.003/분 |
| **예상 월 합계** | **$2~5** | 일반 사내 사용 기준 |

> `--min-instances 1` 설정 시 항상 켜져 있어 +$10~15/월 추가.

---

## 10. 다른 앱에 적용할 때 체크리스트

### 신규 앱 배포 시 바꿔야 하는 값

```
□ GCP 프로젝트 ID
□ Cloud Run 서비스명
□ Artifact Registry 레지스트리명
□ Docker 이미지 경로
□ GCS 버킷명 (필요 시)
□ 리전 (기본 asia-northeast3)
□ 메모리 / CPU / 타임아웃 (앱 특성에 맞게)
□ 환경변수 (DB_PATH, 기타 앱별 변수)
□ GitHub Secret 이름 (GCP_SA_KEY)
```

### 앱 유형별 설정 권고

| 앱 유형 | 메모리 | CPU | 타임아웃 | max-instances |
|---------|--------|-----|---------|--------------|
| 단순 API | 512Mi | 1 | 60s | 10+ |
| LLM 포함 API | 1~2Gi | 2 | 600~3600s | 제한 없음 |
| PDF/이미지 처리 | 2~4Gi | 2 | 3600s | 1~3 |
| 파일 DB 사용 | 어느 것이든 | 어느 것이든 | 어느 것이든 | **1 필수** |

### 보안 체크리스트

```
□ API 키는 Secret Manager 사용 (env vars 평문 금지)
□ key.json은 .gitignore에 추가
□ env.yaml 등 키 포함 파일은 .gitignore에 추가
□ --remove-env-vars로 이전 평문 키 제거
□ --allow-unauthenticated 대신 IAP(Identity-Aware Proxy) 고려 (외부 노출 시)
□ GCS 버킷 공개 접근 차단 확인
```

### Dockerfile 공통 패턴

```dockerfile
# FastAPI + React 멀티스테이지 빌드 템플릿
FROM node:{버전}-slim AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:{버전}-slim
WORKDIR /app
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist
COPY backend/requirements-server.txt ./     # ← 서버 전용 requirements
RUN pip install --no-cache-dir -r requirements-server.txt
COPY backend/ ./backend/
WORKDIR /app/backend
ENV PYTHONUNBUFFERED=1
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
#                                                              ^^^^
#                                           Cloud Run은 8080 기본 수신
```

### deploy.yml 공통 템플릿

```yaml
name: Deploy to Cloud Run
on:
  push:
    branches: [main]
  workflow_dispatch:

env:
  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true
  IMAGE: asia-northeast3-docker.pkg.dev/{프로젝트}/{레지스트리}/app

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: google-github-actions/auth@v2
        with:
          credentials_json: ${{ secrets.GCP_SA_KEY }}
      - uses: google-github-actions/setup-gcloud@v2
      - run: gcloud auth configure-docker asia-northeast3-docker.pkg.dev --quiet
      - run: |
          docker build -t $IMAGE .
          docker push $IMAGE
      - run: |
          gcloud run deploy {서비스명} \
            --image $IMAGE \
            --region asia-northeast3 \
            --project {프로젝트-ID} \
            --execution-environment gen2 \
            --memory {Gi} \
            --cpu {n} \
            --timeout {s} \
            --max-instances {n} \
            --allow-unauthenticated
            # GCS 볼륨 필요 시:
            # --add-volume name=db,type=cloud-storage,bucket={버킷명} \
            # --add-volume-mount volume=db,mount-path=/data \
            # Secret 필요 시:
            # --set-secrets {ENV_NAME}={시크릿명}:latest \
```

---

## 참고 링크

- [Cloud Run 공식 문서](https://cloud.google.com/run/docs)
- [Cloud Run GCS 볼륨 마운트](https://cloud.google.com/run/docs/configuring/services/cloud-storage-volume-mounts)
- [Artifact Registry Docker 가이드](https://cloud.google.com/artifact-registry/docs/docker)
- [Secret Manager 사용법](https://cloud.google.com/secret-manager/docs/creating-and-accessing-secrets)
- [github-actions/auth](https://github.com/google-github-actions/auth)
