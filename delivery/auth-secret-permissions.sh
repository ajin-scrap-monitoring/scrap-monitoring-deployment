# shellcheck shell=bash

auth_check_path() {
  local path=$1 current='' part
  local -a parts
  if [[ "$path" != /* ]]; then
    path="$PWD/$path"
  fi
  IFS=/ read -r -a parts <<< "$path"
  for part in "${parts[@]}"; do
    [[ -n "$part" ]] || continue
    current="$current/$part"
    if [[ -L "$current" ]]; then
      printf '%s\n' "credential path is a symbolic link: $current" >&2
      return 1
    fi
  done
}

auth_root_directory() {
  local path=$1
  auth_check_path "$path" || return 1
  if [[ ! -d "$path" ]]; then
    printf '%s\n' "root directory is missing: $path" >&2
    return 1
  fi
  path=$(realpath --canonicalize-existing -- "$path") || return 1
  if [[ "$path" == / && "$EUID" -ne 0 ]]; then
    printf '%s\n' 'host credential operations require root' >&2
    return 1
  fi
  printf '%s\n' "$path"
}

auth_reader_group() {
  case "$1/$2" in
    edge/edge-backend) printf '%s\n' scrap-edge-uplink ;;
    edge/camera-media) printf '%s\n' scrap-camera-agent ;;
    server/edge-backend) printf '%s\n' scrap-backend-auth ;;
    server/camera-media) printf '%s\n' scrap-media-auth ;;
    *) return 1 ;;
  esac
}

auth_reader_gid() {
  local root=$1 group=$2 create=${3:-false} record gid
  # Fixture roots use their directory group and never change host accounts.
  if [[ "$root" != / ]]; then
    stat --format='%g' "$root"
    return
  fi
  if ! record=$(getent group "$group"); then
    if [[ "$create" != true ]]; then
      printf '%s\n' "credential reader group is missing: $group" >&2
      return 1
    fi
    if ! groupadd --system "$group"; then
      getent group "$group" >/dev/null || return 1
    fi
    record=$(getent group "$group") || return 1
  fi
  gid=$(printf '%s\n' "$record" | awk -F: 'NF == 4 {print $3}')
  if [[ ! "$gid" =~ ^[0-9]+$ ]] || (( gid == 0 )); then
    printf '%s\n' "credential reader group has an invalid ID: $group" >&2
    return 1
  fi
  printf '%s\n' "$gid"
}

auth_private_gid() {
  if [[ "$1" == / ]]; then
    printf '%s\n' 0
  else
    stat --format='%g' "$1"
  fi
}

auth_regular_file() {
  local path=$1
  auth_check_path "$path" || return 1
  if [[ -e "$path" ]] && { [[ ! -f "$path" ]] || (( $(stat --format='%h' "$path") != 1 )); }; then
    printf '%s\n' "credential path is not a single-link regular file: $path" >&2
    return 1
  fi
}

auth_set_permissions() {
  local root=$1 path=$2 mode=$3 gid=$4
  auth_check_path "$path" || return 1
  if [[ "$root" == / ]]; then
    chown "0:$gid" "$path" || return 1
  else
    chgrp "$gid" "$path" || return 1
  fi
  chmod "$mode" "$path"
}

auth_validate_permissions() {
  local root=$1 path=$2 mode=$3 gid=$4 owner
  auth_check_path "$path" || return 1
  if [[ "$root" == / ]]; then
    owner=0
  else
    owner=$(stat --format='%u' "$root") || return 1
  fi
  if [[ "$(stat --format='%a:%u:%g' "$path")" != "$mode:$owner:$gid" ]]; then
    printf '%s\n' "credential ownership or mode is invalid: $path" >&2
    return 1
  fi
}

auth_prepare_directory() {
  local root=$1 path=$2 gid
  auth_check_path "$path" || return 1
  gid=$(auth_private_gid "$root") || return 1
  mkdir -p "$path" || return 1
  auth_set_permissions "$root" "$path" 700 "$gid"
}

auth_lock() {
  local root=$1 path=$2 gid
  auth_regular_file "$path" || return 1
  gid=$(auth_private_gid "$root") || return 1
  exec 9>>"$path"
  auth_set_permissions "$root" "$path" 600 "$gid" || return 1
  flock --exclusive 9
}
