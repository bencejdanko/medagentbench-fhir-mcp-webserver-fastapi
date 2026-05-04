import subprocess
import httpx
from fastapi import FastAPI, HTTPException, Security, Depends, Request
from fastapi.responses import StreamingResponse
from fastapi.security.api_key import APIKeyHeader
from starlette.status import HTTP_403_FORBIDDEN
from dotenv import load_dotenv

load_dotenv()

API_KEY = "your-secure-shared-secret" # Store in .env
API_KEY_NAME = "X-API-KEY"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

app = FastAPI()

async def get_api_key(header_val: str = Security(api_key_header)):
    if header_val == API_KEY:
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
def reset_environment(key: str = Depends(get_api_key)):
    try:
        # Executes your existing bash script
        # Ensure the script is executable: chmod +x setup_mcp.sh
        process = subprocess.run(["./setup_mcp.sh"], capture_output=True, text=True, check=True)
        return {"status": "reset_complete", "details": process.stdout}
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Reset failed: {e.stderr}")

@app.api_route("/fhir/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy_fhir(path: str, request: Request, key: str = Depends(get_api_key)):
    """
    Acts as a reverse proxy. Requires the API key, then forwards the request
    to the local Docker container running on port 8080.
    """
    fhir_server_url = f"http://localhost:8080/fhir/{path}"
    
    # Extract the body and query parameters from the original request
    body = await request.body()
    query_params = request.url.query
    if query_params:
        fhir_server_url += f"?{query_params}"

    # Forward the request using httpx
    async with httpx.AsyncClient() as client:
        try:
            proxy_req = client.build_request(
                method=request.method,
                url=fhir_server_url,
                headers={"Content-Type": request.headers.get("Content-Type", "application/json")},
                content=body,
            )
            proxy_resp = await client.send(proxy_req, stream=True)
            
            # Stream the response back to the client
            return StreamingResponse(
                proxy_resp.aiter_raw(),
                status_code=proxy_resp.status_code,
                headers=dict(proxy_resp.headers)
            )
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Error communicating with FHIR server: {exc}")
