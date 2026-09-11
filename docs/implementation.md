# 배포 구현 결정과 현재 상태

## 현재 상태

GitHub 원격 Repository, 기본 설정, ruleset 4개와 CodeQL Default setup이 구성되어 있다.
Repository에는 문서, 구현 대상 파일 뼈대, CI와 Release workflow가 구성되어 있다. CI는 Markdown,
YAML, GitHub Actions, JSON과 JSON Schema, Docker Compose, Python, Shell, systemd, Release asset,
checksum과 Public 범위를 검사한다. Release workflow는 보호된 version tag, 원격 `main`, version
manifest와 대상별 component를 검증하고 Public GHCR image 취득, asset 생성, Draft Release asset
집합 확인과 게시를 수행한다.

Release asset 생성기는 가상 image archive를 사용하여 Online Package 2개, Offline Bundle 2개와
checksum manifest 1개를 생성하는 경계가 검증되어 있다. 실제 version manifest와 component
image가 없으므로 GHCR image 취득과 GitHub Release 게시는 아직 실행되지 않았다.

Monitoring Server에는 Root CA, Intermediate CA와 `step-ca` 상태가 구성되어 있고 1년 Server
인증서 발급 정책이 검증되어 있다. Edge 장비의 OS trust store와 관리자 MacBook의 System
Keychain에는 운영 Root CA trust가 등록되어 있다. Windows PC의 Client trust 등록, Camera Edge
Agent Container의 Root CA mount, component가 포함된 Docker Compose 정의, Server 인증서를
적용하는 일반 배포와 배포 도구의 실제 동작은 아직 없다. 두 배포 대상 host에는 Docker Engine,
Docker Compose plugin과 containerd가 설치되어 있고 Docker daemon의 부팅 자동 시작과 로그
제한이 구성되어 있다.

## 채택한 구조

| 항목 | 현재 결정 |
| --- | --- |
| Repository 경계 | Edge와 Server를 함께 관리하는 단일 통합 배포 Repository |
| 배포 단위 | 독립적으로 적용 가능한 `edge`와 `server` |
| 목표 상태 | `targets` 아래의 대상별 Docker Compose와 host 연동 |
| 배포 경로 | 같은 목표 상태를 사용하는 Outbound Pull과 Offline Bundle |
| host 수명 주기 | Docker Compose를 시작하고 필수 mount를 확인하는 systemd 경계 |
| host 배포 root | `/srv/scrap-monitoring/deployment` |
| target 환경 파일 | `/etc/scrap-monitoring/edge.env`, `/etc/scrap-monitoring/server.env` |
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
| 비밀정보 | Git과 Release 외부의 대상별 host 설정 |
| 영속 데이터 | container image와 분리한 host storage |
| Private PKI | Monitoring Server의 암호화하지 않은 공유 Root CA와 `step-ca` Intermediate CA를 사용하는 2단계 구조 |
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
|   `-- verify-release
|-- docs/
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
| Root CA 인증서와 암호화하지 않은 개인키 | `/srv/scrap-monitoring/pki/root` | `root:scrap-admin`, directory `0750`, file `0640` |
| Intermediate CA와 `step-ca` 상태 | `/srv/scrap-monitoring/pki/step-ca` | `step-ca` service 전용 쓰기 권한 |
| Server 인증서와 개인키 | `/srv/scrap-monitoring/pki/tls` | TLS service 전용 쓰기 권한 |

Root CA 개인키는 암호화하지 않고 파일 접근 권한으로 보호한다. Intermediate CA 개인키는 별도 암호로
암호화하고 `step-ca`만 읽을 수 있는 Git 외부 secret을 사용해 서비스를 시작한다. 정확한 파일
위치와 Client trust 등록 절차는 [`docs/pki-operations.md`](pki-operations.md)를 따른다.

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

PKI Bootstrap은 `step` CLI 0.30.6을 사용하고 CA 실행 환경은 `step-ca` 0.30.2를 사용한다.

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

- Component image 이름과 Repository별 실행 계약
- Database migration, backup 선행 조건과 rollback 허용 범위
