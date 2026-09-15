# Integrated release

Release manifest와 asset 생성 및 게시 동작은
[`docs/deployment-contract.md`](../docs/deployment-contract.md)를 따른다. 실제 version manifest는
[`release/manifests`](manifests)에 둔다.

| 파일 | 역할 |
| --- | --- |
| `manifest.schema.json` | 통합 Release와 Component 공급망 정보 검증 |
| `package.schema.json` | 대상별 Package descriptor 검증 |
| `validate-manifest` | 게시 가능한 Manifest와 선택적 Public Package 제한 검증 |
| `validate-targets` | Manifest image와 대상별 Compose service 교차 검증 |
| `pull-images` | Manifest의 digest 고정 image 취득과 대상별 archive 생성 |
| `build-assets` | 재현 가능한 Online Package, Offline Bundle과 checksum 생성 |
| `verify-assets` | 생성된 Package 8개와 checksum 집합의 독립 검증 |
