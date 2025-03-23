#!/usr/bin/env python3
from pathlib import Path
from textwrap import dedent
from typing import Any, Literal
from pydantic import BaseModel, field_validator, model_validator

SYSTEMD_MOUNT = "/usr/bin/systemd-mount -A -G --no-block"


class Encryption(BaseModel):
    dm_name: str
    serial: str | None = None
    partuuid: str | None = None

    @model_validator(mode="after")
    def check_id(self) -> "Encryption":
        if self.serial and self.partuuid:
            raise ValueError("serial and partuuid cannot be both set")
        if not self.serial and not self.partuuid:
            raise ValueError("either serial or partuuid must be set")
        return self


class MountPoint(BaseModel):
    path: str
    subvol: str | None = None
    options: list[str] | None = None
    hide: bool = False

    def stroptions(self, fs: "Filesystem") -> str:
        options = (self.options or []) + fs.options
        if self.subvol:
            options.append(f"subvol={self.subvol}")
        if self.hide or fs.hide:
            options.append("x-gvfs-hide")
        if fs.automount:
            options.append("x-systemd.device-bound")
        return ",".join(options)


class Filesystem(BaseModel):
    what: str
    type: str
    where: list[MountPoint] | None = None
    options: list[str] = ["defaults"]
    automount: bool = False
    hide: bool = False
    fsck: Literal[0, 1, 2] = 0
    crypt: Encryption | None = None

    @field_validator("where", mode="before")
    @classmethod
    def convert_where(cls, value: None | str | list[str | MountPoint]):
        if value is None:
            return None
        if isinstance(value, str):
            return [
                MountPoint(path=value)
            ]  # Convert single string to list of MountPoint
        return [
            MountPoint(path=item) if isinstance(item, str) else item for item in value
        ]

    @model_validator(mode="before")
    @classmethod
    def check_where(cls, values: dict[str, Any]):
        crypt = values.get("crypt")
        where = values.get("where")
        if (
            crypt is None
            and values["type"] != "swap"
            and (where is None or len(where) == 0)
        ):
            raise ValueError("Field 'where' must be provided.")
        return values

    @property
    def need_udev(self) -> bool:
        return self.crypt is not None and self.automount

    @property
    def udev_rule(self) -> list[str]:
        assert self.crypt is not None
        crypt = self.crypt

        if crypt.serial:
            dev_id = f'ENV{{ID_SERIAL_SHORT}}=="{crypt.serial}"'
        else:
            dev_id = f'ENV{{PARTUUID}}=="{crypt.partuuid}"'

        id_name, id_value = self.what.split("=")
        fs_id = f'ENV{{ID_FS_{id_name}}}=="{id_value}"'
        cryptsetup_service = f"systemd-cryptsetup@{crypt.dm_name}.service"
        rules = [
            dedent(f"""\
            ACTION=="add", SUBSYSTEM=="block", {dev_id}, \\
              ENV{{SYSTEMD_WANTS}}+="{cryptsetup_service}"
            """)
        ]
        for where in self.where or [MountPoint(path=f"/media/{crypt.dm_name}")]:
            rules.append(
                dedent(f"""\
                ACTION=="change", {fs_id}, ENV{{DM_ACTIVATION}}=="1", ENV{{UDISKS_FILESYSTEM_SHARED}}="1", \\
                  RUN+="{SYSTEMD_MOUNT} -o {where.stroptions(self)},x-systemd.after={cryptsetup_service} $devnode {where.path}"
                """)
            )

        return rules

    @property
    def fstab(self) -> list[str] | None:
        if self.need_udev:
            # automount of encrypted filesystem will be handled by udev rules
            return

        if self.type == "swap":
            return [f"{self.what} none swap {','.join(self.options)} 0 0\n"]

        assert self.where is not None

        output: list[str] = []
        for where in self.where:
            output.append(
                f"{self.what} {where.path} {self.type} {where.stroptions(self)} 0 {self.fsck}\n"
            )

        return output


def main():
    import yaml
    import click

    path_param = click.Path(dir_okay=False, exists=True, path_type=Path)

    @click.command()
    @click.option("--input", "-i", type=path_param, default="/etc/fstab.yml")
    @click.option("--udev", "-u", type=path_param)
    @click.argument("output", type=path_param, required=False)
    def cli(input: Path, udev: Path | None, output: Path | None):
        filesystems: list[Filesystem] = []
        filesystems_udev: list[Filesystem] = []

        with input.open("r") as f:
            data = yaml.safe_load(f)
        for e in data:
            fs = Filesystem(**e)
            if fs.need_udev:
                filesystems_udev.append(fs)
            else:
                filesystems.append(fs)

        fstab_lines = [i for e in filesystems for i in e.fstab or []]

        if output:
            with output.open("w") as f:
                f.writelines(fstab_lines)
        else:
            print("".join(fstab_lines))

        if udev:
            with udev.open("w") as f:
                for fs in filesystems_udev:
                    f.write("".join(fs.udev_rule))

    cli()


if __name__ == "__main__":
    main()
