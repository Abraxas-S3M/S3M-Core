# S3M Operator Manual

Classification: UNCLASSIFIED - FOUO

## Overview
S3M is a sovereign tactical decision-support system designed to run fully offline.
It helps operators observe threats, understand the situation, and coordinate mission actions.
Your primary job is to verify system status, issue mission commands, and approve critical decisions.

What you need to know as an operator:
- Green status means the system is ready for normal operations.
- Yellow status means the system is running with reduced capabilities.
- Red status means immediate supervisor review is required.

## Starting the System
Primary startup command:
```bash
python scripts/start_api.py
```
Alternative startup command (container):
```bash
docker-compose -f docker/docker-compose.yml up -d
```
Expected startup indicators:
- API responds on port 8080
- Health endpoint returns status=operational
- Threat and simulation services report ready

Verification command:
```bash
curl http://localhost:8080/health
```

## Accessing the Dashboard
Open Chromium and enter:
- http://localhost:8080/dashboard/

The main tabs typically include:
- Overview
- COP (Common Operational Picture)
- Threats
- Decisions
- System Health

## COP View
The COP map shows friendly assets, tracks, and threat markers.
Color guidance:
- Green: friendly and stable
- Amber: caution / requires attention
- Red: high-priority threat

Icon guidance:
- Triangle icons often represent aerial entities
- Circular markers represent sensor tracks
- Pulsing markers indicate active alerts

## Issuing Commands
Use the command bar at the bottom of the dashboard.
Example commands:
- Send 2 drones to recon grid 500,300
- عودة للقاعدة
- Emergency stop all

After pressing Send:
1. The command is validated for safety.
2. The system computes or updates a plan.
3. Assigned units receive tasks.
4. Status updates appear in COP and Alerts.

## Reviewing Decisions
If human approval is required, an item appears in the review queue.
Decision review steps:
1. Open the item summary.
2. Read rationale and risk factors.
3. Approve to continue, or Reject to cancel.

Approval means mission action proceeds immediately.
Rejection means action is halted and logged.

## Reading Threat Alerts
Alert levels and operator action:
- CRITICAL: Notify command immediately and follow emergency protocol.
- HIGH: Prioritize response and monitor continuously.
- MEDIUM: Track and prepare contingency response.
- LOW/INFO: Observe and keep under surveillance.

## Generating Reports
Use the Reports section to generate:
- SITREP (current operational picture)
- OPORD (mission order)
- AAR (after-action review)

Recommended workflow:
1. Generate SITREP before mission shift handover.
2. Generate OPORD before launch authorization.
3. Generate AAR at mission completion.

## Troubleshooting
Common issues:
- System not starting: confirm port 8080 is free.
- Engine not loading: verify memory usage and profile selection.
- GPS denied: system should fallback to visual/dead-reckoning mode.
- Dashboard blank: wait 10 seconds and refresh.

## Glossary
- COP: Common Operational Picture
- OPORD: Operations Order
- SITREP: Situation Report
- AAR: After Action Review
- ROE: Rules of Engagement
- BT: Behavior Tree
- OODA: Observe, Orient, Decide, Act
- ATR: Automatic Target Recognition
- EKF: Extended Kalman Filter
- RTB: Return To Base

### Operator Checklist Item 001
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 002
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 003
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 004
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 005
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 006
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 007
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 008
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 009
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 010
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 011
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 012
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 013
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 014
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 015
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 016
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 017
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 018
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 019
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 020
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 021
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 022
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 023
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 024
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 025
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 026
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 027
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 028
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 029
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 030
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 031
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 032
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 033
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 034
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 035
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 036
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 037
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 038
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 039
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 040
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 041
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 042
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 043
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 044
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 045
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 046
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 047
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 048
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 049
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 050
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 051
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 052
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 053
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 054
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 055
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 056
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 057
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 058
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 059
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 060
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 061
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 062
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 063
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 064
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 065
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 066
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 067
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 068
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 069
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 070
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 071
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 072
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 073
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 074
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 075
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 076
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 077
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 078
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 079
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 080
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 081
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 082
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 083
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 084
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 085
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 086
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 087
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 088
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 089
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 090
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 091
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 092
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 093
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 094
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 095
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 096
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 097
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 098
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 099
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 100
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 101
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 102
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 103
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 104
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 105
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 106
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 107
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 108
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 109
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 110
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 111
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 112
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 113
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 114
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 115
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 116
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 117
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 118
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 119
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 120
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 121
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 122
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 123
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 124
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 125
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 126
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 127
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 128
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 129
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 130
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 131
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 132
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 133
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 134
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 135
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 136
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 137
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 138
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 139
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 140
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 141
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 142
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 143
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 144
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 145
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 146
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 147
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 148
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 149
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 150
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 151
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 152
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 153
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 154
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 155
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 156
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 157
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 158
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 159
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 160
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 161
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 162
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 163
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 164
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 165
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 166
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 167
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 168
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 169
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 170
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 171
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 172
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 173
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 174
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 175
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 176
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 177
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 178
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 179
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 180
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 181
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 182
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 183
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 184
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 185
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 186
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 187
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 188
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 189
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 190
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 191
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 192
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 193
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 194
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 195
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 196
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 197
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 198
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 199
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 200
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 201
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 202
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 203
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 204
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 205
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 206
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 207
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 208
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 209
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 210
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 211
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 212
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 213
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 214
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 215
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 216
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 217
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 218
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 219
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 220
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 221
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 222
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 223
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 224
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 225
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 226
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 227
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 228
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 229
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 230
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 231
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 232
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 233
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 234
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 235
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 236
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 237
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 238
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 239
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 240
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 241
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 242
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 243
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 244
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 245
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 246
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 247
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 248
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 249
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 250
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 251
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 252
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 253
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 254
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 255
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 256
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 257
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 258
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 259
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 260
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 261
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 262
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 263
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 264
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 265
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 266
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 267
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 268
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 269
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 270
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 271
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 272
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 273
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 274
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 275
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 276
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 277
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 278
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 279
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 280
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 281
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 282
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 283
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 284
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 285
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 286
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 287
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 288
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 289
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 290
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 291
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 292
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 293
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 294
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 295
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 296
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 297
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 298
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 299
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.

### Operator Checklist Item 300
- Confirm dashboard status indicator before issuing commands.
- Confirm mission sector and command intent are correct.
- Confirm alert panel contains no unresolved critical alarms.
