from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shlex
import socket
from typing import Optional

import paramiko
from PIL import Image


def _default_output_dir() -> Path:
	project_root = Path.cwd()
	while project_root.name != "AC-OTFlex-monorepo" and project_root.parent != project_root:
		project_root = project_root.parent
	out_dir = project_root / "data" / "out" / "images"
	out_dir.mkdir(parents=True, exist_ok=True)
	return out_dir


def connect_pi_ssh(
	host: str,
	username: str,
	password: str,
	*,
	port: int = 22,
	connect_timeout_s: int = 8,
	connect_retries: int = 3,
	precheck_timeout_s: int = 3,
) -> paramiko.SSHClient:
	with socket.create_connection((host, port), timeout=precheck_timeout_s):
		pass

	client = paramiko.SSHClient()
	client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

	last_error: Optional[BaseException] = None
	for attempt in range(1, connect_retries + 1):
		try:
			print(f"[pi_cam] SSH connect attempt {attempt}/{connect_retries} -> {host}:{port}")
			client.connect(
				host,
				port=port,
				username=username,
				password=password,
				timeout=connect_timeout_s,
				banner_timeout=connect_timeout_s,
				auth_timeout=connect_timeout_s,
			)
			return client
		except (socket.timeout, TimeoutError) as exc:
			last_error = exc
			if attempt == connect_retries:
				break

	client.close()
	if last_error is not None:
		raise last_error
	raise TimeoutError("SSH connection timed out")


def capture_pi_image_via_ssh(
	host: str,
	username: str,
	password: str,
	*,
	output_dir: Optional[Path | str] = None,
	remote_capture_dir: str = "/tmp",
	image_prefix: str = "otflex-top",
	image_width: int = 2028,
	image_height: int = 1520,
	port: int = 22,
	connect_timeout_s: int = 8,
	connect_retries: int = 3,
	capture_timeout_s: int = 30,
	cleanup_remote_file: bool = True,
) -> Path:
	local_output_dir = Path(output_dir) if output_dir is not None else _default_output_dir()
	local_output_dir.mkdir(parents=True, exist_ok=True)

	timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
	filename = f"{image_prefix}_{timestamp}.jpg"
	remote_path = f"{remote_capture_dir.rstrip('/')}/{filename}"
	local_path = local_output_dir / filename

	ssh = connect_pi_ssh(
		host,
		username,
		password,
		port=port,
		connect_timeout_s=connect_timeout_s,
		connect_retries=connect_retries,
	)

	try:
		capture_cmd = f"""python3 << 'EOF'
from picamera2 import Picamera2
import time

picam2 = Picamera2()
config = picam2.create_still_configuration(main={{\"size\": ({image_width}, {image_height})}})
picam2.configure(config)
picam2.start()
time.sleep(2)
picam2.capture_file(\"{remote_path}\")
picam2.close()
print(\"OK\")
EOF
"""

		_, stdout, stderr = ssh.exec_command(capture_cmd, timeout=capture_timeout_s)
		exit_code = stdout.channel.recv_exit_status()
		error = stderr.read().decode().strip()
		if exit_code != 0:
			raise RuntimeError(f"Image capture failed on Pi: {error}")

		sftp = ssh.open_sftp()
		try:
			sftp.get(remote_path, str(local_path))
		finally:
			sftp.close()

		if cleanup_remote_file:
			ssh.exec_command(f"rm {shlex.quote(remote_path)}")

		return local_path
	finally:
		ssh.close()


def rotate_image_if_needed(
	image_path: Path | str,
	*,
	rotate: bool = True,
	degrees: int = 180,
) -> Path:
	path = Path(image_path)
	if not rotate:
		return path

	with Image.open(path) as img:
		rotated = img.rotate(degrees, expand=True)
		rotated.save(path)
	return path
