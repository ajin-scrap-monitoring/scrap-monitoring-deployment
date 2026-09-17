# 배포 환경설정 관리

## 역할

이 문서는 통합 배포가 사용하는 설정값의 소유권, 저장 위치와 동기화 규칙의 정본이다.
배포 동작은 deployment-contract.md, 구현 상태는 implementation.md, 인증서 운영은
pki-operations.md를 따른다.

## 설정 영역

배포 설정은 5개 영역으로 구분한다.

| 영역 | 정본 | 변경 주기 | Git 포함 |
| --- | --- | --- | --- |
| Release 설정 | Release manifest | 통합 Release | 공개 manifest와 template만 포함 |
| 장비 환경설정 | 대상 장비의 /etc/scrap-monitoring 환경 파일 | 현장 구성 변경 | 변수 이름과 공개 예시만 포함 |
| Component 설정 | 대상 장비의 Git 외부 설정 파일 | 보정 및 기능 설정 변경 | 공개 template만 포함 |
| 비밀정보 | 대상 장비의 secret 파일 | 발급 및 rotation | 포함하지 않음 |
| PKI 상태 | 대상 장비의 PKI 경로 | 인증서 발급 및 갱신 | 공개 template만 포함 |

하나의 값을 두 영역에서 동시에 관리하지 않는다. Release 변경은 장비 환경설정과 비밀정보를
덮어쓰지 않고, 장비 환경설정 변경은 Release가 고정한 image를 바꾸지 않는다.

## Release 설정

Release manifest는 통합 버전과 대상별 OCI (Open Container Initiative) image digest의 정본이다.
배포 적용기는 manifest를 검증한 뒤 대상별 release.env를 생성한다.

대상별 Release 설정은 3종의 값을 포함한다.

- 통합 version을 가진 `DEPLOYMENT_REVISION`
- 선택한 배포 시나리오를 가진 `DEPLOYMENT_SCENARIO`
- Component 이름의 하이픈을 밑줄로 바꾸고 대문자로 변환한 `<COMPONENT_NAME>_IMAGE`

release.env는 Release asset에서 생성한 파일이며 사람이 수정하지 않는다. Image 값은
`ghcr.io/organization/image@sha256:digest` 형식의 실제 이름과 64자리 digest만 허용한다.

## 장비 환경설정

장비별 실제 환경설정 경로는 다음과 같다.

| 대상 | 공개 schema | 실제 파일 |
| --- | --- | --- |
| Edge hardware | targets/edge/hardware/.env.example | /etc/scrap-monitoring/edge.env |
| Edge simulation | targets/edge/simulation/.env.example | /etc/scrap-monitoring/edge.env |
| Server hardware | targets/server/hardware/.env.example | /etc/scrap-monitoring/server.env |
| Server simulation | targets/server/simulation/.env.example | /etc/scrap-monitoring/server.env |

.env.example은 변수 이름, 공개 가능한 형식과 schema version을 관리한다. 실제 파일은 현장 주소,
Fully Qualified Domain Name (FQDN), 장치 경로, host group ID와 독립적으로 확인한 Root CA
fingerprint를 보관하며 Git과 Release asset에 포함하지 않는다.

실제 환경 파일은 root:scrap-admin, file 0640을 사용한다. 배포 적용기는 값을 로그에 출력하거나
Release 작업 경로로 복사하지 않는다.

## Component 설정과 파생값

hardware Edge의 처리 설정은 /opt/ajin/config/edge.json에서 관리한다. simulation Edge의 처리 설정은
/opt/ajin/config/edge-simulation.json에서 관리한다. Simulator Server의 scene과 sensor 설정, Visualizer
camera profile과 Camera Edge Bridge의 frame 처리 설정은 Simulator component image가 소유한다. 승인된
보정값, 센서 매핑과 service version manifest는 Component 설정의 책임이다.
장비 환경설정이 소유하는 SITE_ID, EDGE_ID,
CAMERA_ID와 CONFIG_REVISION이 설정 파일에도 있으면 배포 적용기가 값의 일치를 검증한다.

CONFIG_SHA256은 edge.json의 정확한 byte에서 계산한 SHA-256 값이다. 운영자가 직접 입력하지 않고
배포 적용기가 계산하여 대상별 generated environment 파일에 기록한다. 설정 파일이 바뀌면
CONFIG_REVISION을 갱신하고 hash를 다시 계산해야 한다.

Generated environment 파일은 Release 설정이나 장비 환경설정의 정본이 아니다. 배포 적용기가
원본을 다시 검증하여 재생성할 수 있어야 한다.

| 생성 파일 | 위치 | 입력 |
| --- | --- | --- |
| Edge Release 환경 | /srv/scrap-monitoring/deployment/current/targets/edge/release.env | Release manifest |
| Server Release 환경 | /srv/scrap-monitoring/deployment/current/targets/server/release.env | Release manifest |
| Edge 파생 환경 | /srv/scrap-monitoring/deployment/state/edge.generated.env | Edge 설정 파일 |

## 비밀정보

비밀정보는 환경변수 값이 아니라 대상 장비의 파일로 관리한다. Docker Compose는 host 파일을
service별 secret으로 연결하고 각 service는 필요한 secret만 `/run/secrets` 아래에서 읽는다.
일반 [Docker Compose의 file 기반 secret](https://docs.docker.com/compose/how-tos/use-secrets/)은
host 파일 bind mount이므로 host 저장소의 소유권과 권한이 비밀정보 보호의 기준이다.

애플리케이션 인증 token은 2종이다.

| 인증 경계 | Client 파일 | Server 파일 | 식별 단위 |
| --- | --- | --- | --- |
| Edge Platform에서 Backend | `/opt/ajin/secrets/edge-token` | `/srv/scrap-monitoring/secrets/backend/edge-token-digests.json` | Edge ID |
| Camera Edge에서 Camera Media Service | `/opt/ajin/secrets/camera-token` | `/srv/scrap-monitoring/secrets/media/camera-token-digests.json` | Camera ID |

배포 도구는 credential Bootstrap에서 각 인증 관계마다 운영체제의 Cryptographically Secure
Pseudo-Random Number Generator (CSPRNG)로 독립적인 256-bit opaque token을 생성한다. Client
파일은 요청의 Bearer 값으로 사용할 원문 token 하나를 가진다. Server JSON 파일은 식별자별로
SHA-256 digest를 1개 또는 rotation 중 2개 가지며 원문 token을 저장하지 않는다. Server
component는 수신한 Bearer token의 digest를 계산하고 constant-time 비교를 수행한다. 배포 도구는
같은 token을 두 인증 경계에 재사용하지 않는다.

Credential Bootstrap은 장비 환경설정에서 Edge ID와 Camera ID를 확정한 뒤 최초 Compose 시작
전에 수행한다. `delivery/generate-auth-secret`이 전달용 credential bundle을 만들고
`delivery/install-auth-secret`이 Server digest와 해당 Edge 원문 token을 설치한다. 설치 후
`delivery/validate-auth-secrets`가 파일 형식, 식별자, digest와 접근 권한을 검사한다.

Token rotation은 명시적으로 다음 순서로 수행한다.

1. `delivery/generate-auth-secret`으로 같은 식별자의 새 bundle을 생성한다.
2. `delivery/install-auth-secret --rotate server`로 Server에 새 digest를 추가한다.
3. `delivery/install-auth-secret --rotate edge`로 해당 Edge의 원문 token을 교체한다.
4. HTTPS 또는 WSS 요청의 성공을 확인한다.
5. `delivery/retire-auth-secret`에 이전 bundle을 전달하여 Server에서 이전 digest를 폐기한다.

일반 Release 적용과 같은 Release 재적용은 기존 token 파일을 유지한다. 대상의 token 파일 또는
digest registry가 없거나 local 검증에 실패하면 일반 배포는 새 값을 임의로 생성하지 않고
credential Bootstrap 또는 rotation 복구를 요구한다. Credential bundle은 설치와 검증에만
사용하며 Git, Release asset과 일반 배포 경로에 보관하지 않는다.

인증 경계는 4개다.

| 호출 경계 | 인증과 보호 |
| --- | --- |
| Edge Platform에서 Backend | TLS와 Edge별 Bearer token |
| Camera Edge에서 Camera Media Service | TLS와 Camera별 Bearer token |
| Browser에서 Server | TLS, Backend가 소유하는 사용자 session과 Cross-Site Request Forgery (CSRF) 보호 |
| 같은 장비의 내부 service | Unix Domain Socket (UDS) 권한 또는 외부에 공개하지 않은 Compose network |

Server reverse proxy는 Browser 요청에 고정 Bearer token을 추가하지 않는다. 같은 장비의 내부
service는 외부 수신 port를 열지 않고 공유 Bearer token을 사용하지 않는다. Camera Media
Service가 Backend를 직접 호출하는 기능을 제공하면 해당 호출 전용 service credential과
최소 권한을 별도 계약으로 추가한다.

Server TLS 개인키는 `/srv/scrap-monitoring/pki/tls/server.key`에서 별도로 관리한다.

비밀 파일 경로는 환경설정에 기록할 수 있지만 비밀값은 Git, Release, command line과 log에 포함하지
않는다. Token은 Online Package, Offline Bundle 또는 Release checksum 대상에 포함하지 않는다.
Component가 file 기반 secret 입력을 지원하지 않으면 해당 제한을 해소하기 전까지 통합 배포 완료
상태로 간주하지 않는다.

## PKI와 Root CA

Edge는 /usr/local/share/ca-certificates/scrap-monitoring-root-ca.crt의 기존 Root CA 인증서를
사용한다. 배포는 인증서를 새로 만들거나 교체하지 않고 fingerprint와 OS trust store 반영 상태를
검증한다. 필요한 Container에는 같은 인증서를 read-only로 연결한다.

Server의 인증서와 개인키 위치, 권한과 갱신 절차는 pki-operations.md에서 관리한다.
Server 환경 파일의 `PKI_ROOT_CA_SHA256`은 Bootstrap 때 별도 위치에 기록한 Root CA의 DER
SHA-256 fingerprint다. `PKI_CA_URL`은 host에서 접근하는 loopback 전용 `step-ca` URL이다. 배포
도구는 fingerprint 입력과 Server PKI 경로의 인증서 및 fingerprint 파일을 교차 검증하며
불일치하면 인증서를 발급하거나 갱신하지 않는다.

## 동기화

설정 동기화는 단방향 목표 상태 적용이며 장비의 실제 값을 Git으로 역전송하지 않는다.

1. Release asset이 대상별 Compose, .env.example, Release manifest와 적용 도구를 제공한다.
2. 배포 적용기가 새 Release를 독립된 version 경로에 staging한다.
3. 배포 적용기가 .env.example과 대상 장비 환경 파일의 schema version 및 변수 집합을 비교한다.
4. 필수 변수가 없거나 알 수 없는 변수가 있으면 현재 배포를 유지하고 적용을 중단한다.
5. 배포 적용기가 manifest에서 대상별 release.env를 생성하고 image digest와 architecture를
   검증한다.
6. Edge 배포 적용기가 Component 설정의 hash를 계산하여 generated environment 파일을 생성한다.
7. 배포 적용기가 비밀 파일, 장치, 영속 경로와 인증서의 존재 및 권한을 검증한다.
8. Docker Compose 구성을 검증한 뒤 current symlink를 새 version으로 전환한다.
9. 상태 확인이 실패하면 이전 current 대상과 Release 설정으로 복구한다.

.env.example에 변수가 추가되면 실제 장비 파일을 자동으로 덮어쓰지 않는다. 운영자가 새 값을
검토하여 실제 파일에 추가한 뒤 다시 적용한다. 변수 제거도 같은 검증을 거치며 이전 값이 남아
있으면 적용을 중단한다.

## 현재 연동 값의 소유권

| 값 | 소유 영역 | 상태 |
| --- | --- | --- |
| SITE_ID, EDGE_ID, CAMERA_ID | Edge 장비 환경설정 | 대상 장비별 필수값 |
| CONFIG_REVISION | Edge 장비 환경설정 | edge.json의 동일 항목과 일치 |
| CONFIG_SHA256 | Generated environment | edge.json에서 계산 |
| LIDAR_A_IP, LIDAR_B_IP | Edge 장비 환경설정 | 현장 센서 주소 |
| SYNTHETIC_CAMERA_SERVER_URL | Edge 장비 환경설정 | Visualizer WebSocket URL |
| CAMERA_DEVICE | Edge 장비 환경설정 | V4L2 loopback device 경로 |
| SIMULATOR_LIDAR_A_IP, SIMULATOR_LIDAR_B_IP | Server 장비 환경설정 | LiDAR별 UDP publish IP |
| SIMULATOR_LIDAR_UDP_PORT | Server 장비 환경설정 | LiDAR별 공통 UDP port |
| SIMULATOR_VISUALIZER_BIND_ADDRESS | Server 장비 환경설정 | Visualizer HTTP와 WebSocket publish IP |
| MEASUREMENT_URL | Edge 장비 환경설정 | Backend HTTPS 수신 경로 |
| HEARTBEAT_URL | Edge 장비 환경설정 | Backend HTTPS heartbeat 경로 |
| MEDIA_WSS_URL | Edge 장비 환경설정 | Media WSS 수신 경로 |
| DEPLOYMENT_REVISION | Release 설정 | 통합 Release에서 생성 |
| 이름이 IMAGE로 끝나는 변수 | Release 설정 | Manifest의 digest 고정 image |
| Backend Bearer token | 비밀정보 | Edge별 원문 Client 파일과 Server digest registry |
| Camera Media Bearer token | 비밀정보 | Camera별 원문 Client 파일과 Server digest registry |
| Root CA | PKI 상태 | Edge에 사전 설치한 인증서 |
| PKI_ROOT_CA_SHA256 | Server 장비 환경설정 | Bootstrap 때 별도 확인한 Root CA fingerprint |
| PKI_CA_URL | Server 장비 환경설정 | Host 인증서 자동화용 loopback CA URL |

## 현재 구현 상태

대상별 .env.example과 이 문서가 환경설정 schema와 소유권을 정의한다.
delivery/validate-environment는 실제 값을 출력하지 않고 schema version, 누락 변수와 알 수 없는
변수를 검사한다.

`delivery/generate-auth-secret`, `delivery/install-auth-secret`, `delivery/retire-auth-secret`과
`delivery/validate-auth-secrets`가 token 생성, 설치, rotation과 배포 전 검증을 구현한다. 대상별
systemd unit은 Compose 시작 전에 인증 파일을 검증한다. Component의 digest registry 입력과
Compose service별 secret 연결은 Component 실행 계약이 확정되지 않아 구현되지 않았다.

`delivery/apply-release`는 Manifest 기반 release.env와 Edge 설정 hash 생성, 불변 Version
staging, current 및 previous 전환, systemd 시작, Compose 실행 상태 확인과 실패 rollback을
구현한다.
