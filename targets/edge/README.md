# Edge target

이 디렉토리는 Linux ARM64 Edge 장비의 배포 목표 상태를 관리한다.

## 설정 입력

Edge 설정 입력은 4개다.

| 입력 | 위치 | 책임 |
| --- | --- | --- |
| Release 설정 | 배포 적용기가 생성한 release.env | 배포 revision과 image digest |
| 장비 환경설정 | /etc/scrap-monitoring/edge.env | 장비 식별자, 주소, endpoint와 host 경로 |
| Generated 설정 | 배포 적용기가 생성한 environment 파일 | CONFIG_SHA256 |
| 비밀 파일 | /opt/ajin/secrets | Backend와 Camera token |

공개 환경설정 schema는 [hardware/.env.example](hardware/.env.example)과
[simulation/.env.example](simulation/.env.example)을 따른다. 값의 소유권과 동기화는
[docs/configuration-management.md](../../docs/configuration-management.md)를 따른다.

## 연결 경계

두 LiDAR 주소는 LIDAR_A_IP와 LIDAR_B_IP로 제공한다. hardware는 실제 sensor 주소를, simulation은
Server가 UDP 8089로 공개한 LiDAR별 IP를 사용한다. simulation Camera Edge Bridge는
SYNTHETIC_CAMERA_SERVER_URL에서 synthetic MJPEG stream을 수신해 CAMERA_DEVICE V4L2 device에
기록한다. 설정, 측정, 판단과 상태는 BACKEND_ORIGIN의 Edge v2 HTTPS 수신 경로를 사용한다.
Camera frame은 MEDIA_WSS_URL의 WebSocket Secure (WSS) endpoint로 전송한다.

Edge의 기존 Root CA 인증서는 EDGE_ROOT_CA_FILE에서 읽고 필요한 Container에 read-only로
연결한다. 배포 과정에서 Root CA를 생성하거나 교체하지 않는다.

## 현재 상태

v2 환경설정 schema, runtime JSON과 Compose 시작 전 원문 token 검증이 반영되어 있다.
Component image와 인수 상태는 [docs/implementation.md](../../docs/implementation.md)를 따른다.
Secret 접근 권한 정책은
[docs/configuration-management.md](../../docs/configuration-management.md)를 따른다. 배포 적용기는
Manifest 기반 release.env와 CONFIG_SHA256을 생성하며 실제 Compose service, service별 secret
연결과 Root CA mount는 구현되지 않았다.
