# DEPLOYMENT.md — 설계공모 경쟁분석 배포 가이드

## 배포 구조

```text
개발자 PC
  │  git push → main 브랜치
  │
  ▼
GitHub Actions (ubuntu-latest) — .github/workflows/deploy.yml
  │  1. docker build (Node.js 빌드 → Python 백엔드)
  │  2. Artifact Registry에 이미지 push
  │  3. Cloud Run 배포
  │
  ▼
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
| ---- | --- |
| 프로젝트 ID | `arch-diagnose` |
| 프로젝트 번호 | `30350777436` |
| 리전 | `asia-northeast3` (서울) |
| Cloud Run 서비스명 | `competition-analyzer` |
| Artifact Registry | `competition-analyzer` |
| GCS 버킷 | `kunwon-competition-db` |
| 서비스 계정 | `30350777436-compute@developer.gserviceaccount.com` |

---

## 환경변수

| 변수 | 값 | 설명 |
| ---- | --- | ---- |
| `DB_PATH` | `/data` | GCS 마운트 경로 → DB 루트 |
| `PYTHONUNBUFFERED` | `1` | 로그 실시간 출력 |

> `ANTHROPIC_API_KEY`는 디스크에 저장하지 않음. 사용자가 앱 설정 탭에서 입력 → 서버 메모리에만 보관 (서버 재시작 시 초기화).

---

## 코드 수정 후 재배포

**`main` 브랜치에 push하면 GitHub Actions가 자동으로 빌드 및 배포합니다. 별도 명령 불필요.**

```bash
git add .
git commit -m "변경 내용"
git push origin main
# → GitHub Actions 자동 실행 → Cloud Run 배포 완료
```

배포 상태 확인:

- GitHub Actions 탭: 워크플로우 실행 로그
- Cloud Run 콘솔: revision 타임스탬프로 배포 완료 여부 확인

### 수동 배포 (Actions 실패 시 fallback)

```powershell
cd d:\APPS\competition_comparison
gcloud run deploy competition-analyzer --source . --region asia-northeast3
```

---

## API 키 교체

앱 설정 탭에서 입력하면 메모리에만 저장됩니다. 서버 재시작 시 초기화되므로 재입력 필요.

환경변수로 영구 설정하려면 Cloud Run 콘솔 → 환경변수에서 `ANTHROPIC_API_KEY` 추가.

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
gsutil iam ch serviceAccount:30350777436-compute@developer.gserviceaccount.com:roles/storage.objectAdmin gs://kunwon-competition-db
```

GitHub Actions가 사용하는 `GCP_SA_KEY` 시크릿은 GitHub 저장소 Settings → Secrets and variables → Actions에서 관리.

---

## 비용

| 항목 | 요금 |
| ---- | ---- |
| Cloud Run | 요청 있을 때만 과금 (월 200만 요청 무료) |
| GCS 스토리지 | ~$0.02/GB/월 |
| GCS 네트워크 | 읽기 무료, 외부 전송 $0.12/GB |
| **예상 월 합계** | **$2~5** (일반 사용 기준) |

---

## 트러블슈팅

### 프로젝트 목록이 안 보일 때

1. 서비스 계정 버킷 권한 확인: `gsutil iam get gs://kunwon-competition-db`
2. GCS 버킷 데이터 확인: `gsutil ls gs://kunwon-competition-db/public/`
3. Cloud Run 로그 확인: `gcloud logging read "resource.type=cloud_run_revision" --limit=50`

### 콜드 스타트 (첫 접속 느림)

인스턴스가 꺼진 상태에서 첫 요청 시 5~10초 지연 발생. 정상 동작.

### API 키 오류 (401/402)

앱 설정 탭에서 API 키 재입력. 서버 재시작 시 항상 초기화됨.

### GitHub Actions 배포 실패 시

1. GitHub → Actions 탭에서 오류 로그 확인
2. `secrets.GCP_SA_KEY`가 만료되었거나 누락된 경우 → GitHub 저장소 Settings → Secrets에서 갱신
3. Fallback: 위 수동 배포 명령 실행
