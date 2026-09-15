# Release delivery

이 디렉토리는 배포 asset 검증과 적용, 애플리케이션 인증 정보 수명 주기 도구를 제공한다.

인증 정보 도구는 4개다.

| 실행 파일 | 역할 |
| --- | --- |
| `generate-auth-secret` | 256-bit opaque token과 metadata bundle 생성 |
| `install-auth-secret` | Edge 원문 token 또는 Server digest 설치와 rotation 중첩 |
| `retire-auth-secret` | 연결 확인을 마친 이전 Server digest 폐기 |
| `validate-auth-secrets` | 대상별 인증 파일, 식별자, digest와 권한 검증 |

Credential bundle은 원문 token을 포함하므로 Git과 Release 경로 밖의 접근 제한된 디렉토리에서
관리한다. 명령은 token 값을 argument나 출력으로 전달하지 않는다. 최초 설치와 rotation 순서는
[`docs/configuration-management.md`](../docs/configuration-management.md)의 비밀정보 절을 따른다.

일반 Release 적용은 인증 정보를 생성하거나 회전하지 않는다. 대상별 systemd unit은 Docker
Compose 시작 전에 `validate-auth-secrets`를 실행하며 파일이 없거나 일치하지 않으면 시작을
중단한다.
