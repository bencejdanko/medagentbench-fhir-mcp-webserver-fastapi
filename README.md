# MedAgentBench Fast Healthcare Interoperability Resources (FHIR) MCP web server management with FastAPI

## Installation

First, pull the benchmark FHIR image:

```bash
sudo docker pull jyxsu6/medagentbench:latest
```

Then, start the image. Make sure that your user is also given permissions to run docker commands

```bash
sudo usermod -aG docker user_here

docker run -d --name medagentbench -p $8080:8080 jyxsu6/medagentbench:latest
```

Clone the repository and install requirements:

```bash
git clone https://github.com/bencejdanko/medagentbench-fhir-mcp-webserver-fastapi

cd medagentbench-fhir-mcp-webserver-fastapi

pip install -r requirements.txt

# also install required system utilities
sudo apt install psmisc
```

Setup enviroment variables for the webserver:

```bash
touch .env
echo "MEDAGENTBENCH_API_KEY=your_secret_here" >> .env
```

Then start the server. If you want a more robust and self reviving service, use systemd to manage the process.

```bash
# Simple start
uvicorn manager:app --host 0.0.0.0 --port 8000
```

```bash
# systemd
sudo vi /etc/systemd/system/medagentbench.service
```

Then set:

```systemd
[Unit]
Description=MedAgentBench Manager Server
After=network.target

[Service]
User=user_here
WorkingDirectory=/home/user_here/medagentbench-fhir-mcp-webserver-fastapi
# Points directly to the uvicorn inside your virtual environment
ExecStart=/home/pasuko/medagentbench-fhir-mcp-webserver-fastapi/venv/bin/uvicorn manager:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

And then start and monitor the server:

```
sudo systemctl daemon-reload
# sudo systemctl stop medagentbench
sudo systemctl start medagentbench
sudo systemctl enable medagentbench

# check if running
sudo systemctl status medagentbench

# check live logs
journalctl -u medagentbench -f
```

Check health and test:

```bash
curl http://localhost:8000/health
```

```bash
curl -H "X-API-KEY: $MEDAGENTBENCH_API_KEY" "http://localhost:8000/fhir/Patient?given=Peter&family=Stafford&birthdate=1932-12-29"
```

For resetting:

```bash
curl -X POST -H "X-API-KEY: $MEDAGENTBENCH_API_KEY" http://localhost:8000/reset
```

Then, I recommend using a cloudflared tunnel to access the server remotely. For example,

```
curl http://medagentbench.openwear.ai/health

curl -H "X-API-KEY: $MEDAGENTBENCH_API_KEY" "http://medagentbench.openwear.ai/fhir/Patient?given=Peter&family=Stafford&birthdate=1932-12-29"
```

Restart the docker image for new tests:

```
curl -X POST -H "X-API-KEY: $MEDAGENTBENCH_API_KEY" http://medagentbench.openwear.ai/reset
```

