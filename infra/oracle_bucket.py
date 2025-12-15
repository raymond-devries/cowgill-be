import json
import lzma
import re
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path
from urllib.request import urlretrieve

import oci as oci_client
import pulumi
import pulumi_oci as oci

TALOS_IMAGE_URL = "https://factory.talos.dev/image/4a0d65c669d46663f377e7161e50cfd570c401f26fd9e7bda34a0216b6f1922b/v1.11.5/oracle-arm64.raw.xz"
TALOS_VERSION = re.search(r"/v([\d.]+)/", TALOS_IMAGE_URL).group(1)


TALOS_IMAGE_METADATA = {
    "version": 2,
    "externalLaunchOptions": {
        "firmware": "UEFI_64",
        "networkType": "PARAVIRTUALIZED",
        "bootVolumeType": "PARAVIRTUALIZED",
        "remoteDataVolumeType": "PARAVIRTUALIZED",
        "localDataVolumeType": "PARAVIRTUALIZED",
        "launchOptionsSource": "PARAVIRTUALIZED",
        "pvAttachmentVersion": 2,
        "pvEncryptionInTransitEnabled": True,
        "consistentVolumeNamingEnabled": True,
    },
    "imageCapabilityData": None,
    "imageCapsFormatVersion": None,
    "operatingSystem": "Talos",
    "operatingSystemVersion": TALOS_VERSION,
    "additionalMetadata": {
        "shapeCompatibilities": [
            {
                "internalShapeName": "VM.Standard.A1.Flex",
                "ocpuConstraints": {"min": 1, "max": 80},
                "memoryConstraints": {"minInGBs": 1, "maxInGBs": 512},
            }
        ]
    },
}


def download_and_process_talos_image(url: str, dir: Path) -> Path:
    downloaded_file = dir / "oracle-arm64.raw.xz"
    urlretrieve(url, downloaded_file)

    print("Decompressing")
    decompressed_file = dir / "oracle-arm64.raw"
    with lzma.open(downloaded_file, "rb") as f_in:
        with open(decompressed_file, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)

    print("Converting")
    qcow2_file = dir / "oracle-arm64.qcow2"
    subprocess.run(["qemu-img", "convert", "-f", "raw", "-O", "qcow2", decompressed_file, qcow2_file], check=True)

    image_metadata_file = dir / "image_metadata.json"
    with image_metadata_file.open("w") as f:
        json.dump(TALOS_IMAGE_METADATA, f)

    oci_file = dir / "oracle-arm64.oci"
    with tarfile.open(oci_file, "w:gz") as tar:
        for f in (qcow2_file, image_metadata_file):
            tar.add(f, arcname=f.name)

    return oci_file


class TalosImageProvider(pulumi.dynamic.ResourceProvider):
    def create(self, props: dict) -> pulumi.dynamic.CreateResult:
        oci_config = {
            "user": props["user_ocid"],
            "fingerprint": props["fingerprint"],
            "tenancy": props["tenancy_ocid"],
            "region": props["region"],
            "key_content": props["private_key"],
        }

        client = oci_client.object_storage.ObjectStorageClient(oci_config)

        object_name = "talos-image.oci"

        with tempfile.TemporaryDirectory() as tmpdir:
            image_path = download_and_process_talos_image(props["download_url"], Path(tmpdir))
            with open(image_path, "rb") as f:
                client.put_object(
                    namespace_name=props["namespace"],
                    bucket_name=props["bucket"],
                    object_name=object_name,
                    put_object_body=f,
                )

        return pulumi.dynamic.CreateResult(id_=object_name, outs={**props, "object_name": object_name})

    def diff(self, id: str, olds: dict, news: dict) -> pulumi.dynamic.DiffResult:
        if olds.get("download_url") == news.get("download_url"):
            return pulumi.dynamic.DiffResult(changes=False)
        return pulumi.dynamic.DiffResult(changes=True, replaces=["download_url"])

    def delete(self, id: str, props: dict) -> None:
        oci_config = {
            "user": props["user_ocid"],
            "fingerprint": props["fingerprint"],
            "tenancy": props["tenancy_ocid"],
            "region": props["region"],
            "key_content": props["private_key"],
        }

        client = oci_client.object_storage.ObjectStorageClient(oci_config)

        client.delete_object(
            namespace_name=props["namespace"],
            bucket_name=props["bucket"],
            object_name=props["object_name"],
        )


class TalosImage(pulumi.dynamic.Resource):
    object_name: pulumi.Output[str]

    def __init__(
        self, name: str, download_url: str, namespace: str, bucket: str, opts: pulumi.ResourceOptions | None = None
    ) -> None:
        config = pulumi.Config("oci")

        super().__init__(
            TalosImageProvider(),
            name,
            {
                "download_url": download_url,
                "namespace": namespace,
                "bucket": bucket,
                "object_name": "",  # placeholder, will be set by create()
                "user_ocid": config.require_secret("userOcid"),
                "fingerprint": config.require_secret("fingerprint"),
                "tenancy_ocid": config.require_secret("tenancyOcid"),
                "region": config.require("region"),
                "private_key": config.require_secret("privateKey"),
            },
            opts,
        )


def put_talos_image_source(compartment: oci.identity.Compartment) -> oci.core.Image:
    namespace = oci.objectstorage.get_namespace()
    bucket = oci.objectstorage.Bucket(
        "os-images-bucket",
        name="os_images",
        compartment_id=compartment.compartment_id,
        namespace=namespace.namespace,
        access_type="NoPublicAccess",
    )

    image_upload = TalosImage(
        "talos-oci",
        download_url=TALOS_IMAGE_URL,
        namespace=namespace.namespace,
        bucket=bucket.name,
    )

    image = oci.core.Image(
        "talos-image",
        compartment_id=compartment.compartment_id,
        display_name=f"talos_v{TALOS_VERSION}",
        image_source_details=oci.core.ImageImageSourceDetailsArgs(
            source_type="objectStorageTuple",
            namespace_name=namespace.namespace,
            bucket_name=bucket.name,
            object_name="talos-image.oci",
            source_image_type="QCOW2",
            operating_system="Talos",
        ),
        opts=pulumi.ResourceOptions(depends_on=[image_upload]),
    )

    return image
