import unittest
from pydantic import ValidationError
from mkfstab import Encryption, MountPoint, Filesystem


class TestFstabUnmarshaling(unittest.TestCase):
    def test_encryption_valid_serial(self):
        data = {"dm_name": "cryptroot", "serial": "12345"}
        enc = Encryption(**data)
        self.assertEqual(enc.dm_name, "cryptroot")
        self.assertEqual(enc.serial, "12345")
        self.assertIsNone(enc.partuuid)

    def test_encryption_valid_partuuid(self):
        data = {"dm_name": "cryptroot", "partuuid": "abcd-efgh"}
        enc = Encryption(**data)
        self.assertEqual(enc.dm_name, "cryptroot")
        self.assertEqual(enc.partuuid, "abcd-efgh")
        self.assertIsNone(enc.serial)

    def test_encryption_invalid_both_set(self):
        data = {"dm_name": "cryptroot", "serial": "12345", "partuuid": "abcd-efgh"}
        with self.assertRaises(ValidationError):
            Encryption(**data)

    def test_encryption_invalid_none_set(self):
        data = {"dm_name": "cryptroot"}
        with self.assertRaises(ValidationError):
            Encryption(**data)

    def test_mount_point_valid(self):
        data = {
            "path": "/mnt/data",
            "subvol": "@home",
            "options": ["compress=zstd"],
            "hide": True,
        }
        mp = MountPoint(**data)
        self.assertEqual(mp.path, "/mnt/data")
        self.assertEqual(mp.subvol, "@home")
        self.assertEqual(mp.options, ["compress=zstd"])
        self.assertTrue(mp.hide)

    def test_mount_point_defaults(self):
        data = {"path": "/mnt/data"}
        mp = MountPoint(**data)
        self.assertEqual(mp.path, "/mnt/data")
        self.assertIsNone(mp.subvol)
        self.assertIsNone(mp.options)
        self.assertFalse(mp.hide)

    def test_fstab_entry_valid(self):
        data = {
            "what": "UUID=abcd-1234",
            "type": "ext4",
            "where": ["/mnt/data", {"path": "/mnt/backup"}],
            "options": ["defaults", "noatime"],
            "automount": True,
            "hide": False,
            "fsck": 1,
            "crypt": {"dm_name": "cryptroot", "serial": "12345"},
        }
        entry = Filesystem(**data)
        self.assertEqual(entry.what, "UUID=abcd-1234")
        self.assertEqual(entry.type, "ext4")
        self.assertEqual(len(entry.where), 2)
        self.assertEqual(entry.where[0].path, "/mnt/data")
        self.assertEqual(entry.where[1].path, "/mnt/backup")
        self.assertEqual(entry.options, ["defaults", "noatime"])
        self.assertTrue(entry.automount)
        self.assertFalse(entry.hide)
        self.assertEqual(entry.fsck, 1)
        self.assertIsNotNone(entry.crypt)
        self.assertEqual(entry.crypt.dm_name, "cryptroot")
        self.assertEqual(entry.crypt.serial, "12345")

    def test_fstab_entry_invalid_fsck(self):
        data = {"what": "UUID=abcd-1234", "type": "ext4", "fsck": 3}
        with self.assertRaises(ValidationError):
            Filesystem(**data)

    def test_fstab_entry_where_conversion(self):
        data = {"what": "UUID=abcd-1234", "type": "ext4", "where": "/mnt/data"}
        entry = Filesystem(**data)
        self.assertEqual(len(entry.where), 1)
        self.assertEqual(entry.where[0].path, "/mnt/data")


if __name__ == "__main__":
    unittest.main()
