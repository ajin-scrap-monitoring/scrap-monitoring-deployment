# shellcheck shell=bash
# Server token files use the raw-token formats read by Backend (EDGE_V2_DEVICES)
# and Camera Media Service (EDGE_AUTH_SECRET). Docker Compose passes each file
# to its component as an env_file.

AUTH_ID_PATTERN='^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$'

auth_registry_relative() {
  case "$1" in
    edge-backend) printf '%s\n' srv/scrap-monitoring/secrets/backend/edge-v2-devices.env ;;
    camera-media) printf '%s\n' srv/scrap-monitoring/secrets/media/edge-auth.env ;;
    *) return 1 ;;
  esac
}

auth_registry_variable() {
  case "$1" in
    edge-backend) printf '%s\n' EDGE_V2_DEVICES ;;
    camera-media) printf '%s\n' EDGE_AUTH_SECRET ;;
    *) return 1 ;;
  esac
}

# Prints the JSON value of the registry file after validating its format.
auth_registry_read() {
  local kind=$1 path=$2 variable line json
  variable=$(auth_registry_variable "$kind") || return 1
  if (( $(wc -l < "$path") != 1 )); then
    printf '%s\n' "token file must contain exactly one line: $path" >&2
    return 1
  fi
  line=$(cat "$path")
  if [[ ! "$line" =~ ^${variable}=\'(.*)\'$ ]]; then
    printf '%s\n' "token file has an invalid format: $path" >&2
    return 1
  fi
  json=${BASH_REMATCH[1]}
  if ! auth_registry_valid "$kind" "$json"; then
    printf '%s\n' "token file content is invalid: $path" >&2
    return 1
  fi
  printf '%s\n' "$json"
}

auth_registry_valid() {
  local kind=$1 json=$2
  case "$kind" in
    edge-backend)
      jq --exit-status --arg id "$AUTH_ID_PATTERN" '
        type == "array" and length > 0 and
        all(.[];
          type == "object" and
          (keys | sort) == ["edge_id", "sensor_ids", "site_id", "token"] and
          (.edge_id | type == "string" and test($id)) and
          (.site_id | type == "string" and test($id)) and
          (.sensor_ids | type == "array" and length == 2 and .[0] != .[1] and
            all(.[]; type == "string" and test($id))) and
          (.token | type == "string" and test("^[0-9a-f]{64}$"))) and
        ((map(.token) | unique | length) == length) and
        (group_by(.edge_id) | all(.[];
          length <= 2 and
          (map(.site_id) | unique | length) == 1 and
          (map(.sensor_ids) | unique | length) == 1))
      ' <<< "$json" >/dev/null
      ;;
    camera-media)
      jq --exit-status --arg id "$AUTH_ID_PATTERN" '
        type == "object" and length > 0 and
        all(to_entries[];
          (.key | test($id)) and
          (.value | type == "string" and test("^[0-9a-f]{64}$")))
      ' <<< "$json" >/dev/null
      ;;
    *) return 1 ;;
  esac
}

# Writes the registry atomically from compact JSON; the caller holds the lock.
auth_registry_write() {
  local root=$1 kind=$2 json=$3 path=$4 directory temporary variable
  auth_registry_valid "$kind" "$json" || return 1
  variable=$(auth_registry_variable "$kind") || return 1
  directory=$(dirname "$path")
  temporary=$(mktemp "$directory/.registry.XXXXXX") || return 1
  printf "%s='%s'\n" "$variable" "$(jq --compact-output . <<< "$json")" > "$temporary"
  auth_set_permissions "$root" "$temporary" 600 "$(auth_private_gid "$root")" || return 1
  mv "$temporary" "$path"
}
