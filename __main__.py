"""A OCI Python Pulumi program"""

import pulumi
import pulumi_oci as oci

from infra.oracle_bucket import put_talos_image_source
from infra.oracle_compute import make_compute

# Get Tailscale auth key from Pulumi config
config = pulumi.Config()
tailscale_auth_key = config.require_secret("tailscaleAuthKey")
cluster_name = "talos"

compartment = oci.identity.Compartment("cowgill", description="Cowgill Resources", name="cowgill-resources")

image = put_talos_image_source(compartment)
make_compute(compartment, image)
