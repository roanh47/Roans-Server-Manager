"""Live smoke tests: the collectors must describe the machine they run on.

These read the real host. They assert shape and self-consistency, never specific
values, so they pass on any Linux box.
"""

from __future__ import annotations

import pytest

from servermanager.collectors import containers, ports, processes, services, system

KNOWN_SCOPES = {"localhost", "tailscale", "lan", "container", "link-local", "public", "other"}


class TestSystem:
    def test_snapshot_is_about_a_machine(self, settings):
        snap = system.snapshot(settings)
        assert snap["hostname"]
        assert snap["cpu_count"] >= 1
        assert 0.0 <= snap["cpu_percent"] <= 100.0 * max(1, snap["cpu_count"])
        assert snap["memory"]["total_bytes"] > 0
        assert snap["uptime_seconds"] >= 0
        assert isinstance(snap["disks"], list)
        assert snap["error"] is None

    def test_server_name_comes_from_the_environment(self):
        from servermanager.config import Settings

        snap = system.snapshot(Settings.from_env({"SM_SERVER_NAME": "testbox"}))
        assert snap["server_name"] == "testbox"


class TestProcesses:
    def test_snapshot_has_rows_and_a_limit(self, settings):
        snap = processes.snapshot(settings, limit=5)
        assert snap["count"] >= 1  # at least this pytest process
        assert len(snap["processes"]) <= 5
        first = snap["processes"][0]
        assert first["pid"] > 0
        assert first["name"]
        assert first["owner_kind"] in ("service", "container", "user", "unmanaged", "unknown")

    def test_sorted_by_cpu_then_memory(self, settings):
        rows = processes.snapshot(settings, limit=25)["processes"]
        keys = [(r["cpu_percent"], r["rss_bytes"]) for r in rows]
        assert keys == sorted(keys, reverse=True)


class TestPorts:
    def test_every_row_has_a_known_scope(self, settings):
        snap = ports.snapshot(settings)
        assert snap["summary"]["total"] == len(snap["ports"])
        for row in snap["ports"]:
            assert row["scope"] in KNOWN_SCOPES, row
            assert 1 <= row["port"] <= 65535
            assert row["protocol"] in ("tcp", "udp")
            assert isinstance(row["exposed"], bool)

    def test_exposed_rows_are_counted(self, settings):
        snap = ports.snapshot(settings)
        assert snap["summary"]["exposed"] == sum(1 for r in snap["ports"] if r["exposed"])

    def test_exposed_first(self, settings):
        rows = ports.snapshot(settings)["ports"]
        flags = [r["exposed"] for r in rows]
        assert flags == sorted(flags, reverse=True)

    def test_loopback_rows_carry_a_meaning(self, settings):
        for row in ports.snapshot(settings)["ports"]:
            assert row["note"]
            if row["scope"] == "localhost":
                assert row["exposed"] is False


class TestServices:
    def test_snapshot_groups_without_raising(self, settings):
        snap = services.snapshot(settings)
        assert isinstance(snap["units"], list)
        assert snap["container_processes"] >= 0
        for unit in snap["units"]:
            assert unit["name"]
            assert unit["process_count"] >= 1
            assert unit["kind"] in ("service", "container", "user", "unmanaged", "unknown")

    def test_containers_are_excluded_from_units(self, settings):
        snap = services.snapshot(settings)
        assert all(unit["kind"] != "container" for unit in snap["units"])


class TestContainers:
    def test_snapshot_reports_instead_of_raising(self, settings):
        snap = containers.snapshot(settings)
        assert isinstance(snap["containers"], list)
        assert snap["count"] == len(snap["containers"])
        if snap["error"] is None:
            for row in snap["containers"]:
                assert row["name"]
                assert isinstance(row["running"], bool)
                assert isinstance(row["ports"], list)
        else:
            assert "docker" in snap["error"].lower()

    def test_missing_socket_is_an_error_not_a_crash(self):
        from servermanager.config import Settings

        snap = containers.snapshot(Settings.from_env({"SM_DOCKER_SOCKET": "/nonexistent/docker.sock"}))
        assert snap["containers"] == []
        assert snap["error"]


@pytest.mark.parametrize("collector", ["system", "processes", "ports", "services", "containers"])
def test_collectors_never_raise(collector, settings):
    module = {
        "system": system,
        "processes": processes,
        "ports": ports,
        "services": services,
        "containers": containers,
    }[collector]
    assert module.snapshot(settings) is not None
