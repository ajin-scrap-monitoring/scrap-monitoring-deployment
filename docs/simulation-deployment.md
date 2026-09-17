# Simulation 배포

## 구성

simulation 배포 단위는 2개다.

| 대상 | 구성 |
| --- | --- |
| Server | Simulation Server, Visualizer, Backend, Camera Media Service, Dashboard와 TLS 종단 |
| Edge | LiDAR Processing, Camera Edge, Camera Edge Bridge와 V4L2 loopback device |

Simulation Server는 서로 다른 Server IP 2개에서 각각 UDP 8089을 공개한다. Edge는
`LIDAR_A_IP`와 `LIDAR_B_IP`로 두 endpoint에 연결한다. Visualizer는 synthetic camera stream을
제공하고 Camera Edge Bridge는 이를 `CAMERA_DEVICE` V4L2 loopback device에 기록한다.

## 설정

Server와 Edge에는 `simulation` 환경 파일을 각각 하나씩 설치한다. 실제 값의 소유권은
[환경설정 관리](configuration-management.md)를 따른다.

### Server 설정

```bash
sudo install -d -o root -g scrap-admin -m 0750 /etc/scrap-monitoring
sudo install -o root -g scrap-admin -m 0640 \
  targets/server/simulation/.env.example \
  /etc/scrap-monitoring/server.env
```

`SIMULATOR_LIDAR_A_IP`와 `SIMULATOR_LIDAR_B_IP`는 서로 다른 Server IP이고,
`SIMULATOR_LIDAR_UDP_PORT`는 `8089`다.

### Edge 설정

```bash
sudo install -d -o root -g scrap-admin -m 0750 /etc/scrap-monitoring
sudo install -o root -g scrap-admin -m 0640 \
  targets/edge/simulation/.env.example \
  /etc/scrap-monitoring/edge.env
```

`LIDAR_A_IP`와 `LIDAR_B_IP`는 Server의 LiDAR별 IP를 사용한다. `SYNTHETIC_CAMERA_SERVER_URL`은
Visualizer stream이고 `CAMERA_DEVICE`는 V4L2 loopback device다.

## 적용

simulation 통합 Release는 Server를 먼저 적용한 뒤 Edge에 적용한다.

### Server 적용

```bash
read -r -p 'Release version: ' version
sudo delivery/quick-start \
  --target server \
  --scenario simulation \
  --version "${version}"
```

### Edge 적용

```bash
read -r -p 'Release version: ' version
sudo delivery/quick-start \
  --target edge \
  --scenario simulation \
  --version "${version}"
```

## 수락 검사

simulation 수락 검사는 [배포 계약](deployment-contract.md)의 simulation 수락 검사를 따른다.
