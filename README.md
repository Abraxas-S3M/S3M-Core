# S3M-Engine Integration Layer

S3M-Engine is the final integration layer that orchestrates packet intake, validation, routing, and cloud-CPU training execution for sovereign tactical AI adaptation.

## System Overview Diagram (ASCII)

```text
                                 +------------------------+
                                 | Cloudflare R2 Vault    |
                                 | datasets / artifacts   |
                                 +-----------+------------+
                                             |
                                             | vault health / sync metadata
                                             v
+------------------+      +------------------+      +----------------------+
| VaultCatalog     |      | R2Client         |      | PostgreSQL           |
| dataset registry |      | vault connector   |      | training_runs table  |
+---------+--------+      +---------+--------+      +----------+-----------+
          \                         |                          /
           \                        |                         /
            \                       |                        /
             \                      |                       /
              +---------------------v----------------------+
              |               Orchestrator                 |
              | (watcher thread + job monitor thread)      |
              +----------+-------------------+-------------+
                         |                   |
                         | validates         | queues jobs
                         v                   v
                +--------+---------+   +-----+-------------+
                | LabelValidator   |   | TrainRunner       |
                | checksum/schema  |   | executes jobs     |
                +--------+---------+   +-----+-------------+
                         |                   |
                         v                   v
                +--------+---------+   +-----+-------------+
                | PacketRouter     |   | TrainerRegistry   |
                | inbox -> tracks  |   | track -> trainer  |
                +--------+---------+   +-----+-------------+
                         |                   |
                         +---------+---------+
                                   v
                           +-------+--------+
                           | TrainerService |
                           | per track loop |
                           +----------------+
```

## Component Descriptions

- **Orchestrator (`src/pipeline/orchestrator.py`)**
  - Initializes all pipeline components.
  - Starts packet watcher and job monitor in parallel threads.
  - Provides unified `status()` and graceful `shutdown()`.

- **R2Client**
  - Validates Cloudflare R2 connector configuration.
  - Exposes tactical vault health for readiness checks.

- **VaultCatalog**
  - Loads dataset catalog metadata used in routing governance.

- **DB connection**
  - Connects to PostgreSQL with `DB_*` settings.
  - Ensures `training_runs` table exists for job lifecycle telemetry.

- **LabelValidator**
  - Uses packet checksum/schema validation before route admission.

- **TrainerRegistry**
  - Controls active training tracks and lazily instantiates trainer services.

- **PacketBuilder**
  - Builds and validates scenario packet structure and checksums.

- **PacketRouter**
  - Routes validated packets from inbox into per-track queues.

- **TrainRunner**
  - Manages queued training jobs, executes trainer cycles, and updates run status.

- **Health check script (`scripts/health_check.sh`)**
  - Produces operator-readable pass/fail readiness checks.

## Setup Instructions

1. Copy environment template:

   ```bash
   cp .env.example .env
   ```

2. Edit `.env` with local values for database, R2, and pipeline paths.

3. Create Python environment and install dependencies:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

4. Ensure pipeline directories exist:

   ```bash
   mkdir -p /opt/s3m/state/training/cloud_cpu/inbox
   mkdir -p /opt/s3m/state/training/staging
   mkdir -p /opt/s3m/packets
   mkdir -p /opt/s3m/logs
   ```

5. Run orchestrator:

   ```python
   from src.pipeline.orchestrator import Orchestrator

   orchestrator = Orchestrator()
   orchestrator.run()
   print(orchestrator.status())
   # ...
   orchestrator.shutdown()
   ```

6. Run health check:

   ```bash
   bash scripts/health_check.sh
   ```

## How to Add a New Scenario

Military/tactical context: packet integrity validation is mandatory so malformed or adversarial data cannot enter active training queues.

1. Prepare JSONL examples:

   ```json
   {"prompt":"Generate sector Bravo SITREP.","completion":"Sector Bravo secure; ISR coverage sustained."}
   {"prompt":"قدم تقريرًا موجزًا للقطاع ألف.","completion":"القطاع ألف مستقر مع استمرار المراقبة."}
   ```

2. Build packet(s):

   ```python
   from pathlib import Path
   from src.training.packet_builder import PacketBuilder

   builder = PacketBuilder(source="manual")
   packet_dirs = builder.build_from_jsonl(
       input_file=Path("scenario_data.jsonl"),
       track="saudi_mod",
       data_class="command",
       output_dir=Path("/opt/s3m/packets"),
       examples_per_pack=50,
   )
   ```

3. Move generated packet directories into inbox:

   ```bash
   mv /opt/s3m/packets/scenario-* /opt/s3m/state/training/cloud_cpu/inbox/
   ```

4. The watcher thread validates, routes, and queues jobs automatically.

## How to Trigger a Training Run Manually

### Method A: Through Orchestrator

1. Start orchestrator with `run()`.
2. Place valid packet directories into `INBOX_DIR`.
3. Observe queued/active jobs with:

   ```python
   orchestrator.status()
   ```

### Method B: Direct Trainer Cycle

```python
from src.training.cloud_cpu.paths import StatePaths, TrainingTrack
from src.training.cloud_cpu.trainer_service import TrainerService

paths = StatePaths("/opt/s3m/state/training/cloud_cpu")
trainer = TrainerService(track=TrainingTrack.SAUDI_MOD, paths=paths)
trainer.run_cycle_once()
print(trainer.get_status())
```

## Environment Variable Reference

| Variable | Description |
|---|---|
| `DB_HOST` | PostgreSQL host |
| `DB_PORT` | PostgreSQL port |
| `DB_NAME` | PostgreSQL database |
| `DB_USER` | PostgreSQL username |
| `DB_PASS` | PostgreSQL password |
| `R2_BUCKET` | Cloudflare R2 bucket name |
| `R2_ENDPOINT` | Cloudflare R2 endpoint URL |
| `R2_ACCESS_KEY` | R2 access key |
| `R2_SECRET_KEY` | R2 secret key |
| `RUNPOD_API_KEY` | RunPod API key |
| `RUNPOD_ENDPOINT_ID` | RunPod endpoint ID |
| `S3M_ENV` | Runtime environment label |
| `S3M_ROOT` | Root pipeline directory |
| `INBOX_DIR` | Packet inbox directory |
| `PACKETS_DIR` | Built packets directory |
| `STAGING_DIR` | Staging/snapshot directory |
| `LOG_DIR` | Log directory |
| `POLL_INTERVAL` | Watcher/monitor poll interval (seconds) |
| `EXAMPLES_PER_PACK` | Default examples per generated packet |
