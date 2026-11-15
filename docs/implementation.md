# 배포 구현 결정과 현재 상태

## 현재 상태

GitHub 원격 Repository, 기본 설정, ruleset 4개와 CodeQL Default setup이 구성되어 있다.
Repository에는 배포 도구, 대상별 목표 상태, CI와 Release workflow가 구성되어 있다. CI는 Validation
container를 사용하여 Markdown, YAML, GitHub Actions, JSON과 JSON Schema, Docker Compose, Python,
Shell, systemd, Release asset, checksum과 Public 범위를 검사하고 High 이상 Node.js 의존성 취약점을
거부한다. Release workflow는 같은 Validation container와 보호된 version tag,
원격 `main`, version manifest, 대상별 component와
Compose image 변수의 일치를 검증한다. 읽기 전용 build job은 계약에 맞는 GHCR image 취득, asset 생성과
독립 검증을 수행하고 쓰기 권한을 가진 publish job은 검증된 artifact만 Draft Release로 게시한다.
`component-images.yml`은 수동 실행으로 component image를 선택하고 필요한 image를 빌드한다.

환경설정은 Release 설정, 장비 환경설정, Component 설정, 비밀정보와 PKI 상태로 분리되어 있다.
대상별 `.env.example`은 공개 schema이고 실제 값은 대상 장비의 Git 외부 파일에서 관리한다.
`delivery/validate-environment`는 실제 값을 출력하지 않고 schema version, 변수 집합과 빈 값을
검사한다. `delivery/install-environment`는 환경 파일을 최초 설치하고 재실행 시 기존 값을 보존한다.
설치 권한과 동기화 규칙은 [docs/configuration-management.md](configuration-management.md)를 따른다.
`delivery/apply-release`는 host에서 파생한 group ID를 실제 환경 파일에 동기화한다.
systemd unit은 실제 환경 파일, Release에서 생성한 `release.env`와 Edge generated environment 파일을
Compose 실행 환경으로 사용한다.

`delivery/install-dashboard-configuration`과 `delivery/validate-dashboard-configuration`은 Server의
Dashboard runtime JSON 최초 설치, 기존 파일 보존, 필드와 식별자 검증, expected 식별자 비교와
파일 권한 검증을 구현한다. 두 Bash 진입점은 Python 표준 라이브러리만 사용하는
`delivery/dashboard_configuration.py`를 실행한다. 설치는 directory 및 파일 lock과 no-clobber
전환을 사용하며 실패 시 기존 설정을 변경하지 않는다. 재현 명령과 설정 소유권은
[docs/configuration-management.md](configuration-management.md)의 Dashboard 설정을 따른다.
두 도구와 Python module은 Server의 Online Package와 Offline Bundle에만 포함된다. Server Release 적용과 systemd 시작은 runtime JSON 검증을 수행한다. Compose mount와
Backend 식별자 자동 주입은 구현되지 않았다.

`tests/test_dashboard_configuration.py`는 식별자 경계, 잘못된 JSON, 기존 byte 및 inode 보존,
동시 최초 설치, file mode, 실제 root 소유권과 link 경로 거부를 검증한다. 별도 Ubuntu test host의
read-only root filesystem Container에서 생성한 JSON의 UID `101` 읽기와 root의 read-only bind
mount 쓰기 거부를 확인한다. 이 검증은 Dashboard의 HTTP 및 HTTPS 응답과 Backend 연동 검증을
대체하지 않는다.

Edge별 Backend Bearer token과 Camera별 Camera Media Service Bearer token은 배포 도구가 생성하고
rotation하는 독립된 opaque secret으로 관리한다. 배포 도구는 256-bit token bundle 생성, Edge
원문 token 설치, Server의 component 원문 token 형식 설치와 rotation 및 이전 token 폐기를
구현한다. Backend 파일은 `EDGE_V2_DEVICES` JSON 배열이며 같은 Edge의 token을 최대 2개까지
중첩할 수 있다. Camera Media Service 파일은 `EDGE_AUTH_SECRET` JSON 객체다. Edge 제어 API token(`edge-control`)은 Edge에만 설치한다. 대상별 systemd unit은 Compose 시작 전에 인증 파일을
검증한다. `delivery/auth-registry.sh`는 Server 파일의 읽기, 형식 검증과 쓰기를 제공하고
`delivery/auth-secret-permissions.sh`는 Edge 읽기 그룹 조회와 생성, 소유권 및 mode 적용과
검증을 제공한다. 설치, rotation과 폐기는
[docs/configuration-management.md](configuration-management.md)의 접근 권한을 유지한다. 같은
credential의 재설치는 기존 파일을 교체하지 않는다. 설치 도구는 symbolic link와 hard link 경로를
거부하고 대상 directory의 lock으로 변경을 직렬화한다. Edge Container의 supplementary group은
`targets/edge/compose.yaml`이 연결하며 파일 교체 후 소비 service의 재생성은 수행하지 않는다.

`targets/edge/compose.yaml`은 calibration-api의 health check를 정의하고 lidar-processing, measurement-uplink와
edge-orchestrator가 calibration-api의 `service_healthy`를 기다리도록 `depends_on`을 구성한다. 개발 장비의 재부팅으로
이 시작 순서를 확인했다.

`tests/test_auth_secret_permissions.py`는 격리한 root Validation container에서 실제 그룹 생성,
non-root 읽기, 쓰기 및 다른 읽기 그룹의 접근 거부와 잘못된 소유권 및 그룹 검출을 검증한다.
시험용 `--root`는 해당 fixture root의 소유자와 그룹을 사용하며 host 계정을 변경하지 않는다.
별도 Ubuntu test host의 실제 Docker Compose file secret 검증은 supplementary group 읽기,
그룹 불일치의 읽기 거부와 root의 read-only mount 쓰기 거부를 확인한다. 이 검증은 실제 component의
인증 연동이나 token rotation 적용 완료를 대체하지 않는다.

`delivery/apply-release`는 Package mode, host architecture와 image platform을 검증하고 취득 전용
파일을 제외한 실행 payload를 `versions/<version>` 불변 경로에 staging한다. Manifest에서 release.env를,
Edge 설정 원본에서 CONFIG_SHA256을 생성하고 환경, secret과 Compose를 검증한 뒤 current와
previous를 원자적으로 전환한다. Compose 상태 검사는 모든 Container의 `running`과 health check가
있는 Container의 `healthy`를 요구한다. systemd와 Compose 실행 상태가 실패하면 이전 link, Edge 파생
설정과 Server 인증서를 복구한다.

`delivery/verify-release`는 asset checksum, archive 경로와 파일 형식, descriptor, Manifest,
version, target, mode와 platform을 교차 검증한다. `delivery/online/fetch-release`는 고정된
GitHub Repository에서 명시한 version의 Online Package와 checksum만 HTTPS로 취득하고
검증이 완료된 디렉토리를 원자적으로 공개한다.

`delivery/offline/import-bundle`은 Offline Bundle에 공통 asset 검증을 적용한 후 대상별
image archive를 Docker에 stream으로 load한다. Manifest가 참조한 각 image digest의 local
존재와 `linux/arm64` 또는 `linux/amd64` platform을 다시 확인한다.

PKI 도구는 기존 CA의 DER 형식 SHA-256 fingerprint, Root와 Intermediate chain,
Intermediate 인증서와 암호화 key 일치, 파일 권한과 `step-ca` 설정을 검증한다. Server
인증서는 DNS SAN 1개, EC P-256 key, TLS Server 용도, chain과 남은 유효기간을 검증한다.
`ensure-server-certificate`와 일일 timer는 최초 1년 인증서 발급과 만료 122일 전 갱신, fullchain의
원자적 파일 전환, Server service reload와 실패 시 이전 인증서 복구를 수행한다.

Release manifest는 Component 출처, full commit, Component version, image digest, Package 공개
범위, Private 예외 사유, pull 인증 방식과 외부 고지 경로를 검증한다. Server target에는 Backend,
Camera Media Service, Dashboard 외에 digest 고정 third-party image인 PostgreSQL과 `step-ca`가
포함되며 manifest는 `docker.io/library`와 `docker.io/smallstep` image 경로를 허용한다. Release asset
생성기는 명시적 allowlist와 정규화된 archive metadata를 사용하여 재현 가능한 Online
Package 2개, Offline Bundle 2개와 checksum manifest 1개를 생성한다. 각 Package에는
target, mode, platform과 Manifest digest를 고정한 descriptor가 있다.

Server Package의 Dashboard Nginx 3개 파일은 `release/fetch-dashboard-assets`가 manifest의 Dashboard Release version으로 취득하고
`SHA256SUMS`로 검증한 `deployment-example.tar.gz`에서 `release/build-assets`가 추출해 넣는다(`release/dashboard_assets.py`,
`--dashboard-asset-directory`). Release workflow가 두 도구를 순서대로 실행한다.

`targets/<target>`에는 `compose.yaml`과 `.env.example`이 있고 Package는 해당 target의 source
tree를 표준 `targets/<target>` 경로로 포함한다. Edge 환경 schema `6`은 v2 runtime JSON,
`BACKEND_ORIGIN`, LiDAR sensor 식별자, 제어 API의 bind 주소와 token 및 제어 directory, host group ID 4개를 사용한다. Server 환경 schema `4`는
Dashboard TLS, Media SD 저장소와 PostgreSQL 초기화 파일 경로를 사용한다.
`delivery/edge_configuration.py`와 `delivery/validate-edge-configuration`은 배포 입력 구조와
Compose의 container 경로 일치를 검증하며 Component의 domain validator를 복제하지 않는다.
배포 적용기는 검증한 정확한 byte의 SHA-256을 생성하며 Edge systemd도 실행 전에 같은 입력을
검사한다. Compose 구성과 미확정 항목은 `장비별 개발 구성`과 `미확정 구현 결정`을 따른다.

실제 통합 version manifest와 Release는 없다. 실제 장비에서 전체 시스템을 연결하는 통합 수락
검사는 완료되지 않았다.

## Component 연동 상태

확인한 외부 source 기준은 4개이며 마지막 확인일은 2026-11-15다. 각 기준은 원격 `main`의 full Git commit으로 고정한다.
이 표는 계약 확인 기준이며 장비의 배포 image 목록이 아니다. 장비 실행 상태는 아래의
`장비별 개발 구성`을 따른다.
Source 구현, 공개 Release와 개발 장비의 구동 상태는 별도로 판정한다. Source 확인은 image 실행이나
통합 배포 성공을 의미하지 않는다.
Component의 현재 계약이 이 Repository의 정책과 충돌하면 Component의 계약을 따른다.

`tools/check-component-updates`는 이 절의 source 및 Release 기준과 GitHub의 공개 metadata를
읽기 전용으로 비교한다. Source 또는 Release 변경은 종료 code `1`, 조회 및 형식 오류는 `2`,
기준 일치는 `0`이다. `--json`은 구조화된 결과를 제공한다. Image pull, 실행, source 자동 수정과
주기적 background 실행은 수행하지 않으며 image 검증 결과는 항상 미검증으로 구분한다.
공개 조회는 인증을 요구하지 않고 API 한도에 필요한 경우에만 `GH_TOKEN` 또는 `GITHUB_TOKEN`을
환경으로 전달한다. 자격 증명과 API 응답 본문은 출력하지 않는다. 도구는 이 절의 표만 읽는다.

| Repository | 확인한 source |
| --- | --- |
| Edge Platform | [cfc692599023f7ab52c209529a101e5a830bc893](https://github.com/ajin-scrap-monitoring/ajin-edge-platform/tree/cfc692599023f7ab52c209529a101e5a830bc893) |
| Backend | [21f78942ff28d114421b1934d41642e6b334d084](https://github.com/ajin-scrap-monitoring/scrap-monitoring-backend/tree/21f78942ff28d114421b1934d41642e6b334d084) |
| Camera Media Service | [b9d3308916b59f8b2eb067c4b0685e1952fc8023](https://github.com/ajin-scrap-monitoring/ajin-camera-media-service/tree/b9d3308916b59f8b2eb067c4b0685e1952fc8023) |
| Dashboard | [eb0b215f01bc9d6959f8a78f81fc19e28e5bdbb1](https://github.com/ajin-scrap-monitoring/scrap-monitoring-dashboard/tree/eb0b215f01bc9d6959f8a78f81fc19e28e5bdbb1) |

| Component | 고정 source의 계약 | 배포 미완료 사항 |
| --- | --- | --- |
| Edge Platform | `v0.1.1` Public ARM64 v1 image, v2 processing, uplink, orchestrator와 calibration API의 `edge-v2` entrypoint와 runtime JSON, Driver `--schema-version 2.0`, file token과 Camera WSS | v2 Release와 v2 Compose 예제, Release workflow의 Package 공개 범위 |
| Backend | `v0.2.0` Public AMD64 image(main은 7 commit 앞섬), v2 Bearer ingest와 저장 Acknowledgement (ACK), `EDGE_V2_DEVICES` 원문 token JSON, PostgreSQL 17 Compose 계약과 role 분리, Alembic schema, 계정과 session, Media 제어 Application Programming Interface (API)와 날짜 녹화, health와 readiness | `MEDIA_API_TOKEN` 필수 조건, PostgreSQL 초기화 파일 전달, migration 및 backup 자동화, ingest request limit |
| Camera Media Service | AMD64 Dockerfile과 SD 저장소 Compose 계약(`compose.sd.yaml`, `SD_STORAGE.md`), Camera별 Bearer binary JPEG ingest, `EDGE_AUTH_SECRET` 원문 token JSON, 내부 HTTP API, MJPEG live와 MP4 clip, 날짜 녹화 | Release, SD host preflight 전달, Dockerfile의 health check |
| Dashboard | `v0.6.0` Public AMD64 image, v2 모니터링과 MJPEG, 날짜 녹화 및 MP4, runtime JSON, TLS 및 reverse proxy 설정 asset과 배포 예제 | 통합 Compose mount와 Release 적용 연결, Edge ingest 경로의 Dashboard 수용 여부, timeout과 Content Security Policy (CSP)의 통합 검증 |

Release 기준은 다음과 같다.

| Component | Release | 게시 image |
| --- | --- | --- |
| Edge Platform Release | `v0.1.1` | v1 image |
| Backend Release | `v0.2.0` | `ghcr.io/ajin-scrap-monitoring/scrap-monitoring-backend@sha256:3ce9df2e224654f7f8c9b1a6618df676dc091b93ea211f2c3f7324c972396ee3` |
| Camera Media Service Release | 없음 | GHCR Package 없음 |
| Dashboard Release | `v0.6.0` | `ghcr.io/ajin-scrap-monitoring/scrap-monitoring-dashboard@sha256:f7057607a0b20aae9d569012370869d6aa72cdb0b748d69d6e8c96d17067217d` |

Dashboard의 마지막 Release 이후 `main` 변경은 문서에 한정된다.

Edge와 Backend의 수신 경로 및 저장 ACK 계약은
[docs/deployment-contract.md](deployment-contract.md)의 Component 연동을 따른다.
Edge v2의 fill algorithm은 구현되지 않아
`fill_estimate=null`과 `FILL_METHOD_NOT_IMPLEMENTED`를 사용한다. 측정하지 않은 clock은
`UNSYNCED`로 표시한다.

Backend는 `EDGE_V2_DEVICES` JSON의 원문 token을, Camera Media Service는 `EDGE_AUTH_SECRET`
JSON의 원문 token을 환경변수로 읽으며 `_FILE` 변형은 없다. Backend는 Media 연결에 `MEDIA_SERVICE_URL`과 `MEDIA_API_TOKEN`을 요구하지만 Camera Media
Service의 내부 HTTP API는 Bearer 인증을 사용하지 않는다. Backend의 `MEDIA_API_TOKEN` 필수 조건은
배포의 내부 통신 기준과 일치하지 않아 외부 Repository에서 해소해야 한다. 이 강제 조건은
v1 Media 연결에 해당하며 날짜 녹화의 v2 JSON 호출은 token을 사용하지 않는다.
고정된 Backend source는 계정과 Browser session을 Database에 저장한다. 비밀번호는 Argon2id
hash로 보관하고 최초 계정의 비밀번호 길이는 12~1024자다. 관리자 설정 API는 session의 역할을
검사하며 변경 요청에 Cross-Site Request Forgery (CSRF) token을 요구한다. Session 삭제의 CSRF
검사는 선택적이며 전체 v1 조회 API의 접근 정책과 운영 계정 관리 기능은 별도 범위다.

Backend의 새 경보 처리는 임계값 판정, 반복 억제, 정상 복귀와 경보 저장을 구현하며
`EDGE_V2_OPERATIONS_ENABLED` 기본값은 `false`다. 새 경보 처리에서 Media의 이벤트 클립을 요청하는
연결과 실제 이메일 발송은 구현되지 않았다. 녹화 요청과 상태 polling은 구현되어 있으나 작업
잠금은 프로세스 내부에서만 적용하므로 단일 worker를 전제로 한다. 현재 source의 경보 로직,
녹화 연결 여부와 실제 장비에서 경보가 발생할 수 있는 조건은 별도로 판정한다.

Camera Media Service의 `/api/v2` 날짜 녹화는 기존 `/api/v1` clip API와 별도 계약이다. 기본값은
비활성이며 활성화에는 `MAX_DAILY_STORAGE_BYTES`의 명시적 저장 예산이 필요하다. 원본과 다운로드
cache의 합산 예산 및 최소 여유 공간 검사는 전체 filesystem quota나 보관 기간 보장을 대체하지
않는다. Media Dockerfile은 UID `10002`의 non-root 사용자를 지정하며 공식 Compose는 loopback
port와 clip 목록 health check를 사용한다. 이 Repository의 통합 Compose 연결은 구현되지 않았다.
실시간 영상과 이벤트 클립의 Media 경로는 `/api/v1`, 날짜 녹화 경로는 `/api/v2`다. 기능별
경로를 하나의 version prefix로 일괄 치환하지 않는다. 이벤트 클립은 Media의 최초 요청 접수
시각을 기준으로 생성하며 사건 발생 시각을 요청으로 전달하지 않는다. Media의 실시간 수신 FPS와
마지막 frame 시각을 Backend가 조회하는 전용 API 연동은 없다.

Dashboard의 공개 Release는 v2 모니터링, MJPEG live, 날짜 HTTP Live Streaming (HLS) 녹화,
MP4 clip 연동과 runtime JSON 로딩을 제공한다.
Release가 게시한 참조는 다음과 같으며 이 배포 Repository의 image 실행 검증 결과와 구분한다.

| 항목 | 게시 값 |
| --- | --- |
| Release source | `1699cad895754096d43ad88ec960e2a8b9434d6f` |
| image 참조 | `ghcr.io/ajin-scrap-monitoring/scrap-monitoring-dashboard@sha256:aa375625e3a37a2c1f883dadedeac5717882924ce4400aea6696660e0fac9f32` |
| 배포 asset | `image-reference.txt`, `nginx-config.tar.gz`, `runtime-config.example.json`, `runtime-config.schema.json`, `SHA256SUMS` |

Release 게시 상태는 개발용 Dashboard Container의 실행 version을 의미하지 않는다. 고정 source는
`camera-edge`의 상태를 카메라 행에 연결하며 수신 시각과 지연시간은 미제공 값으로 유지한다.
Camera Edge의 상태 갱신 시각을 영상 촬영 시각이나 전송 지연으로 해석하지 않는다.

Backend와 Camera Media Service의 공개 Release는 없다. 개발용 local image를 공식 Release image로
간주하지 않는다. Dashboard Release의 Backend 계약 기준은 해당 Release의
`docs/contracts/backend/manifest.json`을 따르며 최신 Backend와 자동으로 일치한다고 간주하지 않는다.
연동 경로와 proxy 동작은
[docs/deployment-contract.md](deployment-contract.md)의 Browser 영상과 모니터링 기준을 따른다.
현재 Release workflow는 `APP_VERSION`만 명시적으로 전달하며 나머지 build 입력은 Dockerfile
기본값을 사용한다. 식별자의 설정 소유권은
[docs/configuration-management.md](configuration-management.md)를 따른다.

개발용 구성의 실제 service 통합 검증에는 session, synthetic 입력, MJPEG, v2 SSE, MP4 Range,
다운로드와 삭제 후 `410` 성공 결과가 있다. 이 결과는 공개 Release 조합의 통합 배포 수락을
대체하지 않는다. 내부 공유 token을 제거한 Backend 연결, 통합 배포의 HTTPS 설정과
현재 Release 조합의 최종 통합 검증은 완료되지 않았다. Media 접근 검사는 유효한 session만
확인하며 camera 또는 pit별 접근 권한은 제공하지 않는다.

Edge v2 ingest의 최대 request byte는 미확정이며 v1의 64 KiB 제한을 v2 승인값으로 사용하지 않는다.

Edge Platform의 5개 GHCR Package는 모두 Public이며 대상 Edge에서 로그인 없이 digest 고정 pull을
사용한다.

## 장비별 개발 구성

### 장비 접근과 관리 경계

장비 작업의 host 역할은 4개다.

| 역할 | 접속 식별자 | 사용 범위 |
| --- | --- | --- |
| Ubuntu build 및 test host | `ubuntu-server` | 이 Repository 작업, image build와 격리 검증 |
| MacBook 경유 host | 로컬 Secure Shell (SSH) alias `macbookair` | 장비 접속과 파일 전달 |
| Edge 장비 | MacBook에서 사용하는 host 이름 `scrap-edge-01` | 승인된 Edge 배포와 상태 확인 |
| Scrap Server | MacBook에서 사용하는 host 이름 `scrap-server-01` | 승인된 Server 배포와 상태 확인 |

MacBook 접속 계정과 인증 key는 로컬 SSH 설정에서 읽는다. Edge와 Server 접속
계정은 `jongckim`이며 host 경로의 사용자 이름에서 추정하지 않는다. 실제 주소, tailnet의 전체
DNS 이름과 인증 key는 Repository에 기록하지 않는다. 비대화형 인증이 실패하면 반복 접속하지
않고 사용자에게 접속 복구를 요청한다.

Ubuntu host에서 MacBook을 경유하는 읽기 전용 Container 조회 명령은 다음과 같다.

```bash
ssh -T -o BatchMode=yes -o ConnectTimeout=10 macbookair \
  'ssh -T -o BatchMode=yes -o ConnectTimeout=10 jongckim@scrap-server-01 "sudo -n docker ps"'
ssh -T -o BatchMode=yes -o ConnectTimeout=10 macbookair \
  'ssh -T -o BatchMode=yes -o ConnectTimeout=10 jongckim@scrap-edge-01 "sudo -n docker ps"'
```

현재 장비 구성은 수동 개발 배포이며 `delivery/quick-start`가 설치한 통합 Release가 아니다.

### 활성 구성

장비별 개발 구성은 통합 Release와 분리되어 있다. 다음 상태는 2026-11-16에 확인했다. 새 작업은
이 문서의 값만 신뢰하지 않고 실행 Container의 metadata에서 활성 구성을 다시 확인한다.

| 대상 | 확인한 구성 |
| --- | --- |
| Server Backend | Container `scrap-monitoring-backend-check`가 source `79ba4a7`의 image `scrap-backend-deploy:79ba4a7`을 실행하며 97개의 overlay Compose file을 순서대로 적용 |
| Server Simulator | Container `scrap-monitoring-simulator-server`가 revision `3cae0a1`(main `189c0a6`과 tree 동일)을 실행 |
| Server Media | local image `policy-f6b22d1`과 SD 저장소 overlay |
| Server Dashboard | `v0.6.0` digest의 demo Container |
| Edge | Edge Platform main `cfc6925`의 service 7개와 Simulator Camera Bridge Container 1개 |

Server Backend의 마지막 overlay는 `/srv/scrap-monitoring/development/backend-height-ref-v12-20261116/compose.override.json`이며
`EDGE_V2_SIMULATION_HEIGHT_REFERENCES`의 `config_revision`만 `synthetic-fill9m-sections-v12`로 설정한다.

Edge의 service 7개(calibration-api, lidar-driver-a, lidar-driver-b, lidar-processing, measurement-uplink,
edge-orchestrator, camera-edge)는 단일 Compose file `/opt/ajin/deployments/edge-v2-main-cfc6925/compose.json`
(Compose project `ajin-edge-simulation-v2`)에서 실행하며 image tag는 `ajin-<image>:main-cfc6925`다.
부팅 unit `ajin-edge-simulation-v2.service`는 `docker compose -f compose.json up --detach --pull never`를 실행한다.
lidar-processing, measurement-uplink와 edge-orchestrator는 calibration-api의 health check가 healthy가 된 뒤 시작한다.
`ajin-edge-simulation-clock.service`는 비활성이다.

Edge의 활성 설정 revision은 `synthetic-fill9m-sections-v12`이고 기준 등록은 `synthetic-fill9m-angle-base-v12`다.
각도 구간과 단면 값은 [docs/edge-geometry.md](edge-geometry.md)가 정본이다.

Edge 개발 장비는 Docker 시작 전에 Tailscale의 DNS 설정을 기다린다. Container는 시작할 때 host의 resolver 설정을
복사하므로 Tailscale이 tailnet search domain을 `/etc/resolv.conf`에 쓰기 전에 시작한 Container는 Server의 짧은
host 이름을 해석하지 못한다. drop-in `/etc/systemd/system/docker.service.d/10-wait-tailscale-dns.conf`는
dockerd를 `tailscaled.service` 이후에 시작하고 `/usr/local/sbin/wait-tailscale-dns`를 실행한다. 이 스크립트는
search domain이 나타날 때까지 최대 60초 대기하며 시간이 지나도 Docker 시작을 막지 않는다. 이 구성은 개발 장비의
host 설정이며 제품 배포 계약에 속하지 않는다.

Server PostgreSQL의 백업 Container `scrap-postgresql-dev-20261016-backup-1`은 정지 상태이며 보관된 백업 데이터는 없다.
개발 장비는 DB 백업을 사용하지 않으며 이 결정은 개발 장비에만 적용한다.

Server Backend의 활성 Compose 목록은 Container label의
`com.docker.compose.project.config_files`가 정본이다. Backend 하나의 Compose file만 사용해
`up`, `down`, `restart` 또는 `config`를 실행하면 뒤의 overlay를 누락할 수 있다.

```bash
sudo docker inspect --format '{{ index .Config.Labels "com.docker.compose.project.config_files" }}' \
  scrap-monitoring-backend-check
sudo docker inspect --format '{{.Image}} {{index .Config.Labels "org.opencontainers.image.revision"}}' \
  scrap-monitoring-backend-check ajin-camera-media-service
```

Docker `inspect`의 전체 출력, `docker compose config`, runtime environment file과 Compose overlay에는
password, token, Database 연결 정보가 포함될 수 있다. 이 값은 출력하거나 Repository에 기록하지 않고,
필요한 field만 선별해 확인한다. 별도 관리 Frontend 개발 구성과 Media 검증 구성은 명시한 요청 없이
교체하거나 정리하지 않는다. 임의의 임시 Container가 종료되었다는 이유로 서비스의 배포 실패를
판정하지 않는다.

기존 장비의 PostgreSQL(project `scrap-postgresql-dev-20261016`)은 named volume `scrap-postgresql-dev-20261016_postgres_data`를 `/var/lib/postgresql/data`에 mount하고, Backend는 `/app/data`를, Media는 SD 경로를 bind로 사용한다(2026-11-15 읽기 전용 조회). 통합 Compose는 PostgreSQL 데이터를 `POSTGRES_DATA_PATH` host bind로 사용하므로 기존 volume 데이터의 이전은 장비 전환 단계에서 별도로 수행한다.
Database 초기화, 계정과 token 재설정, 영상 저장소 변경, PostgreSQL 전환과 정기 백업 활성화는
별도 명시적 요청이 필요한 작업이다. 기존 `admin` 계정의 비밀번호 재설정은 hidden terminal
prompt에서 수행하며 모든 기존 Browser session을 무효화한다.

```bash
sudo docker exec -it scrap-monitoring-backend-check \
  python -m src.app.cli.auth reset-password admin
```

### 개발용 component image

통합 Release에 포함할 수 없는 component는 고정한 source의 자체 Dockerfile을 ubuntu-server에서
빌드한 local image로 대체한다. 이 image는 local Docker storage에만 있으며 GHCR와 통합 Release에
게시하지 않는다. 각 image는 `io.ajin.scrap-deployment.build=development`, OCI source 및 revision
label을 가진다. Edge ARM64 image의 빌드에는 ubuntu-server의 QEMU binfmt가 필요하며 host 재부팅
시 해제된다.

| Image | Revision | Platform | Image ID |
| --- | --- | --- | --- |
| `scrap-dev/ajin-camera-media-service:main-b9d3308` | `b9d3308916b59f8b2eb067c4b0685e1952fc8023` | `linux/amd64` | `sha256:c237045432513cb60a658bf8475f7562424a9036c6ea39e364a4e2d979f050c4` |
| `scrap-dev/scrap-monitoring-backend:main-21f7894` | `21f78942ff28d114421b1934d41642e6b334d084` | `linux/amd64` | `sha256:99895959c61dfefa5cb1b7bd2c5110f2d831f0deaf7fd366efa1efbce0457ac6` |
| `scrap-dev/ajin-lidar-driver:main-cfc6925` | `cfc692599023f7ab52c209529a101e5a830bc893` | `linux/arm64` | `sha256:e5dca8d6a868a0fce3e190cf4f3656e760e8daa3390e24a9940955f821faa8f3` |
| `scrap-dev/ajin-lidar-processing:main-cfc6925` | `cfc692599023f7ab52c209529a101e5a830bc893` | `linux/arm64` | `sha256:9dc985b22c5e5f290fc3b2e7ad6fae249eb6fc2445bdff942600a3991e008f72` |
| `scrap-dev/ajin-measurement-uplink:main-cfc6925` | `cfc692599023f7ab52c209529a101e5a830bc893` | `linux/arm64` | `sha256:6298d3cc7673632156f4ce6c16518a621db240c7f3f4b704bff20dd810e08176` |
| `scrap-dev/ajin-edge-orchestrator:main-cfc6925` | `cfc692599023f7ab52c209529a101e5a830bc893` | `linux/arm64` | `sha256:bc239bdedd3d917c1fd8f645b4768355412257d8e03c790cf1e59e47827bc7ad` |
| `scrap-dev/ajin-camera-edge:main-cfc6925` | `cfc692599023f7ab52c209529a101e5a830bc893` | `linux/arm64` | `sha256:477988774d1ab72f440e1a8be50086cab5470d817febf5411ea21f88a48752c2` |

`tools/build-component-image`는 이 image를 재현한다. 도구는 pinned full SHA를 fetch하고
HEAD가 일치하는지 확인한 뒤 component의 Dockerfile과 context로 `--platform`을 지정해 빌드한다.
`--load`로 `scrap-dev/<image>:main-<short-sha>` tag를 local store에 적재하고 revision label과
os/arch를 검증한 뒤 TSV 기록을 추가한다. Component Repository의 source, branch, version과
Release는 변경하지 않는다.

개발용 빌드 도구는 Ubuntu test host에만 둔다.

| 도구 | version | 목적 | 출처 | license |
| --- | --- | --- | --- | --- |
| Docker Buildx | `0.37.1` | 고정 source의 ARM64 image 빌드 | [docker/buildx](https://github.com/docker/buildx) | Apache-2.0 |
| BuildKit | ARM64 builder `0.32.2`, default builder `0.33.0` | 대상별 image 빌드 실행과 cache | [moby/buildkit](https://github.com/moby/buildkit) | Apache-2.0 |
| QEMU | `10.0.4` | AMD64 host에서 ARM64 빌드 및 검사 실행 | [QEMU](https://www.qemu.org/), [tonistiigi/binfmt](https://github.com/tonistiigi/binfmt) | QEMU GPL-2.0 및 구성 요소별 license, binfmt MIT |
| `tools/build-component-image` | 이 Repository의 revision | pinned source의 local image 빌드 | 이 Repository | 이 Repository의 license |

### 갱신 시 확인 사항

갱신 검사는 다음 5개 범위를 구분한다.

| 범위 | 확인 내용 |
| --- | --- |
| Source | 원격 main full commit, Release와 실행 코드 및 배포 계약의 차이 |
| Image | image 자체의 source revision label, digest와 대상 architecture |
| 배포 입력 | 활성 Compose 경로, 기존 runtime 설정, credential과 영속 mount의 일치 |
| 관리 대상 | 교체할 서비스, 별도 관리 서비스와 rollback Container 구분 |
| 실행 검증 | Health, 신규 Edge 저장, Camera frame 갱신, 영상 및 날짜 녹화 접근과 실제 저장 진행 |

Container의 source label만으로 실행 image의 source를 확정하지 않는다. `docker compose config`와
전체 `docker inspect` 출력에는 secret이 포함될 수 있으므로 공유하지 않고 필요한 metadata만
선별한다. 수신 경로는 승인한 handler만 변경하며 다른 TLS 또는 TCP handler를 초기화하지 않는다.
Ubuntu의 `/var/tmp` 경로는 빌드 및 검증 산출물이며 영구 실행 설정의 정본이 아니다.

Edge의 상태 확인은 해당 장비의 배포 directory를 먼저 확인한 뒤 `systemctl status`와
`docker compose ps -a`를 읽기 전용으로 실행한다.

## 채택한 구조

| 항목 | 현재 결정 |
| --- | --- |
| Repository 경계 | Edge와 Server를 함께 관리하는 단일 통합 배포 Repository |
| 배포 단위 | 독립적으로 적용 가능한 `edge`와 `server` |
| 연동 기준과 구현 순서 | [docs/project-spec.md](project-spec.md)의 배포 대상 기준 |
| 목표 상태 | `targets/<target>` 아래의 Docker Compose와 host 연동 |
| 배포 경로 | 같은 목표 상태를 사용하는 Outbound Pull과 Offline Bundle |
| host 수명 주기 | Docker Compose를 시작하고 필수 mount를 확인하는 systemd 경계 |
| host 배포 root | `/srv/scrap-monitoring/deployment` |
| Version 경로 | `/srv/scrap-monitoring/deployment/versions/<version>` |
| 활성 Version | `/srv/scrap-monitoring/deployment/current` symlink |
| 이전 Version | `/srv/scrap-monitoring/deployment/previous` symlink |
| 적용 상태 | `/srv/scrap-monitoring/deployment/state/<target>.json` |
| 배포 lock | `/run/lock/scrap-monitoring-deployment.lock` |
| target 환경 파일 | `/etc/scrap-monitoring/edge.env`, `/etc/scrap-monitoring/server.env` |
| Release 환경 파일 | Manifest에서 생성한 대상별 `release.env` |
| Edge 파생 설정 | Component 설정에서 생성한 `CONFIG_SHA256` |
| 환경설정 검증 | 공개 schema와 실제 파일의 version, 변수 집합과 빈 값 비교 |
| 버전 해석 | 통합 Release manifest가 고정한 대상별 component image 집합 |
| Release manifest 형식 | JSON 문서와 JSON Schema |
| Release Package descriptor | Version, target, mode, platform, Manifest digest와 Offline image archive 경로 |
| Release Package payload | 명시적 allowlist, symbolic link 거부와 재현 가능한 archive metadata |
| Container registry | GitHub Container Registry (GHCR) |
| Component image 식별 | `ghcr.io` image의 SHA-256 digest |
| Component image 공개 범위 | Public GHCR Package 기본, 정본에 예외를 기록한 경우에만 Private |
| Release image 인증 | Public Package pull은 무인증, Private 예외는 최소 read-only 자격 증명 |
| Image tag 정책 | Release version tag와 `sha-<full-git-sha>` source revision tag, `latest` 미사용 |
| 배포 image 참조 | `ghcr.io/<organization>/<image>@sha256:<digest>` |
| Release archive 형식 | `.tar.gz` |
| 구현 언어 | Release asset 생성, Package 검증과 적용 상태 머신은 Python 3.10 이상, host 실행 진입점은 Bash |
| 애플리케이션 인증 | Edge별 Backend token과 Camera별 Media token을 사용하는 Bearer 인증 |
| Token 수명 주기 | 배포 도구가 credential Bootstrap과 명시적 rotation에서 생성 및 설치 |
| Token Server 저장 | Component 원문 token 형식의 root 전용 파일, Backend는 Edge당 최대 2개 중첩, Media는 Camera당 1개 |
| 내부 service 연결 | UDS 권한 또는 private Compose network |
| Browser 인증 | TLS, Backend 사용자 session과 CSRF 보호, reverse proxy 공용 token 미사용 |
| Docker Compose secret | [docs/configuration-management.md](configuration-management.md)의 비밀정보 접근 권한 기준 |
| 비밀정보 | Git과 Release 외부의 대상별 host 파일 |
| 영속 데이터 | container image와 분리한 host storage |
| Private PKI | 오프라인 Root CA와 Monitoring Server의 `step-ca` Intermediate CA를 사용하는 2단계 구조 |
| PKI 실행 경계 | 수동 Bootstrap 및 Client trust 등록과 일반 배포가 자동화하는 Server 인증서 발급 및 갱신 |
| CA 내부 연결 | Container는 `https://step-ca:9000`, host 자동화는 loopback 전용 `https://127.0.0.1:9000` |
| Server 인증서 발급 | `deployment` JWK Provisioner와 환경별 Server FQDN 1개 |

## 디렉토리 구조

```text
scrap-monitoring-deployment/
|-- .agents/
|   `-- AGENTS.md
|-- .github/
|   `-- workflows/
|       |-- ci.yml
|       |-- component-images.yml
|       `-- release.yml
|-- .markdownlint.json
|-- .yamllint.yml
|-- package-lock.json
|-- package.json
|-- delivery/
|   |-- offline/
|   |   |-- bundle_importer.py
|   |   `-- import-bundle
|   |-- online/
|   |   `-- fetch-release
|   |-- apply-release
|   |-- auth-registry.sh
|   |-- auth-secret-permissions.sh
|   |-- dashboard_configuration.py
|   |-- edge_configuration.py
|   |-- generate-auth-secret
|   |-- install-auth-secret
|   |-- install-container-runtime
|   |-- install-dashboard-configuration
|   |-- install-environment
|   |-- quick-start
|   |-- release_applier.py
|   |-- release_verifier.py
|   |-- runtime-requirements.sh
|   |-- retire-auth-secret
|   |-- validate-auth-secrets
|   |-- validate-dashboard-configuration
|   |-- validate-environment
|   |-- validate-edge-configuration
|   `-- verify-release
|-- docs/
|   |-- configuration-management.md
|   |-- deployment-contract.md
|   |-- implementation.md
|   |-- pki-operations.md
|   `-- project-spec.md
|-- notices/
|   `-- README.md
|-- pki/
|   |-- config/
|   |   `-- ca.template.json
|   |-- systemd/
|   |   |-- scrap-monitoring-certificate-renewal.service
|   |   `-- scrap-monitoring-certificate-renewal.timer
|   |-- ensure-server-certificate
|   |-- validate-ca-state
|   `-- verify-server-certificate
|-- release/
|   |-- manifests/
|   |   `-- README.md
|   |-- build-assets
|   |-- component-sources.json
|   |-- component_images.py
|   |-- dashboard_assets.py
|   |-- fetch-dashboard-assets
|   |-- manifest.example.json
|   |-- manifest.schema.json
|   |-- package.schema.json
|   |-- pull-images
|   |-- release_manifest.py
|   |-- resolve-components
|   |-- update-candidate
|   |-- target_validation.py
|   |-- validate-manifest
|   |-- validate-targets
|   `-- verify-assets
|-- requirements-tooling.in
|-- requirements-tooling.txt
|-- targets/
|   |-- edge/
|   |   |-- systemd/
|   |   |   `-- scrap-monitoring-edge.service
|   |   |-- .env.example
|   |   |-- README.md
|   |   `-- compose.yaml
|   `-- server/
|       |-- dashboard/
|       |   `-- nginx/
|       |       |-- runtime/30-edge-ingest-locations.conf
|       |       `-- upstreams/20-edge-ingest-upstreams.conf
|       |-- systemd/
|       |   `-- scrap-monitoring-server.service
|       |-- .env.example
|       |-- README.md
|       `-- compose.yaml
|-- tests/
|   |-- compose/
|   |-- delivery/
|   |-- pki/
|   |-- release/
|   |-- systemd/
|   |-- test_apply_release.py
|   |-- test_auth_secret_permissions.py
|   |-- test_auth_secrets.py
|   |-- test_configuration.py
|   |-- test_dashboard_configuration.py
|   |-- test_delivery_integration.py
|   |-- test_delivery_release.py
|   |-- test_entrypoints.py
|   |-- test_environment_installation.py
|   |-- test_edge_configuration.py
|   |-- test_server_preflight.py
|   |-- test_build_component_image.py
|   |-- test_component_updates.py
|   |-- test_dashboard_assets.py
|   |-- test_markdown.mjs
|   |-- test_pki.py
|   |-- test_public_content.py
|   |-- test_release.py
|   |-- test_release_targets.py
|   |-- test_repository.py
|   |-- test_runtime_requirements.py
|   |-- test_workflows.py
|   |-- validate-container
|   |-- validate-repository
|   `-- validate-test-host
|-- tools/
|   |-- build-component-image
|   |-- check-component-updates
|   |-- go.mod
|   |-- go.sum
|   |-- lint-markdown.mjs
|   `-- install-validation
|-- AGENTS.md
|-- Dockerfile.validation
|-- .gitignore
`-- README.md
```

`targets`는 배포 경로와 무관한 목표 상태의 정본이다. `delivery`는 목표 상태를 대상 장비에
전달하고 적용하는 방법만 관리한다. `release`는 두 대상의 호환 가능한 image와 asset 구성을
하나의 배포 버전으로 묶는다. `pki`는 Private PKI의 공개 가능한 설정 template, 수동 Bootstrap
절차와 일반 배포의 인증서 발급, 갱신 및 검증 자동화 도구를 관리하며 실제 CA 상태와 개인키를
포함하지 않는다.

## Release asset 이름

| asset | 파일 이름 |
| --- | --- |
| Online Package | `scrap-monitoring-<target>-<version>-online.tar.gz` |
| Offline Bundle | `scrap-monitoring-<target>-<version>-offline.tar.gz` |
| Checksum manifest | `SHA256SUMS` |

## PKI host 경로

| 상태 | host 경로 | 접근 기준 |
| --- | --- | --- |
| Root CA 인증서와 fingerprint | `/srv/scrap-monitoring/pki/root` | `root:scrap-admin`, directory `0750`, file `0640` |
| Intermediate CA와 `step-ca` 상태 | `/srv/scrap-monitoring/pki/step-ca` | `step-ca` service 전용 쓰기 권한 |
| Server 인증서와 개인키 | `/srv/scrap-monitoring/pki/tls` | TLS service 전용 쓰기 권한 |

Root CA 개인키는 암호화하여 Monitoring Server 밖의 오프라인 저장소에 보관한다. Intermediate CA
개인키는 별도 암호로 암호화하고 `step-ca`만 읽을 수 있는 Git 외부 secret을 사용해 서비스를
시작한다. 정확한 파일 위치와 Client trust 등록 절차는
[`docs/pki-operations.md`](pki-operations.md)를 따른다.

## 채택한 PKI 도구

| 도구 | 현재 상태 | 목적 | 출처 | license |
| --- | --- | --- | --- | --- |
| `step` CLI | `0.30.6` | CA 초기화, trust Bootstrap, Server 인증서 요청과 갱신 | [`smallstep/cli`](https://github.com/smallstep/cli) | Apache-2.0 |
| `step-ca` | `0.30.2` | Intermediate CA를 이용한 Server 인증서 발급 서비스 | [`smallstep/certificates`](https://github.com/smallstep/certificates) | Apache-2.0 |

## 대상 host runtime

두 배포 대상은 Docker 공식 APT 저장소의 Docker Engine `29.8.0`, Docker Compose plugin `5.5.1`과
containerd `2.3.5`를 사용한다. `delivery/install-container-runtime --target <edge|server>`는 Debian
또는 Ubuntu에서 대상 architecture와 실행 중인 systemd를 확인한다. 공통 배포 도구의 설치와 최소
version 검증 후 `scrap-admin` 시스템 그룹을 생성하고
`docker-ce`, `docker-ce-cli`, `containerd.io`와 `docker-compose-plugin`의 고정 version을 설치하고
실행 version을 검증한다. Server는 Smallstep APT repository에서 `step` CLI `0.30.6`과 `step-ca`
`0.30.2`도 설치하고 version을 검증한다. Docker daemon은 root 권한의 systemd 서비스로 실행하며
대상 사용자를 `docker` 그룹에 추가하지 않는다. APT의 추천 package는 설치하지 않아 Docker CLI가
추천하는 Buildx를 추가하지 않는다. Docker Buildx는 기능별 Repository CI의 멀티플랫폼 image 빌드에
사용하고 대상 host에는 설치하지 않는다.

`delivery/runtime-requirements.sh`는 직접 의존성 표의 최소 version과 runtime의 정확한 version을
검사한다. APT package 선택은 고정 version 뒤의 Debian package revision만 허용하며 prefix가
비슷한 다른 version과 prerelease를 제외한다. Host 공통 도구는 운영체제의 보안 업데이트를 사용한다.
APT 변경 전 `.list`와 `.sources`의 기존 Docker 및 Smallstep repository를 검사한다. 일치하는
repository는 source와 서명 key를 변경하지 않고 재사용하며 중복 또는 호환되지 않는 정의는
중단한다. 기존 설정이 없을 때만 repository를 추가한다.

서버의 Docker 컨테이너 로그는 `local` driver와 `20m` `max-size`, `5` `max-file`을 사용한다.
엣지는 `local` driver와 `10m` `max-size`, `3` `max-file`을 사용한다. systemd 저널은 서버가
최대 `1G`와 14일, 엣지가 최대 `256M`와 7일로 제한한다.

## 직접 의존성

| 도구 | 지원 version | 목적 | 출처 | license |
| --- | --- | --- | --- | --- |
| Bash | `5.1` 이상 | Host 배포와 인증 정보 도구 실행 | [GNU Bash](https://www.gnu.org/software/bash/) | GPL-3.0-or-later |
| GNU Coreutils | `8.32` 이상 | CSPRNG byte 변환, file 설치, digest와 권한 처리 | [GNU Coreutils](https://www.gnu.org/software/coreutils/) | GPL-3.0-or-later |
| GNU Findutils | `4.8` 이상 | credential 임시 파일 정리 | [GNU Findutils](https://www.gnu.org/software/findutils/) | GPL-3.0-or-later |
| OpenSSL | `3.0.2` 이상 | CA fingerprint, 인증서 chain, SAN, key와 유효기간 검증 | [OpenSSL](https://www.openssl.org/) | Apache-2.0 |
| Python | `3.10` 이상 | 대상 host의 Release Package, Manifest와 Dashboard runtime JSON 검증 | [Python](https://www.python.org/) | PSF-2.0 |
| `curl` | `7.81.0` 이상 | GitHub Release에서 Online Package와 checksum을 HTTPS로 취득 | [curl](https://curl.se/) | curl license |
| `jq` | `1.6` 이상 | Credential metadata와 Server token 파일 검증 및 갱신 | [jqlang](https://jqlang.org/) | MIT |
| `flock` | util-linux `2.37` 이상 | Credential 설치와 Server token 파일 변경 직렬화 | [util-linux](https://github.com/util-linux/util-linux) | GPL-2.0-or-later |
| `step` CLI | `0.30.6` | PKI Bootstrap, Server 인증서 요청과 갱신 | [`smallstep/cli`](https://github.com/smallstep/cli) | Apache-2.0 |
| `step-ca` | `0.30.2` | Intermediate CA를 이용한 Server 인증서 발급 | [`smallstep/certificates`](https://github.com/smallstep/certificates) | Apache-2.0 |
| Docker Engine | `29.8.0` | 대상 Container runtime | [Moby](https://github.com/moby/moby) | Apache-2.0 |
| Docker Compose plugin | `5.5.1` | 대상 Compose 구성 적용 | [Docker Compose](https://github.com/docker/compose) | Apache-2.0 |
| containerd | `2.3.5` | 대상 Container runtime 관리 | [containerd](https://github.com/containerd/containerd) | Apache-2.0 |
| GNU Privacy Guard | Debian 또는 Ubuntu 제공 version | Docker APT repository 서명 key 설치 | [GnuPG](https://gnupg.org/) | GPL-3.0-or-later |
| shadow suite (`passwd` package) | Debian 또는 Ubuntu 제공 version | 배포 관리 그룹과 credential 읽기 그룹 생성 | [shadow](https://github.com/shadow-maint/shadow) | BSD-3-Clause |

## CI와 Release 도구

| 도구 | 버전 | 목적 | 출처 | license |
| --- | --- | --- | --- | --- |
| `actions/checkout` | `v7.0.1` | GitHub Actions의 Repository checkout | [`actions/checkout`](https://github.com/actions/checkout) | MIT |
| `actions/setup-node` | `v7.0.0` | 고정 Node.js 설치와 npm cache | [`actions/setup-node`](https://github.com/actions/setup-node) | MIT |
| `actions/setup-go` | `v7.0.0` | 고정 Go 설치와 module cache | [`actions/setup-go`](https://github.com/actions/setup-go) | MIT |
| `astral-sh/setup-uv` | `v10.1.0` | 고정 uv 설치 | [`astral-sh/setup-uv`](https://github.com/astral-sh/setup-uv) | MIT |
| `docker/setup-compose-action` | `v2.3.0` | 고정 Docker Compose 설치 | [`docker/setup-compose-action`](https://github.com/docker/setup-compose-action) | Apache-2.0 |
| `docker:29.8.0-cli` | `29.8.0-cli` | Validation container의 Docker CLI와 Compose plugin | [Docker Hub](https://hub.docker.com/_/docker) | Apache-2.0 |
| Debian | `bookworm-slim` | Validation container base | [Debian](https://www.debian.org/) | Debian Free Software Guidelines (DFSG) compatible |
| `actions/upload-artifact` | `v7.0.1` | 검증된 Release asset 전달 | [`actions/upload-artifact`](https://github.com/actions/upload-artifact) | MIT |
| `docker/setup-buildx-action` | `v4.3.0` | component image 빌드의 Buildx 설정 | [`docker/setup-buildx-action`](https://github.com/docker/setup-buildx-action) | Apache-2.0 |
| `docker/login-action` | `v4.6.0` | GHCR 로그인 | [`docker/login-action`](https://github.com/docker/login-action) | Apache-2.0 |
| `docker/build-push-action` | `v7.3.0` | component image 빌드와 GHCR 게시 | [`docker/build-push-action`](https://github.com/docker/build-push-action) | Apache-2.0 |
| `actions/download-artifact` | `v8.0.1` | 검증된 Release asset 수신 | [`actions/download-artifact`](https://github.com/actions/download-artifact) | MIT |
| Actionlint | `1.7.12` | GitHub Actions workflow 정적 검사 | [`rhysd/actionlint`](https://github.com/rhysd/actionlint) | MIT |
| Docker Engine | GitHub-hosted runner 제공 version | 대상별 GHCR image pull과 archive 생성 | [Moby](https://github.com/moby/moby) | Apache-2.0 |
| Go | `1.27.1` | Actionlint 실행과 Go module 검증 | [Go](https://go.dev/) | BSD-3-Clause |
| Node.js | `24.21.0` | Markdown 검사 도구 실행 | [Node.js](https://nodejs.org/) | MIT |
| npm | `11.19.0` | Node.js 의존성 lock 설치 | [npm CLI](https://github.com/npm/cli) | Artistic-2.0 |
| Python | `3.10.21`, `3.13.15` | 최소 지원 version과 기본 CI의 Release asset 생성 및 테스트 | [Python](https://www.python.org/) | PSF-2.0 |
| uv | `0.12.15` | Python hash lock 일치 검증 | [uv](https://github.com/astral-sh/uv) | Apache-2.0 OR MIT |
| `jsonschema` | `4.26.0` | Release manifest JSON Schema 검증 | [PyPI](https://pypi.org/project/jsonschema/) | MIT |
| PyYAML | `6.0.3` | GitHub Actions workflow 정책 테스트 | [PyPI](https://pypi.org/project/PyYAML/) | MIT |
| Ruff | `0.16.4` | Python lint와 format 검사 | [PyPI](https://pypi.org/project/ruff/) | MIT |
| `markdownlint` | `0.41.1` | Markdown 검사 | [markdownlint](https://github.com/DavidAnson/markdownlint/tree/v0.41.1) | MIT |
| `yamllint` | `1.38.0` | YAML 검사 | [PyPI](https://pypi.org/project/yamllint/) | GPL-3.0 |
| `jq` | `1.6` | JSON 문법 검사 | [jqlang](https://jqlang.org/) | MIT |
| Docker Compose | `5.5.1` | Compose schema와 Manifest image 연결 검사 | [Docker Compose](https://github.com/docker/compose) | Apache-2.0 |
| GitHub CLI | GitHub-hosted runner 제공 version | Draft Release 생성, asset 첨부와 게시 | [GitHub CLI](https://github.com/cli/cli) | MIT |
| ShellCheck | `0.9.0` | Bash 정적 검사 | [ShellCheck](https://github.com/koalaman/shellcheck) | GPL-3.0 |
| `systemd-analyze` | `252` | systemd unit 검사 | [systemd](https://github.com/systemd/systemd) | LGPL-2.1-or-later |

모든 외부 GitHub Action은 표의 version tag가 가리키는 full commit SHA로 고정한다. Python
전이 의존성은 hash가 포함된 `requirements-tooling.txt`, Node.js 전이 의존성은
`package-lock.json`, Actionlint 전이 의존성은 `tools/go.sum`으로 고정한다.

`tools/lint-markdown.mjs`는 Node.js 기본 file API로 Markdown 파일을 탐색하고 `markdownlint`의
Promise API를 실행한다. `.git`, `.venv`와 `node_modules` directory를 제외하고 숨김 directory의
문서와 Repository 내부 파일을 가리키는 Markdown symbolic link를 검사한다. Directory symbolic
link는 탐색하지 않고 Repository 외부를 가리키거나 target이 없는 Markdown symbolic link는
거부한다. `.markdownlint.json`은 `MD013`만 비활성화한다. 설정 오류, 검사 대상 누락과 Markdown
규칙 위반은 실패를 반환한다. `tests/test_markdown.mjs`는 파일 탐색, 설정, 진단과 command 종료를
검증한다. CI는 `npm audit --audit-level=high` 기준을 유지한다.

## Component image 선택과 Release 절차

`release/component-sources.json`은 component 8개(Edge 5개, Backend, Camera Media Service, Dashboard)의
Repository, 대상 platform, runner, Dockerfile, build context, 공식 image 참조 asset과 최소 호환
Release를 정의한다. PostgreSQL과 `step-ca`는 선택 대상이 아니며 candidate manifest의 고정값이다.

| component | 공식 image 참조 asset | 최소 호환 Release |
| --- | --- | --- |
| Edge Platform 5개 | `release-manifest.json`의 `images` | `v0.2.0` (v2 포함 version) |
| Backend | `image-reference.txt`와 `SHA256SUMS` | `v0.2.0` |
| Camera Media Service | `image-reference.txt`와 `SHA256SUMS` | `v0.1.0` |
| Dashboard | `image-reference.txt`와 `SHA256SUMS` | `v0.6.0` |

`release/resolve-components resolve`는 `release/component_images.py`의 결정 규칙으로 component별
최신 Release와 원격 `main`의 full commit을 조회한다. 최신 Release가 최소 호환 Release 이상이고 공식 image
참조(`ghcr.io/<organization>/<component>@sha256:<digest>`)를 제공하면 공식 digest를 사용한다.
그렇지 않으면 `main` 최신 commit의 image를 선택하며, 통합 배포 Repository가 같은 commit으로 이미 게시한
image가 GHCR에 있으면 재빌드하지 않고 그 digest를 사용한다. 출력 JSON은 GitHub Actions matrix를 포함한다.
`tests/test_component_images.py`가 네트워크 없이 이 규칙을 검증한다.

`component-images.yml`은 `workflow_dispatch`로만 실행하며 입력 `components`는 component 이름의
쉼표 목록 또는 `all`이다. job은 3개다.

| job | 권한 | 동작 |
| --- | --- | --- |
| `resolve` | `contents: read`, `packages: read` | `release/resolve-components resolve` 실행 |
| `build` | `contents: read`, `packages: write` | component별 matrix 빌드, digest 게시와 검증 |
| `summary` | `contents: read` | 결과 병합, job summary와 `component-images` artifact 게시 |

`build` job은 component source를 full commit SHA로 checkout하고 component 자체 Dockerfile을
Buildx로 빌드한다. 이 job은 component의 workflow와 script를 실행하지 않는다. Server component는
`ubuntu-latest`의 `linux/amd64`, Edge component는 native ARM runner `ubuntu-24.04-arm`의
`linux/arm64`로 빌드한다. 이미지 이름은
`ghcr.io/ajin-scrap-monitoring/scrap-monitoring-deployment/<component-image>:sha-<full-git-sha>`이며
label은 `org.opencontainers.image.source`, `org.opencontainers.image.revision`과
`io.ajin.scrap-deployment.build=deployment-ci`다. push 후 digest로 pull하여 revision label,
build label과 os/arch를 검증한다. Dockerfile과 context 규칙은 Edge `release-images.yml`과 같고
(`camera-edge`만 context `services/camera-edge`) `tools/build-component-image`의 개발 image 빌드와 같은
Dockerfile과 context를 사용한다. workflow는 Repository에 commit하지 않고 결과를
job summary와 artifact로만 낸다.

사용자 원격 사전 조건은 `component-images.yml`이 처음 게시한 GHCR Package를 Public으로 전환하는 것이다.
Package는 게시 직후 Private이며 Public 전환 전에는 Release의 `--require-public-packages`가 통과하지 않는다.

Release 준비 절차는 다음과 같다.

1. `component-images.yml`을 수동 실행하고 `component-images` artifact를 내려받는다.
2. 새로 게시된 Package를 Public으로 전환한다.
3. `release/manifests/candidate.json`이 없으면 `release/manifest.example.json`을 복사하고 version을
   `v0.0.0`으로 둔다. PostgreSQL과 `step-ca` 항목은 검증한 digest와 출처 값으로 직접 채운다.
4. `release/update-candidate --results component-images.json`으로 선택 대상 component 항목을 갱신한다.
5. candidate 변경을 PR로 검토하고 병합한다.
6. `release/update-candidate --finalize v0.1.0`이 `release/manifests/v0.1.0.json`을 만든다. placeholder
   revision, schema 위반, Private Package와 `component-release`가 아닌 Dashboard를 거부한다.
7. version manifest를 PR로 병합한 뒤 `main` commit에 `v0.1.0` tag를 push하면 `release.yml`이 asset을 생성하고
   Draft Release를 게시한다. 첫 통합 Release 대상 version은 `v0.1.0`이다.

`release.yml`은 image를 빌드하지 않고 manifest의 digest 고정 image만 pull한다. `release/pull-images`는
pull 후 대상 platform과 image의 os/arch 일치를 확인하며 `deployment-build` image도 같은 경로로
Offline Bundle에 포함한다.

## 미확정 구현 결정

- Camera Media Service의 component Release
- Camera Media Service의 SD host preflight(`/usr/local/libexec/ajin-camera-media-storage-preflight`) 전달
- Edge v2 Release와 v2 Compose 예제
- Edge Release workflow가 Package를 private로 강제하는 문제와 Public 공개 범위 확인
- Backend의 `MEDIA_API_TOKEN` 필수 조건과 Media 내부 API의 Bearer 미사용 불일치
- Edge v2 ingest request byte 제한
- Database migration, backup 선행 조건과 rollback 자동화
- 기존 장비의 named volume 데이터를 `POSTGRES_DATA_PATH` bind 경로로 이전하는 절차
- Backend PostgreSQL 초기화 파일(`init.sh`, `roles.sql`, `runtime-grants.sql`)의 전달 방식
- Edge container의 Root CA 신뢰 방식(`SSL_CERT_FILE` 가정의 component 계약 확인)
- Edge v2 runtime directory 준비 도구
- Backend의 제어 API 호출 구성
- Camera Media Service의 read-only root filesystem 지원 여부
