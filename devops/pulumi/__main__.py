import base64
import pulumi
from pulumi import Config, Output
import pulumi_azure_native as azure
import pulumi_docker as docker

cfg = Config()
app_name = cfg.get("appName") or "devopstp"
location = cfg.get("location") or "westeurope"
image_tag = cfg.get("imageTag") or "v1"

# ── RG
rg = azure.resources.ResourceGroup(f"{app_name}-rg", location=location)

# ── ACR
acr = azure.containerregistry.Registry(
    f"{app_name}acr",
    resource_group_name=rg.name,
    location=rg.location,
    sku=azure.containerregistry.SkuArgs(name="Basic"),
    admin_user_enabled=True,
)
acr_login_server = acr.login_server
creds = azure.containerregistry.list_registry_credentials_output(
    resource_group_name=rg.name, registry_name=acr.name
)
acr_username = creds.username
acr_password = creds.passwords[0].value

# ── Build & push 3 images to ACR
app_image = docker.Image(
    f"{app_name}-app-image",
    image_name=Output.concat(acr_login_server, f"/{app_name}-app:", image_tag),
    build=docker.DockerBuildArgs(
        context=".",
        dockerfile="../Dockerfile",
    ),
    registry=docker.RegistryArgs(server=acr_login_server, username=acr_username, password=acr_password),
)

prom_image = docker.Image(
    f"{app_name}-prom-image",
    image_name=Output.concat(acr_login_server, f"/{app_name}-prometheus:", image_tag),
    build=docker.DockerBuildArgs(
        context=".",
        dockerfile="../prometheus/Dockerfile",
    ),
    registry=docker.RegistryArgs(server=acr_login_server, username=acr_username, password=acr_password),
)

graf_image = docker.Image(
    f"{app_name}-graf-image",
    image_name=Output.concat(acr_login_server, f"/{app_name}-grafana:", image_tag),
    build=docker.DockerBuildArgs(
        context=".",
        dockerfile="../grafana/Dockerfile",
    ),
    registry=docker.RegistryArgs(server=acr_login_server, username=acr_username, password=acr_password),
)

# ── App Service Plan (Linux)
plan = azure.web.AppServicePlan(
    f"{app_name}-plan",
    resource_group_name=rg.name,
    location=rg.location,
    kind="linux",
    reserved=True,
    sku=azure.web.SkuDescriptionArgs(name="B1", tier="Basic", capacity=1),
)

# ── Compose content (references the pushed ACR images)
def _compose_yaml(vals):
    app_img, prom_img, graf_img = vals
    compose = f"""version: "3.9"
services:
  app:
    image: {app_img}
    environment:
      - SPRING_PROFILES_ACTIVE=prod
    ports:
      - "8080:8080"

  prometheus:
    image: {prom_img}
    # baked config inside the image
    ports:
      - "9090:9090"

  grafana:
    image: {graf_img}
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
    ports:
      - "3000:3000"
"""
    return "COMPOSE|" + base64.b64encode(compose.encode()).decode()

linux_fx_version = Output.all(app_image.image_name, prom_image.image_name, graf_image.image_name).apply(_compose_yaml)

# ── Web App (compose)
webapp = azure.web.WebApp(
    f"{app_name}-webapp",
    resource_group_name=rg.name,
    location=rg.location,
    server_farm_id=plan.id,
    https_only=True,
    site_config=azure.web.SiteConfigArgs(
        linux_fx_version=linux_fx_version,
        app_settings=[
            # ACR creds for private images
            azure.web.NameValuePairArgs(
                name="DOCKER_REGISTRY_SERVER_URL",
                value=acr_login_server.apply(lambda s: f"https://{s}")
            ),
            azure.web.NameValuePairArgs(name="DOCKER_REGISTRY_SERVER_USERNAME", value=acr_username),
            azure.web.NameValuePairArgs(name="DOCKER_REGISTRY_SERVER_PASSWORD", value=acr_password),

            # Main HTTP port for inbound traffic to the "app" container
            azure.web.NameValuePairArgs(name="WEBSITES_PORT", value="8080"),

            # Optional: give more time for multi-container startup
            azure.web.NameValuePairArgs(name="WEBSITES_CONTAINER_START_TIME_LIMIT", value="1800"),
        ],
        http20_enabled=True,
    ),
)

# ── Outputs
pulumi.export("webapp_url", webapp.default_host_name.apply(lambda h: f"https://{h}"))
pulumi.export("app_image", app_image.image_name)
pulumi.export("prom_image", prom_image.image_name)
pulumi.export("graf_image", graf_image.image_name)
pulumi.export("acr", acr_login_server)
