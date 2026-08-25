# scrap-monitoring-deployment

스크랩 모니터링 시스템의 Edge와 Server 배포 구성을 함께 관리하는 Repository다. 각 기능의
소스 코드는 해당 개발 Repository에서 관리하고, 이 Repository는 호환되는 컴포넌트 버전과
운영 구성을 하나의 배포 버전으로 묶는다.

## 문서

| 문서 | 역할 |
| --- | --- |
| [`docs/project-spec.md`](docs/project-spec.md) | 배포 프로젝트의 목적, 범위와 외부 경계 |
| [`docs/deployment-contract.md`](docs/deployment-contract.md) | 외부 입력과 배포 영역별 기대 동작 |
| [`docs/implementation.md`](docs/implementation.md) | 채택한 배포 구조와 현재 구현 상태 |
| [`docs/pki-operations.md`](docs/pki-operations.md) | Private PKI 수동 구성과 일반 배포 자동화 |

## 디렉토리

| 경로 | 역할 |
| --- | --- |
| `targets/edge` | Raspberry Pi Edge 배포 목표 상태 |
| `targets/server` | 온프레미스 Server 배포 목표 상태 |
| `delivery/online` | 대상 장비가 외부 배포 위치에서 가져오는 Outbound Pull |
| `delivery/offline` | 외부 네트워크 없이 반입하고 적용하는 Offline Bundle |
| `release` | 전체 시스템 배포 버전과 호환 컴포넌트 집합 |
| `pki` | 공개 가능한 PKI 설정 template와 일반 배포의 인증서 자동화 도구 |
| `tests` | Compose, 배포, PKI와 Release 검증 |
| `.github/workflows` | Repository 검증 CI |

## 소스 이용 조건

> 이 Repository는 코드 검토와 참고를 위해 Public으로 제공하며 프로젝트 소스 코드에 별도 라이선스를 부여하지 않는다.
