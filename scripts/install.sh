#!/usr/bin/env bash
set -euo pipefail

REPO="Monolith-INC/agent-plugins-compliance"
PLUGIN_NAME="agent-plugins-compliance"
VERSION="${AGENT_PLUGINS_COMPLIANCE_VERSION:-latest}"
ARCHIVE_OVERRIDE="${AGENT_PLUGINS_COMPLIANCE_ARCHIVE:-}"

DEST="${PWD}"
HOSTS=""
UNINSTALL=0
NON_INTERACTIVE=0

usage() {
  cat <<'EOF'
Usage: install.sh [options]

Install agent-plugins-compliance into a project and hydrate its specialized
Agent Plugins v1.0.0 compliance agents for one or more hosts.

Options:
  --dest <dir>        Target project directory (default: current directory)
  --host <list>       Comma-separated hosts: claude,codex,cursor,antigravity,all
  --version <tag>     Release tag to install (default: latest; or env AGENT_PLUGINS_COMPLIANCE_VERSION)
  --non-interactive   Skip prompts and use defaults / flags
  --uninstall         Remove installed plugin files and hydrated agents from --dest
  -h, --help          Show this help message
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dest)
      if [[ $# -lt 2 ]]; then
        echo "Error: $1 requires a value." >&2
        usage >&2
        exit 2
      fi
      DEST="$2"
      shift 2
      ;;
    --host)
      if [[ $# -lt 2 ]]; then
        echo "Error: $1 requires a value." >&2
        usage >&2
        exit 2
      fi
      HOSTS="$2"
      shift 2
      ;;
    --version)
      if [[ $# -lt 2 ]]; then
        echo "Error: $1 requires a value." >&2
        usage >&2
        exit 2
      fi
      VERSION="$2"
      shift 2
      ;;
    --non-interactive|-y|--yes)
      NON_INTERACTIVE=1
      shift
      ;;
    --uninstall)
      UNINSTALL=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Error: required command '$1' not found on PATH." >&2
    exit 1
  fi
}

require_cmd python3
if [[ "${UNINSTALL}" -eq 0 ]]; then
  require_cmd tar
  if [[ -z "${ARCHIVE_OVERRIDE}" ]]; then
    require_cmd curl
  fi
fi

IS_TTY=0
if [[ -t 0 && "${NON_INTERACTIVE}" -eq 0 ]]; then
  IS_TTY=1
fi

if [[ "${IS_TTY}" -eq 1 ]]; then
  echo "=== ${PLUGIN_NAME} Installer (Agent Plugins v1.0.0) ==="
  read -r -p "Target project directory [${DEST}]: " input_dest
  if [[ -n "${input_dest}" ]]; then
    DEST="${input_dest}"
  fi
fi

mkdir -p "${DEST}"
DEST="$(cd "${DEST}" && pwd)"
INSTALL_DIR="${DEST}/.agent-plugins/${PLUGIN_NAME}"

if [[ "${UNINSTALL}" -eq 1 ]]; then
  echo "Removing ${PLUGIN_NAME} from ${DEST}..."
  rm -rf "${INSTALL_DIR}"
  for rel in \
    ".claude/agents/compliance-auditor.md" \
    ".claude/agents/compliance-remediator.md" \
    ".claude/skills/audit-plugin-compliance" \
    ".claude/skills/remediate-plugin-compliance" \
    ".codex/agents/compliance-auditor.toml" \
    ".codex/agents/compliance-remediator.toml" \
    ".codex/skills/audit-plugin-compliance" \
    ".codex/skills/remediate-plugin-compliance" \
    ".cursor/agents/compliance-auditor.md" \
    ".cursor/agents/compliance-remediator.md" \
    ".cursor/skills/audit-plugin-compliance" \
    ".cursor/skills/remediate-plugin-compliance" \
    ".agents/agents/compliance-auditor.md" \
    ".agents/agents/compliance-remediator.md" \
    ".agents/skills/audit-plugin-compliance" \
    ".agents/skills/remediate-plugin-compliance" \
    ".gemini/agents/compliance-auditor.md" \
    ".gemini/agents/compliance-remediator.md" \
    ".gemini/skills/audit-plugin-compliance" \
    ".gemini/skills/remediate-plugin-compliance"; do
    rm -rf "${DEST}/${rel}"
  done
  echo "Uninstalled ${PLUGIN_NAME} from ${DEST}."
  exit 0
fi

normalize_hosts() {
  local raw="$1"
  local expanded=()
  local token item seen
  IFS=',' read -r -a tokens <<< "${raw}"
  for token in "${tokens[@]}"; do
    token="$(echo "${token}" | tr -d '[:space:]')"
    [[ -z "${token}" ]] && continue
    case "${token}" in
      1|claude) expanded+=("claude") ;;
      2|codex) expanded+=("codex") ;;
      3|cursor) expanded+=("cursor") ;;
      4|antigravity) expanded+=("antigravity") ;;
      5|all) expanded+=("claude" "codex" "cursor" "antigravity") ;;
      *)
        echo "Unsupported host: ${token}" >&2
        exit 2
        ;;
    esac
  done
  local unique=()
  for item in "${expanded[@]}"; do
    seen=0
    for u in "${unique[@]+"${unique[@]}"}"; do
      if [[ "${u}" == "${item}" ]]; then
        seen=1
        break
      fi
    done
    if [[ "${seen}" -eq 0 ]]; then
      unique+=("${item}")
    fi
  done
  local IFS=','
  echo "${unique[*]}"
}

if [[ -z "${HOSTS}" ]]; then
  if [[ "${IS_TTY}" -eq 1 ]]; then
    echo ""
    echo "Select target host(s) for agent hydration and skill wiring:"
    echo "  1) claude       (.claude/agents/ + .claude/skills/)"
    echo "  2) codex        (.codex/agents/  + .codex/skills/)"
    echo "  3) cursor       (.cursor/agents/ + .cursor/skills/)"
    echo "  4) antigravity  (.agents/agents/ + .agents/skills/)"
    echo "  5) all          (all four hosts)"
    read -r -p "Choose host(s) (comma-separated names or 1-5) [all]: " choice
    HOSTS="${choice:-all}"
  else
    HOSTS="claude,codex,cursor,antigravity"
  fi
fi

HOSTS="$(normalize_hosts "${HOSTS}")"
if [[ -z "${HOSTS}" ]]; then
  echo "Error: no valid hosts selected." >&2
  exit 2
fi

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

if [[ -n "${ARCHIVE_OVERRIDE}" ]]; then
  ARCHIVE_PATH="${ARCHIVE_OVERRIDE}"
  echo "Using local archive: ${ARCHIVE_PATH}"
else
  if [[ "${VERSION}" == "latest" ]]; then
    BASE_URL="https://github.com/${REPO}/releases/latest/download"
  else
    BASE_URL="https://github.com/${REPO}/releases/download/${VERSION}"
  fi
  ARCHIVE_PATH="${TMP_DIR}/${PLUGIN_NAME}.tar.gz"
  SUMS_PATH="${TMP_DIR}/SHA256SUMS"
  echo "Downloading ${PLUGIN_NAME} (${VERSION}) from GitHub Releases..."
  curl -fsSL "${BASE_URL}/${PLUGIN_NAME}.tar.gz" -o "${ARCHIVE_PATH}"
  if curl -fsSL "${BASE_URL}/SHA256SUMS" -o "${SUMS_PATH}" 2>/dev/null; then
    EXPECTED="$(grep "${PLUGIN_NAME}.tar.gz" "${SUMS_PATH}" | awk '{print $1}' | head -n 1)"
    if [[ -n "${EXPECTED}" ]]; then
      ACTUAL="$(python3 -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "${ARCHIVE_PATH}")"
      if [[ "${ACTUAL}" != "${EXPECTED}" ]]; then
        echo "Error: SHA256 checksum mismatch for ${PLUGIN_NAME}.tar.gz" >&2
        exit 1
      fi
      echo "Verified SHA256 checksum."
    fi
  fi
fi

STAGE_DIR="${TMP_DIR}/stage"
mkdir -p "${STAGE_DIR}"
tar -xzf "${ARCHIVE_PATH}" -C "${STAGE_DIR}"

# Support archives with either root files or a single top-level directory
if [[ -f "${STAGE_DIR}/plugin.json" ]]; then
  SRC_ROOT="${STAGE_DIR}"
else
  SRC_ROOT="$(find "${STAGE_DIR}" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
fi

if [[ -z "${SRC_ROOT}" || ! -f "${SRC_ROOT}/plugin.json" ]]; then
  echo "Error: downloaded archive does not contain a valid plugin.json." >&2
  exit 1
fi

rm -rf "${INSTALL_DIR}"
mkdir -p "${INSTALL_DIR}"
cp -R "${SRC_ROOT}/." "${INSTALL_DIR}/"
chmod +x "${INSTALL_DIR}"/bin/*.py "${INSTALL_DIR}"/skills/*/scripts/*.sh

host_dir_for() {
  case "$1" in
    claude) echo ".claude" ;;
    codex) echo ".codex" ;;
    cursor) echo ".cursor" ;;
    antigravity) echo ".agents" ;;
    *)
      echo "Unsupported host: $1" >&2
      exit 2
      ;;
  esac
}

IFS=',' read -r -a HOST_LIST <<< "${HOSTS}"
for raw_host in "${HOST_LIST[@]}"; do
  host="$(echo "${raw_host}" | tr -d '[:space:]')"
  [[ -z "${host}" ]] && continue
  hdir="$(host_dir_for "${host}")"

  echo "Hydrating specialized agents for ${host}..."
  python3 "${INSTALL_DIR}/bin/hydrate_agents.py" --plugin-root "${INSTALL_DIR}" --host "${host}" --output "${DEST}" >/dev/null

  echo "Installing skills for ${host} into ${hdir}/skills/..."
  mkdir -p "${DEST}/${hdir}/skills"
  for skill_dir in "${INSTALL_DIR}"/skills/*; do
    [[ -d "${skill_dir}" ]] || continue
    skill_name="$(basename "${skill_dir}")"
    rm -rf "${DEST}/${hdir}/skills/${skill_name}"
    cp -R "${skill_dir}" "${DEST}/${hdir}/skills/${skill_name}"
  done
done

echo ""
echo "=== Installation complete ==="
echo "  Plugin root: ${INSTALL_DIR}"
echo "  Hosts wired: ${HOSTS}"
echo "  Self-audit:  $(python3 "${INSTALL_DIR}/bin/audit_plugin.py" "${INSTALL_DIR}" --format json | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["status"])')"
echo ""
echo "Next steps:"
echo "  1. Restart your agent session so the newly installed skills and hydrated agents reload."
echo "  2. Run the audit skill:     audit-plugin-compliance"
echo "  3. Run guided remediation:  remediate-plugin-compliance"
echo "  4. Optional CLI audit:      python3 ${INSTALL_DIR}/bin/audit_plugin.py <plugin-dir>"
