# Setup via Ubuntu 24.04

Install [Multipass](https://canonical.com/multipass/install) to launch lightweight Ubuntu VMs.

Launch an Ubuntu 24.04 LTS VM with two CPUs, 20G disk, 6G RAM via Multipass:

```
multipass launch noble -c 2 -d 20G -m 6G -n tee-tutorial
multipass shell tee-tutorial
```

Within the Ubuntu VM shell:

```bash
# Install updates
sudo apt update && sudo apt upgrade -y

# Install Docker
# Add Docker's official GPG key:
sudo apt update
sudo apt install ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

# Add the repository to apt sources:
sudo tee /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Signed-By: /etc/apt/keyrings/docker.asc
EOF

sudo apt update

sudo apt install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin -y

# Add to docker group
sudo groupadd docker
sudo usermod -aG docker $USER

# Install Node via NodeSource
curl -fsSL https://deb.nodesource.com/setup_24.x | sudo bash -
sudo apt install -y nodejs

# Install Phala CLI
sudo npm install -g phala

# Download foundry installer `foundryup`
curl -L https://foundry.paradigm.xyz | bash
# Install forge, cast, anvil, chisel
source ~/.bashrc
foundryup

# Install skopeo
sudo apt install skopeo
```

Log in again to be added to the `docker` group.

Clone the dstack-tutorial repo:

```
git clone https://github.com/amiller/dstack-tutorial
cd dstack-tutorial/
```

For using the dstack-sdk:

```
sudo apt install python3-pip python3-virtualenv
python3 -m virtualenv venv
source venv/bin/activate

pip install dstack-sdk
```
