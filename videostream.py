import socket
import signal
import sys
import time
import subprocess
import argparse
import threading

# ── Configuration ────────────────────────────────────────────────
UDP_IP   = "0.0.0.0"
UDP_PORT = 1234
BUFFER   = 65536
# ─────────────────────────────────────────────────────────────────

def format_bytes(b):
    if b < 1024:
        return f"{b} B"
    elif b < 1024 ** 2:
        return f"{b / 1024:.2f} KB"
    else:
        return f"{b / 1024 / 1024:.2f} MB"

def hex_preview(data, length=32):
    """Show first N bytes as hex + ASCII side by side."""
    chunk = data[:length]
    hex_part   = " ".join(f"{b:02x}" for b in chunk)
    ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
    return f"{hex_part:<48}  {ascii_part}"

def start_ffplay(width, height):
    """Spawn FFplay reading from stdin with low-latency flags."""
    cmd = [
        "ffplay",
        "-fflags", "nobuffer",
        "-flags", "low_delay",
        "-framedrop",
        "-vf", "setpts=0",
        "-x", str(width),
        "-y", str(height),
        "-i", "pipe:0",
    ]
    return subprocess.Popen(cmd, stdin=subprocess.PIPE)


def main():
    parser = argparse.ArgumentParser(description="UDP MPEG-TS receiver")
    parser.add_argument("--video",   action="store_true", help="Play video with FFplay")
    parser.add_argument("--inspect", action="store_true", help="Print packet info (default)")
    parser.add_argument("--port",    type=int, default=UDP_PORT, help=f"UDP port (default: {UDP_PORT})")
    parser.add_argument("--width",   type=int, default=1280,     help="FFplay window width (default: 1280)")
    parser.add_argument("--height",  type=int, default=720,      help="FFplay window height (default: 720)")
    args = parser.parse_args()

    # Default to inspect-only if neither flag given
    if not args.video and not args.inspect:
        args.inspect = True

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
    sock.bind((UDP_IP, args.port))

    ffplay = start_ffplay(args.width, args.height) if args.video else None

    mode = []
    if args.inspect: mode.append("inspect")
    if args.video:   mode.append("video")
    print(f"[*] Mode     : {' + '.join(mode)}")
    print(f"[*] Listening: {UDP_IP}:{args.port}")
    print(f"{'─' * 70}")

    packets_received = 0
    bytes_received   = 0
    start_time       = None
    last_time        = None

    def shutdown(sig, frame):
        elapsed = time.time() - start_time if start_time else 0
        print(f"\n{'─' * 70}")
        print(f"[*] Done — {packets_received} packets | {format_bytes(bytes_received)} | {elapsed:.1f}s")
        sock.close()
        if ffplay:
            ffplay.terminate()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)

    while True:
        try:
            data, addr = sock.recvfrom(BUFFER)
        except OSError:
            break

        now = time.time()

        if start_time is None:
            start_time = now
            print(f"[*] First packet from {addr[0]}:{addr[1]}\n")

        gap       = f"{(now - last_time) * 1000:.1f} ms" if last_time else "—"
        last_time = now

        packets_received += 1
        bytes_received   += len(data)

        # ── Video: pipe into FFplay ───────────────────────────────
        if ffplay:
            try:
                ffplay.stdin.write(data)
                ffplay.stdin.flush()
            except BrokenPipeError:
                print("[!] FFplay closed.")
                ffplay = None

        # ── Inspect: print packet info ────────────────────────────
        if args.inspect:
            elapsed = now - start_time
            avg_bps = bytes_received / elapsed if elapsed > 0 else 0

            print(f"Packet #{packets_received:<6} "
                  f"| From: {addr[0]}:{addr[1]} "
                  f"| Size: {len(data):>5} B "
                  f"| Gap: {gap:>8} "
                  f"| Avg rate: {format_bytes(int(avg_bps))}/s")
            print(f"  Hex: {hex_preview(data)}")
            print()


if __name__ == "__main__":
    main()
