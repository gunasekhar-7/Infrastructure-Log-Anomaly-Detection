"""Unit Tests for Traffic Simulator and Synthetic Workload Engine."""


from scripts.generate_traffic import TrafficGenerator, TrafficProfile


def test_traffic_profiles_generate_valid_logs():
    """Verify each profile produces formatted log strings with required markers."""
    hdfs_logs = TrafficProfile.normal_hdfs()
    assert len(hdfs_logs) >= 2
    assert any("Receiving block" in log for log in hdfs_logs)
    assert any("blk_" in log for log in hdfs_logs)

    bgl_logs = TrafficProfile.normal_bgl()
    assert len(bgl_logs) >= 2
    assert any("RAS KERNEL" in log for log in bgl_logs)

    auth_logs = TrafficProfile.auth_storm()
    assert len(auth_logs) >= 2
    assert any("Authentication failed" in log or "Brute force" in log for log in auth_logs)

    corrupt_logs = TrafficProfile.sequence_corruption()
    assert len(corrupt_logs) >= 3
    assert any("Verification failed" in log or "corrupted" in log for log in corrupt_logs)

    drift_logs = TrafficProfile.drift_surge()
    assert len(drift_logs) >= 3
    assert any("circuit breaker" in log or "KernelDeadlock" in log for log in drift_logs)


def test_generator_batch_sizing():
    """Verify batch generator produces exact requested counts across all profile options."""
    gen = TrafficGenerator()
    for profile in ["normal", "auth_storm", "sequence_corruption", "drift_surge", "mixed"]:
        batch = gen.generate_batch(profile=profile, batch_size=15)
        assert len(batch) == 15
        assert all(isinstance(line, str) and len(line) > 10 for line in batch)


def test_generator_dry_run():
    """Verify generator dry-run calculates throughput and completes without network calls."""
    gen = TrafficGenerator()
    stats = gen.run(
        rate_eps=100,
        duration_sec=1,
        batch_size=20,
        profile="mixed",
        dry_run=True,
    )
    assert stats["failed_batches"] == 0
    assert stats["total_logs"] > 0
    assert stats["achieved_eps"] > 0.0
    assert stats["profile"] == "mixed"


def test_generator_in_process_execution():
    """Verify generator can drive end-to-end ingestion into the in-process FastAPI application."""
    gen = TrafficGenerator()
    stats = gen.run(
        rate_eps=30,
        duration_sec=1,
        batch_size=10,
        profile="sequence_corruption",
        dry_run=False,
        in_process=True,
    )
    assert stats["failed_batches"] == 0
    assert stats["total_logs"] >= 10
    assert stats["profile"] == "sequence_corruption"

