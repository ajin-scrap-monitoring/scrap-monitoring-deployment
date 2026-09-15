# Private PKI automation

PKI 자동화 도구는 3개다.

| 실행 파일 | 역할 |
| --- | --- |
| `validate-ca-state` | Root fingerprint, Root와 Intermediate chain, encrypted key, 권한과 `step-ca` 설정 검증 |
| `verify-server-certificate` | Server DNS SAN, chain, EC P-256 key 일치, TLS Server 용도와 남은 유효기간 검증 |
| `ensure-server-certificate` | 최초 발급, 122일 전 갱신, fullchain 설치, service reload과 실패 복구 |

최초 Root CA와 Intermediate CA Bootstrap은 자동화 도구의 범위가 아니다. 정확한 상태 경로와
운영 절차는 [`docs/pki-operations.md`](../docs/pki-operations.md)를 따른다.

`config/ca.template.json`은 공개 가능한 경로와 발급 정책의 형태만 정의한다. Bootstrap은
실제 JWK public key와 암호화 key를 생성하여 `deployment` Provisioner에 추가한다.
