#!/usr/bin/env python3
"""S3M Phase 14 end-to-end secure communications demo."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.comms import CommsManager
from services.comms.models import ChannelType, MessagePriority, NodeType, RelayBackend


def main() -> None:
    manager = CommsManager()

    # 1-2. Register nodes for command, field, relay, and autonomous assets.
    manager.register_node("COMMAND-ALPHA", NodeType.COMMAND_CENTER, [RelayBackend.SIMULATED], (0.0, 0.0, 0.0))
    manager.register_node("EAGLE-01", NodeType.UAV_PLATFORM, [RelayBackend.SIMULATED], (10.0, 20.0, 200.0))
    manager.register_node("EAGLE-02", NodeType.UAV_PLATFORM, [RelayBackend.SIMULATED], (12.0, 22.0, 210.0))
    manager.register_node("WOLF-01", NodeType.FIELD_UNIT, [RelayBackend.SIMULATED], (5.0, 8.0, 0.0))
    manager.register_node("WOLF-02", NodeType.FIELD_UNIT, [RelayBackend.SIMULATED], (6.0, 9.0, 0.0))
    manager.register_node("RELAY-01", NodeType.RELAY_NODE, [RelayBackend.SIMULATED], (7.0, 10.0, 0.0))

    # 3. Create primary channels.
    command_channel = manager.create_channel(
        "COMMAND-NET",
        ChannelType.COMMAND_NET,
        ["COMMAND-ALPHA", "EAGLE-01", "EAGLE-02", "WOLF-01", "WOLF-02"],
        backend=RelayBackend.SIMULATED,
    )
    intel_channel = manager.create_channel(
        "INTEL-NET",
        ChannelType.INTEL_NET,
        ["COMMAND-ALPHA", "WOLF-01", "WOLF-02"],
        backend=RelayBackend.SIMULATED,
    )
    alert_channel = manager.create_channel(
        "ALERT-NET",
        ChannelType.ALERT_NET,
        ["COMMAND-ALPHA", "EAGLE-01", "EAGLE-02", "WOLF-01", "WOLF-02", "RELAY-01"],
        backend=RelayBackend.SIMULATED,
    )
    print("Channels created:", [command_channel.channel_id, intel_channel.channel_id, alert_channel.channel_id])

    # 4. Send order.
    order_result = manager.send_order(
        sender="COMMAND-ALPHA",
        recipients=["EAGLE-01", "EAGLE-02"],
        order_text="Patrol sector Alpha, report all contacts",
        priority=MessagePriority.PRIORITY,
    )
    print("Order result:", order_result)

    # 5. English SITREP.
    sitrep_result = manager.send_sitrep(
        sender="WOLF-01",
        sitrep_text="Enemy infantry observed at grid 500,300. Estimated platoon strength.",
    )
    print("SITREP result:", sitrep_result)

    # 6. Arabic SITREP.
    ar_result = manager.send_message(
        sender_callsign="WOLF-02",
        recipients=["COMMAND-ALPHA"],
        body="رصد طائرة معادية بدون طيار في الشمال الشرقي. طلب دعم جوي.",
        message_type="SITREP",
        priority="IMMEDIATE",
        language="ar",
    )
    print("Arabic SITREP result:", ar_result)

    # 7. Broadcast flash alert.
    alert_result = manager.broadcast_alert(
        sender="COMMAND-ALPHA",
        alert_text="All units: IED threat on Route Bravo. Avoid grid 400-450.",
    )
    print("Alert result:", alert_result)

    # 8-9. Receive/display traffic with summaries and intel entities.
    print("\nRecent message traffic:")
    for channel in manager.get_channels():
        messages = manager.receive_messages(channel_id=channel.channel_id, backend=RelayBackend.SIMULATED)
        if not messages:
            continue
        print(f"\nChannel {channel.name} ({channel.channel_id})")
        for message in messages:
            intel = manager.intel_extractor.extract(message)
            print(
                {
                    "message_id": message.message_id,
                    "sender": message.sender_callsign,
                    "summary": message.summary,
                    "intent": message.extracted_intent,
                    "urgency": round(message.urgency_score, 3),
                    "entities": message.extracted_entities,
                    "intel": intel,
                }
            )

    # 10. Topology/backends.
    print("\nNetwork topology:")
    print(manager.node_manager.get_network_topology())
    print("\nBackend status:")
    print({k: v.value for k, v in manager.relay_manager.get_backend_status().items()})

    # 11. Comms brief.
    print("\nComms brief:")
    print(manager.get_comms_brief(minutes=120))

    # 12. Message statistics.
    print("\nMessage stats:")
    print(manager.relay_manager.get_message_stats())
    print(f"\nDemo completed at {datetime.now(timezone.utc).isoformat()}")


if __name__ == "__main__":
    main()
