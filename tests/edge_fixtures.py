def runtime_document():
    return {
        "configuration": {
            "schema_version": "2.0",
            "message_type": "edge_configuration",
            "site_id": "example-site",
            "edge_id": "example-edge",
            "config_revision": "example-config-r1",
            "sensors": [{"sensor_id": "lidar-a"}, {"sensor_id": "lidar-b"}],
        },
        "drivers": {
            "lidar-a": "unix:/sockets/a/scan.sock",
            "lidar-b": "unix:/sockets/b/scan.sock",
        },
        "delivery_endpoint": "unix:/sockets/delivery/measurement.sock",
        "observation_endpoint": "unix:/sockets/observations/observations.sock",
        "storage_dir": "/data/outbox",
        "status_dir": "/status",
        "clock_domain_file": "/proc/sys/kernel/random/boot_id",
        "backend_origin": "https://monitoring.example.invalid",
        "token_file": "/run/secrets/edge_token",
    }
