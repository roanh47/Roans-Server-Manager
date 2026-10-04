"""Port parsing and, above all, bind-address classification.

The classification is the part of the panel that can be wrong in a way that
matters: call a public socket localhost and the page lies about your exposure.
"""

from __future__ import annotations

import os

from servermanager.collectors.ports import (
    SCOPE_CONTAINER,
    SCOPE_LAN,
    SCOPE_LINK_LOCAL,
    SCOPE_LOCALHOST,
    SCOPE_OTHER,
    SCOPE_PUBLIC,
    SCOPE_TAILSCALE,
    classify_binding,
    decode_address,
    decode_port,
    parse_proc_net,
    scan_inode_owners,
)

TCP_HEADER = (
    "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt"
    "   uid  timeout inode\n"
)


def tcp_row(local: str, state: str = "0A", uid: str = "1000", inode: str = "12345") -> str:
    return (
        f"   0: {local} 00000000:0000 {state} 00000000:00000000 00:00000000 00000000"
        f"  {uid}        0 {inode} 1 0000000000000000 100 0 0 10 0\n"
    )


class TestAddressDecoding:
    def test_ipv4_is_little_endian(self):
        assert decode_address("0100007F:0") == "127.0.0.1"
        assert decode_address("00000000:0") == "0.0.0.0"
        assert decode_address("6453A8C0:0") == "192.168.83.100"

    def test_ipv6_wildcard(self):
        assert decode_address("00000000000000000000000000000000:0") == "::"

    def test_ipv6_loopback(self):
        assert decode_address("00000000000000000000000001000000:0") == "::1"

    def test_ipv6_mapped_v4_loopback(self):
        # The canonical example: ::ffff:127.0.0.1 as the kernel writes it.
        assert decode_address("0000000000000000FFFF00000100007F:0") == "::ffff:127.0.0.1"

    def test_ipv6_tailscale(self):
        assert decode_address("0000000000000000FFFF000067666564:0") == "::ffff:100.101.102.103"

    def test_port_is_plain_hex(self):
        assert decode_port("1F90") == 8080
        assert decode_port("0050") == 80
        assert decode_port("1F") == 31


class TestClassifyBinding:
    def test_loopback_is_not_exposed(self):
        for address in ("127.0.0.1", "127.0.0.53", "::1"):
            binding = classify_binding(address)
            assert binding["scope"] == SCOPE_LOCALHOST, address
            assert binding["exposed"] is False, address

    def test_wildcard_is_exposed(self):
        for address in ("0.0.0.0", "::"):
            binding = classify_binding(address)
            assert binding["scope"] == SCOPE_PUBLIC, address
            assert binding["exposed"] is True, address
            assert "interface" in binding["note"]

    def test_tailscale_address_is_exposed_but_scoped(self):
        binding = classify_binding("100.64.0.1")
        assert binding["scope"] == SCOPE_TAILSCALE
        assert binding["exposed"] is True
        assert "Tailscale" in binding["note"]

    def test_private_lan_address(self):
        binding = classify_binding("192.168.0.100")
        assert binding["scope"] == SCOPE_LAN
        assert binding["exposed"] is True

    def test_docker_bridge_is_not_exposed(self):
        for address in ("172.17.0.1", "172.18.0.1", "10.88.0.1"):
            binding = classify_binding(address)
            assert binding["scope"] == SCOPE_CONTAINER, address
            assert binding["exposed"] is False, address

    def test_link_local(self):
        assert classify_binding("169.254.10.10")["scope"] == SCOPE_LINK_LOCAL
        assert classify_binding("169.254.10.10")["exposed"] is False

    def test_routable_address_is_other_and_exposed(self):
        binding = classify_binding("8.8.8.8")
        assert binding["scope"] == SCOPE_OTHER
        assert binding["exposed"] is True

    def test_unparsed_address_does_not_raise(self):
        binding = classify_binding("not-an-address")
        assert binding["scope"] == SCOPE_OTHER
        assert binding["exposed"] is False


class TestParseProcNet:
    def test_listening_tcp_row(self):
        rows = parse_proc_net(TCP_HEADER + tcp_row("0100007F:1F90"), "tcp")
        assert len(rows) == 1
        assert rows[0]["port"] == 8080
        assert rows[0]["address"] == "127.0.0.1"
        assert rows[0]["protocol"] == "tcp"
        assert rows[0]["inode"] == 12345
        assert rows[0]["uid"] == "1000"

    def test_wildcard_row(self):
        rows = parse_proc_net(TCP_HEADER + tcp_row("00000000:0050"), "tcp")
        assert rows[0]["address"] == "0.0.0.0"
        assert rows[0]["port"] == 80

    def test_non_listening_tcp_is_ignored(self):
        # 01 == ESTABLISHED
        rows = parse_proc_net(TCP_HEADER + tcp_row("0100007F:1F90", state="01"), "tcp")
        assert rows == []

    def test_udp_unconnected_socket_counts(self):
        rows = parse_proc_net(TCP_HEADER + tcp_row("00000000:0044", state="07"), "udp")
        assert len(rows) == 1
        assert rows[0]["port"] == 68

    def test_udp_established_flow_is_ignored(self):
        rows = parse_proc_net(TCP_HEADER + tcp_row("00000000:0044", state="01"), "udp")
        assert rows == []

    def test_short_lines_are_skipped(self):
        assert parse_proc_net(TCP_HEADER + "   0: 0100007F:1F90\n", "tcp") == []

    def test_header_alone_is_empty(self):
        assert parse_proc_net(TCP_HEADER, "tcp") == []


class TestDeduplication:
    """A socket bound to both 0.0.0.0 and 127.0.0.1 must not hide the specific one."""

    def test_specific_address_wins_over_wildcard(self):
        from servermanager.collectors import ports as ports_module

        text = TCP_HEADER + tcp_row("00000000:1F90") + tcp_row("0100007F:1F90")
        sockets = ports_module.parse_proc_net(text, "tcp")
        best: dict = {}
        for sock in sockets:
            key = (sock["port"], sock["protocol"])
            current = best.get(key)
            if current is None or (
                current["address"] in ("0.0.0.0", "::") and sock["address"] not in ("0.0.0.0", "::")
            ):
                best[key] = sock
        assert best[(8080, "tcp")]["address"] == "127.0.0.1"


class TestInodeAttribution:
    """socket inode -> pid, via /proc/<pid>/fd.

    Uses a fake /proc: real fd directories are readable here, which is exactly
    the case that is NOT guaranteed inside a container.
    """

    @staticmethod
    def _fake_proc(tmp_path, pids):
        for pid, inodes in pids.items():
            fd_dir = tmp_path / str(pid) / "fd"
            fd_dir.mkdir(parents=True)
            for index, inode in enumerate(inodes):
                os.symlink(f"socket:[{inode}]", fd_dir / str(index))
        return str(tmp_path)

    def test_socket_fd_is_mapped_to_its_pid(self, tmp_path):
        root = self._fake_proc(tmp_path, {4242: [111], 7: [222]})
        owners = scan_inode_owners(root)
        assert owners == {111: 4242, 222: 7}

    def test_first_pid_wins_when_two_share_an_inode(self, tmp_path):
        root = self._fake_proc(tmp_path, {4242: [111], 7: [111]})
        owners = scan_inode_owners(root)
        assert len(owners) == 1 and owners[111] in (7, 4242)

    def test_non_socket_fds_and_junk_are_ignored(self, tmp_path):
        fd_dir = tmp_path / "99" / "fd"
        fd_dir.mkdir(parents=True)
        os.symlink("/etc/hosts", fd_dir / "0")
        os.symlink("pipe:[12345]", fd_dir / "1")
        os.symlink("socket:[notanumber]", fd_dir / "2")
        (tmp_path / "notapid").mkdir()
        assert scan_inode_owners(str(tmp_path)) == {}

    def test_missing_proc_root_is_not_an_exception(self, tmp_path):
        assert scan_inode_owners(str(tmp_path / "nope")) == {}

    def test_parsed_inode_is_an_int_so_it_can_join_the_fd_scan(self, tmp_path):
        # A str inode and an int map key never match, and every row silently
        # loses its owner - so this is pinned as its own test.
        rows = parse_proc_net(TCP_HEADER + tcp_row("00000000:1F90", inode="4242"), "tcp")
        assert rows[0]["inode"] == 4242
        root = self._fake_proc(tmp_path, {777: [4242]})
        assert scan_inode_owners(root)[rows[0]["inode"]] == 777

    def test_unreadable_process_does_not_lose_the_others(self, tmp_path):
        root = self._fake_proc(tmp_path, {4242: [111]})
        blocked = tmp_path / "5150" / "fd"
        blocked.mkdir(parents=True)
        os.symlink("socket:[222]", blocked / "0")
        os.chmod(blocked, 0o000)
        try:
            owners = scan_inode_owners(root)
        finally:
            os.chmod(blocked, 0o700)
        assert owners == {111: 4242}
