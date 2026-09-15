# Outbound Pull

`fetch-release`는 고정된 GitHub Release에서 명시한 version, target과 scenario의 Online Package와
`SHA256SUMS`를 HTTPS로 취득한다. 두 파일을 `verify-release`로 검증한 후 출력
디렉토리를 원자적으로 공개한다.

```bash
delivery/online/fetch-release \
  --version v1.2.3 \
  --target edge \
  --scenario hardware \
  --output /var/tmp/scrap-monitoring-edge-hardware-v1.2.3
```

출력 경로가 이미 존재하면 내용을 덮어쓰지 않고 실패한다.

취득이 끝나면 같은 version, target, scenario와 출력 경로의 파일을 적용한다.

```bash
delivery/apply-release \
  --version v1.2.3 \
  --target edge \
  --scenario hardware \
  --package /var/tmp/scrap-monitoring-edge-hardware-v1.2.3/scrap-monitoring-edge-hardware-v1.2.3-online.tar.gz \
  --checksums /var/tmp/scrap-monitoring-edge-hardware-v1.2.3/SHA256SUMS \
  --mode online
```
