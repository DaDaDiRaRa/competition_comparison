# DEPLOYMENT.md — 설계공모 경쟁분석 배포 가이드

## 배포 구조

```
외부 PC (브라우저)
       ↓ HTTPS
Google Cloud Run (asia-northeast3)
  - 이미지: asia-northeast3-docker.pkg.dev/arch-diagnose/competition-analyzer/app
  - 실행환경: gen2 (GCS 볼륨 마운트 지원)
  - 메모리: 2Gi / CPU: 2 / 타임아웃: 3600s
       ↓ /data 마운트
Google Cloud Storage (gs://kunwon-competition-db)
  - DB 파일 영구 저장 (JSON, HTML 리포트)
  - 서비스 계정: 30350777436-compute@developer.gserviceaccount.com
```

**서비스 URL:** `https://competition-analyzer-30350777436.asia-northeast3.run.app`

---

## GCP 프로젝트 정보

| 항목 | 값 |
|------|-----|
| 프로젝트 ID | `arch-diagnose` |
| 프로젝트 번호 | `30350777436` |
| 리전 | `asia-northeast3` (서울) |
| Cloud Run 서비스명 | `competition-analyzer` |
| Artifact Registry | `competition-analyzer` |
| GCS 버킷 | `kunwon-competition-db` |
| 서비스 계정 | `30350777436-compute@developer.gserviceaccount.com` |
| API 키 Secret | `anthropic-api-key` (Secret Manager) |

---

## 환경변수

| 변수 | 값 | 설명 |
|------|-----|------|
| `DB_PATH` | `/data` | GCS 마운트 경로 → DB 루트 |
| `ANTHROPIC_API_KEY` | Secret Manager 참조 | Claude API 키 (메모리에만 보관) |
| `PYTHONUNBUFFERED` | `1` | 로그 실시간 출력 |

---

## 코드 수정 후 재배포

```cmd
# 1. 이미지 빌드 & 푸시
gcloud builds submit --tag asia-northeast3-docker.pkg.dev/arch-diagnose/competition-analyzer/app .

# 2. Cloud Run 재배포
gcloud run deploy competition-analyzer --image=asia-northeast3-docker.pkg.dev/arch-diagnose/competition-analyzer/app --region=asia-northeast3 --execution-environment=gen2 --add-volume=name=db,type=cloud-storage,bucket=kunwon-competition-db --add-volume-mount=volume=db,mount-path=/data --set-env-vars=DB_PATH=/data --set-secrets=ANTHROPIC_API_KEY=anthropic-api-key:latest --memory=2Gi --cpu=2 --timeout=3600 --allow-unauthenticated
```

---

## API 키 교체

```cmd
# 새 버전 추가
echo -n "sk-ant-새키" | gcloud secrets versions add anthropic-api-key --data-file=-

# Cloud Run은 자동으로 latest 버전을 사용하므로 재배포 불필요
# (단, 새 인스턴스가 뜰 때 적용됨 — 강제 적용 시 재배포)
```

---

## GCS 데이터 관리

### 기존 데이터 업로드 (최초 1회 또는 수동 동기화)
```cmd
gsutil -m cp -r "M:\06_설계사업6본부\설계사업6본부 1소\01 개인폴더\16 김정현\KUNWON_COMPETITION_DB\*" gs://kunwon-competition-db/
```

### 버킷 내용 확인
```cmd
gsutil ls gs://kunwon-competition-db/
gsutil ls gs://kunwon-competition-db/public/
```

### 서비스 계정 버킷 권한 부여 (최초 1회)
```cmd
gsutil iam ch serviceAccount:30350777436-compute@developer.gserviceaccount.com:roles/storage.objectAdmin gs://kunwon-competition-db
```

---

## 권한 설정 (최초 1회)

```cmd
# Secret Manager 서비스 활성화
gcloud services enable secretmanager.googleapis.com

# 서비스 계정에 Secret 접근 권한
gcloud secrets add-iam-policy-binding anthropic-api-key --member=serviceAccount:30350777436-compute@developer.gserviceaccount.com --role=roles/secretmanager.secretAccessor

# 서비스 계정에 GCS 버킷 접근 권한
gsutil iam ch serviceAccount:30350777436-compute@developer.gserviceaccount.com:roles/storage.objectAdmin gs://kunwon-competition-db
```

---

## 비용

| 항목 | 요금 |
|------|------|
| Cloud Run | 요청 있을 때만 과금 (월 200만 요청 무료) |
| GCS 스토리지 | ~$0.02/GB/월 |
| GCS 네트워크 | 읽기 무료, 외부 전송 $0.12/GB |
| **예상 월 합계** | **$2~5** (일반 사용 기준) |

---

## 데스크톱 앱 (PyInstaller) 병행 사용

로컬 Windows에서 데스크톱 앱은 기존과 동일하게 `M:\` 드라이브 사용.
웹 앱은 GCS 버킷을 DB로 사용하므로 **데이터가 별도로 관리됨** — 양쪽 동기화는 수동 `gsutil rsync` 필요.

```cmd
# M:\ → GCS 동기화 (필요 시)
gsutil -m rsync -r -d "M:\06_설계사업6본부\설계사업6본부 1소\01 개인폴더\16 김정현\KUNWON_COMPETITION_DB" gs://kunwon-competition-db
```

---

## 트러블슈팅

### 프로젝트 목록이 안 보일 때
1. 서비스 계정 버킷 권한 확인: `gsutil iam get gs://kunwon-competition-db`
2. GCS 버킷 데이터 확인: `gsutil ls gs://kunwon-competition-db/public/`
3. Cloud Run 로그 확인: `gcloud logging read "resource.type=cloud_run_revision" --limit=50`

### 콜드 스타트 (첫 접속 느림)
인스턴스가 꺼진 상태에서 첫 요청 시 5~10초 지연 발생. 정상 동작.
최소 인스턴스 1개 유지 시 해소되나 비용 증가 ($10~15/월 추가).

### API 키 오류
Secret Manager에서 키 확인: `gcloud secrets versions access latest --secret=anthropic-api-key`
