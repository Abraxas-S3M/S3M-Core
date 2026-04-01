"""Simulation interoperability pipeline orchestrating chunk-10 adapters."""

from __future__ import annotations

from typing import Any

from packages.providers.sim_ardupilot_sitl.adapter import ArduPilotSITLAdapter
from packages.providers.sim_dronekit.adapter import DroneKitAdapter
from packages.providers.sim_hla.adapter import HLAAdapter
from packages.providers.sim_sensorthings.adapter import SensorThingsAdapter


class SimulationInteropPipeline:
    """Coordinates HLA, SensorThings, SITL, and DroneKit in simulation-only mode."""

    def __init__(self):
        self.hla = HLAAdapter(mode="airgapped")
        self.sensorthings = SensorThingsAdapter(mode="airgapped")
        self.sitl = ArduPilotSITLAdapter(mode="airgapped")
        self.dronekit = DroneKitAdapter(mode="airgapped")
        self.providers = {
            "sim-hla": self.hla,
            "sim-sensorthings": self.sensorthings,
            "sim-ardupilot-sitl": self.sitl,
            "sim-dronekit": self.dronekit,
        }

    def start_joint_exercise(self, federation_name: str, vehicle_type: str = "copter") -> dict[str, Any]:
        self.hla.validate_credentials()
        self.hla.create_federation(name=federation_name)
        self.hla.join_federation(federation_name=federation_name, federate_name="S3M_Federate")

        self.sitl.validate_credentials()
        self.sitl.connect()
        self.sitl._vehicle_type = vehicle_type  # stub field selection for scenario profile

        self.dronekit.validate_credentials()
        self.dronekit.connect()

        registered = [
            self.sensorthings.register_s3m_sensor("ground_radar", "Radar Alpha", (24.71, 46.68, 612.0)),
            self.sensorthings.register_s3m_sensor("weather_station", "Weather Bravo", (24.72, 46.69, 614.0)),
        ]
        return {
            "federation": federation_name,
            "sitl_connected": True,
            "dronekit_connected": True,
            "sensors_registered": len(registered),
        }

    def run_test_scenario(self, scenario: str) -> dict[str, Any]:
        scenario_result = self.dronekit.execute_test_scenario(scenario)
        telemetry = self.sitl.get_telemetry()
        self.hla.publish_entity(
            entity_type="Aircraft",
            entity_name="SITL_Vehicle_01",
            position=(float(telemetry["lat"]), float(telemetry["lon"]), float(telemetry["alt"])),
            velocity=(float(telemetry["groundspeed"]), 0.0, 0.0),
            force_id=1,
        )
        sensor_observation = self.sensorthings.publish_observation(
            datastream_id="thing-001-target_range_km",
            value=12.5,
        )
        return {
            "scenario": scenario_result["scenario"],
            "completed": scenario_result["completed"],
            "hla_entities_published": self.hla.get_federation_status()["published_objects"],
            "sensor_observations": 1 if sensor_observation["published"] else 0,
            "events": scenario_result["events"],
        }

    def bridge_dis_to_hla(self, exercise_id: int | None = None) -> dict[str, Any]:
        dis_entities = {
            "1-1-101": {
                "entity_id": "101",
                "entity_type": "Aircraft",
                "position": {"lat": 24.71, "lon": 46.68, "alt": 620.0},
                "velocity": {"x": 18.0, "y": 0.0, "z": 0.0},
                "affiliation": "friendly",
                "marking": "DIS_BLUE_101",
            },
            "1-1-202": {
                "entity_id": "202",
                "entity_type": "GroundVehicle",
                "position": {"lat": 24.73, "lon": 46.70, "alt": 610.0},
                "velocity": {"x": 5.0, "y": 0.0, "z": 0.0},
                "affiliation": "hostile",
                "marking": "DIS_RED_202",
            },
        }
        bridged = self.hla.sync_from_phase16_dis(dis_entities)
        return {
            "exercise_id": exercise_id if exercise_id is not None else 1,
            "dis_entities": len(dis_entities),
            "hla_published": bridged,
            "bridged_count": bridged,
        }

    def get_simulation_status(self) -> dict[str, Any]:
        return {
            "sim-hla": self.hla.get_federation_status(),
            "sim-ardupilot-sitl": self.sitl.get_telemetry(),
            "sim-dronekit": self.dronekit.health_check(),
            "sim-sensorthings": self.sensorthings.health_check(),
            "hla": self.hla.get_federation_status(),
            "ardupilot_sitl": self.sitl.get_telemetry(),
            "dronekit": self.dronekit.health_check(),
            "sensorthings": self.sensorthings.health_check(),
        }

    def health_check(self) -> dict[str, Any]:
        provider_health = {pid: provider.health_check() for pid, provider in self.providers.items()}
        provider_health.update(
            {
                "hla": provider_health["sim-hla"],
                "ardupilot_sitl": provider_health["sim-ardupilot-sitl"],
                "dronekit": provider_health["sim-dronekit"],
                "sensorthings": provider_health["sim-sensorthings"],
            }
        )
        return {"status": "ok", "providers": provider_health}
