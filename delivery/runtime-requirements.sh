# shellcheck shell=bash
# The runtime installer sources this library to check package and command versions.

runtime_apt_source_state() {
  local apt_directory="$1" repository_uri="$2" suite="$3" component="$4" architecture="$5"
  local source_file
  local source_files=()
  for source_file in "$apt_directory/sources.list" \
    "$apt_directory/sources.list.d/"*.list "$apt_directory/sources.list.d/"*.sources; do
    [[ ! -f "$source_file" ]] || source_files+=("$source_file")
  done
  if [[ "${#source_files[@]}" -eq 0 ]]; then
    printf '%s\n' absent
    return 0
  fi
  awk -v uri="$repository_uri" -v suite="$suite" -v component="$component" \
    -v architecture="$architecture" '
    function contains(value, expected, tokens, count, token_index) {
      count = split(value, tokens, /[[:space:]]+/)
      for (token_index = 1; token_index <= count; token_index++)
        if (tokens[token_index] == expected) return 1
      return 0
    }
    function matches_uri(value) { return contains(value, uri) || contains(value, uri "/") }
    function flush(key) {
      if (matches_uri(fields["uris"]) && fields["enabled"] != "no" &&
          (contains(fields["types"], "deb") || contains(fields["types"], "deb-src"))) {
        sources++
        if (contains(fields["types"], "deb")) binary_sources++
        if (!contains(fields["suites"], suite) || !contains(fields["components"], component) ||
            (fields["architectures"] != "" && !contains(fields["architectures"], architecture)))
          incompatible++
      }
      for (key in fields) delete fields[key]
      field = ""
    }
    FNR == 1 { flush() }
    /^[[:space:]]*#/ { next }
    FILENAME !~ /\.sources$/ {
      if ($1 != "deb" && $1 != "deb-src") next
      for (position = 2; position <= NF; position++) {
        if ($position ~ /^#/) break
        if ($position == uri || $position == uri "/") {
          sources++
          if ($1 == "deb") binary_sources++
          valid_component = 0
          for (component_index = position + 2; component_index <= NF && $component_index !~ /^#/; component_index++)
            if ($component_index == component) valid_component = 1
          if ($(position + 1) != suite || !valid_component) incompatible++
          if (match($0, /arch=[^][:space:]]+/)) {
            arches = substr($0, RSTART + 5, RLENGTH - 5)
            gsub(/,/, " ", arches)
            if (!contains(arches, architecture)) incompatible++
          }
        }
      }
      next
    }
    /^[[:space:]]*$/ { flush(); next }
    /^[[:space:]]+/ { if (field != "") fields[field] = fields[field] " " $0; next }
    /^[A-Za-z-]+:/ {
      field = tolower(substr($0, 1, index($0, ":") - 1))
      value = substr($0, index($0, ":") + 1)
      sub(/^[[:space:]]+/, "", value)
      sub(/[[:space:]]+$/, "", value)
      fields[field] = value
    }
    END {
      flush()
      if (sources > 1 || incompatible || (sources > 0 && !binary_sources)) {
        print "existing APT repository configuration is duplicate or incompatible" > "/dev/stderr"
        exit 1
      }
      print sources == 1 ? "present" : "absent"
    }
  ' "${source_files[@]}"
}

package_version() {
  local package="$1"
  local expected_version="$2"
  local version
  version="$(apt-cache madison "${package}" \
    | awk -v expected="${expected_version}" '
      index($3, expected) == 1 {
        suffix = substr($3, length(expected) + 1)
        if (suffix == "" || suffix ~ /^-/) {
          if (version == "") version = $3
        }
      }
      END { if (version != "") print version }
    ')"
  if [[ -z "${version}" ]]; then
    printf '%s\n' "required package version is unavailable: ${package} ${expected_version}" >&2
    return 1
  fi
  printf '%s\n' "${version}"
}

require_minimum_version() {
  local component="$1"
  local actual="$2"
  local minimum="$3"
  if [[ -z "${actual}" ]] || ! dpkg --compare-versions "${actual}" ge "${minimum}"; then
    printf '%s\n' "${component} version must be at least ${minimum}: ${actual:-unknown}" >&2
    return 1
  fi
}

require_exact_version() {
  local component="$1"
  local actual="$2"
  local expected="$3"
  if [[ "${actual}" != "${expected}" ]]; then
    printf '%s\n' "${component} version must be ${expected}: ${actual:-unknown}" >&2
    return 1
  fi
}

validate_host_tools() {
  local command
  for command in awk bash curl find flock getent gpg groupadd install jq openssl python3 \
    sha256sum stat systemctl update-ca-certificates; do
    if ! command -v "${command}" >/dev/null; then
      printf '%s\n' "required host command is missing: ${command}" >&2
      return 1
    fi
  done
  require_minimum_version Bash "${BASH_VERSION%%(*}" '5.1'
  require_minimum_version Coreutils "$(install --version | awk 'NR == 1 { print $NF }')" '8.32'
  require_minimum_version Findutils "$(find . --version | awk 'NR == 1 { print $NF }')" '4.8'
  require_minimum_version curl "$(curl --version | awk 'NR == 1 { print $2 }')" '7.81.0'
  require_minimum_version jq "$(jq --version | sed 's/^jq-//')" '1.6'
  require_minimum_version OpenSSL "$(openssl version | awk '{ print $2 }')" '3.0.2'
  require_minimum_version Python "$(python3 --version | awk '{ print $2 }')" '3.10'
  require_minimum_version util-linux "$(flock --version | awk 'NR == 1 { print $NF }')" '2.37'
}
