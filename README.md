# Scrap Monitoring Deployment

스크랩 모니터링 시스템의 Edge와 Server 통합 배포 구성을 관리한다. 기능별 Repository가 제공한
고정 OCI (Open Container Initiative) image digest와 대상별 설정을 하나의 배포 Release로 조합한다.
애플리케이션 소스와 내부 구현은 각 기능별 Repository가 소유한다.

## 의존성

| 의존성 | version |
| --- | --- |
| Docker Engine | `29.8.0` |
| Docker Compose plugin | `5.5.1` |

## 빠른 시작

통합 Release 발행 후 hardware Edge를 구성하고 Online Package를 적용한다.

```bash
target=edge
scenario=hardware
sudo install -D -m 0640 \
  "targets/${target}/${scenario}/.env.example" \
  "/etc/scrap-monitoring/${target}.env"
sudoedit "/etc/scrap-monitoring/${target}.env"
```

```bash
version=v1.2.3
output="/var/tmp/scrap-monitoring-${target}-${scenario}-${version}"
delivery/online/fetch-release \
  --version "${version}" \
  --target "${target}" \
  --scenario "${scenario}" \
  --output "${output}"
sudo delivery/apply-release \
  --version "${version}" \
  --target "${target}" \
  --scenario "${scenario}" \
  --package "${output}/scrap-monitoring-${target}-${scenario}-${version}-online.tar.gz" \
  --checksums "${output}/SHA256SUMS" \
  --mode online
```

Offline Bundle은 [Offline Bundle](delivery/offline/README.md)을 따른다.

## 설정

대상별 schema는 `targets/<target>/<scenario>/.env.example`이다. 실제 값의 소유권과 동기화는
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
