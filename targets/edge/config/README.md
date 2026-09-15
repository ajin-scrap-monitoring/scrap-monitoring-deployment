# Edge configuration

이 디렉토리는 공개 가능한 Edge 설정 template의 위치다. 실제 승인 설정은
/opt/ajin/config/edge.json에 두며 Git과 Release asset에 포함하지 않는다.

배포 적용기는 실제 설정의 CONFIG_REVISION을 장비 환경설정과 대조하고 정확한 byte에서
CONFIG_SHA256을 계산한다. 승인된 보정값과 현장 센서 매핑이 없는 예제 설정을 실제 배포에
사용하지 않는다.
