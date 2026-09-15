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

Edge의 Release 설정은 다음 값을 포함한다.

- DEPLOYMENT_REVISION
- LIDAR_DRIVER_IMAGE
- LIDAR_PROCESSING_IMAGE
- MEASUREMENT_UPLINK_IMAGE
- CAMERA_EDGE_IMAGE
- EDGE_ORCHESTRATOR_IMAGE

Server의 Release 설정은 다음 값을 포함한다.

- DEPLOYMENT_REVISION
- BACKEND_IMAGE
- DASHBOARD_IMAGE
- MEDIA_SERVICE_IMAGE

release.env는 Release asset에서 생성한 파일이며 사람이 수정하지 않는다. Image 값은
`ghcr.io/organization/image@sha256:digest` 형식의 실제 이름과 64자리 digest만 허용한다.

## 장비 환경설정

장비별 실제 환경설정 경로는 다음과 같다.

| 대상 | 공개 schema | 실제 파일 |
| --- | --- | --- |
| Edge | targets/edge/.env.example | /etc/scrap-monitoring/edge.env |
| Server | targets/server/.env.example | /etc/scrap-monitoring/server.env |

.env.example은 변수 이름, 공개 가능한 형식과 schema version을 관리한다. 실제 파일은 현장 주소,
Fully Qualified Domain Name (FQDN), 장치 경로와 host group ID를 보관하며 Git과 Release asset에
포함하지 않는다.

실제 환경 파일은 root:scrap-admin, file 0640을 사용한다. 배포 적용기는 값을 로그에 출력하거나
Release 작업 경로로 복사하지 않는다.

## Component 설정과 파생값

Edge의 처리 설정은 /opt/ajin/config/edge.json에서 관리한다. 승인된 보정값, 센서 매핑,
서비스 version manifest는 이 파일의 책임이다. 장비 환경설정이 소유하는 SITE_ID, EDGE_ID,
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

비밀정보는 환경변수 값이 아니라 대상 장비의 파일로 관리하고 Compose secret 또는 read-only
file mount로 Container에 제공한다.

| 대상 | 비밀정보 경로 | 내용 |
| --- | --- | --- |
| Edge | /opt/ajin/secrets/edge-token | Backend 측정 및 heartbeat Bearer token |
| Edge | /opt/ajin/secrets/camera-token | Camera Media Service Bearer token |
| Server | /srv/scrap-monitoring/secrets | Backend, Media와 외부 연동 자격 증명 |
| Server | /srv/scrap-monitoring/pki/tls/server.key | HTTPS 및 WSS Server 개인키 |

비밀 파일 경로는 환경설정에 기록할 수 있지만 비밀값은 Git, Release, command line과 log에 포함하지
않는다. Component가 file 기반 secret 입력을 지원하지 않으면 해당 제한을 해소하기 전까지 통합
배포 완료 상태로 간주하지 않는다.

## PKI와 Root CA

Edge는 /usr/local/share/ca-certificates/scrap-monitoring-root-ca.crt의 기존 Root CA 인증서를
사용한다. 배포는 인증서를 새로 만들거나 교체하지 않고 fingerprint와 OS trust store 반영 상태를
검증한다. 필요한 Container에는 같은 인증서를 read-only로 연결한다.

Server의 인증서와 개인키 위치, 권한과 갱신 절차는 pki-operations.md에서 관리한다.

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
| MEASUREMENT_URL | Edge 장비 환경설정 | Backend HTTPS 수신 경로 |
| HEARTBEAT_URL | Edge 장비 환경설정 | Backend HTTPS heartbeat 경로 |
| MEDIA_WSS_URL | Edge 장비 환경설정 | Media WSS 수신 경로 |
| DEPLOYMENT_REVISION | Release 설정 | 통합 Release에서 생성 |
| 이름이 IMAGE로 끝나는 변수 | Release 설정 | Manifest의 digest 고정 image |
| Edge 및 Camera token | 비밀정보 | 대상 장비의 token 파일 |
| Root CA | PKI 상태 | Edge에 사전 설치한 인증서 |

## 현재 구현 상태

대상별 .env.example과 이 문서가 환경설정 schema와 소유권을 정의한다.
delivery/validate-environment는 실제 값을 출력하지 않고 schema version, 누락 변수와 알 수 없는
변수를 검사한다.

Manifest 기반 release.env 생성, Component 설정 hash 생성, 원자적 적용과 rollback은
delivery/apply-release 구현 범위이며 아직 구현되지 않았다.
