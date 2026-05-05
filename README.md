# MedAgentBench Fast Healthcare Interoperability Resources (FHIR) MCP web server management with FastAPI

## Installation

First, pull the benchmark FHIR image:

```
sudo docker pull jyxsu6/medagentbench:latest
```

Then, start the image:

```
export FHIR_PORT=8080
export IMAGE_NAME=medagentbench

docker run -d --name medagentbench_server -p $FHIR_PORT:8080 $IMAGE_NAME
```

