"""A OCI Python Pulumi program"""

import base64

import pulumi
import pulumi_oci as oci

# Docs:
# - VCN: https://www.pulumi.com/registry/packages/oci/api-docs/core/vcn/
# - NAT Gateway: https://www.pulumi.com/registry/packages/oci/api-docs/core/natgateway/
# - Route Table: https://www.pulumi.com/registry/packages/oci/api-docs/core/routetable/
# - Security List: https://www.pulumi.com/registry/packages/oci/api-docs/core/securitylist/
# - Subnet: https://www.pulumi.com/registry/packages/oci/api-docs/core/subnet/
# - Instance: https://www.pulumi.com/registry/packages/oci/api-docs/core/instance/
# - Image lookup: https://www.pulumi.com/registry/packages/oci/api-docs/core/getimages/

# Get Tailscale auth key from Pulumi config
config = pulumi.Config()
tailscale_auth_key = config.require_secret("tailscaleAuthKey")

compartment = oci.identity.Compartment("cowgill", description="Cowgill Resources")

# Create VCN (10.0.0.0/16)
vcn = oci.core.Vcn(
    "vcn",
    cidr_block="10.0.0.0/16",
    compartment_id=compartment.compartment_id,
    display_name="vcn",
    dns_label="vcn",
)

# Create NAT Gateway attached to the VCN
nat_gateway = oci.core.NatGateway(
    "nat-gateway",
    compartment_id=compartment.compartment_id,
    vcn_id=vcn.id,
    display_name="nat-gw",
)

# Create Route Table with default route to NAT Gateway
private_route_table = oci.core.RouteTable(
    "nat-route-table",
    compartment_id=compartment.compartment_id,
    vcn_id=vcn.id,
    display_name="nat-private_route_table",
    route_rules=[
        oci.core.RouteTableRouteRuleArgs(
            # destination_type "CIDR_BLOCK" for IPv4 default route
            destination="0.0.0.0/0",
            destination_type="CIDR_BLOCK",
            network_entity_id=nat_gateway.id,
            description="Default route via NAT Gateway",
        )
    ],
)

# Create Security List: allow all egress; no inbound rules
security_list = oci.core.SecurityList(
    "private-sec-list",
    compartment_id=compartment.compartment_id,
    vcn_id=vcn.id,
    display_name="private-sl",
    # No ingress rules by default
    ingress_security_rules=[],
    # Allow all egress
    egress_security_rules=[
        oci.core.SecurityListEgressSecurityRuleArgs(
            destination="0.0.0.0/0",
            destination_type="CIDR_BLOCK",
            protocol="all",  # allow all protocols
            description="Allow all outbound",
        )
    ],
)

# Create private Subnet (10.0.1.0/24) with prohibit_public_ip_on_vnic=True
subnet = oci.core.Subnet(
    "private-subnet",
    compartment_id=compartment.compartment_id,
    vcn_id=vcn.id,
    cidr_block="10.0.1.0/24",
    display_name="private-subnet",
    dns_label="privsubnet",
    route_table_id=private_route_table.id,
    security_list_ids=[security_list.id],
    prohibit_public_ip_on_vnic=True,
    prohibit_internet_ingress=True,
)


# 7) Lookup an Arm64 Oracle Linux image compatible with VM.Standard.A1.Flex
# Filter images for Oracle Linux, aarch64, and compatible with the A1 Flex shape.
image_id = compartment.compartment_id.apply(
    lambda cid: oci.core.get_images(
        compartment_id=cid,
        shape="VM.Standard.A1.Flex",
        operating_system="Oracle Linux",
        sort_by="TIMECREATED",
        sort_order="DESC",
    )
    .images[0]
    .id
)

cloud_init = """#cloud-config
# The above header must generally appear on the first line of a cloud config
# file, but all other lines that begin with a # are optional comments.

runcmd:
  # One-command install, from https://tailscale.com/download/
  - ['sh', '-c', 'curl -fsSL https://tailscale.com/install.sh | sh']
  # Set sysctl settings for IP forwarding (useful when configuring an exit node)
  - ['sh', '-c', "echo 'net.ipv4.ip_forward = 1' | sudo tee -a /etc/sysctl.d/99-tailscale.conf && echo 'net.ipv6.conf.all.forwarding = 1' | sudo tee -a /etc/sysctl.d/99-tailscale.conf && sudo sysctl -p /etc/sysctl.d/99-tailscale.conf" ]
  # Generate an auth key from your Admin console
  # https://login.tailscale.com/admin/settings/keys
  # and replace the placeholder below
  - ['tailscale', 'up', '--auth-key={}']
  # (Optional) Include this line to make this node available over Tailscale SSH
  - ['tailscale', 'set', '--ssh']
"""


# 7) Create Instance with shape VM.Standard.A1.Flex
# Specify OCPUs and memory in shape_config for Flex shapes
instance = oci.core.Instance(
    "slackbot-compute",
    availability_domain="cNEV:US-SANJOSE-1-AD-1",
    compartment_id=compartment.compartment_id,
    display_name="slackbot",
    shape="VM.Standard.A1.Flex",
    shape_config=oci.core.InstanceShapeConfigArgs(
        ocpus=1,
        memory_in_gbs=6,
    ),
    source_details=oci.core.InstanceSourceDetailsArgs(
        source_type="image",
        source_id=image_id,
    ),
    create_vnic_details=oci.core.InstanceCreateVnicDetailsArgs(
        subnet_id=subnet.id,
        assign_public_ip="false",  # do not assign a public IP
        hostname_label="slackbot",
    ),
    metadata={
        "user_data": tailscale_auth_key.apply(lambda key: base64.b64encode(cloud_init.format(key).encode()).decode())
    },
)

# 8) Outputs
pulumi.export("vcn_id", vcn.id)
pulumi.export("subnet_id", subnet.id)
pulumi.export("nat_gateway_id", nat_gateway.id)
pulumi.export("route_table_id", private_route_table.id)
pulumi.export("security_list_id", security_list.id)
pulumi.export("instance_id", instance.id)
pulumi.export("instance_private_ip", instance.private_ip)
