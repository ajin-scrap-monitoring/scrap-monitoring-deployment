# Release delivery

이 디렉토리는 배포 asset 검증과 적용, 애플리케이션 인증 정보 수명 주기 도구를 제공한다.

`install-container-runtime`은 대상 host의 배포 의존성을 설치하고 version을 검증한다.
`install-environment`는 대상과 시나리오의 환경 파일을 설치하거나 기존 파일을 보존하고 검증한다.
환경 파일의 소유권과 동기화는
[docs/configuration-management.md](../docs/configuration-management.md)를 따른다.

Dashboard 설정 도구는 2개다.

| 실행 파일 | 역할 |
| --- | --- |
| `install-dashboard-configuration` | Server runtime JSON 최초 설치 또는 같은 식별자의 기존 파일 보존과 검증 |
| `validate-dashboard-configuration` | 설치한 JSON, 접근 권한과 선택적 expected 식별자 검증 |

설치 명령과 설정값은 [docs/configuration-management.md](../docs/configuration-management.md)의
Dashboard 설정을 따른다. 실제 Compose 연결 상태는
[docs/implementation.md](../docs/implementation.md)를 따른다.

`verify-release`는 Package checksum과 archive 안전성을 검증하고 Package descriptor와
Manifest의 version, target, scenario, mode, platform과 digest를 교차 검증한다.

`apply-release`는 검증된 Package에서 실행 payload를 시나리오를 포함한 불변 Version 경로로 staging하고 Manifest
기반 release.env와 Edge CONFIG_SHA256을 생성한다. 환경설정, secret, image, Compose와 Server
인증서를 확인한 뒤 current 및 previous link를 전환하고 systemd를 시작한다. 시작 또는 Compose
실행 상태 확인이 실패하면 이전 link, Edge 파생 설정과 Server 인증서를 복구한다.

`quick-start`는 대상 환경 파일이 준비된 host에서 Online Package 취득, 적용과 systemd active 상태
확인을 하나의 명령으로 수행한다. 기본 시나리오는 `hardware`다.

인증 정보 도구는 4개다.

| 실행 파일 | 역할 |
| --- | --- |
| `generate-auth-secret` | 256-bit opaque token과 metadata bundle 생성 |
| `install-auth-secret` | 전용 읽기 그룹, Edge 원문 token 또는 Server digest 설치와 rotation 중첩 |
| `retire-auth-secret` | 연결 확인을 마친 이전 Server digest 폐기 |
| `validate-auth-secrets` | 대상별 인증 파일, 식별자, digest와 권한 검증 |

Credential bundle은 원문 token을 포함하므로 Git과 Release 경로 밖의 접근 제한된 디렉토리에서
관리한다. 명령은 token 값을 argument나 출력으로 전달하지 않는다. 최초 설치와 rotation 순서는
[`docs/configuration-management.md`](../docs/configuration-management.md)의 비밀정보 절을 따른다.

일반 Release 적용은 인증 정보를 생성하거나 회전하지 않는다. 대상별 systemd unit은 Docker
Compose 시작 전에 `validate-auth-secrets`를 실행하며 파일이 없거나 일치하지 않으면 시작을
중단한다.
