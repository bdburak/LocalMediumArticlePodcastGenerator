import subprocess
import sys
import time
import os

from port_utils import find_free_port

FLASK_PREFERRED = 5000
TTS_PREFERRED = 8091


def main():
    cwd = os.path.dirname(os.path.abspath(__file__))

    tts_port = find_free_port(preferred=TTS_PREFERRED, max_tries=100)
    flask_port = find_free_port(preferred=FLASK_PREFERRED, max_tries=100)

    print(f"Starting Qwen3-TTS server on :{tts_port}...")
    tts_proc = subprocess.Popen(
        [sys.executable, "local_tts_server.py"],
        cwd=cwd,
        env={**os.environ, "TTS_PORT": str(tts_port)},
    )

    print("Waiting for TTS server to load the model...")
    import httpx
    for attempt in range(60):
        try:
            r = httpx.get(f"http://127.0.0.1:{tts_port}/health", timeout=2)
            if r.status_code == 200:
                print("TTS server is ready!")
                break
        except Exception:
            pass
        time.sleep(2)
    else:
        print("TTS server did not become ready in time.")
        tts_proc.terminate()
        return

    print(f"Starting Flask web app on :{flask_port}...")
    web_proc = subprocess.Popen(
        [sys.executable, "web/app.py"],
        cwd=cwd,
        env={
            **os.environ,
            "TTS_API_URL": f"http://127.0.0.1:{tts_port}",
            "FLASK_PORT": str(flask_port),
        },
    )

    # Give Flask a moment to bind, then announce readiness for the launcher.
    time.sleep(1)
    print(f"[READY] flask_port={flask_port} tts_port={tts_port}")

    print()
    print("  === Podcast Generator Running ===")
    print(f"  TTS Server: http://127.0.0.1:{tts_port}")
    print(f"  Web App:    http://127.0.0.1:{flask_port}")
    print()
    print("  Press Ctrl+C to stop both servers.")
    print()

    try:
        tts_proc.wait()
    except KeyboardInterrupt:
        print("\nShutting down...")
        tts_proc.terminate()
        web_proc.terminate()
        tts_proc.wait()
        web_proc.wait()
        print("Done.")


if __name__ == "__main__":
    main()
