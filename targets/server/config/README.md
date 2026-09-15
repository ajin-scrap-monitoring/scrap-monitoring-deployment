# Server configuration

이 디렉토리는 공개 가능한 Server 설정 template의 위치다. 실제 FQDN, Browser origin, 데이터
경로, 자격 증명과 PKI 상태는 /etc/scrap-monitoring 및 /srv/scrap-monitoring에서 관리한다.

Reverse proxy 설정은 일반 Backend API와 Camera Media Service WebSocket 경로를 구분하고
Authorization 및 Idempotency-Key 요청 header를 Backend에 유지해야 한다.
