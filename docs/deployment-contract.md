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
| 대상 환경 계약 | 현장 운영 환경 | Runtime, host 자원, network, 설정, 비밀정보와 PKI 상태 |

### Component 실행 계약

각 component Repository는 다음 항목을 제공한다.

| 항목 | 필수 내용 |
| --- | --- |
| Component 식별 | 고유 이름과 담당 기능 |
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
| Online 인증 | Public image는 불필요하며 Private Package 예외에만 최소 범위의 GHCR 자격 증명 |
| PKI 상태 | Server의 기존 CA 상태와 Edge의 Root CA trust |
| Offline 반입 | 대상별 Bundle과 checksum manifest를 읽을 수 있는 경로 |

대상 architecture가 manifest와 다르거나 필수 host 자원이 없으면 적용을 시작하지 않는다.
실제 주소, 자격 증명, 인증서 개인키와 현장별 값은 Repository와 Release asset에 포함하지 않는다.

## Repository 영역

구현 영역은 6개다.

| 영역 | 기대 동작 |
| --- | --- |
| `release` | Manifest 검증, 대상별 package와 Bundle 생성, checksum 작성 |
| `delivery/online` | Release metadata와 Online Package 취득 |
| `delivery/offline` | Offline Bundle 생성, 검증과 image import |
| `delivery` | 취득 경로와 무관한 검증, 적용, 상태 확인과 rollback |
| `targets` | Edge와 Server의 Compose 목표 상태와 systemd 연결 |
| `pki` | 기존 CA 검증과 Server 인증서 발급, 갱신 및 검증 |

`tests`와 `.github/workflows`는 위 6개 영역을 검증하고 Release 게시를 제어한다.

## Release 생성

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

### Outbound Pull

1. 대상과 통합 버전을 입력받는다.
2. GitHub Release에서 대상별 Online Package와 checksum manifest를 취득한다.
3. Manifest가 참조한 대상 platform의 image를 GHCR에서 digest로 취득한다.
4. 공통 검증과 적용 절차에 package와 image를 전달한다.

### Offline Bundle

1. 외부 연결이 가능한 빌드 환경에서 통합 버전과 대상을 입력받는다.
2. Manifest가 참조한 대상 platform의 image를 digest로 취득한다.
3. 대상별 배포 파일과 image archive를 하나의 Offline Bundle로 생성한다.
4. Bundle과 checksum manifest를 이동식 매체로 대상 환경에 반입한다.
5. 대상 환경에서 checksum을 검증한 뒤 image archive를 Container runtime에 import한다.
6. 공통 검증과 적용 절차에 Bundle을 전달한다.

### 공통 검증과 적용

1. Asset checksum, Manifest schema, 통합 버전, 대상과 architecture를 확인한다.
2. 대상별 실제 설정, host storage, 장치, network와 PKI 선행 조건을 확인한다.
3. 새 버전을 `/srv/scrap-monitoring/deployment` 아래의 독립된 version 경로에 staging한다.
4. Docker Compose 구성을 검증하고 필요한 Server 인증서 상태를 준비한다.
5. `current`가 가리키는 version을 전환하고 대상별 systemd unit을 시작하거나 재시작한다.
6. Compose health check와 외부 HTTPS 또는 WebSocket Secure (WSS) 연결을 확인한다.
7. 적용 확인이 실패하면 이전 `current` version과 이전 인증서 상태로 복구하고 실패를 반환한다.

배포 갱신은 Git 외부의 환경 설정과 영속 데이터를 덮어쓰거나 삭제하지 않는다. 같은 통합 버전의
재적용은 같은 목표 상태를 만들고 불필요한 CA, key와 영속 상태를 다시 생성하지 않는다.

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
| `delivery/online/fetch-release` | 통합 버전, 대상과 출력 경로 | 검증 가능한 Online Package와 checksum 취득 |
| `delivery/offline/build-bundle` | Manifest와 대상 image archive | 대상별 Offline Bundle과 checksum 생성 |
| `delivery/offline/import-bundle` | 대상별 Bundle과 checksum | 검증된 대상 image의 local import |
| `delivery/verify-release` | Package 또는 Bundle과 checksum | checksum, Manifest, 대상과 architecture 검증 |
| `delivery/apply-release` | 검증된 대상 package | Version staging, 목표 상태 전환과 상태 확인 |

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

### Server

Server 목표 상태는 `linux/amd64` component만 사용한다. Compose는 확인된 backend, 영속 데이터
저장소, Camera Media Service, Dashboard, TLS 종단, service routing과 `step-ca` 계약을 정의한다.
systemd는 Server 환경 파일과 `current/targets/server/compose.yaml`을 사용하여 Compose project를
관리한다.

Component 이름, image와 실행 계약이 확인되기 전에는 빈 Compose service를 임의의 예제로 채우지
않는다. 확인한 계약을 반영할 때 공개 설정은 대상별 `.env.example`과 `config`에 기록하고 실제 값은
host 환경 파일에 둔다.

## 자동 검증

Continuous Integration (CI) job `CI`는 모든 `main` 대상 Pull Request와 `main` Push에서 실행한다.
Markdown, YAML, JSON,
JSON Schema, Python, Shell, Docker Compose, systemd, Repository 구조, Public 범위, Release asset과
checksum을 검사한다. 실제 동작을 구현한 실행 파일은 성공 경로, 입력 오류, checksum 오류,
architecture 불일치와 외부 의존성 실패를 테스트한다.

Release workflow는 `vMAJOR.MINOR.PATCH` tag Push에서 실행한다. CI와 같은 정적 검증 및 테스트를
다시 수행하고 Release 생성 순서를 완료한 뒤에만 Release를 게시한다.

Docker와 Docker Compose 실행 검증은 별도 Ubuntu test host에서 수행한다. 실제 Edge와 Monitoring
Server는 Release 적용과 운영 상태 확인에만 사용한다.

## 미확정 입력 처리

다음 입력이 없으면 관련 실제 구현을 완료된 것으로 기록하지 않는다.

- Component image와 실행 계약이 없으면 대상별 Compose service 구성을 보류한다.
- Database migration과 rollback 계약이 없으면 schema 변경 Release의 자동 rollback을 허용하지 않는다.
- 실제 CA 상태와 Server FQDN이 없으면 Server 인증서를 발급하거나 TLS 종단을 시작하지 않는다.
- Release에 필요한 image가 없으면 실제 Offline Bundle과 GitHub Release를 게시하지 않는다.
