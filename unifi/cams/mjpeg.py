import argparse
import logging
import subprocess
import sys
import tempfile
from pathlib import Path

from unifi.cams.base import UnifiCamBase


class MJPEGCam(UnifiCamBase):
    def __init__(self, args: argparse.Namespace, logger: logging.Logger) -> None:
        super().__init__(args, logger)
        self.args = args
        self.event_id = 0
        self.snapshot_dir = tempfile.mkdtemp()
        self.snapshot_stream = None

        if not self.args.snapshot_url:
            self.start_snapshot_stream()

    @classmethod
    def add_parser(cls, parser: argparse.ArgumentParser) -> None:
        super().add_parser(parser)
        parser.add_argument(
            "--source",
            "-s",
            required=True,
            help="HTTP URL to stream MJPEG from",
        )
        parser.add_argument(
            "--snapshot-url",
            "-i",
            default=None,
            type=str,
            required=False,
            help="HTTP URL to fetch JPEG snapshot image from",
        )

    async def get_ffmpeg_stream_command(self, stream_index: str, stream_name: str, destination: tuple[str, int]):
        if stream_index != "video1":
            raise ValueError("MJPEG cameras only support 1 streaming quality")

        return (
            f"ffmpeg -f mjpeg -nostdin -loglevel error -y {self.get_base_ffmpeg_args(stream_index)}"
            f' -i "{await self.get_stream_source(stream_index)}"'
            f" {self.get_extra_ffmpeg_args(stream_index)} -metadata streamName={stream_name} -f flv -vcodec flv - "
            f"| {sys.executable} -m unifi.clock_sync {'--write-timestamps' if self._needs_flv_timestamps else ''} "
            f"| nc {destination[0]} {destination[1]}"
        )

    def start_snapshot_stream(self) -> None:
        if not self.snapshot_stream or self.snapshot_stream.poll() is not None:
            cmd = (
                f"ffmpeg -f mjpeg -nostdin -y -re "
                f'-i "{self.args.source}" -r 1 '
                f"-update 1 {self.snapshot_dir}/screen.jpg"
            )
            self.logger.info(f"Spawning stream for snapshots: {cmd}")
            self.snapshot_stream = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=True
            )

    async def get_snapshot(self) -> Path:
        img_file = Path(self.snapshot_dir, "screen.jpg")

        if self.args.snapshot_url:
            await self.fetch_to_file(self.args.snapshot_url, img_file)
        else:
            self.start_snapshot_stream()

        return img_file

    async def close(self) -> None:
        await super().close()

        if self.snapshot_stream:
            self.snapshot_stream.kill()

    async def get_stream_source(self, stream_index: str) -> str:
        return self.args.source
