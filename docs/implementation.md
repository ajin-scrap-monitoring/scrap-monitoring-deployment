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

환경설정은 Release 설정, 장비 환경설정, Component 설정, 비밀정보와 PKI 상태로 분리되어 있다.
대상과 시나리오별 `.env.example`은 공개 schema이고 실제 값은 대상 장비의 Git 외부 파일에서 관리한다.
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
두 도구와 Python module은 hardware 및 simulation Server의 Online Package와 Offline Bundle에만
포함된다. Compose mount, Backend 설정 자동 주입, Release 적용 및 systemd와의 연결은 구현되지
않았다.

`tests/test_dashboard_configuration.py`는 식별자 경계, 잘못된 JSON, 기존 byte 및 inode 보존,
동시 최초 설치, file mode, 실제 root 소유권과 link 경로 거부를 검증한다. 별도 Ubuntu test host의
read-only root filesystem Container에서 생성한 JSON의 UID `101` 읽기와 root의 read-only bind
mount 쓰기 거부를 확인한다. 이 검증은 Dashboard의 HTTP 및 HTTPS 응답과 Backend 연동 검증을
대체하지 않는다.

Edge별 Backend Bearer token과 Camera별 Camera Media Service Bearer token은 배포 도구가 생성하고
rotation하는 독립된 opaque secret으로 관리한다. 배포 도구는 256-bit token bundle 생성, Edge
원문 token 설치, Server SHA-256 digest registry 설치, 2개 digest 중첩 rotation과 이전 digest
폐기를 구현한다. 대상별 systemd unit은 Compose 시작 전에 인증 파일을 검증한다.
`delivery/auth-secret-permissions.sh`는 service별 읽기 그룹 조회와 생성, 소유권 및 mode 적용과
검증을 제공한다. 설치, rotation과 이전 digest 폐기는
[docs/configuration-management.md](configuration-management.md)의 접근 권한을 유지한다. 같은
credential의 재설치는 기존 파일을 교체하지 않는다. 설치 도구는 symbolic link와 hard link 경로를
거부하고 대상 directory의 lock으로 변경을 직렬화한다. Container supplementary group 연결과
파일 교체 후 소비 service의 재생성 또는 reload는 실제 Compose service가 없어 구현되지 않았다.

`tests/test_auth_secret_permissions.py`는 격리한 root Validation container에서 실제 그룹 생성,
non-root 읽기, 쓰기 및 다른 읽기 그룹의 접근 거부와 잘못된 소유권 및 그룹 검출을 검증한다.
시험용 `--root`는 해당 fixture root의 소유자와 그룹을 사용하며 host 계정을 변경하지 않는다.
별도 Ubuntu test host의 실제 Docker Compose file secret 검증은 supplementary group 읽기,
그룹 불일치의 읽기 거부와 root의 read-only mount 쓰기 거부를 확인한다. 이 검증은 실제 component의
인증 연동이나 token rotation 적용 완료를 대체하지 않는다.

`delivery/apply-release`는 Package mode, scenario, host architecture와 image platform을 검증하고 취득 전용
파일을 제외한 실행 payload를 `<version>-<scenario>` 불변 경로에 staging한다. Manifest에서 release.env를,
Edge 설정 원본에서 CONFIG_SHA256을 생성하고 환경, secret과 Compose를 검증한 뒤 current와
previous를 원자적으로 전환한다. Compose 상태 검사는 모든 Container의 `running`과 health check가
있는 Container의 `healthy`를 요구한다. systemd와 Compose 실행 상태가 실패하면 이전 link, Edge 파생
설정과 Server 인증서를 복구한다.

`delivery/verify-release`는 asset checksum, archive 경로와 파일 형식, descriptor, Manifest,
version, target, scenario, mode와 platform을 교차 검증한다. `delivery/online/fetch-release`는 고정된
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
범위, Private 예외 사유, pull 인증 방식과 외부 고지 경로를 검증한다. Release asset
생성기는 명시적 allowlist와 정규화된 archive metadata를 사용하여 재현 가능한 Online
Package 4개, Offline Bundle 4개와 checksum manifest 1개를 생성한다. 각 Package에는
target, scenario, mode, platform과 Manifest digest를 고정한 descriptor가 있다.

`targets`는 target과 `hardware`, `simulation` scenario로 분리되어 있다. Release manifest는
시나리오별 component 집합을 명시하고, Package에는 선택한 scenario source tree만 표준
`targets/<target>` 경로로 포함한다. systemd와 Compose 실행 경로는 scenario와 무관하게 유지한다.
현재 Compose service는 전체 시스템의 호환 실행 계약이 충족되지 않아 비어 있다. simulation 환경 파일은
Server의 LiDAR별 IP와 공통 UDP 8089, Visualizer publish address, Edge의 LiDAR endpoint와 synthetic Camera
device 입력을 정의한다. 현재 Edge 환경 schema와 설정 검증은 Edge v1 계약을 사용하며 v2 runtime
JSON을 소비하지 않는다. 배포 기준의 v2 연동에 필요한 runtime JSON 입력, v1과 분리된 socket 및
storage 연결과 목표 Compose는 구현되지 않았다. simulation 구성과 적용 순서는
[docs/simulation-deployment.md](simulation-deployment.md)를 따른다.

실제 통합 version manifest와 Release는 없다. 실제 장비에서 전체 시스템을 연결하는 통합 수락
검사는 완료되지 않았다.

## Component 연동 상태

확인한 외부 source 기준은 5개다. 각 기준은 원격 `main`의 full Git commit으로 고정한다.
Source 구현, 공개 Release와 개발 장비의 구동 상태는 별도로 판정한다. Source 확인은 image 실행이나
통합 배포 성공을 의미하지 않는다.

`tools/check-component-updates`는 이 절의 source 및 Release 기준과 GitHub의 공개 metadata를
읽기 전용으로 비교한다. Source 또는 Release 변경은 종료 code `1`, 조회 및 형식 오류는 `2`,
기준 일치는 `0`이다. `--json`은 구조화된 결과를 제공한다. Image pull, 실행, source 자동 수정과
주기적 background 실행은 수행하지 않으며 image 검증 결과는 항상 미검증으로 구분한다.
공개 조회는 인증을 요구하지 않고 API 한도에 필요한 경우에만 `GH_TOKEN` 또는 `GITHUB_TOKEN`을
환경으로 전달한다. 자격 증명과 API 응답 본문은 출력하지 않는다.

| Repository | 확인한 source |
| --- | --- |
| Simulator | [d0e4b3f3b153c0709e8b333fb3ee425c0aec3619](https://github.com/ajin-scrap-monitoring/scrap-monitoring-simulator/tree/d0e4b3f3b153c0709e8b333fb3ee425c0aec3619) |
| Edge Platform | [69a667b57325432d3511a4597b7d3552ad09b42b](https://github.com/ajin-scrap-monitoring/ajin-edge-platform/tree/69a667b57325432d3511a4597b7d3552ad09b42b) |
| Backend | [73b9e28b135e670d6c5d6a460da3b76af16250a8](https://github.com/ajin-scrap-monitoring/scrap-monitoring-backend/tree/73b9e28b135e670d6c5d6a460da3b76af16250a8) |
| Camera Media Service | [daf293e756004e7c740b585b089f257d557ad7ab](https://github.com/ajin-scrap-monitoring/ajin-camera-media-service/tree/daf293e756004e7c740b585b089f257d557ad7ab) |
| Dashboard | [84b26794098486dcbfb2eae6d5cc2a95fab242ee](https://github.com/ajin-scrap-monitoring/scrap-monitoring-dashboard/tree/84b26794098486dcbfb2eae6d5cc2a95fab242ee) |

| Component | 고정 source의 계약 | 배포 미완료 사항 |
| --- | --- | --- |
| Simulator Repository | `v0.5.0` Public AMD64 Simulation Server와 Visualizer, ARM64 Camera Edge Bridge image, LiDAR별 IP와 공통 UDP 8089, synthetic Motion JPEG (MJPEG) stream, Video4Linux2 (V4L2) host 구성과 90 frame 검사 | 통합 Compose 등록과 전체 시스템 수락 검사 |
| Edge Platform | `v0.1.1` Public ARM64 image 5개, file token과 Camera WSS, 별도 v2 processing, uplink, orchestrator와 runtime JSON | v2 Release image, v1과 v2 통합 배포 설정 분리, 통합 Compose secret 권한 연결, 실제 fill algorithm과 clock 인수 검증 |
| Backend | AMD64 Dockerfile, v2 Bearer ingest, 저장 후 멱등 Acknowledgement (ACK), monitoring snapshot과 Server-Sent Events (SSE), 적재율 추이, v2 경보와 수거 사건 이력, Media 제어 Application Programming Interface (API), health와 readiness | Release image, file 기반 token 입력, 운영 DB와 session, Browser 역할과 필수 CSRF 검증, ingest request limit |
| Camera Media Service | AMD64 Dockerfile과 공식 Server Compose, Camera별 Bearer binary JPEG ingest, 원문 token JSON, 내부 HTTP API, MJPEG live와 MP4 clip, 날짜 녹화, 유한 저장 예산과 clip 목록 health check | Release image, digest registry file, 통합 Compose의 secret 권한 및 storage 연결, 날짜 녹화의 Backend 및 Dashboard 연동, 통합 영상 권한 검증 |
| Dashboard Nginx | `v0.2.0` Public AMD64 image, v2 모니터링과 MJPEG 및 MP4, runtime JSON과 TLS 및 reverse proxy 설정 asset | 통합 Compose mount와 Release 적용 연결, runtime 설정 및 upstream, timeout과 Content Security Policy (CSP)의 통합 검증 |

Simulator Server와 Visualizer의 상태 endpoint는 `/status`다. Visualizer는 `/visual/v1/stream`과
`/camera/v1/stream`에서 같은 canonical scene의 시각화와 1920 x 1080, 30 Frames Per Second (FPS)
MJPEG stream을 제공한다. Camera Edge Bridge의 host 장치는 `/dev/video42`이고 consumer 경로는
`/dev/scrap-synthetic-camera`다. Host V4L2의 `exclusive_caps=0`과 `sustain_framerate=0`이 필요하다.

Edge와 Backend의 수신 경로 및 저장 ACK 계약은
[docs/deployment-contract.md](deployment-contract.md)의 Component 연동을 따른다.
Edge v2의 fill algorithm은 구현되지 않아
`fill_estimate=null`과 `FILL_METHOD_NOT_IMPLEMENTED`를 사용한다. 측정하지 않은 clock은
`UNSYNCED`로 표시한다.

현재 인증 입력은 배포 도구와 일치하지 않는다. Backend는 `EDGE_V2_DEVICES` JSON의 원문 token을,
Camera Media Service는 `EDGE_AUTH_SECRET` JSON의 원문 token을 읽으며 digest registry file을 읽지
않는다. Backend는 Media 연결에 `MEDIA_SERVICE_URL`과 `MEDIA_API_TOKEN`을 요구하지만 Camera Media
Service의 내부 HTTP API는 Bearer 인증을 사용하지 않는다. Backend의 `MEDIA_API_TOKEN` 필수 조건은
배포의 내부 통신 기준과 일치하지 않아 외부 Repository에서 해소해야 한다.
고정된 Backend source의 Browser session은 기본 사용자,
process memory 저장과 누락을 허용하는 Cross-Site Request Forgery (CSRF) 검사를 사용하므로 운영
인증 계약이 충족되지 않는다.

Camera Media Service의 `/api/v2` 날짜 녹화는 기존 `/api/v1` clip API와 별도 계약이다. 기본값은
비활성이며 활성화에는 `MAX_DAILY_STORAGE_BYTES`의 명시적 저장 예산이 필요하다. 원본과 다운로드
cache의 합산 예산 및 최소 여유 공간 검사는 전체 filesystem quota나 보관 기간 보장을 대체하지
않는다. Media Dockerfile은 UID `10002`의 non-root 사용자를 지정하며 공식 Compose는 loopback
port와 clip 목록 health check를 사용한다. 이 Repository의 통합 Compose 연결은 구현되지 않았다.

Dashboard의 공개 Release는 v2 모니터링, MJPEG live, MP4 clip 연동과 runtime JSON 로딩을 제공한다.
Release가 게시한 참조는 다음과 같으며 이 배포 Repository의 image 실행 검증 결과와 구분한다.

| 항목 | 게시 값 |
| --- | --- |
| Release source | `8e5f0c068955d92532420a69fa48d3eb49ad9397` |
| image 참조 | `ghcr.io/ajin-scrap-monitoring/scrap-monitoring-dashboard@sha256:5de751cfae097c208b13d00dc5729e8ba9646b82baf1b3a6cea8572d9b194862` |
| 배포 asset | `image-reference.txt`, `nginx-config.tar.gz`, `runtime-config.example.json`, `runtime-config.schema.json`, `SHA256SUMS` |

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

장비별 개발 구성은 통합 Release와 분리되어 있다. Edge의 v2 image 4개는 고정된 Component
source의 Dockerfile을 별도 Ubuntu test host에서 `linux/arm64`로 빌드한다. 원본 Repository의
source, branch, version과 Release는 변경하지 않는다. 개발용 image는 local Docker storage에
digest로 고정하고 GHCR 또는 통합 Release에 게시하지 않는다. Camera는 기존 `v0.1.1` Public
image를 사용한다.

| 대상 | 구성 | 관리 경로 |
| --- | --- | --- |
| Edge | LiDAR Driver 2개, LiDAR Processing, Measurement Uplink, Camera Edge, Edge Orchestrator | `/opt/ajin/deployments/simulation-v2-69a667b` |
| Edge host | v2 Compose 시작 unit | `ajin-edge-simulation-v2.service` |
| Edge 설정 | v2 설정 등록 JSON과 service runtime 입력 | `/opt/ajin/config/edge-simulation-v2.runtime.json` |
| Edge runtime | v2 전용 socket, 상태와 Outbox | `/opt/ajin/runtime/simulation-v2` |
| Server | 개발용 Backend ingress Nginx와 기존 Tailscale Serve TLS 종단 | `/srv/scrap-monitoring/development/edge-ingress` |
| Server Backend | source mount 없는 개발용 image와 기존 Database 연결 | `/srv/scrap-monitoring/development/backend-v2-73b9e28` |

Source의 `edge-v2 processing`, `edge-v2 uplink`, `edge-v2 orchestrator`와 Driver의
`--schema-version 2.0`을 별도 개발 Compose에서 실행한다. 기존 v1 저장소와 중지된 Container는
보존하며 v1 unit은 비활성 상태다. Camera와 Media의 endpoint, image와 credential은 유지한다.
각 Container는 non-root, read-only root filesystem, capability 제거와 제한된 Docker `local` 로그를
사용한다. File secret은 해당 service의 읽기 그룹으로 연결한다.

개발용 Backend ingress는 `/api/edge/v2/`의 `configurations`, `measurements`, `assessments`,
`status`에 대한 POST만 전달한다. Bearer, Idempotency-Key, request body와 query는 보존하고
Cookie는 제거한다. 다른 method는 `403`, 다른 경로는 `404`로 거부한다. 개발용 request body
상한은 16 MiB이며 운영 v2 계약의 승인값이 아니다. 외부 평문 port를 추가하지 않고 기존 tailnet
내부 HTTPS를 사용한다. 이 TLS 구성은 통합 배포의 Private PKI를 대체하지 않는다.

설정 등록의 저장 ACK를 확인한 뒤 정상 출력을 활성화한다. 등록 파일의 message ID와 본문은
재시작 시 유지한다. 현재 Backend에는 설정, 측정, 판단과 상태가 schema `2.0`으로 저장되며
Uplink가 실제 ACK를 확인한다. v2 health check는 schema, 상태와 snapshot freshness를 확인한다.
Driver와 Camera의 상태 파일 schema `1.0`은 각각의 상태 계약이며 전송 schema와 구분한다.

검증 범위는 SDK를 통한 두 Driver의 scan 수신, v2 설정 등록과 원본 point 선택, Backend의 네
메시지 유형 저장과 ACK, Camera WSS 인증, Media의 1920 x 1080 MJPEG 90 frame decode와 약 30 FPS
수신이다. 검증 구간에서 v2 Processing의 drop과 Uplink의 loss 및 quarantine은 0이다. 장시간
무손실 운전, 측정 정확도, Dashboard와 MP4 종단 인수는 완료되지 않았다.

개발용 등록은 미검증 보정값을 승인하지 않고 `calibration=null`을 사용한다. Point 좌표는
`null`이고 transform은 `UNAVAILABLE`이다. v2 source는 실제 clock exporter와 연결되지 않아
`UNSYNCED`를 보고하며 overall 상태는 `DEGRADED`다. Component 프로세스의 `HEALTHY`와 기능의
가용성은 별도로 판정한다.

Image 전달 archive의 SHA-256은
`4a06f91400bf21b6513bbcc2b5f7271a43e9dd2aa2f1645a3cbc3206201a9dc7`이다. Docker image load 이후
각 image의 digest, source revision과 architecture를 다시 검증한다.

| 개발용 image | manifest digest |
| --- | --- |
| `scrap-edge-dev/lidar-driver` | `sha256:1f5a0e6cb840b3b527864a9292f7a99220caceb67a81434d645a92add114f691` |
| `scrap-edge-dev/lidar-processing` | `sha256:256bb6b7122c6d211a2f95d158fe02eaa7eb9abef4288fc56398ddfc23b4f488` |
| `scrap-edge-dev/measurement-uplink` | `sha256:a6bf19300070678a43729e76f20afe0e88a865bd0928ccc4cd13c06daa7de351` |
| `scrap-edge-dev/edge-orchestrator` | `sha256:d10043d70ddaf199dbfc7db97bd65db3bfcb0ab1f364fcbddb085a8b362ee1c7` |

별도 Ubuntu test host에서 고정 source의 Python 테스트 207개, Driver의 CTest 2개, 정적 검사,
ARM64 image의 v2 명령과 runtime JSON 로딩을 검증한다. MacBook은 SSH와 파일 전달에만 사용한다.
Source snapshot, image archive와 build metadata는 Ubuntu test host의
`/var/tmp/scrap-edge-v2.v5q7J8`에서 관리한다.

### Backend 개발용 image

Backend 개발용 image는 위의 고정 source와 원본 Dockerfile을 별도 Ubuntu test host에서
`linux/amd64`로 빌드한 산출물이다. Component source와 version은 변경하지 않으며 GHCR 또는
Release에 게시하지 않는다. Source snapshot, image archive와 build metadata는
`/var/tmp/scrap-backend-v2.ViPmmT`에서 관리한다.

| 항목 | 값 |
| --- | --- |
| image 참조 | `scrap-backend-dev/backend@sha256:af7f5c8a0e38b8f9d8b84b50c0b15f7bad5547f8aa9608e382befbc210f3ab61` |
| Component version | `0.1.0` |
| image archive SHA-256 | `16d08ad1876836977707531afeb43f8874aac1261bfc47ca2a9e1d0ca684cefb` |
| Python base image | `python:3.13-slim@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f` |
| uv build image | `ghcr.io/astral-sh/uv:0.5.15@sha256:ea861f8e28b5c0e85ec14dc0f367d9d5cfa5b418024cc250219288d4fff591f1` |

Ubuntu test host에서 Backend 테스트 182개, 정적 검사와 non-root 및 read-only Container 시작을
검증한다. Image의 `app.openapi()`에서 Dashboard가 사용하는 경로와 schema는
`docs/contracts/backend/manifest.json`과 `openapi.json`에 고정된 계약과 일치한다.
기존 Server Database의 테이블 12개를 사용하며 schema 변경이나 migration은 없다.

Server의 `scrap-monitoring-backend-check`는 위의 image를 사용하며 host source를 mount하지 않는다.
개발용 Compose는 기존 Database bind mount, UID `1002`, GID `1004`, 내부 network와 loopback
port를 유지한다. Runtime 입력은 root-only `backend.env`에 보관하며 기존 token을 유지한다.
개발용 계정 `admin`과 `operator`의 비밀번호는 `ADMIN_PASSWORD`와 `OPERATOR_PASSWORD`로 주입하며
실제 값은 Repository에 기록하지 않는다.
`EDGE_V2_MONITORING_SOURCES`는 기존 Media pit과 등록된 Edge의 식별자를 연결한다.
기존 Component Repository의 source, branch와 version은 변경하지 않는다.

Browser session이 없는 v2 snapshot, events와 load-history 요청은 `401`이다. 유효한 session의 snapshot은
schema `2`와 `200`을 반환하며 SSE는 `monitoring.snapshot`을 제공한다. 경보, 수거 사건과 녹화
조회는 `200`, 영상 권한 검사는 `204`이며 Edge 수신 경로 4개의 멱등 재전송은 `200`이다.
적재율 추이의 기본 24시간 조회는 60초 구간 1,441개와 `LATEST_STATE_PER_BUCKET`을 반환한다.
현재 계산 불가 구간은 `valuePercent=null`, `valid=false`이며 0%로 대체하지 않는다.
실제 Edge의 신규 데이터 저장과 ACK, loss와 quarantine `0`을 확인한다.
적재율 계산의 가용성은 위의 Edge 기능 상태를 따르며 이 API 검증으로 측정 정확도를 승인하지 않는다.

Database backup과 기존 설정은 개발용 배포 경로의 root-only `rollback`에 보관한다.
백업의 테이블 12개는 행 수가 일치하며 활성 Database는 기존 행 수 이상을 유지한다.
직전 Backend Container는 `scrap-monitoring-backend-check-pre-73b9e28-20261015` 이름으로 중지 상태다.
Database는 자동 삭제나 보존 기간 제한을 설정하지 않은 개발 데이터이며 저장 공간 점검이 필요하다.
Backend 재생성은 process memory의 Browser session을 유지하지 않으므로 재로그인이 필요하다.

Server의 재현 가능한 상태 및 API 확인 명령은 다음과 같다.

```bash
sudo docker compose \
  --env-file /srv/scrap-monitoring/development/backend-v2-73b9e28/images.env \
  -f /srv/scrap-monitoring/development/backend-v2-73b9e28/compose.yaml ps -a
sudo python3 /srv/scrap-monitoring/development/backend-v2-73b9e28/verify-live.py
```

API 확인 도구는 기존 계정으로 검증용 session을 생성하고 검사 후 삭제한다. Token과 계정
입력은 출력하지 않으며 Edge 재전송은 이미 저장된 메시지의 식별자와 본문을 사용한다.
이 검사는 Dashboard의 Browser, HTTPS routing과 MP4 본문 전달의 종단 검증을 대체하지 않는다.

### Edge 상태 확인

Edge의 재현 가능한 상태 확인 명령은 다음과 같다.

```bash
sudo systemctl status ajin-edge-simulation-v2.service --no-pager
sudo docker compose \
  --env-file /opt/ajin/deployments/simulation-v2-69a667b/edge.env \
  --env-file /opt/ajin/deployments/simulation-v2-69a667b/images.env \
  -f /opt/ajin/deployments/simulation-v2-69a667b/compose.v2.yaml ps -a
```

개발용 빌드 도구는 Ubuntu test host에만 둔다.

| 도구 | version | 목적 | 출처 | license |
| --- | --- | --- | --- | --- |
| Docker Buildx | `0.37.1` | 고정 source의 ARM64 image 빌드 | [docker/buildx](https://github.com/docker/buildx) | Apache-2.0 |
| BuildKit | `0.32.2` | 전용 builder의 빌드 실행과 cache | [moby/buildkit](https://github.com/moby/buildkit) | Apache-2.0 |
| QEMU | `10.0.4` | AMD64 host에서 ARM64 빌드 및 검사 실행 | [QEMU](https://www.qemu.org/), [tonistiigi/binfmt](https://github.com/tonistiigi/binfmt) | QEMU GPL-2.0 및 구성 요소별 license, binfmt MIT |

개발용 TLS 도구는 2개다.

| 도구 | version | 목적 | 출처 | license | 현재 상태 |
| --- | --- | --- | --- | --- | --- |
| Nginx | `1.30.5-alpine` | Backend v2 전송 경로 allowlist | [Docker Official Image](https://hub.docker.com/_/nginx), [Nginx source](https://github.com/nginx/nginx/tree/release-1.30.5) | BSD-2-Clause | Server의 non-root, read-only Container |
| Tailscale | `1.102.2` | 기존 tailnet의 개발용 HTTPS 종단 | [Tailscale source](https://github.com/tailscale/tailscale/tree/v1.102.2), [Serve](https://tailscale.com/docs/features/tailscale-serve) | BSD-3-Clause | Server의 기존 host 서비스 |

Nginx image는
`docker.io/library/nginx@sha256:0985e772fb9f729e6fa0980da05fca5d9c468e870eed43071545afa9d2e27d94`로
고정한다. 별도 Ubuntu test host의 proxy 검사는 경로와 method 제한, credential 전달, Cookie 제거,
body와 query 및 Idempotency-Key 보존, 개발용 body 제한을 확인한다.

## 채택한 구조

| 항목 | 현재 결정 |
| --- | --- |
| Repository 경계 | Edge와 Server를 함께 관리하는 단일 통합 배포 Repository |
| 배포 단위 | 독립적으로 적용 가능한 `edge`와 `server` |
| 배포 시나리오 | target별 `hardware`와 `simulation` |
| 연동 기준과 구현 순서 | [docs/project-spec.md](project-spec.md)의 배포 대상 기준 |
| 목표 상태 | `targets/<target>/<scenario>` 아래의 Docker Compose와 host 연동 |
| 배포 경로 | 같은 목표 상태를 사용하는 Outbound Pull과 Offline Bundle |
| host 수명 주기 | Docker Compose를 시작하고 필수 mount를 확인하는 systemd 경계 |
| host 배포 root | `/srv/scrap-monitoring/deployment` |
| Version 경로 | `/srv/scrap-monitoring/deployment/versions/<version>-<scenario>` |
| 활성 Version | `/srv/scrap-monitoring/deployment/current` symlink |
| 이전 Version | `/srv/scrap-monitoring/deployment/previous` symlink |
| 적용 상태 | `/srv/scrap-monitoring/deployment/state/<target>.json` |
| 배포 lock | `/run/lock/scrap-monitoring-deployment.lock` |
| target 환경 파일 | `/etc/scrap-monitoring/edge.env`, `/etc/scrap-monitoring/server.env`와 `DEPLOYMENT_SCENARIO` |
| Release 환경 파일 | Manifest에서 생성한 대상별 `release.env` |
| Edge 파생 설정 | Component 설정에서 생성한 `CONFIG_SHA256` |
| 환경설정 검증 | 공개 schema와 실제 파일의 version, 변수 집합과 빈 값 비교 |
| 버전 해석 | 통합 Release manifest가 고정한 대상별 component image 집합 |
| Release manifest 형식 | JSON 문서와 JSON Schema |
| Release Package descriptor | Version, target, scenario, mode, platform, Manifest digest와 Offline image archive 경로 |
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
| Token Server 저장 | 식별자별 SHA-256 digest 1개, rotation 중 최대 2개 |
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
|   |-- auth-secret-permissions.sh
|   |-- dashboard_configuration.py
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
|   |-- manifest.example.json
|   |-- manifest.schema.json
|   |-- package.schema.json
|   |-- pull-images
|   |-- release_manifest.py
|   |-- target_validation.py
|   |-- validate-manifest
|   |-- validate-targets
|   `-- verify-assets
|-- requirements-tooling.in
|-- requirements-tooling.txt
|-- targets/
|   |-- edge/
|   |   |-- hardware/
|   |   |   |-- .env.example
|   |   |   `-- compose.yaml
|   |   |-- simulation/
|   |   |   |-- .env.example
|   |   |   `-- compose.yaml
|   |   |-- systemd/
|   |   |   `-- scrap-monitoring-edge.service
|   |   `--
|   `-- server/
|       |-- hardware/
|       |   |-- .env.example
|       |   `-- compose.yaml
|       |-- simulation/
|       |   |-- .env.example
|       |   `-- compose.yaml
|       |-- systemd/
|       |   `-- scrap-monitoring-server.service
|       `--
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
| Online Package | `scrap-monitoring-<target>-<scenario>-<version>-online.tar.gz` |
| Offline Bundle | `scrap-monitoring-<target>-<scenario>-<version>-offline.tar.gz` |
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
| `jq` | `1.6` 이상 | Credential metadata와 digest registry 검증 및 갱신 | [jqlang](https://jqlang.org/) | MIT |
| `flock` | util-linux `2.37` 이상 | Credential 설치와 digest registry 변경 직렬화 | [util-linux](https://github.com/util-linux/util-linux) | GPL-2.0-or-later |
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

## 미확정 구현 결정

- 실제 Release manifest에 포함할 Backend와 Camera Media Service image digest
- Backend와 Camera Media Service의 file 기반 token 입력
- Backend의 내부 Media 연결에서 `MEDIA_API_TOKEN` 필수 조건 해소
- Edge v2 ingest request byte 제한
- Backend의 운영 Database version, migration과 session 저장 방식
- 게시된 Dashboard Release image의 통합 배포 검증
- Database migration, backup 선행 조건과 rollback 허용 범위
