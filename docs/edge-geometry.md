# 개발 장비 Edge 형상 기준

이 문서는 개발 장비 Edge의 형상 기준(적재공간, LiDAR 2대, Camera)과 각 값의 출처 및 Component 사이의
일치 판정의 정본이다. 기준 시각은 2026-11-16이며 값은 아래 revision의 source와 개발 장비 조사 결과로
확인했다. 값에는 token, 사설 주소, tailnet 이름, hostname과 Backend origin을 포함하지 않는다.

| Component | 비교 기준 revision |
| --- | --- |
| Simulator (`scrap-monitoring-simulator`) | `189c0a6a8244973d4d4acc02f9b775b03122652d` (Server 실행 `3cae0a1`과 git tree 동일) |
| Edge Platform (`ajin-edge-platform`) | `cfc692599023f7ab52c209529a101e5a830bc893` |
| Backend (`scrap-monitoring-backend`) | `21f78942ff28d114421b1934d41642e6b334d084` |

## 정본과 출처

형상의 정본은 Simulator의 `services/simulation-server/config/environment.v1.json`이다. 다음 값은 모두
이 정본과 수치가 일치한다.

| 대상 | 출처 |
| --- | --- |
| Edge 기본 설정 | `packages/edge-common/src/ajin_edge/v2/settings_defaults.py` |
| Edge 활성 등록 | 장비 control 상태 `calibration-control.json`의 active registration |
| Backend 기준 | 환경 변수 `EDGE_V2_SIMULATION_HEIGHT_REFERENCES`의 `pit-01` 항목 |

## 좌표계와 규약

Simulator는 단위 m, 오른손 좌표계, Z 위 방향, 바닥 Z=0을 사용한다. Edge는 frame_id
`synthetic-scrap-pit-v1`, 단위 mm, `RIGHT_HANDED`를 사용하며 Z=0은 Simulator 바닥이다
(Edge `docs/CONFIGURATION_API.md` 66행, `packages/edge-common/src/ajin_edge/v2/contracts.py` 277행).
Backend는 단위 cm, `coordinate_source` `EDGE_WORLD`를 사용한다
(`src/app/schemas/lidar_height.py` 80행). 단위 환산은 1 m = 1000 mm = 100 cm다.

Simulator X, Y와 Edge X, Y가 같은 축이라는 관계는 어느 Component 문서에도 명시되어 있지 않고
수치 일치로만 확인한다.

각도 규약은 다음과 같다. Simulator의 방향은 `cos(theta)*u0 + sin(theta)*u90`이다. Edge의 점은
`p = R*[r cos(theta), r sin(theta), 0] + t`이며 `theta = angle_sign*angle + angle_zero_offset`이다
(`ajin_edge/v2/processing.py`, `section_profile.py`). 따라서 Edge 회전 행렬 R의 0열은 Simulator `u0`,
1열은 `u90`, 2열은 scan plane 법선이다. `angle_sign`은 1, `angle_zero_offset`은 0 mdeg다.

## 형상 비교

판정 MATCH는 단위 환산 후 수치가 같다는 뜻이고 NOT DEFINED는 해당 Component가 값을 정의하지 않는다는
뜻이다.

### 적재공간

| 항목 | Simulator (m) | Edge (mm) | Backend (cm) | 판정 |
| --- | --- | --- | --- | --- |
| pit 경계 다각형 | (0,0) (4,0) (4,5.3) (2.7,5.3) (1.9,2.5) (0,2.5), `boundary_xy_m` | NOT DEFINED | 같은 6점 x100, `boundary_xy_cm` | Edge NOT DEFINED, Simulator와 Backend MATCH |
| 바닥 | 0, `floor_z_m` | 0, 단면 `floor_z_mm` | 0, `floor_z_cm` | MATCH |
| 상단 | 10, `top_z_m` | 10000, 단면 `ceiling_z_mm` | 1000, `top_z_cm` | MATCH |

Edge 단면의 바닥과 상단은 `settings_defaults.py` 52행 이하에서 정의한다. Simulator 값은
`environment.v1.json` 5행 이하다.

### LiDAR A (Simulator `lidar_1`, Edge `lidar-a`)

| 항목 | Simulator | Edge | Backend | 판정 |
| --- | --- | --- | --- | --- |
| 위치 | (0.5, 2.5, 10) m | (500, 2500, 10000) mm | (50, 250, 1000) cm | MATCH |
| `u0` | (0, -0.22414769292142694, -0.9745551866148997) | R 0열과 동일 | 비교 미수행 | MATCH |
| `u90` | (-1, 0, 0) | R 1열과 동일 | 비교 미수행 | MATCH |
| 회전 행렬 R | 해당 없음 | [[0,-1,0],[-0.22414769292142694,0,0.9745551866148997],[-0.9745551866148997,0,-0.22414769292142694]] | 해당 없음 | MATCH |
| scan plane 법선 | (0, 0.97456, -0.22415), 수직에서 약 12.95 deg | R 2열과 동일 | 해당 없음 | MATCH |
| `angle_sign`, `angle_zero_offset` | 해당 없음 | 1, 0 mdeg | 해당 없음 | 해당 없음 |
| 사용 각도 구간 | 해당 없음 | 장비 등록 [0, 25980)과 [286330, 360000) mdeg | 해당 없음 | 아래 `LiDAR 사용 각도 구간` 절 |

### LiDAR B (Simulator `lidar_2`, Edge `lidar-b`)

| 항목 | Simulator | Edge | Backend | 판정 |
| --- | --- | --- | --- | --- |
| 위치 | (2.3, 3.9, 10) m | (2300, 3900, 10000) mm | (230, 390, 1000) cm | MATCH |
| `u0` | (0.14834045293024462, 0, -0.9889363528682975) | R 0열과 동일 | 비교 미수행 | MATCH |
| `u90` | (0, -1, 0) | R 1열과 동일 | 비교 미수행 | MATCH |
| 회전 행렬 R | 해당 없음 | [[0.14834045293024462,0,-0.9889363528682975],[0,-1,0],[-0.9889363528682975,0,-0.14834045293024462]] | 해당 없음 | MATCH |
| scan plane 법선 | (-0.98894, 0, -0.14834), 수직에서 약 8.53 deg | R 2열과 동일 | 해당 없음 | MATCH |
| `angle_sign`, `angle_zero_offset` | 해당 없음 | 1, 0 mdeg | 해당 없음 | 해당 없음 |
| 사용 각도 구간 | 해당 없음 | 장비 등록 [0, 75470)과 [305830, 360000) mdeg | 해당 없음 | 아래 `LiDAR 사용 각도 구간` 절 |

Simulator 값은 `environment.v1.json` 15행 이하, Edge 값은 `settings_defaults.py` 13행 이하다. Backend의 `sensor_poses`는
이 조사에서 개별 값을 비교하지 않았다.

### LiDAR 사용 각도 구간

각도 구간은 적재 표면 높이 9 m까지 측정선의 양쪽 벽에 닿는 범위다. 적재 표면이 높을수록 같은 수평 범위를
보는 데 필요한 각도가 커지므로 각도 구간은 최대 적재 높이 기준으로 정하고, 적재공간 밖과 벽의 점은 Edge
단면의 위치 범위로 제외한다. 적재 높이가 9 m를 넘으면 벽 쪽 끝 bin부터 관측되지 않는다.

| 센서 | 각도 구간 | 폭 |
| --- | --- | --- |
| LiDAR A | [0, 25980)과 [286330, 360000) mdeg | 99.7 deg |
| LiDAR B | [0, 75470)과 [305830, 360000) mdeg | 129.6 deg |

전방 180 deg 구간은 Simulator 회전 10 Hz와 sample 32000 Hz에서 센서당 스캔마다 약 1,600개 점을 만들며,
개발 장비 Edge(4 core)의 lidar-processing과 edge-orchestrator가 각각 CPU 약 90%를 사용해 STATE 판정 간격이
1.5초를 넘는다. 위 구간에서는 각각 약 66%, 61%, measurement-uplink는 약 61%이고 STATE 판정 간격은 1.0초다.

적재 표면이 센서 높이에 가까우면 측정선 위 고철 꼭대기가 그 너머의 낮은 경사면을 가린다. 적재 약 8.85 m에서
LiDAR B는 y=1.1 m 부근 꼭대기 너머의 y=0.05~1.09 m(bin 0~3)를 관측하지 못하고, 해당 각도의 빔은 y=0 벽의
7.3~9.0 m 높이에 닿아 단면 범위 밖으로 제외된다. 이 구간은 각도 구간으로 해결되지 않는다.

| 적재 표면 높이 | A x=0 쪽 | A x=4 m 쪽 | B y=0 쪽 | B y=5.3 m 쪽 |
| --- | --- | --- | --- | --- |
| 0 m | 2.8 deg | 18.8 deg | 21.1 deg | 7.9 deg |
| 5 m | 5.6 deg | 34.3 deg | 37.7 deg | 15.5 deg |
| 8 m | 13.7 deg | 59.6 deg | 62.6 deg | 34.7 deg |

표의 각도는 0 deg에서 벽까지 닿는 데 필요한 각도이며 Simulator `environment.v1.json`의 `p0`, `u0`, `u90`과
Edge 각도 규약(theta = angle, `angle_sign` 1, `angle_zero_offset` 0)으로 계산한다.

Edge 계약상 `angle_intervals_mdeg`는 `start_inclusive`(0..359999)와 `end_exclusive`(1..360000)를 가진 객체의
배열이므로 0 deg를 걸치는 범위는 두 구간으로 나누어 표현한다(Edge `packages/edge-common/src/ajin_edge/v2/contracts.py`
43~48행). 각도 구간의 소유와 변경 절차는 [docs/configuration-management.md](configuration-management.md)의
`Edge v2 runtime 설정` 절을 따른다.

센서 ID 대응(`lidar_1` -> `lidar-a`, `lidar_2` -> `lidar-b`)은 문서 정의가 없다. Server
Simulator의 LiDAR별 host IP와 Edge driver `--ip`의 일치로 확인했다.

### 거리와 품질

| 항목 | Simulator | Edge | 판정 |
| --- | --- | --- | --- |
| 최대 거리 | 30 m, `simulation-server.v1.json` 31행 | 30000 mm, `distance_max_mm` | MATCH |
| 최소 거리 | 0.05 m, 같은 파일 30행 | 1 mm, `distance_min_mm` | 값 다름, 수신 필터가 더 넓음 |
| 품질 | valid 48 또는 80, invalid 0 또는 24, `quality-profile.v1.json` | `quality_min` 10 | valid 48과 80, invalid 24는 기준 이상, invalid 0은 기준 미만 |

Simulator는 무효 반환(거리 0, 최소 거리 미만, 최대 거리 초과)의 거리를 `distance_tick = 0`, 즉 거리 0으로 보내고 품질만
invalid 분포(0 또는 24)에서 뽑는다(Simulator `services/simulation-server/src/measurement/generation.rs` 317행 이하).
따라서 품질 24인 무효 반환은 Edge `quality_min` 10을 통과하지만 Edge `distance_min_mm` 1에서 제외된다.

### Camera

Camera pose는 Simulator 내부 값이며 Edge와 Backend는 사용하지 않는다.

| 항목 | Simulator | Edge | Backend |
| --- | --- | --- | --- |
| 위치 | normalized (0, -0.354685843, 1.448540394), 환산 약 (2.0, -0.897, 14.485) m | NOT DEFINED | NOT DEFINED |
| 조준점 | normalized (0, 0.255314157, 0.498540394), 환산 약 (2.0, 5.203, 4.985) m | NOT DEFINED | NOT DEFINED |
| view up, 시야각 | (0, 0, 1), 45 deg | NOT DEFINED | NOT DEFINED |
| 출력 | 1920x1080, 30 FPS, MJPEG | 기본값 1920x1080, 30 FPS, `mjpeg` | 해당 없음 |

Camera 값은 `services/visualizer/src/scrap_monitoring_visualizer/synthetic_camera/profiles/default.v1.json`
17행 이하와 4행 이하(video)에서 읽는다. 환산은 `renderer.py` 126행 이하의 규칙을 따른다. 중심은
경계 bounding box 중심 (2.0, 2.65) m, scale은 `max(X 범위, Y 범위, Z 범위, 1.0)`이며 값은 10 m다.
환산 좌표는 `중심 + normalized * scale`(Z는 `floor_z + normalized * scale`)이다. Edge `camera-edge`의
기본값은 `services/camera-edge/src/camera_edge/ingest.py` 31행 이하다.

## Backend 기준값

Server에서 실행 중인 Backend의 환경 변수는 비밀이 아니며 다음과 같다.

| 항목 | 값 |
| --- | --- |
| `EDGE_V2_EMPTY_FLOOR_DISTANCE_CM` | 1000 |
| `EDGE_V2_HEIGHT_FILL_ENABLED` | true |
| `EDGE_V2_COLLECTION_HEIGHT_BASIS` | UPPER |
| `EDGE_V2_HEIGHT_REFERENCES` | 미설정 |

`EDGE_V2_SIMULATION_HEIGHT_REFERENCES`의 `pit-01` 항목은 다음 값을 가진다.

| 항목 | 값 |
| --- | --- |
| `config_revision` | `synthetic-fill9m-sections-v12` |
| `calibration_versions` | 두 센서 모두 `default-simulator-installation-v1` |
| `simulator_revision` | `d0e4b3f3b153c0709e8b333fb3ee425c0aec3619` |
| `minimum_coverage` | 0.7 |
| `wall_margin_cm` | 5 |

필드 정의는 Backend `src/app/schemas/lidar_height.py` 62행 이하다.

## Edge 활성 등록

Edge의 기준 등록은 `config_revision` `synthetic-fill9m-angle-base-v12`이고 활성 등록은 `config_revision`
`synthetic-fill9m-sections-v12`, calibration version `default-simulator-installation-v1`이다.
judgment의 `sections`는 아래 `단면과 적재율 기준` 절의 값이고 `method_version`은 `wall-margin-sections-v1`이다.
`window`, `fusion`, `point_cloud` 값은 `settings_defaults.py`와 Edge `FILTERED_POINT_CLOUD_CONTRACT.md`의
기본값과 같다.

## 단면과 적재율 기준

적재율과 높이 곡선의 기준은 Edge 판정 결과다. Edge가 점 필터, 단면 bin 계산과 보간을 수행하고
Backend는 Edge의 `section_profiles`와 `fusion_result`를 보존하여 Dashboard에 제공한다. 이 역할
분담은 Backend `docs/FILTERED_POINT_CLOUD.md`의 "필터는 엣지에서 수행하고 백엔드는 필터를
재적용하거나 빈 점을 보간하지 않는다"는 계약과 Backend `docs/EDGE_V2_INTEGRATION.md`의 단면
profile 저장 계약을 따른다.

Edge 단면은 각 LiDAR의 측정선 중 벽에서 50 mm 안쪽 범위를 20개 구간으로 나눈다. 벽에 맞은 점은
Simulator 거리 noise(표준편차 10 mm, 상한 30 mm) 때문에 벽 위치에서 최대 30 mm 벗어나므로 50 mm 여백
밖의 점만 단면 bin에 들어간다. Edge `section_profile.py`는 점을 world 좌표로 변환한 뒤 축 방향 위치와
바닥, 상한 높이로 bin을 정하고, 양끝 bin은 이웃이 1개뿐이라 공간 편차 필터가 적용되지 않는다.

| 센서 | 측정선 | `origin_xy_mm` | `axis_xy` | `bin_width_mm` x bin 수 | 단면 범위 |
| --- | --- | --- | --- | --- | --- |
| LiDAR A | 바닥에서 y=0.2 m, x=0~4 m | (50, 200) | (1, 0) | 195 x 20 | x=0.05~3.95 m |
| LiDAR B | 바닥에서 x=3.8 m, y=0~5.3 m | (3800, 50) | (0, 1) | 260 x 20 | y=0.05~5.25 m |

Edge `scan_profile`에 Simulator 형상과 noise 상한을 적용한 평면 표면 계산에서 적재 높이 0~9 m 범위의 모든 bin
오차는 10 mm 이하다. LiDAR B는 적재 높이 약 7.3 m를 넘으면 scan plane이 대각선 벽 밖으로 나가 y=5.3 m 쪽 끝
bin부터 `UNAVAILABLE`이 된다(8 m: bin 19, 9 m: bin 17~19). bin 경계는 Backend `floor_section` 20구간과 최대
50 mm 다르다.

Edge 계약상 bin index는 0~511, `bin_width_mm`은 1 이상의 정수이고 bin 출처는 `OBSERVED`,
`INTERPOLATED`, `UNAVAILABLE`, `MASKED`, `CONFLICT`다(EDGE
`packages/edge-common/src/ajin_edge/v2/judgment_schema.py` 73~112행). 보간 한도
`max_interpolation_gap_bins`는 0~10이며 기본값은 1이다.

개발 장비는 위 단면과 각도 구간 기준을 적용한 상태다. 장비의 STATE assessment에서 두 센서 모두 20개 bin이
`OBSERVED`이고 `coverage_ratio`는 1.0이며 `fusion_result`가 생성된다. Backend 화면 적재율(`meanSectionFillPercent`)이 표시된다. Backend 화면 경로는 다음과 같다.

| 항목 | 장비 상태 |
| --- | --- |
| Backend `/api/v2/monitoring/profiles` | `EDGE_V2_FILTERED_PROFILES_ENABLED=true`로 Edge 필터 점을 점 단위로 제공. `section_profiles`는 저장만 하고 화면 API에 사용하지 않음 |
| Backend 화면 적재율 | 센서별 스캔 평균 높이의 최근 5초 시간 중앙값 |

## 미정의 사항

- Edge의 pit 경계 다각형
- Edge와 Backend의 Camera pose
- Simulator X, Y와 Edge X, Y가 같은 축이라는 관계의 문서 정의
- 센서 ID 대응 `lidar_1` -> `lidar-a`, `lidar_2` -> `lidar-b`의 문서 정의
