# 배포 구현 결정과 현재 상태

## 현재 상태

GitHub 원격 Repository, 기본 설정, ruleset 4개와 CodeQL Default setup이 구성되어 있다.
Repository에는 문서, 구현 대상 파일 뼈대, CI와 Release workflow가 구성되어 있다. CI는 Markdown,
YAML, GitHub Actions, JSON과 JSON Schema, Docker Compose, Python, Shell, systemd, Release asset,
checksum과 Public 범위를 검사한다. Release workflow는 보호된 version tag, 원격 `main`, version
manifest와 대상별 component를 검증하고 Public GHCR image 취득, asset 생성, Draft Release asset
집합 확인과 게시를 수행한다.

환경설정은 Release 설정, 장비 환경설정, Component 설정, 비밀정보와 PKI 상태로 분리되어 있다.
대상별 `.env.example`은 공개 schema이고 실제 값은 대상 장비의 Git 외부 파일에서 관리한다.
`delivery/validate-environment`는 실제 값을 출력하지 않고 schema version, 변수 집합과 빈 값을
검사한다. systemd unit은 실제 환경 파일, Release에서 생성한 `release.env`와 Edge generated
environment 파일을 Compose 실행 환경으로 사용한다.

Edge별 Backend Bearer token과 Camera별 Camera Media Service Bearer token은 배포 도구가 생성하고
rotation하는 독립된 opaque secret으로 관리한다. 배포 도구는 256-bit token bundle 생성, Edge
원문 token 설치, Server SHA-256 digest registry 설치, 2개 digest 중첩 rotation과 이전 digest
폐기를 구현한다. 대상별 systemd unit은 Compose 시작 전에 인증 파일을 검증한다.

`delivery/online/fetch-release`, `delivery/offline/import-bundle`, `delivery/verify-release`,
`delivery/apply-release`와 PKI 실행 파일 3개는 명령 계약만 유지하는 stub이다. Stub은 `--help`만
성공하고 실제 실행은 미구현 오류로 종료하므로 현재 Repository만으로 end-to-end 배포를 수행할
수 없다. `delivery/offline/build-bundle`은 `release/build-assets`와 책임이 중복된 stub이며 배포
실행 계약에 포함하지 않는다.

Release asset 생성기는 가상 image archive를 사용하여 Online Package 2개, Offline Bundle 2개와
checksum manifest 1개를 생성하는 경계가 검증되어 있다. Edge Platform `v0.1.1`의 ARM64 image
5개와 Dashboard `v0.1.2`의 AMD64 image 1개가 GHCR에 존재한다. Backend와 Camera Media Service는
배포 Release image를 제공하지 않으므로 실제 통합 version manifest와 Release는 없다.

Monitoring Server에는 Root CA 인증서, Intermediate CA와 `step-ca` 상태가 구성되어 있고 1년 Server
인증서 발급 정책이 검증되어 있다. Edge 장비의 OS trust store와 관리자 MacBook의 System
Keychain에는 운영 Root CA trust가 등록되어 있다. Windows PC의 Client trust 등록, Camera Edge
Agent Container의 Root CA mount, component가 포함된 Docker Compose 정의, Server 인증서를
적용하는 일반 배포와 배포 도구의 실제 동작은 아직 없다. 두 배포 대상 host에는 Docker Engine,
Docker Compose plugin과 containerd가 설치되어 있고 Docker daemon의 부팅 자동 시작과 로그
제한이 구성되어 있다.

## Component 연동 상태

| Component | 확인된 계약 | 미완료 사항 |
| --- | --- | --- |
| Edge Platform | `v0.1.1`, ARM64 image 5개, UDS 처리, HTTPS 측정과 heartbeat, WSS Camera, file token과 Compose 예제 | Private Package 예외, read-only pull 인증, secret 소유권, Root CA 입력과 현장 검증 |
| Backend | AMD64 Dockerfile, `/api/v1/metrics/ingest`, `X-Edge-API-Key`, health와 readiness, Browser session API | Release image, Bearer digest registry, Edge schema, 멱등 ACK, heartbeat, 운영 DB와 인증 강화 |
| Camera Media Service | AMD64 Dockerfile, Camera별 Bearer 인증, 원문 token JSON 환경변수와 binary JPEG WebSocket ingest | Release image, digest registry file, health, Browser 전달, 녹화와 운영 검증 |
| Dashboard Nginx | `v0.1.2` Public AMD64 image, 정적 파일, health, TLS와 runtime reverse proxy 설정 입력 | 승인된 Backend API, SSE, WHEP, upstream, timeout과 CSP 계약 |

Backend의 현재 인증, 요청 본문과 response는 Edge Platform 전송 계약과 일치하지 않는다.
Heartbeat endpoint는 Backend에 존재하지 않는다. Backend Browser session은 기본 사용자,
process memory 저장과 누락을 허용하는 Cross-Site Request Forgery (CSRF) 검사 때문에 운영 계약으로
사용할 수 없다. Camera Media Service는 Backend 직접 연결 설정에 빈 값만 허용하고 배포 도구가
생성하는 digest registry를 읽지 않는다.

Edge Platform의 5개 GHCR Package는 모두 Private이다. Organization 정책은 Public Package를
기본으로 사용하고 배포 제한이 있는 경우에만 사유와 인증 경계를 기록하도록 요구한다. 현재
Component 문서는 Private 사용 절차만 기록하고 배포 제한 사유를 확정하지 않으므로 배포
Repository는 해당 image를 통합 Release에 포함하지 않는다.

## 채택한 구조

| 항목 | 현재 결정 |
| --- | --- |
| Repository 경계 | Edge와 Server를 함께 관리하는 단일 통합 배포 Repository |
| 배포 단위 | 독립적으로 적용 가능한 `edge`와 `server` |
| 목표 상태 | `targets` 아래의 대상별 Docker Compose와 host 연동 |
| 배포 경로 | 같은 목표 상태를 사용하는 Outbound Pull과 Offline Bundle |
| host 수명 주기 | Docker Compose를 시작하고 필수 mount를 확인하는 systemd 경계 |
| host 배포 root | `/srv/scrap-monitoring/deployment` |
| Version 경로 | `/srv/scrap-monitoring/deployment/versions/<version>` |
| 활성 Version | `/srv/scrap-monitoring/deployment/current` symlink |
| 이전 Version | `/srv/scrap-monitoring/deployment/previous` symlink |
| 적용 상태 | `/srv/scrap-monitoring/deployment/state/<target>.json` |
| 배포 lock | `/run/lock/scrap-monitoring-deployment.lock` |
| target 환경 파일 | `/etc/scrap-monitoring/edge.env`, `/etc/scrap-monitoring/server.env` |
| Release 환경 파일 | Manifest에서 생성한 대상별 `release.env` |
| Edge 파생 설정 | Component 설정에서 생성한 `CONFIG_SHA256` |
| 환경설정 검증 | 공개 schema와 실제 파일의 version, 변수 집합과 빈 값 비교 |
| 버전 해석 | 통합 Release manifest가 고정한 대상별 component image 집합 |
| Release manifest 형식 | JSON 문서와 JSON Schema |
| Container registry | GitHub Container Registry (GHCR) |
| Component image 식별 | `ghcr.io` image의 SHA-256 digest |
| Component image 공개 범위 | Public GHCR Package 기본, 정본에 예외를 기록한 경우에만 Private |
| Release image 인증 | Public Package pull은 무인증, Private 예외는 최소 read-only 자격 증명 |
| Image tag 정책 | Release version tag와 `sha-<full-git-sha>` source revision tag, `latest` 미사용 |
| 배포 image 참조 | `ghcr.io/<organization>/<image>@sha256:<digest>` |
| Release archive 형식 | `.tar.gz` |
| 구현 언어 | Release asset 생성과 검증은 Python 3.10 이상, host 적용 도구는 Bash |
| 애플리케이션 인증 | Edge별 Backend token과 Camera별 Media token을 사용하는 Bearer 인증 |
| Token 수명 주기 | 배포 도구가 credential Bootstrap과 명시적 rotation에서 생성 및 설치 |
| Token Server 저장 | 식별자별 SHA-256 digest 1개, rotation 중 최대 2개 |
| 내부 service 인증 | UDS 권한 또는 private Compose network, 공유 Bearer token 미사용 |
| Browser 인증 | TLS, Backend 사용자 session과 CSRF 보호, reverse proxy 공용 token 미사용 |
| Docker Compose secret | Service별 file secret 연결, host 파일 권한을 저장 보호 경계로 사용 |
| 비밀정보 | Git과 Release 외부의 대상별 host 파일 |
| 영속 데이터 | container image와 분리한 host storage |
| Private PKI | 오프라인 Root CA와 Monitoring Server의 `step-ca` Intermediate CA를 사용하는 2단계 구조 |
| PKI 실행 경계 | 수동 Bootstrap 및 Client trust 등록과 일반 배포가 자동화하는 Server 인증서 발급 및 갱신 |
| CA 내부 연결 | Compose network의 `https://step-ca:9000` |
| Server 인증서 발급 | `deployment` JWK Provisioner와 환경별 Server FQDN 1개 |

## 디렉토리 구조

```text
scrap-monitoring-deployment/
|-- .agents/
|   `-- AGENTS.md
|-- .github/
|   `-- workflows/
|       |-- ci.yml
|       `-- release.yml
|-- .markdownlint-cli2.jsonc
|-- .yamllint.yml
|-- delivery/
|   |-- offline/
|   |   |-- build-bundle
|   |   `-- import-bundle
|   |-- online/
|   |   `-- fetch-release
|   |-- apply-release
|   |-- generate-auth-secret
|   |-- install-auth-secret
|   |-- retire-auth-secret
|   |-- validate-auth-secrets
|   |-- validate-environment
|   `-- verify-release
|-- docs/
|   |-- configuration-management.md
|   |-- deployment-contract.md
|   |-- implementation.md
|   |-- pki-operations.md
|   `-- project-spec.md
|-- pki/
|   |-- config/
|   |   `-- ca.template.json
|   |-- systemd/
|   |   |-- scrap-monitoring-certificate-renewal.service
|   |   `-- scrap-monitoring-certificate-renewal.timer
|   |-- ensure-server-certificate
|   |-- validate-ca-state
|   `-- verify-server-certificate
|-- release/
|   |-- manifests/
|   |   `-- README.md
|   |-- build-assets
|   |-- manifest.example.json
|   |-- manifest.schema.json
|   |-- pull-images
|   |-- release_manifest.py
|   `-- validate-manifest
|-- targets/
|   |-- edge/
|   |   |-- config/
|   |   |-- systemd/
|   |   |   `-- scrap-monitoring-edge.service
|   |   |-- .env.example
|   |   `-- compose.yaml
|   `-- server/
|       |-- config/
|       |-- systemd/
|       |   `-- scrap-monitoring-server.service
|       |-- .env.example
|       `-- compose.yaml
|-- tests/
|   |-- compose/
|   |-- delivery/
|   |-- pki/
|   |-- release/
|   |-- systemd/
|   |-- test_auth_secrets.py
|   |-- test_configuration.py
|   |-- test_entrypoints.py
|   |-- test_public_content.py
|   |-- test_release.py
|   |-- test_repository.py
|   `-- validate-repository
|-- AGENTS.md
|-- .gitignore
|-- requirements-tooling.txt
`-- README.md
```

`targets`는 배포 경로와 무관한 목표 상태의 정본이다. `delivery`는 목표 상태를 대상 장비에
전달하고 적용하는 방법만 관리한다. `release`는 두 대상의 호환 가능한 image와 asset 구성을
하나의 배포 버전으로 묶는다. `pki`는 Private PKI의 공개 가능한 설정 template, 수동 Bootstrap
절차와 일반 배포의 인증서 발급, 갱신 및 검증 자동화 도구를 관리하며 실제 CA 상태와 개인키를
포함하지 않는다.

## Release asset 이름

| asset | 파일 이름 |
| --- | --- |
| Edge Online Package | `scrap-monitoring-edge-<version>-online.tar.gz` |
| Server Online Package | `scrap-monitoring-server-<version>-online.tar.gz` |
| Edge Offline Bundle | `scrap-monitoring-edge-<version>-offline.tar.gz` |
| Server Offline Bundle | `scrap-monitoring-server-<version>-offline.tar.gz` |
| Checksum manifest | `SHA256SUMS` |

## PKI host 경로

| 상태 | host 경로 | 접근 기준 |
| --- | --- | --- |
| Root CA 인증서와 fingerprint | `/srv/scrap-monitoring/pki/root` | `root:scrap-admin`, directory `0750`, file `0640` |
| Intermediate CA와 `step-ca` 상태 | `/srv/scrap-monitoring/pki/step-ca` | `step-ca` service 전용 쓰기 권한 |
| Server 인증서와 개인키 | `/srv/scrap-monitoring/pki/tls` | TLS service 전용 쓰기 권한 |

Root CA 개인키는 암호화하여 Monitoring Server 밖의 오프라인 저장소에 보관한다. Intermediate CA
개인키는 별도 암호로 암호화하고 `step-ca`만 읽을 수 있는 Git 외부 secret을 사용해 서비스를
시작한다. 정확한 파일 위치와 Client trust 등록 절차는
[`docs/pki-operations.md`](pki-operations.md)를 따른다.

## 채택한 PKI 도구

| 도구 | 현재 상태 | 목적 | 출처 | license |
| --- | --- | --- | --- | --- |
| `step` CLI | `0.30.6` | CA 초기화, trust Bootstrap, Server 인증서 요청과 갱신 | [`smallstep/cli`](https://github.com/smallstep/cli) | Apache-2.0 |
| `step-ca` | `0.30.2` | Intermediate CA를 이용한 Server 인증서 발급 서비스 | [`smallstep/certificates`](https://github.com/smallstep/certificates) | Apache-2.0 |

## 대상 host runtime

두 배포 대상은 Docker 공식 APT 저장소의 Docker Engine `29.8.0`, Docker Compose plugin `5.5.1`과
containerd `2.3.5`를 사용한다. 설치 패키지는 `docker-ce`, `docker-ce-cli`, `containerd.io`와
`docker-compose-plugin`이며 Docker 공식 APT 저장소에서 취득한다. Docker daemon은 root 권한의
systemd 서비스로 실행하며 대상 사용자를 `docker` 그룹에 추가하지 않는다. Docker Buildx는
기능별 Repository CI의 멀티플랫폼 image 빌드에 사용하고 대상 host에는 설치하지 않는다.

서버의 Docker 컨테이너 로그는 `local` driver와 `20m` `max-size`, `5` `max-file`을 사용한다.
엣지는 `local` driver와 `10m` `max-size`, `3` `max-file`을 사용한다. systemd 저널은 서버가
최대 `1G`와 14일, 엣지가 최대 `256M`와 7일로 제한한다.

## 직접 의존성

| 도구 | 지원 version | 목적 | 출처 | license |
| --- | --- | --- | --- | --- |
| Bash | `5.1` 이상 | Host 배포와 인증 정보 도구 실행 | [GNU Bash](https://www.gnu.org/software/bash/) | GPL-3.0-or-later |
| GNU Coreutils | `8.32` 이상 | CSPRNG byte 변환, file 설치, digest와 권한 처리 | [GNU Coreutils](https://www.gnu.org/software/coreutils/) | GPL-3.0-or-later |
| `jq` | `1.6` 이상 | Credential metadata와 digest registry 검증 및 갱신 | [jqlang](https://jqlang.org/) | MIT |
| `flock` | util-linux `2.37` 이상 | Server digest registry 갱신 직렬화 | [util-linux](https://github.com/util-linux/util-linux) | GPL-2.0-or-later |
| `step` CLI | `0.30.6` | PKI Bootstrap, Server 인증서 요청과 갱신 | [`smallstep/cli`](https://github.com/smallstep/cli) | Apache-2.0 |
| `step-ca` | `0.30.2` | Intermediate CA를 이용한 Server 인증서 발급 | [`smallstep/certificates`](https://github.com/smallstep/certificates) | Apache-2.0 |

## CI와 Release 도구

| 도구 | 버전 | 목적 | 출처 | license |
| --- | --- | --- | --- | --- |
| `actions/checkout` | `v6` | GitHub Actions의 Repository checkout | [`actions/checkout`](https://github.com/actions/checkout) | MIT |
| Actionlint | `1.7.12` | GitHub Actions workflow 정적 검사 | [`rhysd/actionlint`](https://github.com/rhysd/actionlint) | MIT |
| Docker Engine | GitHub-hosted runner 제공 version | 대상별 GHCR image pull과 archive 생성 | [Moby](https://github.com/moby/moby) | Apache-2.0 |
| Go | GitHub-hosted runner 제공 version | Actionlint 실행 | [Go](https://go.dev/) | BSD-3-Clause |
| Node.js | GitHub-hosted runner 제공 version | Markdown 검사 도구 실행 | [Node.js](https://nodejs.org/) | MIT |
| Python | `3.10` 이상 | Release asset 생성과 Repository 테스트 | [Python](https://www.python.org/) | PSF-2.0 |
| `jsonschema` | `4.26.0` | Release manifest JSON Schema 검증 | [PyPI](https://pypi.org/project/jsonschema/) | MIT |
| Ruff | `0.16.4` | Python lint와 format 검사 | [PyPI](https://pypi.org/project/ruff/) | MIT |
| `markdownlint-cli2` | `0.23.2` | Markdown 검사 | [npm](https://www.npmjs.com/package/markdownlint-cli2) | MIT |
| `yamllint` | `1.38.0` | YAML 검사 | [PyPI](https://pypi.org/project/yamllint/) | GPL-3.0 |
| `jq` | GitHub-hosted runner 제공 version | JSON 문법 검사 | [jqlang](https://jqlang.org/) | MIT |
| Docker Compose | GitHub-hosted runner 제공 version | Compose schema 검사 | [Docker Compose](https://github.com/docker/compose) | Apache-2.0 |
| GitHub CLI | GitHub-hosted runner 제공 version | Draft Release 생성, asset 첨부와 게시 | [GitHub CLI](https://github.com/cli/cli) | MIT |
| ShellCheck | GitHub-hosted runner 제공 version | Bash 정적 검사 | [ShellCheck](https://github.com/koalaman/shellcheck) | GPL-3.0 |
| `systemd-analyze` | GitHub-hosted runner 제공 version | systemd unit 검사 | [systemd](https://github.com/systemd/systemd) | LGPL-2.1-or-later |

## 미확정 구현 결정

- Edge Platform Private Package의 예외 승인 또는 Public 전환
- Secret file과 non-root Component UID 사이의 소유권 및 mode
- 실제 Release manifest에 포함할 Backend와 Camera Media Service image digest
- Backend의 Edge measurement 저장 변환과 heartbeat 상태 model
- Backend의 운영 Database version, migration과 session 저장 방식
- Camera Media Service의 Browser 전달 방식
- Database migration, backup 선행 조건과 rollback 허용 범위
