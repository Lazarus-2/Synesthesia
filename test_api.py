import requests
import json
import time
import sys

API_URL = "http://localhost:8000"
FILE_PATH = "test.wav"

def test_analysis():
    print(f"Uploading {FILE_PATH}...")
    with open(FILE_PATH, "rb") as f:
        response = requests.post(
            f"{API_URL}/analyze",
            files={"file": f},
            data={"instrument": "guitar", "difficulty": "beginner"}
        )
    
    if not response.ok:
        print(f"Failed to upload: {response.text}")
        sys.exit(1)
        
    data = response.json()
    job_id = data.get("job_id")
    print(f"Started job ID: {job_id}")
    
    if data.get("status") == "done":
        print("Analysis completed instantly (cache hit)!")
        return

    print("Listening for SSE progress...")
    # Poll SSE
    response = requests.get(f"{API_URL}/jobs/{job_id}/progress", stream=True)
    for line in response.iter_lines():
        if line:
            line_str = line.decode('utf-8')
            if line_str.startswith('data: '):
                payload = json.loads(line_str[6:])
                status = payload.get("status")
                progress = payload.get("progress", 0)
                msg = payload.get("message", "")
                
                print(f"[{status.upper()}] {progress}% - {msg}")
                if status in ["done", "error"]:
                    print("Stream ended.")
                    break

if __name__ == "__main__":
    test_analysis()
