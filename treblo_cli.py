#!/usr/bin/env python3
import io
import json
import os
import re
import shutil
import sys
import time
import wave
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import requests

BASE = "https://api.treblo.com/v1"
OUT = Path("beats")
MIN_SECONDS = 60
POLL_SECONDS = 5
MAX_WAIT_SECONDS = 1800
KEY = os.environ.get("TREBLO_API_KEY", "").strip()
AUTH = {"Authorization": "Bearer " + KEY}


class JobFailed(Exception):
    pass


class RecoverLater(Exception):
    pass


def safe_id(value):
    return re.sub(r"[^A-Za-z0-9._-]", "", str(value))


def response_error(r):
    return f"HTTP {r.status_code}: {r.text[:500]}"


def validate_wav_file(path):
    with wave.open(str(path), "rb") as w:
        duration = w.getnframes() / float(w.getframerate())
        if w.getnframes() <= 0 or duration <= 0:
            raise ValueError("WAV has no audio frames")
        return duration


def validate_wav_bytes(data):
    with wave.open(io.BytesIO(data), "rb") as w:
        duration = w.getnframes() / float(w.getframerate())
        if w.getnframes() <= 0 or duration <= 0:
            raise ValueError("Downloaded WAV has no audio frames")
        return duration


def ask_yes(question):
    try:
        return input(question + " [y/N] ").strip().lower() in ("y", "yes")
    except EOFError:
        return False


def upload_reference(source):
    OUT.mkdir(exist_ok=True)
    temp = OUT / f"upload_tmp_{os.getpid()}_{int(time.time())}.wav"
    shutil.copyfile(source, temp)

    try:
        with temp.open("rb") as f:
            r = requests.post(
                BASE + "/uploads",
                headers=AUTH,
                files={"file": (temp.name, f, "audio/wav")},
                timeout=180,
            )
    except requests.RequestException as e:
        print(f"Upload failed: {e}")
        print(f"Temporary copy kept at: {temp}")
        raise JobFailed("Reference upload failed")

    if not r.ok:
        print("Upload rejected:", response_error(r))
        print(f"Temporary copy kept at: {temp}")
        raise JobFailed("Reference upload rejected")

    try:
        data = r.json()
    except ValueError:
        print("Upload response was not JSON:", r.text[:500])
        print(f"Temporary copy kept at: {temp}")
        raise JobFailed("Could not read upload response")

    upload_id = (
        data.get("audio_upload_id")
        or data.get("upload_id")
        or data.get("id")
    )
    if not upload_id:
        print("No audio_upload_id in response:", data)
        print(f"Temporary copy kept at: {temp}")
        raise JobFailed("Upload ID missing")

    # Delete only the temporary copy, after Treblo confirms the upload.
    temp.unlink(missing_ok=True)
    print("Reference uploaded.")
    return str(upload_id)


def save_task(task_id, mode, prompt, tags):
    OUT.mkdir(exist_ok=True)
    path = OUT / f"{safe_id(task_id)}.json"
    path.write_text(json.dumps({
        "task_id": str(task_id),
        "mode": mode,
        "prompt": prompt,
        "tags": tags,
    }, indent=2))
    print("Saved task ID:", task_id)


def poll_task(task_id):
    url = BASE + "/generations/status/" + str(task_id)
    deadline = time.monotonic() + MAX_WAIT_SECONDS
    delay = POLL_SECONDS

    while time.monotonic() < deadline:
        try:
            r = requests.get(url, headers=AUTH, timeout=60)
        except requests.RequestException as e:
            print(f"\nTemporary polling error; will retry: {str(e)[:160]}")
            time.sleep(delay)
            delay = min(delay * 2, 30)
            continue

        if r.status_code == 429 or r.status_code >= 500:
            print(f"\nTreblo polling HTTP {r.status_code}; retrying.")
            time.sleep(delay)
            delay = min(delay * 2, 30)
            continue

        if not r.ok:
            raise RecoverLater(
                f"Could not poll task ({response_error(r)}). "
                f"Do not submit again; recover with: "
                f"python treblo_cli.py recover {task_id}"
            )

        try:
            data = r.json()
        except ValueError:
            data = r.text.strip().strip('"')

        if isinstance(data, dict):
            status = str(data.get("status") or data.get("state") or "?").upper()
        else:
            status = str(data).strip().strip('"').upper()

        print(f"Task {task_id}: {status}", end="\r", flush=True)

        if status in ("SUCCESS", "COMPLETED", "COMPLETE"):
            print()
            return
        if status in ("FAILED", "FAILURE", "ERROR", "CANCELLED"):
            print()
            raise JobFailed(f"Treblo task ended with status {status}")

        delay = POLL_SECONDS
        time.sleep(POLL_SECONDS)

    raise RecoverLater(
        f"Polling timed out. The task may still be running. "
        f"Do not submit again; recover with: python treblo_cli.py recover {task_id}"
    )


def get_with_retries(url, label):
    for attempt in range(5):
        try:
            r = requests.get(url, headers=AUTH, timeout=90)
        except requests.RequestException as e:
            if attempt == 4:
                raise JobFailed(f"{label} failed: {e}")
            time.sleep(min(2 ** attempt, 10))
            continue

        if r.status_code == 429 or r.status_code >= 500:
            if attempt == 4:
                raise JobFailed(f"{label} failed: {response_error(r)}")
            time.sleep(min(2 ** attempt, 10))
            continue

        if not r.ok:
            raise JobFailed(f"{label} failed: {response_error(r)}")
        return r

    raise JobFailed(label + " failed")


def result_urls(data):
    boxes = [data]
    if isinstance(data, dict):
        for key in ("data", "result"):
            if isinstance(data.get(key), dict):
                boxes.append(data[key])

    for box in boxes:
        if not isinstance(box, dict):
            continue
        paths = box.get("song_paths")
        if isinstance(paths, str):
            paths = [paths]
        if isinstance(paths, dict):
            paths = [paths]
        if paths:
            urls = []
            for item in paths:
                if isinstance(item, dict):
                    item = item.get("url") or item.get("path")
                if item:
                    urls.append(str(item))
            if urls:
                return urls

        for key in ("audio_url", "song_url", "url"):
            if box.get(key):
                return [str(box[key])]

    return []


def absolute_audio_url(path):
    if path.startswith("http://") or path.startswith("https://"):
        return path
    if path.lstrip("/").startswith("pubapi/"):
        return "https://cdn.treblo.com/" + path.lstrip("/")
    return urljoin(BASE + "/", path.lstrip("/"))


def download_result(task_id, mode):
    r = get_with_retries(BASE + "/generations/" + str(task_id), "Fetching generation")
    try:
        data = r.json()
    except ValueError:
        raise JobFailed("Generation details were not JSON: " + r.text[:300])

    urls = result_urls(data)
    if not urls:
        raise JobFailed("Generation details contain no song_paths/audio URL")

    OUT.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    short = safe_id(task_id)[:8]

    for index, path in enumerate(urls):
        url = absolute_audio_url(path)
        try:
            audio = requests.get(url, timeout=(20, 300))
            audio.raise_for_status()
            blob = audio.content
            duration = validate_wav_bytes(blob)
        except Exception as e:
            print(f"Could not validate/download result {index + 1}: {e}")
            continue

        suffix = "" if index == 0 else f"_{index + 1}"
        filename = f"{mode}_{stamp}_{short}{suffix}.wav"
        output = OUT / filename
        output.write_bytes(blob)
        print(f"Saved: {output} ({duration:.1f}s, {len(blob)} bytes)")
        return output, duration

    raise JobFailed("No valid WAV could be downloaded from the generation")


def generate(mode, prompt, tags, upload_id=None):
    body = {
        "prompt": prompt,
        "tags": tags,
        "instrumental": True,
        "length_range": [60, 90],
        "output_format": "wav",
    }

    if upload_id:
        body["audio_upload_id"] = upload_id
        body["reference_scale"] = 1.0
        endpoint = "/generations/v3/reference"
    else:
        endpoint = "/generations/v3"

    # Do not retry this POST automatically: it may create a second paid job.
    try:
        r = requests.post(
            BASE + endpoint,
            headers={**AUTH, "Content-Type": "application/json"},
            json=body,
            timeout=120,
        )
    except requests.RequestException as e:
        raise RecoverLater(
            f"Generation submission result is unknown ({e}). "
            "Do not resubmit until you check your Treblo tasks."
        )

    if r.status_code >= 500:
        raise RecoverLater(
            f"Treblo returned {r.status_code}; submission may have been accepted. "
            "Do not resubmit blindly."
        )
    if not r.ok:
        raise JobFailed("Generation rejected: " + response_error(r))

    try:
        data = r.json()
    except ValueError:
        raise RecoverLater(
            "Generation response was not JSON; submission outcome is uncertain. "
            "Do not resubmit blindly."
        )

    task_id = data.get("task_id") or data.get("id")
    if not task_id:
        raise RecoverLater(
            "No task_id returned; submission outcome is uncertain. "
            "Do not resubmit blindly."
        )

    save_task(task_id, mode, prompt, tags)
    poll_task(task_id)
    return download_result(task_id, mode)


def offer_text_fallback(prompt, tags, reason):
    print("\n" + reason)
    if not ask_yes("Try a TEXT-ONLY beat instead? This starts another generation"):
        print("Okay. No fallback generation started.")
        return

    try:
        generate("text_only", prompt, tags)
    except (JobFailed, RecoverLater) as e:
        print("\nText-only generation:", e)


def run_reference(wav_path, prompt, tags):
    source = Path(wav_path)
    if not source.is_file():
        print("Reference WAV not found:", source)
        return

    try:
        duration = validate_wav_file(source)
    except Exception as e:
        print("Reference must be a valid WAV:", e)
        return

    print(f"Reference: {source} ({duration:.1f}s)")
    try:
        upload_id = upload_reference(source)
    except JobFailed as e:
        offer_text_fallback(prompt, tags, str(e))
        return

    try:
        output, seconds = generate(
            "reference_matched", prompt, tags, upload_id=upload_id
        )
    except JobFailed as e:
        offer_text_fallback(prompt, tags, str(e))
        return
    except RecoverLater as e:
        print("\n" + str(e))
        return

    if seconds < MIN_SECONDS:
        reason = (
            f"Reference result is {seconds:.1f}s, below the requested "
            f"{MIN_SECONDS}s minimum. Saved at {output}."
        )
        offer_text_fallback(prompt, tags, reason)
        return

    if ask_yes(f"After listening, use this reference-matched beat? ({output})"):
        print("Great. Use that WAV in your mixer.")
    else:
        offer_text_fallback(prompt, tags, "You rejected the reference-matched preview.")


def usage():
    print('''Usage:
  python treblo_cli.py ref WAV "PROMPT" [tags...]
  python treblo_cli.py text "PROMPT" [tags...]
  python treblo_cli.py recover TASK_ID

Examples:
  python treblo_cli.py ref ref.wav "Amapiano instrumental; use my vocal only for groove and energy, do not copy or continue its melody; no vocals." amapiano
  python treblo_cli.py text "Amapiano instrumental with deep log drums, rolling bass and airy pads; no vocals." amapiano
  python treblo_cli.py recover 324075be-c798-4300-b2dc-65494505e926''')


def main():
    if not KEY:
        sys.exit("Set TREBLO_API_KEY in the environment first.")
    if len(sys.argv) < 2:
        usage()
        return

    OUT.mkdir(exist_ok=True)
    mode = sys.argv[1].lower()

    if mode == "ref":
        if len(sys.argv) < 4:
            usage()
            return
        tags = sys.argv[4:] or ["amapiano"]
        run_reference(sys.argv[2], sys.argv[3], tags)

    elif mode == "text":
        if len(sys.argv) < 3:
            usage()
            return
        tags = sys.argv[3:] or ["amapiano"]
        try:
            generate("text_only", sys.argv[2], tags)
        except (JobFailed, RecoverLater) as e:
            print(e)

    elif mode == "recover":
        if len(sys.argv) != 3:
            usage()
            return
        task_id = sys.argv[2]
        meta_file = OUT / f"{safe_id(task_id)}.json"
        mode_name = "recovered"
        if meta_file.exists():
            try:
                mode_name = json.loads(meta_file.read_text()).get("mode", mode_name)
            except Exception:
                pass
        try:
            poll_task(task_id)
            download_result(task_id, mode_name)
        except (JobFailed, RecoverLater) as e:
            print(e)

    else:
        usage()


if __name__ == "__main__":
    main()
