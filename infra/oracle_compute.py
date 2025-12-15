import pulumi
import pulumi_oci as oci


def make_compute(compartment: oci.identity.Compartment, image: oci.core.Image) -> None:
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

    # 7) Create Instance with shape VM.Standard.A1.Flex
    # Specify OCPUs and memory in shape_config for Flex shapes
    instance = oci.core.Instance(
        "slackbot-compute",
        availability_domain="cNEV:US-SANJOSE-1-AD-1",
        compartment_id=compartment.compartment_id,
        display_name="slackbot",
        shape="VM.Standard.A1.Flex",
        shape_config=oci.core.InstanceShapeConfigArgs(
            ocpus=2,
            memory_in_gbs=12,
        ),
        source_details=oci.core.InstanceSourceDetailsArgs(
            source_type="image",
            source_id=image.id,
        ),
        create_vnic_details=oci.core.InstanceCreateVnicDetailsArgs(
            subnet_id=subnet.id,
            assign_public_ip="false",  # do not assign a public IP
            hostname_label="slackbot",
        ),
        # metadata={
        #     "user_data": tailscale_auth_key.apply(lambda key: base64.b64encode(cloud_init.format(key).encode()).decode())
        # },
    )

    pulumi.export("instance_private_ip", instance.private_ip)
