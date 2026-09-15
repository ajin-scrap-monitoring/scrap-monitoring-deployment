# 통합 배포 프로젝트 명세

## Repository

| 항목 | 결정 |
| --- | --- |
| Repository | `ajin-scrap-monitoring/scrap-monitoring-deployment` |
| 공개 범위 | Public |
| 소스 이용 조건 | 별도 라이선스 부여 없음 |

## 상위 컨텍스트

스크랩 모니터링 시스템은 Raspberry Pi Edge 장비, 온프레미스 Monitoring Server와 관리자
Browser로 구성한다. Edge 장비에서는 LiDAR 처리와 Camera Edge Agent가 실행되고, Server에서는
모니터링 백엔드, 영속 데이터 저장소, Camera Media Service, Dashboard 제공과 서비스 라우팅이
실행된다.

이 Repository는 기능별 개발 Repository가 제공하는 배포 가능한 컴포넌트를 Edge와 Server에
일관된 버전으로 설치하고 운영하는 구성을 관리한다. 기능별 소스 코드와 애플리케이션 내부
설계는 각 개발 Repository의 책임이다.

## 목적

인터넷 연결이 가능한 환경과 외부 네트워크 연결이 없는 환경에서 동일한 시스템 버전을
재현할 수 있는 통합 배포 구성을 제공한다.

## 배포 대상

배포 단위는 2개다.

| 배포 단위 | 대상 환경 | 책임 |
| --- | --- | --- |
| Edge | Linux ARM64 Raspberry Pi | LiDAR 처리, Camera Edge Agent와 장비 연동 |
| Server | Linux x86_64 Ubuntu Server | 백엔드, 영속 데이터 저장소, 미디어 처리, Dashboard 제공, Transport Layer Security (TLS) 종단과 서비스 라우팅 |

Edge와 Server는 서로 다른 장비와 CPU 아키텍처를 사용하므로 독립적으로 설치하고 재시작할 수
있어야 한다. 두 배포 단위의 호환 버전은 하나의 통합 배포 Release에서 함께 관리한다.

## 배포 경로

지원하는 배포 경로는 2개다.

| 배포 경로 | 시작 주체 | 이미지 취득 | 적용 환경 |
| --- | --- | --- | --- |
| Outbound Pull | 대상 장비 또는 현장 작업자 | 대상 장비가 허용된 외부 배포 위치에 HTTPS로 연결하여 취득 | 외부 연결 가능 환경 |
| Offline Bundle | 현장 작업자 | 외부 환경에서 만든 대상별 Bundle을 이동식 매체로 반입하여 취득 | 외부 연결 불가 환경 |

외부 자동화가 Secure Shell (SSH)로 대상 장비에 접속하여 배포를 시작하는 Remote Push 경로는
제공하지 않는다. Outbound Pull과 Offline Bundle은 서로 다른 배포 구성을 갖지 않고 같은
Release manifest와 대상별 Docker Compose 정의를 사용한다. 두 경로의 차이는 배포 파일과
컨테이너 이미지를 대상 장비에 전달하는 방법으로 제한한다.

이 경계는 배포 제어 경로에만 적용한다. 실행 중인 Edge 서비스는 WebSocket Secure (WSS)로
Server의 미디어 수신 경계에 연결하며, 관리자 Browser는 허용된 네트워크에서 Server의 웹과
미디어 경계에 연결한다.

## 배포 구성

배포 구성의 최상위 영역은 6개다.

| 영역 | 책임 |
| --- | --- |
| `targets` | Edge와 Server의 Compose, 설정 template와 host 연동 |
| `delivery` | Outbound Pull과 Offline Bundle의 취득, 검증과 적용 절차 |
| `release` | 통합 배포 버전과 대상별 컴포넌트 버전 집합 |
| `pki` | 공개 가능한 Private PKI 설정 template와 일반 배포의 인증서 자동화 도구 |
| `docs` | 제품 명세, 채택한 구현 결정과 현재 상태 |
| `notices` | Release asset에 포함할 Component별 외부 고지 |

Docker Compose는 각 대상의 컨테이너, 네트워크, volume, health check와 서비스 의존 관계를
정의한다. systemd는 운영체제 부팅 시 Docker Compose 구성과 필수 host mount를 준비하고
시작하거나 중지하는 host 수명 주기 경계로만 사용한다. 애플리케이션 프로세스 구성을
Docker Compose와 systemd에 중복하여 정의하지 않는다.

## Release와 버전

통합 배포 Release는 `vMAJOR.MINOR.PATCH` 형식의 tag를 사용한다. 각 Release는 Edge와 Server에
적용할 컴포넌트 이미지를 변경 불가능한 버전으로 고정하고 두 배포 단위의 호환 집합을
정의한다. 기능별 개발 Repository의 버전과 통합 배포 버전은 서로 독립적이며, 하나의 통합
배포 버전이 여러 컴포넌트 버전을 참조할 수 있다.

Release asset 유형은 3개다.

| asset | 수량 | 내용 |
| --- | --- | --- |
| Online Package | Edge와 Server 각 1개 | 대상별 Compose, Release manifest, 설정 template, 적용 도구와 외부 고지 |
| Offline Bundle | Edge와 Server 각 1개 | Online Package 내용과 대상 CPU 아키텍처용 컨테이너 이미지 archive |
| Checksum manifest | Release당 1개 | 모든 배포 asset의 Secure Hash Algorithm 256-bit (SHA-256) checksum |

Release는 모든 asset을 첨부한 뒤 게시한다. 게시된 Release의 tag와 asset은 변경하지 않고,
수정이 필요하면 새 버전을 게시한다.

## Container image 정책

기능별 공개 개발 Repository가 게시하는 OCI (Open Container Initiative) image는 기본적으로
Public GHCR (GitHub Container Registry) Package로 제공한다. 배포 제한이 있는 외부 코드나
계약상 공개할 수 없는 산출물이 포함된 경우에만 Private Package를 사용하며, 해당 예외의
이유와 배포 인증 경계를 구현 문서에 기록한다.

| 항목 | 결정 |
| --- | --- |
| 사람이 읽는 image tag | 기능별 Repository의 Release version에서 파생한 `MAJOR.MINOR.PATCH` |
| source revision tag | `sha-<full-git-sha>` |
| 변경 가능한 tag | `latest`를 게시하지 않음 |
| 배포 image 참조 | `ghcr.io/<organization>/<image>@sha256:<digest>` |
| image 공개 pull | 자격 증명 없이 허용 |
| image 빌드 | 기능별 Repository CI에서 Docker Buildx 사용 |

통합 배포 Repository는 image tag를 배포 식별자로 사용하지 않고 Release manifest에 기록한
SHA-256 digest로 대상을 고정한다. 통합 Release의 `vMAJOR.MINOR.PATCH` tag에는 image digest를
결합하지 않는다.

배포 대상 host의 실행 환경은 Docker Engine `29.8.0`, Docker Compose plugin `5.5.1`과
containerd `2.3.5`로 구성한다. Docker daemon은 root 권한의 systemd 서비스로 실행하며
운영 사용자와 배포 계정을 `docker` 그룹에 추가하지 않는다. Docker Buildx는 기능별 image를
멀티플랫폼으로 빌드하는 CI 환경에만 둔다.

## 설정과 비밀정보

Repository와 Release에는 공개 가능한 설정 template만 포함한다. 자격 증명, 비밀키, 인증서
개인키, 실제 사설 주소와 현장별 값은 Git 또는 Release asset에 포함하지 않는다. 실제 설정과
비밀정보는 각 대상 장비의 Git 외부 경로에서 관리하고 배포 버전을 바꾸어도 유지한다.

통합 배포 도구는 Edge별 Backend Bearer token과 Camera별 Camera Media Service Bearer token의
생성 및 rotation을 소유한다. 일반 Release 적용은 기존 token을 유지하며 token 값은 Online
Package와 Offline Bundle에 포함하지 않는다.

Release가 소유하는 image와 배포 revision, 장비가 소유하는 환경설정, Component 설정에서 계산하는
파생값, 비밀 파일과 PKI 상태를 서로 다른 정본으로 관리한다. Release 적용은 장비 값을 자동으로
덮어쓰지 않고 schema와 필수값을 검증한다. 정확한 분류, 경로와 동기화 규칙은
[`docs/configuration-management.md`](configuration-management.md)를 따른다.

## Private PKI와 TLS 인증서

HTTPS와 WSS는 이 Repository가 관리하는 자체 Public Key Infrastructure (PKI)를 사용한다.
인증서 관리 도구는 Smallstep의 `step` Command-Line Interface (CLI)와 `step-ca`를 사용한다.
`step`은 CA 초기화, 인증서 요청과 갱신을 수행하는 명령어 도구이며 `step-ca`는 Intermediate
CA 개인키로 Server 인증서를 발급하는 서비스다.

인증서 관리 영역은 2개다.

| 영역 | 실행 시점 | 책임 |
| --- | --- | --- |
| 수동 구성 | 환경별 최초 구성과 Root CA 교체 | PKI Bootstrap과 Edge 및 관리자 컴퓨터의 Root CA trust 등록 |
| 일반 배포 자동화 | 최초 배포와 이후 모든 배포 | Server 개인키 생성, Server 인증서 발급 또는 갱신, 검증, TLS 종단 적용과 연결 확인 |

PKI Bootstrap과 Client trust 등록은 운영자가 직접 수행한다. Client trust는 Root CA 인증서의
생성과 fingerprint 확인이 끝나면 일반 배포와 관계없이 등록할 수 있다. 일반 배포는 이미 생성한
CA 상태를 전제로 자동 실행한다. CA 상태가 없거나 일치하지 않으면 일반 배포는 새로운 CA를
생성하지 않고 실패해야 한다.

Root CA 개인키, Intermediate CA 개인키, Server 개인키, CA database와 발급 자격 증명은 Git,
Container image, Online Package와 Offline Bundle에 포함하지 않는다. Root CA 개인키는 최초
PKI Bootstrap에서 암호화하여 생성하고 Monitoring Server 밖의 오프라인 저장소에 보관한다.
Monitoring Server의 `/srv/scrap-monitoring/pki/root`에는 Root CA 인증서와 fingerprint만
보관한다.

Intermediate CA 상태와 Server TLS 상태는 Monitoring Server의 Git 외부 영속 경로에서
관리한다. 일반 배포와 `step-ca`는 Root CA 개인키를 읽지 않으며 Intermediate CA 개인키를
사용해 Server 인증서를 발급한다. Intermediate CA 개인키는 암호화하고 `step-ca` 전용 암호로
복호화한다.

Camera Edge Agent와 관리자 Browser에는 Client 인증서를 발급하지 않는다. 두 Client는 Root CA
인증서를 trust store에 설치하고 Server 인증서 chain을 검증한다. WebRTC를 채택할 경우 Browser와
Camera Media Service의 Datagram Transport Layer Security (DTLS) 인증서와 개인키는 WebRTC
runtime이 별도로 생성하고 관리한다.

인증서 파일의 역할과 전체 발급, 배포 및 갱신 절차는
[`docs/pki-operations.md`](pki-operations.md)를 따른다.

## 영속 데이터와 복구

데이터베이스, 녹화 영상, 운영 설정과 필요한 장비 상태는 컨테이너 이미지와 분리한 host
storage에 저장한다. 배포 갱신과 컨테이너 재생성은 영속 데이터를 삭제하지 않아야 한다.

이전 통합 배포 Release의 대상별 구성과 이미지를 다시 적용할 수 있어야 한다. 데이터 schema
변경이 이전 버전과 호환되지 않는 Release는 갱신 전에 backup과 별도 복구 절차를 요구하며,
정확한 migration과 rollback 방식은 해당 컴포넌트 계약을 확인한 뒤 구현 문서에서 결정한다.

## 포함 범위

- Edge와 Server의 Docker Compose 구성
- 대상별 공개 설정 template와 host 수명 주기 연동
- Edge와 Server 사이의 애플리케이션 Bearer token 생성 및 rotation
- Outbound Pull 취득, 검증, 적용과 재실행
- Offline Bundle 생성, 반입 후 검증, image load와 적용
- 통합 배포 manifest, Release asset과 checksum 생성
- Private PKI 수동 Bootstrap 절차와 Server 인증서 발급, 갱신 및 검증 자동화
- Server의 TLS 종단, Dashboard 제공과 서비스 라우팅 구성
- host storage 연결과 배포 버전 rollback 경계

## 제외 범위

- LiDAR, Camera, Backend, Media와 Dashboard 애플리케이션 소스 구현
- 운영체제 설치와 disk partition 구성
- 사용자 계정, SSH 공개키, Virtual Private Network (VPN)와 현장 network provisioning
- 자격 증명, 인증서 개인키와 현장별 실제 설정의 Git 및 Release 보관
- 실제 운영 데이터의 backup 정책과 장기 보존 정책 결정
- 인터넷에서 대상 장비로 접속하여 시작하는 Remote Push 배포

## 외부 계약

| 제공 주체 | 배포 Repository에 제공할 계약 |
| --- | --- |
| 기능별 개발 Repository | 대상 아키텍처용 container image, 변경 불가능한 버전 식별자, 설정 항목, health check, volume과 network 요구 |
| 현장 운영 환경 | 대상 운영체제, Docker 실행 환경, host storage, 실제 설정, Root CA trust, 비밀정보와 허용된 network 경로 |
| 배포 Release | 대상별 Compose 구성, 고정된 image 집합, 적용 도구, 외부 고지와 checksum |

컴포넌트 Repository의 실제 이름, image 배포 위치와 세부 실행 계약이 확정되면 이 Repository의
구현 문서와 배포 manifest에 반영한다. 프로젝트 전체 정본에는 해당 세부 기술을 복제하지
않는다. 각 외부 입력의 필수 항목과 배포 영역별 동작은
[`docs/deployment-contract.md`](deployment-contract.md)를 따른다.

## 완료 방향

- 외부 연결이 가능한 Edge와 Server에서 대상 장비가 지정한 통합 배포 버전을 가져와 적용할 수 있는 구성
- 외부 연결이 없는 Edge와 Server에서 검증한 Offline Bundle만으로 같은 버전을 적용할 수 있는 구성
- 재부팅 후 host storage와 실행 서비스가 정해진 순서로 복구되는 구성
- 배포 갱신이 영속 데이터와 현장별 설정을 보존하는 구성
- 최초 PKI Bootstrap 이후 일반 배포가 Server 인증서 발급과 갱신을 자동화하는 구성
- 대상별 설치 결과와 실행 중 서비스 상태를 확인할 수 있는 검증 절차
- 이전 호환 Release로 되돌릴 수 있는 rollback 절차
