"""Traffic Generation & Real-Time Log Simulation Engine.

Simulates normal operations, volumetric auth storms, sequence corruption,
and drift anomalies against the LogPulse AnomalyGuard ingestion pipeline.
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import sys
import time
from typing import Any

# Ensure repository root is on sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import httpx


# =============================================================================
# SCENARIO LOG GENERATORS
# =============================================================================
class TrafficProfile:
    """Generates synthetic log events according to specific operational profiles."""

    @staticmethod
    def normal_hdfs() -> list[str]:
        blk = f"-{random.randint(1000000000000000000, 9000000000000000000)}"
        ip = f"10.250.{random.randint(10, 50)}.{random.randint(1, 254)}"
        port = random.randint(50000, 59999)
        size = random.choice([67108864, 134217728, 91178, 268435456])
        return [
            f"081109 203518 143 INFO dfs.DataNode$DataXceiver: Receiving block blk_{blk} src: /{ip}:{port} dest: /{ip}:50010",
            f"081109 203519 145 INFO dfs.DataNode$PacketResponder: PacketResponder 1 for block blk_{blk} terminating",
            f"081109 203519 146 INFO dfs.DataNode$DataXceiver: Received block blk_{blk} of size {size} from /{ip}",
        ]

    @staticmethod
    def normal_bgl() -> list[str]:
        ts = int(time.time())
        rack = random.randint(1, 16)
        core = random.randint(1000, 9999)
        return [
            f"- {ts} 2005.06.03 R{rack:02d}-M1-N0-C:J12-U11 2005-06-03-15.42.50.675872 R{rack:02d}-M1-N0-C:J12-U11 RAS KERNEL INFO generating core.{core}",
            f"- {ts+1} 2005.06.03 R{rack:02d}-M1-N0-C:J12-U11 2005-06-03-15.42.51.102384 R{rack:02d}-M1-N0-C:J12-U11 RAS KERNEL INFO total of 0 ddr error(s) detected and corrected",
        ]

    @staticmethod
    def auth_storm() -> list[str]:
        ip = f"192.168.1.{random.randint(100, 250)}"
        user = random.choice(["admin", "root", "deploy", "postgres", "svc_account"])
        return [
            f"081109 203518 143 WARN auth.SecurityManager: Authentication failed for user {user} from {ip}: invalid password hash",
            f"081109 203519 144 ERROR auth.SecurityManager: Brute force rate limit exceeded for IP {ip}: 50 failed attempts in 3s",
            f"081109 203520 145 ERROR security.AccessController: Access denied to secret resource /vault/credentials/production_db for service auth_service",
        ]

    @staticmethod
    def sequence_corruption() -> list[str]:
        blk = f"-{random.randint(1000000000000000000, 9000000000000000000)}"
        return [
            f"081109 203519 145 INFO dfs.DataNode$PacketResponder: PacketResponder 2 for block blk_{blk} terminating",
            f"081109 203520 148 ERROR dfs.DataNode$DataXceiver: Verification failed for block blk_{blk} checksum mismatch on replica 1",
            f"081109 203521 149 ERROR dfs.DataNode$DataXceiver: Block blk_{blk} is corrupted. Exceeded max block read retries.",
            f"081109 203522 150 WARN dfs.DataNode$BlockScanner: Corrupted block blk_{blk} moved to bad_blocks quarantine.",
        ]

    @staticmethod
    def drift_surge() -> list[str]:
        shard = random.randint(1, 10)
        return [
            f"081109 203521 146 INFO k8s.NodeLifecycleController: Node worker-gpu-{shard}.cloud.internal cordoned due to KernelDeadlock condition",
            f"081109 203522 147 WARN envoy.mesh.proxy: Upstream cluster database_shard_{shard} circuit breaker tripped with 503 response",
            f"081109 203523 148 ERROR telemetry.otel.exporter: Collector endpoint unreachable at grpc://otel-collector:4317: deadline exceeded",
            f"- 1117838573 2005.06.03 R02-M1-N0-C:J12-U11 2005-06-03-15.42.53.882910 R02-M1-N0-C:J12-U11 RAS HARDWARE ERROR card unresponsive",
        ]


class TrafficGenerator:
    """Configurable load and anomaly injector targeting FastAPI log ingestion endpoints."""

    def __init__(self, target_url: str = "http://localhost:8000/api/v1/ingest/stream") -> None:
        self.target_url = target_url

    def generate_batch(self, profile: str, batch_size: int) -> list[str]:
        """Generate a batch of raw log strings according to the requested profile."""
        profile_lower = profile.lower()
        events: list[str] = []

        while len(events) < batch_size:
            if profile_lower == "normal":
                choice = random.choice([TrafficProfile.normal_hdfs, TrafficProfile.normal_bgl])
                events.extend(choice())
            elif profile_lower == "auth_storm":
                events.extend(TrafficProfile.auth_storm())
            elif profile_lower == "sequence_corruption":
                events.extend(TrafficProfile.sequence_corruption())
            elif profile_lower == "drift_surge":
                events.extend(TrafficProfile.drift_surge())
            elif profile_lower == "mixed":
                roll = random.random()
                if roll < 0.75:
                    choice = random.choice([TrafficProfile.normal_hdfs, TrafficProfile.normal_bgl])
                    events.extend(choice())
                elif roll < 0.85:
                    events.extend(TrafficProfile.auth_storm())
                elif roll < 0.95:
                    events.extend(TrafficProfile.sequence_corruption())
                else:
                    events.extend(TrafficProfile.drift_surge())
            else:
                events.extend(TrafficProfile.normal_hdfs())

        return events[:batch_size]

    def run(
        self,
        rate_eps: int = 50,
        duration_sec: int = 10,
        batch_size: int = 20,
        profile: str = "mixed",
        dry_run: bool = False,
        in_process: bool = False,
    ) -> dict[str, Any]:
        """Run continuous injection loop with rate throttling and telemetry."""
        total_logs = 0
        total_batches = 0
        failed_batches = 0
        latencies_ms: list[float] = []

        # Target batch interval
        batch_size = max(1, min(batch_size, 500))
        batches_per_sec = max(1.0, rate_eps / batch_size)
        interval_sec = 1.0 / batches_per_sec

        client = None
        if not dry_run:
            if in_process:
                from fastapi.testclient import TestClient
                from src.api.main import app
                client = TestClient(app)
            else:
                client = httpx.Client(timeout=10.0)

        start_time = time.perf_counter()
        print(
            f"Starting Traffic Generator: Profile='{profile}', Rate={rate_eps} EPS, "
            f"BatchSize={batch_size}, Duration={duration_sec}s, Mode={'DRY_RUN' if dry_run else ('IN_PROCESS' if in_process else 'REMOTE_HTTP')}"
        )

        try:
            while True:
                elapsed = time.perf_counter() - start_time
                if duration_sec > 0 and elapsed >= duration_sec:
                    break

                batch_start = time.perf_counter()
                batch_logs = self.generate_batch(profile, batch_size)

                if dry_run:
                    # In dry-run mode, simulate generation time
                    total_logs += len(batch_logs)
                    total_batches += 1
                    latencies_ms.append(0.05)
                else:
                    # Send payload to API
                    try:
                        req_start = time.perf_counter()
                        if in_process:
                            res = client.post(
                                "/api/v1/ingest/stream",
                                json={"source_id": f"sim_{profile}", "lines": batch_logs},
                            )
                        else:
                            res = client.post(
                                self.target_url,
                                json={"source_id": f"sim_{profile}", "lines": batch_logs},
                            )
                        req_duration = (time.perf_counter() - req_start) * 1000.0
                        latencies_ms.append(req_duration)

                        if res.status_code == 200:
                            total_logs += len(batch_logs)
                            total_batches += 1
                        else:
                            failed_batches += 1
                    except Exception as exc:
                        failed_batches += 1
                        print(f"\n[ERROR] Request failed: {exc}", file=sys.stderr)

                # Maintain rate control
                batch_duration = time.perf_counter() - batch_start
                sleep_time = interval_sec - batch_duration
                if sleep_time > 0:
                    time.sleep(sleep_time)

                # Live ticker in console
                cur_elapsed = time.perf_counter() - start_time
                current_eps = total_logs / cur_elapsed if cur_elapsed > 0 else 0
                avg_lat = sum(latencies_ms) / len(latencies_ms) if latencies_ms else 0.0
                sys.stdout.write(
                    f"\r[Telemetry] Elapsed: {cur_elapsed:5.1f}s | Logs Sent: {total_logs:7,d} | "
                    f"Throughput: {current_eps:6.1f} EPS | Avg Lat: {avg_lat:5.1f}ms | Failures: {failed_batches}"
                )
                sys.stdout.flush()

        except KeyboardInterrupt:
            print("\nSimulation aborted by user.")
        finally:
            if client and not in_process:
                client.close()

        total_elapsed = time.perf_counter() - start_time
        final_eps = total_logs / total_elapsed if total_elapsed > 0 else 0.0
        avg_latency = sum(latencies_ms) / len(latencies_ms) if latencies_ms else 0.0
        p95_latency = (
            sorted(latencies_ms)[int(len(latencies_ms) * 0.95)]
            if latencies_ms
            else 0.0
        )

        summary = {
            "profile": profile,
            "duration_sec": round(total_elapsed, 2),
            "total_logs": total_logs,
            "total_batches": total_batches,
            "failed_batches": failed_batches,
            "achieved_eps": round(final_eps, 1),
            "avg_latency_ms": round(avg_latency, 2),
            "p95_latency_ms": round(p95_latency, 2),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        print("\n" + "=" * 65)
        print(" Traffic Simulation Run Completed")
        print("=" * 65)
        print(f" Profile:             {summary['profile']}")
        print(f" Total Logs Sent:     {summary['total_logs']:,}")
        print(f" Duration:            {summary['duration_sec']}s")
        print(f" Achieved Throughput: {summary['achieved_eps']:,} EPS")
        print(f" Average Latency:     {summary['avg_latency_ms']} ms")
        print(f" P95 Latency:         {summary['p95_latency_ms']} ms")
        print(f" Failed Batches:      {summary['failed_batches']}")
        print("=" * 65)

        return summary


def main():
    """Command-line interface entrypoint."""
    parser = argparse.ArgumentParser(description="LogPulse Real-Time Traffic & Anomaly Generator")
    parser.add_argument("--rate", type=int, default=50, help="Target ingestion rate (Events Per Second)")
    parser.add_argument("--duration", type=int, default=10, help="Simulation duration in seconds (0 for infinite)")
    parser.add_argument("--batch-size", type=int, default=20, help="Log line count per HTTP batch")
    parser.add_argument(
        "--profile",
        type=str,
        default="mixed",
        choices=["normal", "auth_storm", "sequence_corruption", "drift_surge", "mixed"],
        help="Operational traffic profile to simulate",
    )
    parser.add_argument("--target-url", type=str, default="http://localhost:8000/api/v1/ingest/stream")
    parser.add_argument("--dry-run", action="store_true", help="Generate logs locally without network transmission")
    parser.add_argument("--in-process", action="store_true", help="Use in-process FastAPI TestClient without external uvicorn")
    parser.add_argument("--output-json", type=str, default="", help="Optional JSON path to save benchmark statistics")

    args = parser.parse_args()

    gen = TrafficGenerator(target_url=args.target_url)
    stats = gen.run(
        rate_eps=args.rate,
        duration_sec=args.duration,
        batch_size=args.batch_size,
        profile=args.profile,
        dry_run=args.dry_run,
        in_process=args.in_process,
    )

    if args.output_json:
        with open(args.output_json, "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2)
        print(f"Saved run summary to: {args.output_json}")


if __name__ == "__main__":
    main()
