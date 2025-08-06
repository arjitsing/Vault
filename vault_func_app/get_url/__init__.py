import azure.functions as func
import logging
import json
import uuid
import time
import os
import requests

from azure.identity import ManagedIdentityCredential
from azure.mgmt.containerinstance import ContainerInstanceManagementClient
from azure.mgmt.containerinstance.models import (
    ContainerGroup,
    Container,
    ResourceRequests,
    ResourceRequirements,
    OperatingSystemTypes,
    IpAddress,
    Port,
    ContainerGroupSubnetId,
    ImageRegistryCredential
)

def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        # Read input
        data = req.get_json()
        name = data.get("name")
        user_id = data.get("id")
        if not name or not user_id:
            return func.HttpResponse("Missing 'name' or 'id'", status_code=400)

        # Environment setup
        job_id = str(uuid.uuid4())
        container_name = f"geturl-{job_id[:8]}"
        LOCATION = os.environ.get("AZURE_LOCATION", "centralus")
        RESOURCE_GROUP = os.environ["RESOURCE_GROUP"]
        SUB_ID = os.environ["AZURE_SUBSCRIPTION_ID"]
        ACR_IMAGE = os.environ["CONTAINER_IMAGE"]
        SUBNET_ID = os.environ["ACI_SUBNET_ID"]
        CONTAINER_PORT = int(os.environ.get("CONTAINER_PORT", 8080))
        ACR_SERVER = os.environ["ACR_SERVER"]       # e.g., myregistry.azurecr.io
        ACR_USERNAME = os.environ["ACR_USERNAME"]
        ACR_PASSWORD = os.environ["ACR_PASSWORD"]

        # Auth client
        credential = ManagedIdentityCredential()
        ci_client = ContainerInstanceManagementClient(credential, SUB_ID)

        # Prepare container group
        container = Container(
            name=container_name,
            image=ACR_IMAGE,
            resources=ResourceRequirements(
                requests=ResourceRequests(cpu=1.0, memory_in_gb=1.0)
            ),
            ports=[Port(protocol="TCP", port=CONTAINER_PORT)],
            environment_variables=[
                {"name": "PAYLOAD", "value": json.dumps({"name": name, "id": user_id})}
            ]
        )

        image_registry_credentials = [
            ImageRegistryCredential(
                server=ACR_SERVER,
                username=ACR_USERNAME,
                password=ACR_PASSWORD
            )
        ]

        group = ContainerGroup(
            location=LOCATION,
            containers=[container],
            os_type=OperatingSystemTypes.linux,
            restart_policy="Never",
            subnet_ids=[ContainerGroupSubnetId(id=SUBNET_ID)],
            identity={"type": "SystemAssigned"},
            image_registry_credentials=image_registry_credentials,
            ip_address=None  # Private IP
        )

        

        # Create container group
        logging.info(f"Creating ACI: {container_name}")
        poller = ci_client.container_groups.begin_create_or_update(RESOURCE_GROUP, container_name, group)
        poller.result()

        # Wait for container to be running
        timeout = 120
        elapsed = 0
        interval = 5
        private_ip = None

        while elapsed < timeout:
            cg = ci_client.container_groups.get(RESOURCE_GROUP, container_name)
            state = cg.instance_view.state
            logging.info(f"Container state: {state}")
            if state == "Running":
                private_ip = cg.ip_address and cg.ip_address.ip
                break
            time.sleep(interval)
            elapsed += interval

        if not private_ip:
            return func.HttpResponse("ACI did not start properly", status_code=500)

        # Make internal request to ACI's /get_url endpoint
        aci_url = f"http://{private_ip}:{CONTAINER_PORT}/get_url"
        logging.info(f"Calling container at: {aci_url}")
        try:
            res = requests.post(aci_url, json=data,timeout=10)
            if res.status_code == 200:
                response_data = res.text
            else:
                response_data = f"Error calling container: {res.status_code}"
        except Exception as e:
            response_data = f"Failed to reach ACI: {str(e)}"

        # Optionally cleanup the ACI
        ci_client.container_groups.begin_delete(RESOURCE_GROUP, container_name)

        return func.HttpResponse(response_data, mimetype="application/json")

    except Exception as e:
        logging.exception("Unexpected failure")
        return func.HttpResponse(str(e), status_code=500)