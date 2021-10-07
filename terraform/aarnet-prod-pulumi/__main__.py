import pulumi
from pulumi_openstack import compute, networking, blockstorage

# define our external variables - UUIDs from OpenStack
EXT_NET  =   "734b0f49-349c-44b1-a4cd-d0c9752d9a06"
VM_IMAGE =   "beb74dea-c478-4514-ac35-30722883b375" # ubuntu
DEFAULT_SECGROUP_ID = "39fb9fb9-92e9-4c61-8e24-12d8c264f61a"

EXTERNAL_IP_TYPE = "floating" # value must be "floating" or "fixed"

# cloud-init config to pass through to VMs
USER_DATA = """
#cloud-config

package_update: true
package_upgrade: true
manage_etc_hosts: true
users:
  - default
  - name: ubuntu
    ssh-authorized-keys:
      - ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQC8TymxWTJSmirXaZKdFebz2vRpKWQD881XpqceMEpTJ/i46sR4rRwFOlYR19Zpr8dyMjkZ/hxWGVG60vKKFKcqzoTJ/aTbfSF4FUyVlb84XEig+9w1LZ7kTmrX4qRQZIuf6b21FOOaLrF+xcGSnbidQ8aKzEAFv1jxWHV7jTE/Np/ne2Ir2CdH7Qq9bz680mArBK/L056GY+4rwUNINW2YiZT+5qP3nOKHW7JYXovOdZyZIAKUmb8/O7EK6GxPyUh5DkkL1z9tcgQ/ZB0XM9h4igcvPJkRyqXpN1Tdm36aByF2gkXxpdpSLYsMKMHcYGE4zVanhKCi1ucenWFn0t/z Generated-by-Nova 
"""

# create a key we use later on
key = compute.Keypair("ssh-key", name = "ssh-key")

# create a network
galaxy_net = networking.Network("galaxy-net", name = "galaxy-net")
galaxy_subnet = networking.Subnet("galaxy-subnet",
    name = "galaxy-subnet",
    cidr = "192.168.199.0/24",
    ip_version=4,
    network_id=galaxy_net.id)

# create our router
router = networking.Router("router",
    admin_state_up=True,
    external_network_id=EXT_NET)
interface = networking.RouterInterface("interface", router_id=router.id, subnet_id=galaxy_subnet.id)

# set our security groups right up
ssh_icmp = networking.SecGroup("ssh-icmp", name="ssh-icmp", description="Security Group for SSH and ICMP")
ingress_ssh = networking.SecGroupRule("ingress-ssh",
    direction="ingress", ethertype="IPv4", port_range_max=22,
    port_range_min=22, protocol="tcp", security_group_id=ssh_icmp.id)
ingress_icmp = networking.SecGroupRule("ingress-icmp",
    direction="ingress", ethertype="IPv4", security_group_id=ssh_icmp.id)

web_services = networking.SecGroup("web-services", name="web-services", description="Security Group for Web Services")
ingress_http = networking.SecGroupRule("ingress-http",
    direction="ingress", ethertype="IPv4", port_range_max=80,
    port_range_min=80, protocol="tcp", security_group_id=web_services.id)
ingress_https = networking.SecGroupRule("ingress-https",
    direction="ingress", ethertype="IPv4", port_range_max=443,
    port_range_min=443, protocol="tcp", security_group_id=web_services.id)

rabbitmq = networking.SecGroup("rabbitmq", name="rabbitmq", description="Security Group for RabbitMQ")
ingress_http = networking.SecGroupRule("ingress-rabbit-tcp",
    direction="ingress", ethertype="IPv4", port_range_max=5671,
    port_range_min=5671, protocol="tcp", security_group_id=rabbitmq.id)
ingress_https = networking.SecGroupRule("ingress-rabbit-udp",
    direction="ingress", ethertype="IPv4", port_range_max=5671,
    port_range_min=5671, protocol="udp", security_group_id=rabbitmq.id)

# configuration reference for our VMs
DEFAULT_SECGROUPS = [DEFAULT_SECGROUP_ID, ssh_icmp.id]
VM_CONFIG = {
    "aarnet":               { "ext-net": True, "sec-groups": [web_services.id], "volume": [500] },
    "aarnet-queue":         { "ext-net": True, "sec-groups": [rabbitmq.id, web_services.id], "flavor": "C4R16D40" },
    "aarnet-job-nfs":       { "volume": [20000], "flavor": "C8R32D40" },
    "aarnet-misc-nfs":      { "volume": [200,300,300,1000], "flavor": "C8R32D40" },
    "aarnet-user-nfs":      { "volume": [80000], "flavor": "C8R32D40" },
    "aarnet-db":            { "volume": [200], "flavor": "C8R32D40" },
    "aarnet-backup":        { "ext-net": True, "volume": [500], "flavor": "C2R8D40"},
    "aarnet-ftp-proxy":     { "ext-net": True, "volume": [1000], "flavor": "C2R4D40"},
    "aarnet-w1":            { "volume": [100] },
    "aarnet-w2":            { "volume": [100] },
    "aarnet-w3":            { "volume": [100] },
    "aarnet-w4":            { "volume": [100] },
    "aarnet-w5":            { "volume": [100] },
    "aarnet-w6":            { "volume": [100], "flavor": "C32R128D40" },
    "aarnet-w7":            { "volume": [100] },
    "aarnet-w8":            { "volume": [100] }
}

# create our VMs and store the info somewhere
info = {}
for vm in VM_CONFIG.keys():
    info[vm] = {}

    # define instance port & network config
    info[vm]['port'] = networking.Port(vm + "-port", 
        name = vm + "-port",
        dns_name = vm, 
        security_group_ids = DEFAULT_SECGROUPS + VM_CONFIG[vm].get("sec-groups", []),
        network_id = galaxy_net.id)

    instance_networks = [compute.InstanceNetworkArgs(uuid=galaxy_net.id, port=info[vm]['port'].id)]

    # if we require external access and are using fixed IPs, add the external network to the networks list
    if VM_CONFIG[vm].get("ext-net") == True and EXTERNAL_IP_TYPE == "fixed":
        instance_networks.append(compute.InstanceNetworkArgs(uuid=EXT_NET))

    # create the instance
    info[vm]['instance'] = compute.Instance(vm,
        name = vm,
        flavor_name = VM_CONFIG[vm].get("flavor", "C16R64D40"),
        block_devices = [compute.InstanceBlockDeviceArgs(source_type = "image", boot_index = 0, delete_on_termination = True, uuid = VM_IMAGE, destination_type = "volume", volume_size = 3)],
        key_pair = key.name,
        networks = instance_networks,
        user_data = USER_DATA
    )

    # if we require external access and are using floating IPs, create and assign one
    if VM_CONFIG[vm].get("ext-net") == True and EXTERNAL_IP_TYPE == "floating":
        info[vm]['fip'] = networking.FloatingIp(vm + "-fip", pool = "ext-net")
        networking.FloatingIpAssociate(vm + "-fip-assoc", floating_ip = info[vm]['fip'].address, port_id = info[vm]['instance'].networks[0].port)

    # if we are allocating any storage, do it now
    info[vm]['blockstorage'] = []
    for index, bs in enumerate(VM_CONFIG[vm].get("volume", [])):
        info[vm]['blockstorage'].append(blockstorage.Volume(vm + "-vol-" + str(index), name = vm + "-vol-" + str(index), size = bs))
        compute.VolumeAttach(vm + "-vol-" + str(index), instance_id = info[vm]['instance'].id, volume_id = info[vm]['blockstorage'][index].id)

## Export the IP of the instance
for vm in info.keys():
    pulumi.export( vm + '-instance-network', info[vm]['instance'].networks)
    if 'fip' in info[vm]:
        pulumi.export( vm + '-floating-ip', info[vm]['fip'].address)

