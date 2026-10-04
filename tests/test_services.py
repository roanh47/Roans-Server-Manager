"""Attributing a process to its systemd unit or container via /proc/<pid>/cgroup."""

from __future__ import annotations

from servermanager.collectors.services import (
    KIND_CONTAINER,
    KIND_SERVICE,
    KIND_UNKNOWN,
    KIND_UNMANAGED,
    KIND_USER,
    parse_cgroup,
)


class TestParseCgroup:
    def test_systemd_service(self):
        owner = parse_cgroup("0::/system.slice/ssh.service\n")
        assert owner == {"kind": KIND_SERVICE, "name": "ssh.service"}

    def test_nested_systemd_service(self):
        owner = parse_cgroup("0::/system.slice/system-getty.slice/getty@tty1.service\n")
        assert owner["kind"] == KIND_SERVICE
        assert owner["name"] == "getty@tty1.service"

    def test_docker_container(self):
        owner = parse_cgroup("0::/system.slice/docker-abc123def456.scope\n")
        assert owner["kind"] == KIND_CONTAINER

    def test_cgroup_v1_docker(self):
        owner = parse_cgroup("11:memory:/docker/9b1deb4d3b7d4bad9bdd2b0d7b3dcb6d\n")
        assert owner["kind"] == KIND_CONTAINER

    def test_containerd_scope(self):
        assert parse_cgroup("0::/system.slice/containerd.service/crio-abc\n")["kind"] == KIND_CONTAINER

    def test_user_session(self):
        owner = parse_cgroup("0::/user.slice/user-1000.slice/session-3.scope\n")
        assert owner["kind"] == KIND_USER

    def test_unmanaged_process(self):
        owner = parse_cgroup("0::/\n")
        assert owner["kind"] == KIND_UNMANAGED

    def test_empty_file_is_unknown(self):
        assert parse_cgroup("")["kind"] == KIND_UNKNOWN
        assert parse_cgroup("\n\n")["kind"] == KIND_UNKNOWN

    def test_real_file_for_this_process_is_readable(self):
        import os

        from servermanager.collectors.services import resolve_owner

        owner = resolve_owner(os.getpid())
        assert owner["kind"] in (KIND_SERVICE, KIND_CONTAINER, KIND_USER, KIND_UNMANAGED, KIND_UNKNOWN)

    def test_missing_process_is_unknown(self):
        from servermanager.collectors.services import resolve_owner

        assert resolve_owner(999_999_999)["kind"] == KIND_UNKNOWN
