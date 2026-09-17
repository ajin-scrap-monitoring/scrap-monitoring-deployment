# 스크랩 모니터링 배포

스크랩 모니터링 시스템의 Edge와 Server 통합 배포 구성을 관리한다. 기능별 Repository가 제공한
고정 OCI (Open Container Initiative) image digest와 대상별 설정을 하나의 배포 Release로 조합한다.
애플리케이션 소스와 내부 구현은 각 기능별 Repository가 소유한다.

## 주요 기능

- Edge와 Server hardware 배포 구성
- Outbound Pull과 Offline Bundle 배포 경로
- Release manifest, Package와 checksum 검증
- Private PKI 인증서와 애플리케이션 token 배포 도구

## 사전 조건

| 의존성 | version |
| --- | --- |
| Docker Engine | `29.8.0` |
| Docker Compose plugin | `5.5.1` |

## Hardware 배포 순서

### 1. Host Bootstrap

#### Edge host

```bash
sudo delivery/install-container-runtime --target edge
```

#### Server host

```bash
sudo delivery/install-container-runtime --target server
```

### 2. PKI와 Root CA trust

Server에서 [docs/pki-operations.md](docs/pki-operations.md)의 PKI Bootstrap을 완료하고 Edge에 Root CA
trust를 등록한다.

### 3. 대상 설정

아래 설정 절에서 두 대상의 환경 파일을 설치하고 현장 값을 설정한다. Edge의 `edge.json`, runtime
directory, camera device와 Root CA 파일, Server의 Backend와 Media storage directory가 존재해야 한다.

### 4. Credential Bootstrap

두 환경 파일의 `EDGE_ID`와 `CAMERA_ID`를 확정한 뒤 [delivery/README.md](delivery/README.md)의
credential Bootstrap을 완료한다.

### 5. Server Release 적용

[Server hardware deployment](#server-hardware-deployment)의 Release 적용을 완료한다.

### 6. Edge Release 적용

[Edge hardware deployment](#edge-hardware-deployment)의 Release 적용을 완료한다.

## 설정

각 대상에는 `hardware` 환경 파일을 설치한다. 실제 설정값의 소유권은
[docs/configuration-management.md](docs/configuration-management.md)를 따른다.

### Edge hardware configuration

```bash
sudo install -d -o root -g scrap-admin -m 0750 /etc/scrap-monitoring
sudo install -o root -g scrap-admin -m 0640 \
  targets/edge/hardware/.env.example \
  /etc/scrap-monitoring/edge.env
```

템플릿 설치 뒤 다음 15개 환경변수를 현장 값으로 설정하거나 확인한다.

| 환경변수 | 설정 또는 확인 값 |
| --- | --- |
| `SITE_ID` | 현장 식별자 |
| `EDGE_ID` | Edge 장비 식별자 |
| `CONFIG_REVISION` | `edge.json`의 승인된 revision |
| `CAMERA_ID` | 연결한 홈캠 식별자 |
| `RUNTIME_DIR` | Edge runtime 경로 |
| `CONFIG_FILE` | 승인된 `edge.json` 경로 |
| `LIDAR_A_IP` | 첫 번째 LiDAR IP |
| `LIDAR_B_IP` | 두 번째 LiDAR IP |
| `MEASUREMENT_URL` | Backend metrics ingest HTTPS endpoint |
| `HEARTBEAT_URL` | Backend heartbeat HTTPS endpoint |
| `MEDIA_WSS_URL` | Camera Media Service WSS endpoint |
| `EDGE_TOKEN_FILE` | 설치한 Edge Platform token 파일 경로 |
| `CAMERA_TOKEN_FILE` | 설치한 Camera Edge token 파일 경로 |
| `EDGE_ROOT_CA_FILE` | 설치한 Root CA 인증서 경로 |
| `CAMERA_DEVICE` | 홈캠 Video4Linux 장치 경로 |

### Server hardware configuration

```bash
sudo install -d -o root -g scrap-admin -m 0750 /etc/scrap-monitoring
sudo install -o root -g scrap-admin -m 0640 \
  targets/server/hardware/.env.example \
  /etc/scrap-monitoring/server.env
```

템플릿 설치 뒤 다음 13개 환경변수를 현장 값으로 설정하거나 확인한다.

| 환경변수 | 설정 또는 확인 값 |
| --- | --- |
| `SERVER_FQDN` | Server TLS 인증서의 DNS 이름 |
| `PKI_ROOT_CA_SHA256` | 별도 기록한 Root CA DER SHA-256 fingerprint |
| `PKI_CA_URL` | host-local `step-ca` endpoint |
| `SERVER_BIND_ADDRESS` | 승인된 TLS 수신 host interface |
| `SERVER_HTTPS_PORT` | 공개 HTTPS port |
| `DASHBOARD_TMPFS_SIZE` | Dashboard writable temporary filesystem 제한 |
| `DASHBOARD_TLS_CERTIFICATE_FILE` | Server certificate chain 경로 |
| `DASHBOARD_TLS_PRIVATE_KEY_FILE` | Server private key 경로 |
| `BACKEND_DATA_PATH` | Backend persistent storage 경로 |
| `BACKEND_CORS_ORIGINS` | 허용할 Browser origin |
| `MEDIA_INGEST_PORT` | Camera Media Service 내부 WSS port |
| `MEDIA_STORAGE_PATH` | Media persistent storage 경로 |
| `MEDIA_MAX_FRAME_BYTES` | binary JPEG frame 최대 byte |

## 빠른 시작

발행된 통합 Release의 Online Package를 대상별로 적용한다.

### Server hardware deployment

```bash
# Replace <release-version> with a published tag, for example v3.6.6.
sudo delivery/quick-start --target server --version "<release-version>"
```

### Edge hardware deployment

```bash
# Replace <release-version> with a published tag, for example v3.6.6.
sudo delivery/quick-start --target edge --version "<release-version>"
```

## 개발 및 검증

```bash
sudo tests/validate-container
```

Validation container에서 Markdown, YAML, Python, Shell, Compose, systemd와 단위 검사를 실행한다.

## 배포

Offline Bundle 적용은 [delivery/offline/README.md](delivery/offline/README.md)을 따른다.

## 문서

| 문서 | 역할 |
| --- | --- |
| [docs/project-spec.md](docs/project-spec.md) | 제품 목적, 범위, 배포 대상과 시나리오 |
| [docs/deployment-contract.md](docs/deployment-contract.md) | 외부 입력, 대상별 동작과 수락 검사 |
| [docs/configuration-management.md](docs/configuration-management.md) | 설정값과 비밀정보의 소유권 및 동기화 |
| [docs/implementation.md](docs/implementation.md) | 채택한 구조, 구현 범위와 component 연동 상태 |
| [docs/pki-operations.md](docs/pki-operations.md) | Private PKI Bootstrap, 인증서 발급과 갱신 |
| [docs/simulation-deployment.md](docs/simulation-deployment.md) | Simulation Server, Visualizer와 Camera Edge Bridge 배포 |

## 이용 조건

> 이 Repository는 코드 검토와 참고를 위해 Public으로 제공하며 프로젝트 소스 코드에 별도 라이선스를 부여하지 않는다.

외부 의존성에는 각 저작권자가 정한 라이선스를 적용한다.
