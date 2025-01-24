#!/bin/bash
#
# Trigger custom juju event when promtail start syncing logs
#

CHARM_DIR="/var/lib/juju/agents/unit-$(echo "${JUJU_UNIT_NAME}" | tr / -)/charm"
POSITIONS_FILE="/var/snap/grafana-agent/current/grafana-agent-positions/log_file_scraper.yml"

# Support bin path for 3.x and 2.x
[[ -x "/usr/bin/juju-exec" ]] && JUJU_CMD="/usr/bin/juju-exec" || JUJU_CMD="/usr/bin/juju-run"

while true; do
  if [[ -e "${POSITIONS_FILE}" ]]; then
    # Test logic for mysql log files path in position file lines
    if grep -q "mysql.*log" "${POSITIONS_FILE}"; then
      ${JUJU_CMD} -u "${JUJU_UNIT_NAME}" JUJU_DISPATCH_PATH=hooks/log-syncing "${CHARM_DIR}"/dispatch
      exit 0
    fi
  fi
  sleep 30
done
