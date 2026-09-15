# Server target

이 디렉토리는 Linux x86_64 Monitoring Server의 배포 목표 상태를 관리한다.

## 설정 입력

Server 설정 입력은 3개다.

| 입력 | 위치 | 책임 |
| --- | --- | --- |
| Release 설정 | 배포 적용기가 생성한 release.env | 배포 revision과 image digest |
| 장비 환경설정 | /etc/scrap-monitoring/server.env | FQDN, listener, host 경로와 Browser origin |
| 비밀 및 PKI 파일 | /srv/scrap-monitoring | 자격 증명, Server 인증서와 개인키 |

공개 환경설정 schema는 [.env.example](.env.example)을 따른다. 값의 소유권과 동기화는
[배포 환경설정 관리](../../docs/configuration-management.md)를 따른다.

## 라우팅 경계

TLS 종단은 Dashboard 정적 파일과 공통 reverse proxy를 제공한다. 일반 Backend API 경로는
Backend로 전달하고 Camera ingest WebSocket 경로는 Camera Media Service로 전달한다. Camera
경로는 일반 API 경로보다 먼저 일치해야 한다.

Backend port는 Container network에만 두며 외부 Client는 Server의 HTTPS endpoint를 사용한다.

## 현재 상태

환경설정 schema, 라우팅 계약과 Compose 시작 전 digest registry 검증이 반영되어 있다. Backend와
Edge Platform의 측정 계약 정합화, heartbeat API, Backend와 Camera Media Service의 digest
registry 입력, service별 secret 연결과 실제 Compose service는 아직 구현되지 않았다.
