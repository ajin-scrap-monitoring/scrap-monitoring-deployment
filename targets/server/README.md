# Server target

이 디렉토리는 Linux x86_64 Monitoring Server의 배포 목표 상태를 관리한다.

## 설정 입력

Server 설정 입력은 3개다.

| 입력 | 위치 | 책임 |
| --- | --- | --- |
| Release 설정 | 배포 적용기가 생성한 release.env | 배포 revision과 image digest |
| 장비 환경설정 | /etc/scrap-monitoring/server.env | FQDN, listener, host 경로와 Browser origin |
| 비밀 및 PKI 파일 | /srv/scrap-monitoring | 자격 증명, Server 인증서와 개인키 |

공개 환경설정 schema는 [.env.example](.env.example)를 따른다. 값의 소유권과 동기화는
[docs/configuration-management.md](../../docs/configuration-management.md)를 따른다.

## 구성

`compose.yaml`의 service는 `step-ca`, `postgres`, `scrap-backend`, `camera-media`, `dashboard`와
`management` profile의 `backend-manage`다. Database network는 internal이다. `dashboard/nginx`의
Edge ingest용 파일은 이 Repository가 관리하고 나머지 3개 파일은 Release build가 Dashboard Release에서
취득해 Package에 넣는다.
Backend와 Media의 secret 입력은 `env_file`로 연결하며 파일 위치는
[docs/configuration-management.md](../../docs/configuration-management.md)를 따른다.

## 라우팅 경계

TLS 종단은 Dashboard 정적 파일과 공통 reverse proxy를 제공한다. 일반 Backend API 경로는
Backend로 전달하고 Camera ingest WebSocket 경로는 Camera Media Service로 전달한다.
Backend와 Media port는 Container network에만 두며 외부 Client는 Server의 HTTPS endpoint를 사용한다.

## 현재 상태

Component image와 미완료 계약은 [docs/implementation.md](../../docs/implementation.md)를 따른다.
