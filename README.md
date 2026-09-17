# Scrap Monitoring Deployment

스크랩 모니터링 시스템의 Edge와 Server 통합 배포 구성을 관리한다. 기능별 Repository가 제공한
고정 OCI (Open Container Initiative) image digest와 대상별 설정을 하나의 배포 Release로 조합한다.
애플리케이션 소스와 내부 구현은 각 기능별 Repository가 소유한다.

## 빠른 시작

Docker Compose, ShellCheck, systemd-analyze, uv, Node.js, npm과 Go를 설치한 뒤 Repository 루트에서
검증 환경을 구성하고 전체 검사를 실행한다. `tools/install-validation`은 지원하는 정확한 도구 version을
검사한다.

```bash
tools/install-validation
tests/validate-repository
```

## 설정

실제 환경설정, token, 인증서 개인키와 현장 주소는 Git과 Release asset에 포함하지 않는다. 대상별
공개 schema는 `targets/<target>/<scenario>/.env.example`이고, 소유권과 동기화는
[환경설정 관리](docs/configuration-management.md)를 따른다.

## 문서

| 문서 | 역할 |
| --- | --- |
| [프로젝트 명세](docs/project-spec.md) | 제품 목적, 범위, 배포 대상과 시나리오 |
| [배포 계약](docs/deployment-contract.md) | 외부 입력, 대상별 동작과 수락 검사 |
| [환경설정 관리](docs/configuration-management.md) | 설정값과 비밀정보의 소유권 및 동기화 |
| [구현 상태](docs/implementation.md) | 채택한 구조, 구현 범위와 component 연동 상태 |
| [PKI 운영](docs/pki-operations.md) | Private PKI Bootstrap, 인증서 발급과 갱신 |

## 소스 이용 조건

> 이 Repository는 코드 검토와 참고를 위해 Public으로 제공하며 프로젝트 소스 코드에 별도 라이선스를 부여하지 않는다.
