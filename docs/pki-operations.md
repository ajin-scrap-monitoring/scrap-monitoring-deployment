# Private PKI 운영 절차

## 적용 범위

이 문서는 Monitoring Server가 제공하는 HTTPS와 WebSocket Secure (WSS)의 인증서 chain을
관리한다. WebRTC의 Datagram Transport Layer Security (DTLS) 인증서와 개인키는 Browser와
Camera Media Service runtime이 별도로 관리하므로 이 절차에 포함하지 않는다.

## 도구

인증서 관리 도구는 2개다.

| 도구 | 형태 | 책임 |
| --- | --- | --- |
| `step` | Command-Line Interface (CLI) | CA 초기화, trust Bootstrap, 인증서 요청과 갱신 |
| `step-ca` | CA Server | Intermediate CA 개인키를 사용한 Server 인증서 발급 |

## 확정 설정

| 항목 | 설정 |
| --- | --- |
| CA 이름 | `Scrap Monitoring CA` |
| Root CA 이름 | `Scrap Monitoring Root CA` |
| Intermediate CA 이름 | `Scrap Monitoring Intermediate CA` |
| CA 내부 URL | `https://step-ca:9000` |
| 발급 Provisioner | `deployment` JSON Web Key (JWK) |
| Key 알고리즘 | Elliptic Curve (EC) P-256 |
| Server 발급 범위 | 환경별 Server Fully Qualified Domain Name (FQDN) 1개 |
| 유효기간 | Root 10년, Intermediate 5년, Server 1년 |
| Server 갱신 시점 | 유효기간의 3분의 2 경과 시점 |

## 인증서 파일

핵심 파일은 6개다.

| 파일 | 공개 여부 | 소유 위치 | 책임 |
| --- | --- | --- | --- |
| `root_ca_key` | 비밀 | Monitoring Server의 공유 Root 상태 | Intermediate CA 인증서 서명 |
| `root_ca.crt` | 공개 | CA, Edge, Server와 관리자 컴퓨터 | 인증서 chain의 최상위 trust 기준 |
| `intermediate_ca_key` | 비밀 | Monitoring Server의 `step-ca` 영속 상태 | Server 인증서 서명 |
| `intermediate_ca.crt` | 공개 | Monitoring Server의 `step-ca`와 TLS chain | Root CA가 승인한 발급자 증명 |
| `server.key` | 비밀 | Monitoring Server의 TLS 영속 상태 | HTTPS와 WSS Server 소유권 증명 |
| `server.crt` | 공개 | Monitoring Server의 TLS 영속 상태 | Server 이름과 공개키 증명 |

검증 chain은 다음과 같다.

```text
Trusted root_ca.crt
-> verifies intermediate_ca.crt
-> verifies server.crt
-> verifies Server owns server.key
```

Root CA는 `root_ca_key`와 `root_ca.crt`로 구성한 최상위 Certificate Authority (CA)다.
Intermediate CA는 `intermediate_ca_key`와 `intermediate_ca.crt`로 구성한 실제 발급자다.
`step-ca`는 Root CA 개인키를 보유하지 않고 Intermediate CA 개인키로 Server 인증서를 발급한다.

## Monitoring Server 파일 배치

PKI 영속 상태는 3개 경로로 분리한다.

| 경로 | 내용 | 접근 기준 |
| --- | --- | --- |
| `/srv/scrap-monitoring/pki/root` | `root_ca.crt`, `root_ca.sha256`, 암호화하지 않은 `root_ca_key` | `root:scrap-admin`, directory `0750`, file `0640` |
| `/srv/scrap-monitoring/pki/step-ca` | Root CA 인증서 사본, Intermediate CA 상태, CA 설정과 database | `step-ca` service 전용 권한 |
| `/srv/scrap-monitoring/pki/tls` | `server.crt`, `server.key`와 인증서 chain | TLS service 전용 쓰기 권한 |

`step-ca` 상태는 `STEPPATH=/srv/scrap-monitoring/pki/step-ca`를 기준으로 7개 항목을 사용한다.

| 항목 | host 경로 | 접근 기준 |
| --- | --- | --- |
| Root CA 인증서 사본 | `/srv/scrap-monitoring/pki/step-ca/certs/root_ca.crt` | `step-ca` service 계정, file `0644` |
| Intermediate CA 인증서 | `/srv/scrap-monitoring/pki/step-ca/certs/intermediate_ca.crt` | `step-ca` service 계정, file `0644` |
| 암호화된 Intermediate CA 개인키 | `/srv/scrap-monitoring/pki/step-ca/secrets/intermediate_ca_key` | `step-ca` service 계정, file `0600` |
| Intermediate CA 암호 | `/srv/scrap-monitoring/pki/step-ca/secrets/intermediate_ca_password` | `step-ca` service 계정, file `0600` |
| Provisioner 암호 | `/srv/scrap-monitoring/pki/step-ca/secrets/provisioner_password` | `step-ca` service 계정, file `0600` |
| CA 설정 | `/srv/scrap-monitoring/pki/step-ca/config/ca.json` | `step-ca` service 계정, file `0640` |
| CA database | `/srv/scrap-monitoring/pki/step-ca/db` | `step-ca` service 계정, directory `0700` |

`step-ca`는 Intermediate CA 암호를 Container의 `/run/secrets/step_ca_password`에 읽기 전용으로
연결하고 `--password-file`로 사용한다. 일반 배포는 Provisioner 암호로 최초 Server
인증서 발급을 인가한다. Root CA 개인키는 `step-ca` 경로에 복사하지 않는다.

`scrap-admin` 구성원은 `/srv/scrap-monitoring/pki/root/root_ca.crt`, `root_ca.sha256`와 암호화하지
않은 `/srv/scrap-monitoring/pki/root/root_ca_key`를 읽을 수 있다. Root CA 개인키가 권한 없는 주체에게
노출되거나 무단 서명이 의심되면 기존 Root CA의 사용을 중단하고 새 Root CA를 생성한 뒤
Edge와 관리자 컴퓨터의 trust를 교체한다.

## Client Root CA 배치

Root CA trust가 필요한 Client 범위는 4개다.

| 범위 | Root CA 인증서 위치 | 적용 위치 |
| --- | --- | --- |
| Edge host | `/usr/local/share/ca-certificates/scrap-monitoring-root-ca.crt` | `/etc/ssl/certs/ca-certificates.crt`에 반영되는 OS trust store |
| Camera Edge Agent Container | `/run/scrap-monitoring/pki/root_ca.crt` | Edge host 인증서의 읽기 전용 mount와 WSS Client TLS 설정 |
| 관리자 MacBook | `/Users/<account>/Library/Application Support/Scrap Monitoring/PKI/root_ca.crt` | macOS System Keychain의 Root trust |
| 관리자 Windows PC | `C:\ProgramData\Scrap Monitoring\PKI\root_ca.crt` | Local Computer의 Trusted Root Certification Authorities |

Edge host의 Root CA 인증서는 `root:root`, file `0644`로 관리한다. 관리자 MacBook과 Windows
PC의 원본 파일은 해당 운영체제의 application data 경로에 보관한다. Root CA 인증서는 공개
정보이며 Client에는 Root CA 개인키나 Intermediate CA 인증서를 배치하지 않는다. Monitoring
Server의 TLS 종단이 Server 인증서와 Intermediate CA 인증서를 chain으로 제공한다.

## 작업 구분

인증서 관리 영역은 2개다.

| 영역 | 실행 방식 | 범위 |
| --- | --- | --- |
| 수동 구성 | 운영자의 직접 실행 | PKI Bootstrap과 Client Root CA trust 등록 |
| 일반 배포 자동화 | 최초 및 후속 배포의 자동 실행 | Server 인증서 발급, 적용, 갱신과 Container trust 연결 |

## PKI Bootstrap

PKI Bootstrap은 환경별 최초 1회 직접 수행하는 수동 절차다.

1. 운영자가 Server FQDN을 확인하고 해당 이름만 Server 인증서로 발급하도록 CA 정책에 설정한다.
2. 운영자가 EC P-256 Key를 사용하여 10년 Root CA 인증서와 암호화하지 않은 개인키를 생성한다.
3. 운영자가 EC P-256 Key를 사용하여 5년 Intermediate CA 인증서와 암호화한 개인키를 생성한다.
4. 운영자가 `deployment` JWK Provisioner, 1년 Server 인증서 정책과 `https://step-ca:9000` 내부 URL을 `ca.json`에 설정한다.
5. 운영자가 Root CA 인증서의 Secure Hash Algorithm 256-bit (SHA-256) fingerprint를 출력하여 별도 위치에 기록한다.
6. 운영자가 Root CA 인증서와 암호화하지 않은 Root CA 개인키를 `/srv/scrap-monitoring/pki/root`에 설치하고 `root:scrap-admin`, directory `0750`, file `0640` 권한을 적용한다.
7. 운영자가 `step-ca` 상태 7개 항목을 `/srv/scrap-monitoring/pki/step-ca`에 설치한다.
8. 운영자가 `step-ca`를 시작하고 CA health와 인증서 chain을 확인한다.

## Client Root CA trust 등록

Client Root CA trust 등록은 Root CA 인증서의 생성과 fingerprint 확인이 끝나면 수행할 수 있다.

### Edge Device

Edge에서는 Root CA 인증서의 fingerprint를 기록값과 대조한 뒤 다음 순서로 등록한다.

1. 운영자가 Root CA 인증서를 `/usr/local/share/ca-certificates/scrap-monitoring-root-ca.crt`에 `root:root`, file `0644`로 설치한다.
2. 운영자가 `update-ca-certificates`를 실행하여 Edge OS trust store에 반영한다.

### macOS

관리자 MacBook에서는 Root CA 인증서의 fingerprint를 기록값과 대조한 뒤 다음 순서로 등록한다.

1. 운영자가 Root CA 인증서를 `/Users/<account>/Library/Application Support/Scrap Monitoring/PKI/root_ca.crt`에 보관한다.
2. 운영자가 Keychain Access에서 System Keychain을 선택하고 Root CA 인증서를 가져온다.
3. 운영자가 Root CA 인증서의 Trust를 `Always Trust`로 설정하고 macOS 관리자 인증을 완료한다.

### Windows와 Chrome

Windows PC에서는 Root CA 인증서의 fingerprint를 기록값과 대조한 뒤 다음 순서로 등록한다.

1. 운영자가 Root CA 인증서를 `C:\ProgramData\Scrap Monitoring\PKI\root_ca.crt`에 보관한다.
2. 운영자가 Local administrator 권한으로 `certlm.msc`를 실행한다.
3. 운영자가 Local Computer의 Trusted Root Certification Authorities 아래 Certificates에서 Root CA 인증서를 가져온다.
4. 운영자가 Chrome을 다시 열고 `chrome://certificate-manager`의 Local certificates에서 등록한 Root CA를 확인한다.

## 일반 배포 자동화

최초 Server TLS 적용은 일반 배포 자동화의 첫 실행이다. 후속 배포는 같은 절차로 기존 인증서
상태를 확인하고 필요한 발급, 갱신과 적용을 수행한다.

일반 배포는 다음 작업을 자동화한다.

1. 기존 Root CA 인증서, Intermediate CA 인증서 및 개인키와 CA database의 존재 및 일관성을 확인한다.
2. `step-ca`를 시작하고 health를 확인한다.
3. `server.key`가 없으면 Monitoring Server에서 생성하고 기존 파일이 있으면 유지한다.
4. Server DNS 이름과 공개키를 포함한 인증서 요청을 `step-ca`에 전달한다.
5. `step-ca`가 Intermediate CA 개인키로 서명한 `server.crt`와 인증서 chain을 반환한다.
6. 배포 도구가 Server 인증서의 개인키 일치, DNS 이름, chain과 유효기간을 검사한다.
7. 검증된 인증서와 개인키를 TLS 종단에 읽기 전용으로 연결한다.
8. Edge 배포는 Root CA 인증서를 Camera Edge Agent Container의 `/run/scrap-monitoring/pki/root_ca.crt`에 읽기 전용으로 연결한다.
9. TLS 종단과 Camera Edge Agent를 시작하거나 reload하고 HTTPS와 WSS 연결을 확인한다.

CA 상태가 없거나 fingerprint가 예상값과 다르면 일반 배포는 실패하고 PKI Bootstrap 또는 복구
절차를 요구한다.

### 인증서 갱신

일반 배포의 Server 인증서 갱신은 애플리케이션 Release와 독립적으로 자동 수행한다.

1. 일반 배포 도구가 1년 Server 인증서의 남은 유효기간을 확인한다.
2. Monitoring Server가 기존 개인키 또는 교체용 새 개인키로 인증서 갱신을 요청한다.
3. `step-ca`가 새 Server 인증서를 발급한다.
4. 일반 배포 도구가 새 인증서의 개인키 일치, DNS 이름, chain과 유효기간을 검사한다.
5. 일반 배포 도구가 검증된 파일로 전환하고 TLS 종단을 reload한다.
6. 일반 배포 도구가 HTTPS와 WSS 연결을 확인하고 실패하면 기존 인증서로 복구한다.

Root CA 또는 Intermediate CA의 갱신과 교체는 일반 Server 인증서 갱신에 포함하지 않는 별도
PKI 변경 작업이다.
