"""Disk detection has to describe the host, and it has to survive a container.

Two things go wrong if you read the container's own /proc/mounts: "/" becomes an
overlay with meaningless numbers, and every bind mount the panel itself uses
turns up as a "disk". Both are fixed by parsing the host's mount table, so the
parser is a pure function and gets tested as one.
"""

from __future__ import annotations

from servermanager.collectors.system import parse_mounts

MOUNTS = """\
sysfs /sys sysfs rw,nosuid,nodev,noexec,relatime 0 0
proc /proc proc rw,nosuid,nodev,noexec,relatime 0 0
udev /dev devtmpfs rw,nosuid,relatime,size=8142908k 0 0
tmpfs /run tmpfs rw,nosuid,nodev,noexec,relatime,size=1637888k 0 0
/dev/nvme0n1p2 / ext4 rw,relatime,errors=remount-ro 0 0
overlay /var/lib/docker/overlay2/abc/merged overlay rw,relatime 0 0
/dev/nvme0n1p2 /app/web ext4 ro,relatime,errors=remount-ro 0 0
/dev/nvme0n1p2 /etc/hosts ext4 ro,relatime,errors=remount-ro 0 0
/dev/nvme0n1p1 /boot/efi vfat rw,relatime,fmask=0077 0 0
cgroup2 /sys/fs/cgroup cgroup2 rw,nosuid,nodev,noexec,relatime 0 0
/dev/sdb1 /mnt/usb\\040stick exfat rw,nosuid,nodev 0 0
"""


class TestParseMounts:
    def test_keeps_real_filesystems_including_the_root(self):
        devices = {entry["device"] for entry in parse_mounts(MOUNTS)}
        assert devices == {"/dev/nvme0n1p2", "/dev/nvme0n1p1", "/dev/sdb1"}

    def test_drops_pseudo_filesystems(self):
        types = {entry["fstype"] for entry in parse_mounts(MOUNTS)}
        assert "overlay" not in types
        assert "tmpfs" not in types
        assert "devtmpfs" not in types
        assert "cgroup2" not in types

    def test_drops_bind_mounts_of_the_same_device(self):
        # /app/web and /etc/hosts are this container's own mounts of the root
        # device; only "/" should be reported.
        roots = [e for e in parse_mounts(MOUNTS) if e["device"] == "/dev/nvme0n1p2"]
        assert len(roots) == 1
        assert roots[0]["mount"] == "/"

    def test_unescapes_spaces_in_mount_points(self):
        assert parse_mounts(MOUNTS)[-1]["mount"] == "/mnt/usb stick"

    def test_ignores_devices_that_are_not_paths(self):
        text = "server:/export /mnt/nfs nfs4 rw 0 0\nUUID=1234 /data ext4 rw 0 0\n"
        assert parse_mounts(text) == []

    def test_survives_a_truncated_line(self):
        assert parse_mounts("/dev/sda1 /mnt\n") == []
