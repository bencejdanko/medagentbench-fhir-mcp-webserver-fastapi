import os
import asyncio
import subprocess
import httpx
from fastapi import FastAPI, HTTPException, Security, Depends, Request
from fastapi.responses import StreamingResponse
from fastapi.security.api_key import APIKeyHeader
from starlette.status import HTTP_403_FORBIDDEN
from dotenv import load_dotenv

load_dotenv()

# Configuration
FHIR_BASE_URL = os.getenv("FHIR_BASE_URL", "http://localhost:8080")
FHIR_PORT = os.getenv("FHIR_PORT", "8080")
MEDAGENTBENCH_API_KEY = os.getenv("MEDAGENTBENCH_API_KEY")

if not MEDAGENTBENCH_API_KEY:
    raise ValueError("MEDAGENTBENCH_API_KEY is missing from the environment variables.")

API_KEY_NAME = "X-API-KEY"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

app = FastAPI()

async def get_api_key(header_val: str = Security(api_key_header)):
    if header_val == MEDAGENTBENCH_API_KEY:
        return header_val
    raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Could not validate credentials")

@app.get("/health")
def health_check():
    # Basic check to see if the container is running
    result = subprocess.run(["docker", "inspect", "-f", "{{.State.Running}}", "medagentbench_server"], 
                            capture_output=True, text=True)
    is_running = result.stdout.strip() == "true"
    return {"status": "ok", "docker_running": is_running}

@app.post("/reset")
async def reset_environment(key: str = Depends(get_api_key)):
    """
    Performs a true reset of the MedAgentBench Docker container, 
    matching the logic of the original bash script.
    """
    # 1. Cleanup
    subprocess.run(["docker", "rm", "-f", "medagentbench_server"], capture_output=True)
    subprocess.run(["fuser", "-k", f"{FHIR_PORT}/tcp"], capture_output=True)

    # 2. Ensure Image and Start Container
    subprocess.run(["docker", "pull", "jyxsu6/medagentbench:latest"], capture_output=True)
    subprocess.run(["docker", "tag", "jyxsu6/medagentbench:latest", "medagentbench"], capture_output=True)
    
    start_result = subprocess.run([
        "docker", "run", "-d", 
        "--name", "medagentbench_server", 
        "-p", f"{FHIR_PORT}:8080", 
        "medagentbench"
    ], capture_output=True, text=True)

    if start_result.returncode != 0:
        raise HTTPException(status_code=500, detail=f"Docker start failed: {start_result.stderr}")

    # 3. Wait for FHIR Server to be ready (Polling /fhir/metadata)
    async with httpx.AsyncClient() as client:
        is_ready = False
        metadata_url = f"http://localhost:{FHIR_PORT}/fhir/metadata"
        
        for _ in range(90):  # 90 retries * 2 seconds = 180 seconds max
            try:
                res = await client.get(metadata_url, timeout=2.0)
                if res.status_code == 200:
                    is_ready = True
                    break
            except httpx.RequestError:
                pass
            await asyncio.sleep(2)
            
        if not is_ready:
            raise HTTPException(status_code=500, detail="FHIR Server failed to start in time. Check Docker logs.")

    # 4. Verify Real Data via Direct Call
    verify_url = f"http://localhost:{FHIR_PORT}/fhir/Patient?given=Peter&family=Stafford&birthdate=1932-12-29"
    async with httpx.AsyncClient() as client:
        try:
            verify_res = await client.get(verify_url)
            if "S6534835" not in verify_res.text:
                raise HTTPException(status_code=500, detail="Data mismatch: Real patient record not found in database.")
        except httpx.RequestError as e:
            raise HTTPException(status_code=500, detail=f"Data verification failed: {str(e)}")

    return {
        "status": "reset_complete", 
        "details": "Container rebuilt, FHIR server is up, and real data verified."
    }

@app.api_route("/fhir/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy_fhir(path: str, request: Request, key: str = Depends(get_api_key)):
    """
    Acts as a reverse proxy. Requires the API key, then forwards the request
    to the local Docker container running on the configured port.
    """
    fhir_server_url = f"{FHIR_BASE_URL}/fhir/{path}"
    
    body = await request.body()
    query_params = request.url.query
    if query_params:
        fhir_server_url += f"?{query_params}"

    # Prepare headers for proxying
    forward_headers = dict(request.headers)
    forward_headers.pop("host", None) # Let httpx handle the host
    forward_headers["accept-encoding"] = "identity" # Force plain text to avoid terminal binary issues

    async with httpx.AsyncClient() as client:
        try:
            proxy_req = client.build_request(
                method=request.method,
                url=fhir_server_url,
                headers=forward_headers,
                content=body,
            )
            proxy_resp = await client.send(proxy_req, stream=True)
            
            # Strip headers that conflict with FastAPI's StreamingResponse
            resp_headers = dict(proxy_resp.headers)
            resp_headers.pop("content-encoding", None)
            resp_headers.pop("content-length", None)
            
            return StreamingResponse(
                proxy_resp.aiter_raw(),
                status_code=proxy_resp.status_code,
                headers=resp_headers
            )
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Error communicating with FHIR server: {exc}")
