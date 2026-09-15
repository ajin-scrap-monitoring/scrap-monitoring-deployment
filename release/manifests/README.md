# Version manifests

실제 통합 배포 Release manifest는 `vMAJOR.MINOR.PATCH.json` 이름으로 관리한다. 파일 이름,
manifest의 `version`과 Release tag는 일치해야 한다.

Edge와 Server의 확인된 component image가 모두 준비된 version만 이 디렉토리에 manifest를
추가한다. Image는 GitHub Container Registry (GHCR)의 Secure Hash Algorithm 256-bit (SHA-256)
digest로 고정한다. Component별 Public source Repository, Release version과 full Git commit을
함께 기록하며 자격 증명과 현장별 값은 포함하지 않는다.
