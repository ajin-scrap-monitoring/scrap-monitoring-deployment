# Outbound Pull

`fetch-release`는 고정된 GitHub Release에서 명시한 version과 target의 Online Package와
`SHA256SUMS`를 HTTPS로 취득한다. 두 파일을 `verify-release`로 검증한 후 출력
디렉토리를 원자적으로 공개한다.

```bash
delivery/online/fetch-release \
  --version v1.2.3 \
  --target edge \
  --output /var/tmp/scrap-monitoring-edge-v1.2.3
```

출력 경로가 이미 존재하면 내용을 덮어쓰지 않고 실패한다.
