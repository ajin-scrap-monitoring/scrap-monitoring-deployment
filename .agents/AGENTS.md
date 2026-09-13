# Repository 작업 지침

## 적용 범위

이 파일은 이 Repository에서 작업하는 사람과 코딩 에이전트가 공유하는 지침의 정본이다.
Codex는 `/AGENTS.md` 심링크를 통해 이 파일을 읽는다.

## 문서 체계

프로젝트 문서는 역할 4개로 구분한다.

| 문서 | 역할 |
| --- | --- |
| `docs/project-spec.md` | 배포 제품 명세의 정본 |
| `docs/deployment-contract.md` | 외부 입력과 배포 동작 계약의 정본 |
| `docs/implementation.md` | 채택한 기술, 구조와 현재 구현 상태의 정본 |
| `docs/pki-operations.md` | Private PKI 구성과 인증서 운영 절차의 정본 |

현재 작업 요청과 확인된 외부 계약이 가장 우선한다. 제품 목적, 범위와 경계는
`docs/project-spec.md`, 외부 입력과 구현할 동작은 `docs/deployment-contract.md`, 채택한 구현 결정과
현재 상태는 `docs/implementation.md`를 따른다.
인증서 파일의 역할, 최초 Bootstrap, 일반 배포와 갱신 절차는 `docs/pki-operations.md`를 따른다.
같은 사실은 하나의 정본에만 기록하고 `README.md`는 Repository와 문서의 진입점으로 사용한다.

## 프로젝트 방향

- 기능별 공개 개발 Repository는 검증한 OCI (Open Container Initiative) 컨테이너 이미지를 기본적으로 Public GHCR (GitHub Container Registry) Package로 게시함
- GHCR Package의 기본 공개 범위는 Public이며, Private Package가 필요하면 해당 Repository의 정본에 공개 제한 이유, 읽기 인증과 배포 영향을 기록함
- 기능별 Repository는 Release version에서 파생한 사람이 읽을 수 있는 image tag와 `sha-<full-git-sha>` source revision tag를 사용하고 `latest`를 게시하지 않음
- `release` manifest와 대상 Compose는 image tag가 아닌 `ghcr.io/<organization>/<image>@sha256:<digest>` 형식의 digest 고정 참조를 사용함
- 통합 Release tag는 `vMAJOR.MINOR.PATCH` 형식을 유지하며 digest를 tag 문자열에 결합하지 않음
- 배포 대상 host는 Docker Engine `29.8.0`, Docker Compose plugin `5.5.1`과 containerd `2.3.5`를 사용함
- Docker Buildx는 component CI의 멀티플랫폼 image 빌드에 사용하고 배포 대상 host에는 설치하지 않음
- Docker daemon은 root 권한의 systemd 서비스로 실행하고 사용자를 `docker` 그룹에 추가하지 않으며 애플리케이션 컨테이너는 가능한 경우 비root 사용자로 실행함
- 컨테이너 표준 출력과 표준 오류는 대상별 Docker `local` 로그 제한을 사용하고 애플리케이션이 제한되지 않은 host 파일 로그를 생성하지 않게 함

## 작업 시작

1. `git status`와 관련 파일을 확인하여 기존 변경을 구분한다.
2. `docs/project-spec.md`에서 배포 대상, 지원 경로와 외부 계약을 확인한다.
3. `docs/deployment-contract.md`에서 필요한 입력과 구현할 동작을 확인한다.
4. `docs/implementation.md`에서 채택한 구조, 현재 상태와 미확정 구현 결정을 확인한다.
5. 인증서 관련 작업은 `docs/pki-operations.md`에서 Bootstrap과 반복 배포의 경계를 확인한다.
6. 연동할 component Repository의 실제 source와 배포 계약을 확인한다.

## 변경 원칙

- 현재 작업 범위에 필요한 파일만 변경한다.
- 기존 작업 트리의 사용자 변경을 덮어쓰거나 되돌리지 않는다.
- `targets`의 목표 상태를 Outbound Pull과 Offline Bundle에 복제하지 않는다.
- 일반 배포에서 Root CA 또는 Intermediate CA를 생성하거나 교체하지 않는다.
- CA 상태가 없거나 일치하지 않으면 새 CA를 만들지 않고 배포를 중단한다.
- Edge와 Server의 CPU architecture, host storage와 network 경계를 혼합하지 않는다.
- component source 구현을 이 Repository에 복제하지 않는다.
- 자격 증명, 인증서 개인키, 사설 주소, 현장 데이터와 공개할 수 없는 asset을 포함하지 않는다.
- 제품 의존성, 도구와 배포 구성을 채택하면 version, 목적, 출처, license와 현재 상태를
  `docs/implementation.md`에 반영한다.
- 요구사항이나 외부 계약이 변경되면 확인된 결정만 `docs/project-spec.md`에 반영한다.

## 검증과 인계

변경 범위에 맞는 format 검사, Compose 구성 검사, script 정적 검사, Bundle checksum 검사와
대상 architecture 검사를 수행한다. 구현되지 않은 검증 단계를 대체 명령으로 통과한 것으로
간주하지 않는다.

Docker와 Compose의 실행 실험은 배포 대상 장비가 아닌 별도 Ubuntu test host에서 수행한다.

완료된 구현 상태와 재현 방법은 `docs/implementation.md`에 기록한다. 작업 중인 상태와 다음
행동은 현재 작업 요청, GitHub Issue 또는 Pull Request (PR)에서 관리한다.

## Git 작업

- 변경 전후에 `git status`와 `git diff`를 확인한다.
- 명시적인 요청 없이 commit, push, tag, Release 또는 원격 설정 변경을 수행하지 않는다.
- 명시적인 요청 없이 branch를 전환하거나 기존 변경을 삭제하지 않는다.
- commit과 PR에 코딩 에이전트가 작성했다는 metadata를 추가하지 않는다.

## 문서 작성

- 현재 반영된 사실과 채택한 결정만 기록한다.
- 과거 수정 과정, 폐기한 대안과 작업 일지를 남기지 않는다.
- 설명 중심 문서는 서술식으로 작성하고 본문 문장은 마침표로 끝낸다.
- 목록과 표 셀은 명사구를 기본으로 사용한다.
- 약어는 처음 사용할 때 전체 이름을 함께 적는다.
