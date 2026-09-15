# 배포 동작 계약

## 역할

이 문서는 통합 배포 Repository가 외부에서 받는 입력과 각 배포 영역이 제공해야 하는 동작의
정본이다. 프로젝트 목적과 범위는 `project-spec.md`, 채택한 기술과 현재 구현 상태는
`implementation.md`, Private PKI (Public Key Infrastructure) 운영 절차는 `pki-operations.md`를
따른다.

구현은 이 문서에 없는 component 설정, host 경로와 운영 값을 추정하지 않는다. 확인되지 않은
입력은 공개 template에 임의의 값으로 채우지 않고 외부 계약이 필요한 상태로 유지한다.

## 외부 입력

통합 배포가 소비하는 외부 입력은 3개다.

| 입력 | 제공 주체 | 사용 범위 |
| --- | --- | --- |
| Component 실행 계약 | 기능별 개발 Repository | Compose, 설정 template, 상태 검사와 배포 순서 |
| Release 선택 | Release 작업자 | 통합 버전과 포함할 component image 집합 |
| 대상 환경 계약 | 현장 운영 환경 | Runtime, host 자원, network, 설정, secret 저장 경로와 PKI 상태 |

### Component 실행 계약

각 component Repository는 다음 항목을 제공한다.

| 항목 | 필수 내용 |
| --- | --- |
| Component 식별 | 고유 이름과 담당 기능 |
| Component 출처 | Public source Repository, Release version과 full Git commit |
| 배포 대상 | `edge` 또는 `server` |
| Container image | GitHub Container Registry (GHCR) 경로, Release image tag와 Secure Hash Algorithm 256-bit (SHA-256) digest |
| Package 공개 범위 | Public 기본, 공개 제한 사유가 정본에 기록된 경우에만 Private |
| Package 접근 | Public Package는 자격 증명 없이 pull하며 Private 예외는 read-only 자격 증명을 사용 |
| Platform | 운영체제와 CPU architecture |
| 시작 명령 | Image 기본 명령 또는 Compose에서 필요한 명시적 명령 |
| 설정 | 환경 변수 이름, 형식, 필수 여부와 공개 가능한 예시 값 |
| 비밀정보 | 필요한 secret 이름과 주입 위치 |
| Network | 수신 port, 송신 endpoint, protocol과 이름 해석 요구 |
| 상태 검사 | 준비 완료와 정상 동작을 판정하는 명령 또는 endpoint |
| 영속 상태 | host storage, volume, 소유권과 backup 요구 |
| Host 연동 | 장치, file mount, 권한과 Linux capability 요구 |
| 의존 관계 | 시작 순서, 필수 service와 장애 시 동작 |
| 변경 절차 | Data migration, 갱신 전 조건과 rollback 가능 조건 |
| 외부 고지 | 배포 asset에 포함할 license와 notice |

Image tag만 제공하거나 `latest`처럼 변경 가능한 참조만 제공한 component는 통합 Release에
포함하지 않는다. 상태 검사와 필수 설정이 확인되지 않은 component는 실제 Compose service로
등록하지 않는다. 배포 Compose와 Release manifest는 image tag가 아닌 digest 고정 참조를 사용하며
통합 Release tag에 digest를 결합하지 않는다.

### Release 선택

Release 작업자는 다음 항목을 확정한다.

| 항목 | 필수 내용 |
| --- | --- |
| 통합 버전 | `vMAJOR.MINOR.PATCH` 형식의 Release tag |
| 기준 commit | 원격 `main` 이력에 포함된 검증 완료 commit |
| Manifest | `release/manifests/<version>.json`의 통합 버전과 일치하는 Release manifest |
| Edge image 집합 | `linux/arm64`용 digest 고정 image |
| Server image 집합 | `linux/amd64`용 digest 고정 image |
| 외부 고지 | 포함한 image와 도구에 필요한 license 및 notice |

Manifest의 통합 버전, tag와 asset 이름의 버전이 다르면 Release 생성을 중단한다. 하나의 대상에
필요한 image가 누락되면 Online Package와 Offline Bundle을 게시하지 않는다.

### 대상 환경 계약

각 대상 환경은 다음 항목을 Git 외부에서 제공한다.

| 항목 | 필수 내용 |
| --- | --- |
| Host | Linux 배포판, CPU architecture와 systemd 사용 가능 여부 |
| Container runtime | Docker Engine `29.8.0`, Docker Compose plugin `5.5.1`과 containerd `2.3.5` |
| 배포 경로 | `/srv/scrap-monitoring/deployment` 쓰기 권한 |
| 환경 설정 | 대상별 `/etc/scrap-monitoring/*.env` 실제 값 |
| 영속 저장소 | Database, 영상, 운영 상태와 설정의 host 경로 및 권한 |
| 장치 | Edge component가 사용하는 실제 장치 경로와 접근 권한 |
| Network | Server Fully Qualified Domain Name (FQDN), 허용 port와 outbound 접근 |
| Secret 저장소 | 배포 도구가 생성한 애플리케이션 token을 설치할 host 경로와 접근 권한 |
| Online 인증 | Public image는 불필요하며 Private Package 예외에만 최소 범위의 GHCR 자격 증명 |
| PKI 상태 | Server의 기존 CA 상태와 Edge의 Root CA trust |
| Offline 반입 | 대상별 Bundle과 checksum manifest를 읽을 수 있는 경로 |

대상 architecture가 manifest와 다르거나 필수 host 자원이 없으면 적용을 시작하지 않는다.
실제 주소, 자격 증명, 인증서 개인키와 현장별 값은 Repository와 Release asset에 포함하지 않는다.
Release 설정, 장비 환경설정, Component 설정, 비밀정보와 PKI 상태의 정본 및 동기화 방식은
[`configuration-management.md`](configuration-management.md)를 따른다.

## Repository 영역

구현 영역은 6개다.

| 영역 | 기대 동작 |
| --- | --- |
| `release` | Manifest 검증, 대상별 package와 Bundle 생성, checksum 작성 |
| `delivery/online` | Release metadata와 Online Package 취득 |
| `delivery/offline` | Offline Bundle 검증과 image import |
| `delivery` | 애플리케이션 token 관리, 공통 검증, 적용, 상태 확인과 rollback |
| `targets` | Edge와 Server의 Compose 목표 상태와 systemd 연결 |
| `pki` | 기존 CA 검증과 Server 인증서 발급, 갱신 및 검증 |

`tests`와 `.github/workflows`는 위 6개 영역을 검증하고 Release 게시를 제어한다.

## Release 생성

Release Package descriptor의 필드는 7개다.

| 필드 | 내용 |
| --- | --- |
| `schemaVersion` | Package schema version |
| `version` | 통합 Release version |
| `target` | `edge` 또는 `server` |
| `mode` | `online` 또는 `offline` |
| `platform` | `linux/arm64` 또는 `linux/amd64` |
| `manifestSha256` | Package 내 Release manifest의 SHA-256 digest |
| `imageArchive` | Offline Bundle의 대상별 image archive 경로 |

`imageArchive`는 Offline Bundle에만 포함한다. Edge는 `linux/arm64`, Server는
`linux/amd64`만 허용하며 descriptor와 Manifest의 version, target, platform과 digest가
일치해야 한다.

Package payload 영역은 8개다.

| 영역 | 포함 조건 |
| --- | --- |
| Package descriptor | 모든 Package |
| Release manifest, schema와 검증기 | 모든 Package |
| 대상별 `targets` 목표 상태 | 모든 Package |
| 공통 배포 도구와 배포 mode별 취득 도구 | 모든 Package |
| 운영 문서와 Repository 이용 조건 | 모든 Package |
| Manifest가 참조한 외부 고지 | 모든 Package |
| PKI 설정과 운영 도구 | Server Package |
| 대상별 image archive | Offline Bundle |

Package 생성기는 명시적 allowlist에 있는 일반 파일만 포함하고 symbolic link와
누락된 외부 고지를 거부한다. Archive의 경로 순서, 시간, 소유자와 file mode를
정규화하여 같은 입력은 동일한 byte의 asset을 생성한다.

Release 생성은 다음 순서를 제공한다.

1. Release tag 형식과 tag commit의 원격 `main` 포함 여부를 확인한다.
2. Manifest schema와 Manifest version의 tag 일치를 확인한다.
3. Manifest가 참조한 모든 image를 digest와 대상 platform으로 검증한다.
4. Edge와 Server의 image archive를 각각 생성한다.
5. 같은 Manifest와 대상별 목표 상태를 사용하여 Online Package 2개와 Offline Bundle 2개를 생성한다.
6. 생성한 4개 asset의 SHA-256 checksum manifest를 작성하고 다시 검증한다.
7. 모든 asset이 준비된 뒤 하나의 GitHub Release에 첨부하여 게시한다.

중간 산출물 일부만 첨부한 Release는 게시하지 않는다. Release 생성 실패 시 tag를 다른 commit으로
이동하거나 기존 asset을 교체하지 않고 원인을 수정한 새 버전을 사용한다.

## 배포 적용

두 배포 경로는 취득 단계만 다르고 검증 이후의 적용 동작을 공유한다.

### 애플리케이션 인증 token

애플리케이션 인증 token은 2종이다.

| 인증 경계 | 식별 단위 | 요청 형식 |
| --- | --- | --- |
| Edge Platform에서 Backend | Edge | `Authorization: Bearer <edge-token>` |
| Camera Edge에서 Camera Media Service | Camera | `Authorization: Bearer <camera-token>` |

두 token은 서로 다른 권한과 rotation 범위를 가지며 값을 재사용하지 않는다. 배포 도구는
credential Bootstrap 또는 명시적인 rotation에서 token을 생성하고 양쪽 대상의 Git 외부 secret
저장소에 Client 원문과 Server digest를 설치한다. Credential Bootstrap은 장비 식별자를 확정한 뒤
최초 Compose 시작 전에 수행한다. 일반 Release 적용은 기존 token을 생성하거나 교체하지 않고
파일 형식, 식별자, digest와 권한을 검증한다. 정확한 파일 경로와 수명 주기는
`configuration-management.md`를 따른다.

최초 구축 순서는 5단계다.

1. 운영자가 오프라인 Root CA와 Monitoring Server의 Intermediate CA를 Bootstrap한다.
2. 운영자가 Root CA 인증서를 Edge와 관리자 Client의 trust store에 등록한다.
3. 운영자가 대상별 장비 환경설정과 host 저장소를 구성한다.
4. 운영자가 두 종류의 credential을 생성하고 Server와 해당 Edge에 설치하여 검증한다.
5. 일반 배포가 기존 CA 상태를 검증하고 Server 인증서를 발급한 뒤 Docker Compose를 시작한다.

후속 Release 배포는 5단계만 반복하고 기존 CA, token과 영속 데이터를 유지한다. Server 인증서의
갱신 시점이 되면 일반 배포 또는 인증서 갱신 timer가 같은 Server 인증서 발급 절차를 수행한다.
Root CA와 애플리케이션 token의 교체는 일반 Release 배포와 분리한 명시적 운영 작업이다.

### Outbound Pull

1. 대상과 통합 버전을 입력받는다.
2. GitHub Release에서 대상별 Online Package와 checksum manifest를 취득한다.
3. Manifest가 참조한 대상 platform의 image를 GHCR에서 digest로 취득한다.
4. 공통 검증과 적용 절차에 package와 image를 전달한다.

Online 취득 도구는 `ajin-scrap-monitoring/scrap-monitoring-deployment`의 HTTPS Release
asset만 사용하며 외부 URL, `latest`와 기존 출력 경로를 입력으로 받지 않는다. Package와
checksum이 모두 취득되고 검증을 통과한 후에만 출력 디렉토리를 공개한다.

### Offline Bundle

1. Release workflow가 외부 연결 가능한 환경에서 대상별 image를 digest로 취득한다.
2. `release/build-assets`가 대상별 배포 파일과 image archive를 Offline Bundle로 생성한다.
3. Release 작업자가 통합 버전, 대상과 checksum을 확인한다.
4. Bundle과 checksum manifest를 이동식 매체로 대상 환경에 반입한다.
5. 대상 환경에서 checksum을 검증한 뒤 image archive를 Container runtime에 import한다.
6. 공통 검증과 적용 절차에 Bundle을 전달한다.

Image import는 Bundle 전체 검증을 통과한 대상별 archive만 Docker에 stream으로 load한다.
Load 후 Manifest가 참조한 모든 image digest의 local 존재와 대상 platform을 다시
확인한다. 사후 검증이 실패하면 명령은 실패하며 기존 image를 삭제하지 않는다.

### 공통 검증과 적용

1. Asset checksum, Manifest schema, 통합 버전, 대상과 architecture를 확인한다.
2. 대상별 실제 설정, host storage, 장치, network, 인증 파일과 PKI 선행 조건을 확인한다.
3. 새 버전을 `/srv/scrap-monitoring/deployment/versions/<version>`에 staging한다.
4. Docker Compose 구성을 검증하고 필요한 Server 인증서 상태를 준비한다.
5. 기존 `current`를 `previous`로 보존하고 `current` symlink를 새 version으로 전환한 뒤 대상별
   systemd unit을 시작하거나 재시작한다.
6. Compose health check와 외부 HTTPS 또는 WebSocket Secure (WSS) 연결을 확인한다.
7. 적용 확인이 실패하면 이전 `current` version과 이전 인증서 상태로 복구하고 실패를 반환한다.

배포 갱신은 Git 외부의 환경 설정과 영속 데이터를 덮어쓰거나 삭제하지 않는다. 같은 통합 버전의
재적용은 같은 목표 상태를 만들고 불필요한 CA, key와 영속 상태를 다시 생성하지 않는다.

Asset 검증은 checksum manifest의 중복과 비정상 항목, Package checksum 불일치, archive의
절대 경로, 상위 경로, 중복 경로, symbolic link, 비정규화 metadata와 allowlist 외부
파일을 거부한다. Package descriptor와 Manifest의 version, target, platform과 Manifest
digest를 서로 비교한다.

배포 상태 경로는 6개다.

| 상태 | 경로 |
| --- | --- |
| Version root | `/srv/scrap-monitoring/deployment/versions` |
| 활성 Version | `/srv/scrap-monitoring/deployment/current` |
| 이전 Version | `/srv/scrap-monitoring/deployment/previous` |
| 대상 적용 상태 | `/srv/scrap-monitoring/deployment/state/<target>.json` |
| Edge 파생 환경 | `/srv/scrap-monitoring/deployment/state/edge.generated.env` |
| 배포 lock | `/run/lock/scrap-monitoring-deployment.lock` |

`current`와 `previous`는 `versions` 아래의 검증된 경로만 가리킨다. 적용 상태에는 secret 값과
환경설정 값을 기록하지 않고 version, target, 적용 결과, 활성 경로와 직전 경로만 기록한다.

## 실행 파일 계약

### Release

| 실행 파일 | 입력 | 성공 조건 |
| --- | --- | --- |
| `release/validate-manifest` | 통합 버전과 version manifest | Schema, version과 대상별 component 존재 확인 |
| `release/pull-images` | 검증된 manifest와 출력 경로 | 대상 platform별 digest 고정 image archive 생성 |
| `release/build-assets` | Manifest와 Edge 및 Server image archive | 대상별 package 4개와 checksum manifest 생성 |

### Delivery

| 실행 파일 | 입력 | 성공 조건 |
| --- | --- | --- |
| `delivery/online/fetch-release` | `--version`, `--target`, `--output` | 명시한 Online Package와 checksum의 검증된 원자적 취득 |
| `delivery/offline/import-bundle` | `--version`, `--target`, `--bundle`, `--checksums` | 검증된 대상 image의 local import |
| `delivery/verify-release` | `--version`, `--target`, `--package`, `--checksums` | checksum, archive, Manifest와 대상 검증 |
| `delivery/generate-auth-secret` | 인증 경계, 식별자와 출력 경로 | 독립적인 256-bit token bundle 생성 |
| `delivery/install-auth-secret` | 대상과 credential bundle | Edge 원문 token의 파일별 원자적 설치 또는 Server registry의 원자적 전환 |
| `delivery/retire-auth-secret` | 이전 credential bundle | Rotation 확인 후 Server의 이전 digest 폐기 |
| `delivery/validate-auth-secrets` | 대상과 Edge 환경 파일 | 인증 파일 형식, 식별자, digest와 권한 검증 |
| `delivery/validate-environment` | 대상과 실제 환경 파일 | Schema version, 변수 집합과 빈 값 검증 |
| `delivery/apply-release` | `--version`, `--target`, `--package`, `--checksums`, `--mode` | 재검증, Version staging, 목표 상태 전환과 상태 확인 |

모든 실행 파일은 입력 오류, 검증 실패와 미구현 동작에 성공 code를 반환하지 않는다. 실패 메시지는
실패한 단계와 대상을 식별할 수 있어야 하며 자격 증명과 secret 값을 출력하지 않는다.

### PKI

| 실행 파일 | 입력 | 성공 조건 |
| --- | --- | --- |
| `pki/validate-ca-state` | Server의 기존 CA 경로와 예상 fingerprint | Root 및 Intermediate 인증서 chain, key와 CA database 일관성 확인 |
| `pki/ensure-server-certificate` | Server FQDN, 기존 CA 상태와 TLS 경로 | 필요한 Server key와 1년 인증서의 발급 또는 갱신 |
| `pki/verify-server-certificate` | Server FQDN, 인증서 chain과 key | DNS 이름, key 일치, chain과 유효기간 확인 |

PKI 실행 파일은 Root CA와 Intermediate CA를 새로 Bootstrap하지 않는다. 인증서 전환 전 새 파일을
검증하고, 전환 후 HTTPS와 WSS 확인이 실패하면 기존 Server 인증서로 복구한다.

## 대상 목표 상태

### Edge

Edge 목표 상태는 `linux/arm64` component만 사용한다. Compose는 확인된 LiDAR 처리와 Camera Edge
Agent의 image, 설정, 장치, Root CA mount, Server WSS endpoint와 health check를 정의한다. systemd는
Edge 환경 파일과 `current/targets/edge/compose.yaml`을 사용하여 Compose project를 관리한다.

Edge는 실제 LiDAR 2개의 site network 주소와 TCP 8089를 각 LiDAR driver에 제공한다. 처리
설정은 host의 `/opt/ajin/config/edge.json`, token은 `/opt/ajin/secrets`, runtime 상태는
`/opt/ajin/runtime`에서 관리한다. 기존 Root CA는
`/usr/local/share/ca-certificates/scrap-monitoring-root-ca.crt`에서 읽고 필요한 Container에
read-only로 연결한다.

Server 연결 경로는 다음 형식을 사용한다.

| 용도 | 경로 |
| --- | --- |
| 측정 전송 | `https://<server-fqdn>/api/v1/metrics/ingest` |
| Heartbeat | `https://<server-fqdn>/api/v1/edge/heartbeat` |
| Camera frame | `wss://<server-fqdn>/api/v1/cameras/<camera-id>/stream` |

### Server

Server 목표 상태는 `linux/amd64` component만 사용한다. Compose는 확인된 backend, 영속 데이터
저장소, Camera Media Service, Dashboard, TLS 종단, service routing과 `step-ca` 계약을 정의한다.
systemd는 Server 환경 파일과 `current/targets/server/compose.yaml`을 사용하여 Compose project를
관리한다.

TLS 종단은 HTTPS 443에서 Server 인증서 chain을 제공한다. 일반 `/api/` 요청은 Backend로
전달하고 Camera ingest 경로는 일반 API 규칙보다 먼저 Camera Media Service로 전달한다.
`Authorization`, `Idempotency-Key`, `Host`, Client 주소와 request ID를 upstream에 유지한다.
Backend와 Camera Media Service의 내부 port는 host 외부에 공개하지 않는다.

### Component 연동

Backend의 측정 수신은 Edge measurement contract v1.0을 원본 입력으로 처리한다. Backend는
Edge ID에 연결된 Bearer token을 측정과 heartbeat에 동일하게 검증하고 `measurement_id`의
고유성을 저장 transaction에서 보장한다. 최초 저장은 동일한 `measurement_id`와
`accepted=true`, 동일 측정의 재전송은 `accepted=true` 또는 `duplicate=true`로 확인한다.

Backend는 `GOOD`, `DEGRADED`, `INVALID` 측정을 모두 수신한다. Edge 계약과 Backend domain
model 사이의 site, Edge, 적재함, 단위와 품질 상태 변환은 Backend가 소유한다. 배포 Repository는
해당 변환을 Compose 또는 reverse proxy에서 구현하지 않는다.

Heartbeat endpoint는 Edge heartbeat contract v1.0을 검증하고 Edge별 최신 snapshot과 마지막 정상
수신 시각을 갱신한다. 정상 처리는 response body 없이 2xx를 반환할 수 있다.

Camera Media Service는 path의 Camera ID에 연결된 `Authorization: Bearer <camera-token>`을
검증하고 binary JPEG frame을 수신한다. TLS는 Server reverse proxy에서 종료하고 Media Service는
private Compose network의 WebSocket listener를 사용한다.

관리자 Browser는 TLS 경계를 통해 Server에 연결하고 Backend가 소유하는 사용자 session과
Cross-Site Request Forgery (CSRF) 보호를 사용한다. Reverse proxy는 Browser 요청에 배포 공용
Bearer token을 추가하지 않는다. 같은 Edge 또는 Server 안의 service는 Unix Domain Socket (UDS)
권한이나 외부에 공개하지 않은 Compose network로 격리하고 공유 Bearer token을 사용하지 않는다.
Camera Media Service에서 Backend로 향하는 직접 API 호출은 현재 계약에 없으며, 해당 기능이
추가되면 별도 service credential과 최소 권한을 Component 실행 계약에 포함한다.

Component 이름, image와 실행 계약이 확인되기 전에는 빈 Compose service를 임의의 예제로 채우지
않는다. 확인한 계약을 반영할 때 공개 설정은 대상별 `.env.example`과 `config`에 기록하고 실제 값은
host 환경 파일에 둔다.

## 자동 검증

Continuous Integration (CI) job `CI`는 모든 `main` 대상 Pull Request와 `main` Push에서 실행한다.
Markdown, YAML, JSON,
JSON Schema, Python, Shell, Docker Compose, systemd, Repository 구조, Public 범위, Release asset과
checksum을 검사한다. `delivery/validate-environment`는 대상별 공개 schema와 실제 환경 파일의
schema version, 누락 변수, 알 수 없는 변수와 빈 값을 검사하고 실제 값을 출력하지 않는다. 실제
동작을 구현한 실행 파일은 성공 경로, 입력 오류, checksum 오류, architecture 불일치와 외부
의존성 실패를 테스트한다.

Release workflow는 `vMAJOR.MINOR.PATCH` tag Push에서 실행한다. CI와 같은 정적 검증 및 테스트를
다시 수행하고 Release 생성 순서를 완료한 뒤에만 Release를 게시한다.

Docker와 Docker Compose 실행 검증은 별도 Ubuntu test host에서 수행한다. 실제 Edge와 Monitoring
Server는 Release 적용과 운영 상태 확인에만 사용한다.

## 미확정 입력 처리

외부 입력이 필요한 영역은 5개다.

### Edge Platform

- Private GHCR Package의 승인된 예외 사유 또는 Public 전환
- Private 유지 시 대상 장비의 read-only pull 인증 계약
- UID `10001` service가 host secret을 읽는 소유권과 mode
- HTTPS 및 WSS Client가 사용할 Root CA file 입력과 mount
- 실제 Raspberry Pi, LiDAR, Camera와 운영 보정값의 인수 결과

### Backend

- Edge별 Bearer digest registry file 입력과 constant-time 검증
- Edge measurement schema, `Idempotency-Key`, 저장 후 ACK와 중복 처리
- Edge heartbeat endpoint와 상태 저장 model
- 운영 Database version, migration, volume, backup과 rollback 계약
- 기본 계정을 사용하지 않는 사용자 저장소, session 영속화와 필수 CSRF 검증
- `linux/amd64` Release image digest와 외부 고지

### Camera Media Service

- Camera별 Bearer digest registry file 입력과 2개 digest rotation
- UID `10002` service의 secret 소유권과 mode
- Liveness, readiness와 reverse proxy 뒤의 평문 WebSocket 계약
- Browser 전달 protocol, 짧은 수명 media ticket과 권한 검증
- 녹화 형식, segment, storage quota, retention과 복구 계약
- `linux/amd64` Release image digest와 외부 고지

### Dashboard

- Backend OpenAPI와 Server-Sent Events (SSE) 계약 승인
- WebRTC-HTTP Egress Protocol (WHEP) signaling과 재연결 계약 승인
- Nginx upstream, route, timeout, request limit과 Content Security Policy (CSP) 값
- Backend session과 CSRF 오류 처리 계약

### 운영 환경

- Server FQDN, DNS, bind 주소, port와 허용 network 경로
- 대상 Docker host, storage 경로, 용량과 UID 및 GID 매핑
- Root CA trust, 기존 Intermediate CA 상태와 발급 자격 증명
- PostgreSQL backup 및 복구 위치와 실제 LiDAR 및 Camera 장치
- Docker Compose 실행 검증에 사용할 별도 Ubuntu test host

위 입력이 없으면 실제 Compose service, 통합 Release, 외부 HTTPS 및 WSS 연결과 현장 배포를
완료 상태로 기록하지 않는다. 실제 환경 파일의 schema가 대상별 `.env.example`과 일치하지 않으면
적용을 중단한다.
