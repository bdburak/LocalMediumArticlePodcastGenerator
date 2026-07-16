import subprocess
import sys
import time
import os


def main():
    cwd = os.path.dirname(os.path.abspath(__file__))

    print("Starting Qwen3-TTS server on :8091...")
    tts_proc = subprocess.Popen(
        [sys.executable, "local_tts_server.py"],
        cwd=cwd,
    )

    print("Waiting for TTS server to load the model...")
    import httpx
    for attempt in range(60):
        try:
            r = httpx.get("http://127.0.0.1:8091/health", timeout=2)
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

    print("Starting Flask web app on :5000...")
    web_proc = subprocess.Popen(
        [sys.executable, "web/app.py"],
        cwd=cwd,
        env={**os.environ, "TTS_API_URL": "http://127.0.0.1:8091"},
    )

    print()
    print("  === Podcast Generator Running ===")
    print("  TTS Server: http://127.0.0.1:8091")
    print("  Web App:    http://127.0.0.1:5000")
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
