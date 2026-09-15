# Offline Bundle

Offline Bundle은 Release workflow의 `release/build-assets`가 생성한다. 대상 host에서는
`import-bundle`이 Bundle을 공통 검증한 후 image archive를 Docker에 load하고 Manifest의
image digest와 platform을 다시 확인한다.

```bash
delivery/offline/import-bundle \
  --version v1.2.3 \
  --target edge \
  --scenario hardware \
  --bundle /media/release/scrap-monitoring-edge-hardware-v1.2.3-offline.tar.gz \
  --checksums /media/release/SHA256SUMS
```

Image load 후 digest 또는 platform 검증이 실패하면 명령은 실패를 반환한다. 기존 image와
이번 load가 추가한 image를 안전하게 구분할 수 없으므로 image를 자동 삭제하지 않는다.

Image import가 끝나면 같은 Bundle과 checksum을 적용한다.

```bash
delivery/apply-release \
  --version v1.2.3 \
  --target edge \
  --scenario hardware \
  --package /media/release/scrap-monitoring-edge-hardware-v1.2.3-offline.tar.gz \
  --checksums /media/release/SHA256SUMS \
  --mode offline
```
