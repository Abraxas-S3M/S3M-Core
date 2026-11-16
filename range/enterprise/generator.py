"""Deterministic synthetic enterprise for the Cortex CyberTwin range.

Military/tactical context:
A ministry-scale enclave (users, engineering, IT admins, CCTV, 20 servers, 10 business
applications) used to rehearse Cortex attack-path reduction before any live XiiD
deployment. Everything here is synthetic: addresses are RFC1918, vulnerability IDs use a
``SYN-`` prefix and do not refer to real CVEs.

Two files are produced, deliberately separated by ownership:

* ``range/mock_xiid_mcp/scenarios/enterprise_200.yaml`` - what the (mock) XiiD control
  plane knows and returns over MCP: routes, STLinks, hosts, sessions, findings.
* ``range/enterprise/mission_enterprise_200.yaml`` - Abraxas-side mission context XiiD
  does not hold: protected assets, required business flows, footholds, identity exposure.

Regenerate with ``python -m range.enterprise.generator``; output is byte-stable.
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml

ROOT = Path(__file__).resolve().parents[2]
SCENARIO_PATH = ROOT / "range" / "mock_xiid_mcp" / "scenarios" / "enterprise_200.yaml"
MISSION_PATH = ROOT / "range" / "enterprise" / "mission_enterprise_200.yaml"

SEED = 20261116

# group id -> (prefix, size, role)
GROUPS: Dict[str, Tuple[str, int, str]] = {
    "grp:corp-users": ("10.10.0.0/16", 120, "workstation"),
    "grp:eng-users": ("10.11.0.0/24", 20, "workstation"),
    "grp:it-admins": ("10.12.0.0/28", 6, "admin-workstation"),
    "grp:cctv-cams": ("10.30.0.0/24", 30, "camera"),
    "grp:printers": ("10.10.250.0/28", 4, "printer"),
}

# server id -> (address, segment, role)
SERVERS: Dict[str, Tuple[str, str, str]] = {
    "srv-web-01": ("172.16.1.10", "dmz", "public web portal"),
    "srv-vpn-01": ("172.16.1.11", "dmz", "remote access gateway"),
    "srv-mail-01": ("172.16.1.12", "dmz", "mail relay"),
    "srv-api-01": ("172.16.1.13", "dmz", "partner API gateway"),
    "srv-erp-app-01": ("10.20.1.10", "corp-server", "ERP application"),
    "srv-erp-db-01": ("10.20.2.10", "data", "ERP database"),
    "srv-hr-app-01": ("10.20.1.11", "corp-server", "HR application"),
    "srv-hr-db-01": ("10.20.2.11", "data", "HR database"),
    "srv-file-01": ("10.20.1.20", "corp-server", "file share"),
    "srv-dc-01": ("10.20.0.10", "identity", "domain controller"),
    "srv-pki-01": ("10.20.0.20", "identity", "certificate authority"),
    "srv-jump-01": ("10.20.9.10", "mgmt", "admin jump host"),
    "srv-ci-01": ("10.20.5.10", "corp-server", "CI/CD runner"),
    "srv-git-01": ("10.20.5.11", "corp-server", "source control"),
    "srv-siem-01": ("10.20.9.20", "mgmt", "SIEM collector"),
    "srv-backup-01": ("10.20.9.30", "mgmt", "backup server"),
    "srv-nvr-01": ("10.30.1.10", "ot-cctv", "CCTV evidence recorder"),
    "srv-vms-01": ("10.30.1.11", "ot-cctv", "video management"),
    "srv-ot-hist-01": ("10.40.1.10", "ot", "OT historian"),
    "srv-print-01": ("10.20.1.30", "corp-server", "print server"),
}

# 10 business applications and the servers that host them.
APPLICATIONS: Dict[str, List[str]] = {
    "app:erp": ["srv-erp-app-01", "srv-erp-db-01"],
    "app:hr": ["srv-hr-app-01", "srv-hr-db-01"],
    "app:public-web": ["srv-web-01"],
    "app:email": ["srv-mail-01"],
    "app:remote-access": ["srv-vpn-01"],
    "app:file-share": ["srv-file-01"],
    "app:devops": ["srv-ci-01", "srv-git-01"],
    "app:cctv": ["srv-nvr-01", "srv-vms-01"],
    "app:security-monitoring": ["srv-siem-01"],
    "app:backup": ["srv-backup-01"],
}

# (route id, source, target, service, port, observed sessions in 30d, narrow_to or None,
#  sealed by XiiD SealedTunnel)
ROUTES: List[Tuple[str, str, str, str, int, int, Any, bool]] = [
    # Internet-facing
    ("rt-inet-web", "ext:internet", "srv-web-01", "https", 443, 90210, None, False),
    ("rt-inet-vpn", "ext:internet", "srv-vpn-01", "https", 443, 4120, None, False),
    ("rt-inet-mail", "ext:internet", "srv-mail-01", "smtp", 25, 18877, None, False),
    ("rt-inet-api", "ext:internet", "srv-api-01", "https", 443, 2210, "198.51.100.0/28", False),
    ("rt-inet-jump-ssh", "ext:internet", "srv-jump-01", "ssh", 22, 0, None, False),  # legacy exposure
    # DMZ -> internal
    ("rt-web-erp", "srv-web-01", "srv-erp-app-01", "https-api", 8443, 5510, None, False),
    ("rt-api-erp", "srv-api-01", "srv-erp-app-01", "https-api", 8443, 1203, None, False),
    ("rt-vpn-users", "srv-vpn-01", "grp:corp-users", "ipsec", 0, 4120, None, False),
    ("rt-mail-file", "srv-mail-01", "srv-file-01", "smb", 445, 0, None, False),  # unnecessary
    # Users -> apps
    ("rt-users-erp", "grp:corp-users", "srv-erp-app-01", "https", 443, 33012, None, False),
    ("rt-users-hr", "grp:corp-users", "srv-hr-app-01", "https", 443, 8121, None, False),
    ("rt-users-file", "grp:corp-users", "srv-file-01", "smb", 445, 21455, "10.10.4.0/22", False),
    ("rt-users-dc", "grp:corp-users", "srv-dc-01", "kerberos", 88, 120034, None, False),
    ("rt-users-siem", "grp:corp-users", "srv-siem-01", "syslog", 514, 98000, None, False),
    ("rt-users-print", "grp:corp-users", "srv-print-01", "ipp", 631, 3022, None, False),
    ("rt-users-erpdb", "grp:corp-users", "srv-erp-db-01", "postgres", 5432, 0, None, False),  # legacy direct DB
    ("rt-users-jump-rdp", "grp:corp-users", "srv-jump-01", "rdp", 3389, 41, "10.10.9.0/29", False),
    ("rt-users-vms", "grp:corp-users", "srv-vms-01", "https", 8443, 230, "10.10.30.0/26", False),
    ("rt-users-ci", "grp:corp-users", "srv-ci-01", "https", 443, 12, "10.10.5.0/28", False),
    # Engineering
    ("rt-eng-git", "grp:eng-users", "srv-git-01", "https", 443, 6540, None, False),
    ("rt-eng-ci", "grp:eng-users", "srv-ci-01", "https", 443, 2210, None, False),
    ("rt-eng-erpdb", "grp:eng-users", "srv-erp-db-01", "postgres", 5432, 3, "10.11.0.16/30", False),
    ("rt-ci-git", "srv-ci-01", "srv-git-01", "ssh", 22, 1800, None, False),
    ("rt-ci-erp-deploy", "srv-ci-01", "srv-erp-app-01", "ssh", 22, 60, None, False),
    ("rt-ci-dc", "srv-ci-01", "srv-dc-01", "ldap", 389, 0, None, False),  # over-broad service account
    # Admins
    ("rt-admins-jump", "grp:it-admins", "srv-jump-01", "ssh", 22, 1530, None, True),
    ("rt-jump-dc", "srv-jump-01", "srv-dc-01", "rdp", 3389, 410, None, True),
    ("rt-jump-pki", "srv-jump-01", "srv-pki-01", "ssh", 22, 22, None, True),
    ("rt-jump-erpdb", "srv-jump-01", "srv-erp-db-01", "ssh", 22, 95, None, True),
    ("rt-jump-hrdb", "srv-jump-01", "srv-hr-db-01", "ssh", 22, 40, None, True),
    ("rt-jump-nvr", "srv-jump-01", "srv-nvr-01", "ssh", 22, 12, None, True),
    # App tiers
    ("rt-erp-erpdb", "srv-erp-app-01", "srv-erp-db-01", "postgres", 5432, 880000, None, True),
    ("rt-hr-hrdb", "srv-hr-app-01", "srv-hr-db-01", "mssql", 1433, 210000, None, True),
    ("rt-erp-hrdb", "srv-erp-app-01", "srv-hr-db-01", "mssql", 1433, 0, None, False),  # unnecessary
    ("rt-backup-erpdb", "srv-backup-01", "srv-erp-db-01", "postgres", 5432, 30, None, True),
    ("rt-backup-hrdb", "srv-backup-01", "srv-hr-db-01", "mssql", 1433, 30, None, True),
    ("rt-file-backup", "srv-file-01", "srv-backup-01", "smb", 445, 30, None, False),
    # CCTV / OT
    ("rt-cams-nvr", "grp:cctv-cams", "srv-nvr-01", "rtsp", 554, 2600000, None, True),
    ("rt-vms-nvr", "srv-vms-01", "srv-nvr-01", "https-api", 8443, 44000, None, True),
    ("rt-cams-corp", "grp:cctv-cams", "grp:corp-users", "any", 0, 0, None, False),  # flat-network leftover
    ("rt-printers-file", "grp:printers", "srv-file-01", "smb", 445, 300, None, False),
    ("rt-hist-file", "srv-ot-hist-01", "srv-file-01", "smb", 445, 720, None, False),
]

# Synthetic findings: (host, service, cvss, epss, kev, summary)
FINDINGS: List[Tuple[str, str, float, float, bool, str]] = [
    ("srv-web-01", "https", 8.1, 0.42, False, "Deserialisation flaw in portal framework"),
    ("srv-vpn-01", "https", 9.8, 0.91, True, "Pre-auth path traversal on gateway"),
    ("srv-mail-01", "smtp", 6.5, 0.08, False, "Header injection in relay"),
    ("srv-erp-app-01", "https-api", 7.5, 0.21, False, "IDOR in ERP API"),
    ("srv-erp-app-01", "https", 5.3, 0.05, False, "Weak session fixation control"),
    ("srv-erp-db-01", "postgres", 8.8, 0.33, False, "Outdated DB engine with auth bypass"),
    ("srv-hr-db-01", "mssql", 7.2, 0.12, False, "Default service account password"),
    ("srv-jump-01", "ssh", 7.4, 0.36, False, "Weak SSH key exchange + password auth"),
    ("srv-jump-01", "rdp", 8.1, 0.55, True, "RDP pre-auth memory corruption"),
    ("srv-file-01", "smb", 8.8, 0.62, True, "SMB signing disabled; relay possible"),
    ("srv-ci-01", "https", 8.6, 0.40, False, "Unauthenticated pipeline trigger"),
    ("srv-ci-01", "ssh", 6.0, 0.06, False, "Shared deploy key"),
    ("srv-dc-01", "ldap", 6.8, 0.15, False, "LDAP signing not enforced"),
    ("srv-dc-01", "kerberos", 5.9, 0.10, False, "Kerberoastable service principals"),
    ("srv-vms-01", "https", 9.1, 0.71, True, "Auth bypass in video management UI"),
    ("srv-nvr-01", "rtsp", 7.5, 0.30, False, "RTSP buffer overflow"),
    ("srv-print-01", "ipp", 7.0, 0.25, False, "Print spooler privilege escalation"),
    ("grp:corp-users", "any", 6.5, 0.20, False, "Unpatched browser fleet (aggregate)"),
]


def _hosts(rng: random.Random) -> List[Dict[str, Any]]:
    hosts: List[Dict[str, Any]] = []
    for gid, (prefix, size, role) in GROUPS.items():
        base = prefix.split("/")[0].rsplit(".", 2)[0]
        for i in range(size):
            hosts.append(
                {
                    "id": f"{gid.split(':')[1]}-{i + 1:03d}",
                    "address": f"{base}.{rng.randint(1, 250)}.{i + 2}",
                    "group": gid,
                    "role": role,
                    "quarantined": False,
                }
            )
    for sid, (addr, segment, role) in SERVERS.items():
        hosts.append({"id": sid, "address": addr, "group": f"seg:{segment}", "role": role, "quarantined": False})
    return hosts


def build() -> Tuple[Dict[str, Any], Dict[str, Any]]:
    rng = random.Random(SEED)
    hosts = _hosts(rng)

    stlinks = [
        {"id": f"stlink-{sid}", "endpoint": SERVERS[sid][0], "status": "active", "host": sid}
        for sid in ("srv-erp-db-01", "srv-hr-db-01", "srv-dc-01", "srv-pki-01", "srv-nvr-01", "srv-jump-01")
    ]

    def prefix_of(node: str) -> str:
        if node in GROUPS:
            return GROUPS[node][0]
        if node in SERVERS:
            return f"{SERVERS[node][0]}/32"
        return "0.0.0.0/0"

    def size_of(node: str) -> int:
        return GROUPS[node][1] if node in GROUPS else 1

    routes = []
    for rid, src, dst, svc, port, used, narrow_to, sealed in ROUTES:
        routes.append(
            {
                "id": rid,
                "source": src,
                "target": dst,
                "service": svc,
                "port": port,
                "prefix": prefix_of(src),
                "source_size": size_of(src),
                "status": "active",
                "narrow_to": None,
                "narrow_candidate": narrow_to,
                "observed_sessions_30d": used,
                "sealed_tunnel": sealed,
            }
        )

    vulns = []
    for i, (host, svc, cvss, epss, kev, summary) in enumerate(FINDINGS, start=1):
        sev = "critical" if cvss >= 9.0 else "high" if cvss >= 7.0 else "medium"
        vulns.append(
            {
                "id": f"SYN-2026-{i:04d}",
                "host": host,
                "component": host,
                "service": svc,
                "cvss": cvss,
                "epss": epss,
                "kev": kev,
                "severity": sev,
                "summary": summary,
            }
        )

    scenario = {
        "scenario_id": "enterprise_200",
        "description": "Synthetic 200-host enterprise for Cortex CyberTwin range (all data synthetic)",
        "stlinks": stlinks,
        "routes": routes,
        "hosts": hosts,
        "sessions": [
            {"id": "sess-da-jump", "user": "svc-domain-admin", "host": "srv-jump-01", "active": True},
            {"id": "sess-ci-deploy", "user": "svc-ci-deploy", "host": "srv-ci-01", "active": True},
        ],
        "vulnerabilities": vulns,
    }

    mission = {
        "mission_id": "enterprise_200_continuity",
        "footholds": ["ext:internet", "grp:corp-users"],
        "protected_assets": {
            "srv-erp-db-01": "Financial system of record",
            "srv-hr-db-01": "Personnel records",
            "srv-dc-01": "Enterprise identity",
            "srv-pki-01": "Certificate authority",
            "srv-nvr-01": "CCTV evidence store",
            "srv-backup-01": "Recovery capability",
        },
        "required_flows": [
            {"id": "F-WEB", "app": "app:public-web", "route": "rt-inet-web"},
            {"id": "F-VPN", "app": "app:remote-access", "route": "rt-inet-vpn"},
            {"id": "F-VPN-LAN", "app": "app:remote-access", "route": "rt-vpn-users"},
            {"id": "F-MAIL", "app": "app:email", "route": "rt-inet-mail"},
            {"id": "F-API", "app": "app:erp", "route": "rt-inet-api"},
            {"id": "F-ERP-UI", "app": "app:erp", "route": "rt-users-erp"},
            {"id": "F-ERP-WEB", "app": "app:erp", "route": "rt-web-erp"},
            {"id": "F-ERP-DB", "app": "app:erp", "route": "rt-erp-erpdb"},
            {"id": "F-HR-UI", "app": "app:hr", "route": "rt-users-hr"},
            {"id": "F-HR-DB", "app": "app:hr", "route": "rt-hr-hrdb"},
            {"id": "F-AUTH", "app": "app:identity", "route": "rt-users-dc"},
            {"id": "F-FILE", "app": "app:file-share", "route": "rt-users-file"},
            {"id": "F-LOGS", "app": "app:security-monitoring", "route": "rt-users-siem"},
            {"id": "F-ADMIN", "app": "app:operations", "route": "rt-admins-jump"},
            {"id": "F-ADMIN-DC", "app": "app:operations", "route": "rt-jump-dc"},
            {"id": "F-GIT", "app": "app:devops", "route": "rt-eng-git"},
            {"id": "F-CI-GIT", "app": "app:devops", "route": "rt-ci-git"},
            {"id": "F-BACKUP-ERP", "app": "app:backup", "route": "rt-backup-erpdb"},
            {"id": "F-BACKUP-HR", "app": "app:backup", "route": "rt-backup-hrdb"},
            {"id": "F-CCTV-INGEST", "app": "app:cctv", "route": "rt-cams-nvr"},
            {"id": "F-CCTV-VMS", "app": "app:cctv", "route": "rt-vms-nvr"},
        ],
        # Identity exposure XiiD route policy cannot fix (requires identity remediation).
        "identity_edges": [
            {"source": "srv-jump-01", "target": "srv-dc-01", "kind": "cached_domain_admin", "p": 0.45},
            {"source": "srv-ci-01", "target": "srv-erp-app-01", "kind": "deploy_key_reuse", "p": 0.30},
            {"source": "srv-dc-01", "target": "srv-erp-db-01", "kind": "domain_control", "p": 0.85},
            {"source": "srv-dc-01", "target": "srv-hr-db-01", "kind": "domain_control", "p": 0.85},
            {"source": "srv-dc-01", "target": "srv-file-01", "kind": "domain_control", "p": 0.85},
            {"source": "srv-dc-01", "target": "srv-backup-01", "kind": "domain_control", "p": 0.85},
        ],
        "applications": APPLICATIONS,
    }
    return scenario, mission


def write() -> None:
    scenario, mission = build()
    header = "# GENERATED by range/enterprise/generator.py - do not edit by hand. All data synthetic.\n"
    SCENARIO_PATH.write_text(header + yaml.safe_dump(scenario, sort_keys=False), encoding="utf-8")
    MISSION_PATH.write_text(header + yaml.safe_dump(mission, sort_keys=False), encoding="utf-8")


if __name__ == "__main__":
    write()
    print(f"wrote {SCENARIO_PATH.relative_to(ROOT)} and {MISSION_PATH.relative_to(ROOT)}")
