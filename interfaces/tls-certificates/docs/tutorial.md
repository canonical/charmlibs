# Getting started

In this tutorial, we will take a [working Nginx charm](https://github.com/canonical/tls-certificates-interface-demo) and add the TLS Certificates integration using the `charmlibs.interfaces.tls_certificates` library.

## Pre-requisites

### Knowledge
- You have some experience writing charms and are comfortable with the charm development tooling

### Software
- Ubuntu 22.04
- A Juju controller with at least version 3.0 running on MicroK8s.
- Charmcraft

## 1. Pack and deploy the nginx demo charm
In this section, we will deploy a demo Nginx charm and access its HTTP address via our browser.

Clone the TLS Certificates Interface Demo project:
```shell
git clone git@github.com:canonical/tls-certificates-interface-demo.git
```

Move to the repo directory:

```shell
cd tls-certificates-interface-demo
```

Pack the charm

```shell
charmcraft pack
```

Create a Juju model:

```shell
juju add-model demo
```

Deploy the charm

```shell
juju deploy ./tls-certificates-interface-demo_amd64.charm nginx-http --resource nginx-image=nginx:1.27.1
```

Wait for the charm to go to the Active/Idle status:

```shell
> juju status
Model  Controller          Cloud/Region        Version  SLA          Timestamp
demo   microk8s-localhost  microk8s/localhost  3.5.3    unsupported  15:12:25-04:00

App         Version  Status  Scale  Charm                            Channel  Rev  Address         Exposed  Message
nginx-http           active      1  tls-certificates-interface-demo             0  10.152.183.199  no

Unit           Workload  Agent  Address      Ports  Message
nginx-http/0*  active    idle   10.1.19.158
```

Using your browser, navigate to the application address on port 8080 using the HTTP scheme. Here this would be `http://10.152.183.199:8080`.

You should see the default Nginx landing page ("Welcome to nginx!") with a short paragraph confirming the server is working and a link to nginx.org.

We now know that have a working Nginx charm.

## 2. Import and use the TLS Certificates Library

This section outlines the changes that have to be made to the Nginx charm to support the TLS certificates integration. You can use [this pull request](https://github.com/canonical/tls-certificates-interface-demo/pull/5) as reference as well.

Add `charmlibs-interfaces-tls-certificates` to your Python dependencies, then import the classes you need at the top of `src/charm.py`:

```python
from charmlibs.interfaces.tls_certificates import (
    Certificate,
    CertificateRequestAttributes,
    Mode,
    PrivateKey,
    TLSCertificatesRequiresV4,
)
```

All of the following changes are made in `src/charm.py`.

Add the following global variables:

```python
CERTS_DIR_PATH = "/etc/nginx"
PRIVATE_KEY_NAME = "nginx.key"
CERTIFICATE_NAME = "nginx.pem"
```

In the charm's class constructor, instantiate a `TLSCertificatesRequiresV4` object and have the `certificate_available` event handled by our central `_configure` event handler:

```python

class TlsCertificatesInterfaceDemoCharm(ops.CharmBase):
    """Charm the service."""

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        ...
        self.certificates = TLSCertificatesRequiresV4(
            charm=self,
            relationship_name="certificates",
            certificate_requests=[self._get_certificate_request_attributes()],
            mode=Mode.UNIT,
        )
        ...
        framework.observe(
            self.certificates.on.certificate_available, self._configure
        )
        ...
```

Add a `_get_certificate_request_attributes` method that describes the attributes of the certificate we'd like to request.

```python

class TlsCertificatesInterfaceDemoCharm(ops.CharmBase):

    def _get_certificate_request_attributes(self) -> CertificateRequestAttributes:
        return CertificateRequestAttributes(common_name="example.com")

```

In the collect unit status event handler, have the charm go to `Blocked` status until it is integrated with a TLS Certificates Provider:

```python

class TlsCertificatesInterfaceDemoCharm(ops.CharmBase):

    def __init__(self, framework: ops.Framework):
        ...
        framework.observe(self.on.collect_unit_status, self._on_collect_status)

    def _on_collect_status(self, event: ops.CollectStatusEvent):
        ...
        if not self._relation_created("certificates"):
            event.add_status(
                ops.BlockedStatus("certificates integration not created")
            )
            return
        ...
```

Update the `_configure` event handler to manage TLS Certificates and restart the Pebble container when certificates have changed:

```python
class TlsCertificatesInterfaceDemoCharm(ops.CharmBase):
    """Charm the service."""

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        ...
        framework.observe(self.on["nginx"].pebble_ready, self._configure)
        framework.observe(self.on.config_changed, self._configure)
        framework.observe(self.certificates.on.certificate_available, self._configure)

    def _configure(self, _: ops.EventBase):
        if not self.container.can_connect():
            return
        if not self._relation_created("certificates"):
            return
        if not self._certificate_is_available():
            return
        certificate_update_required = self._check_and_update_certificate()
        desired_config_file = self._generate_config_file()
        if config_update_required := self._is_config_update_required(desired_config_file):
            self._push_config_file(content=desired_config_file)
        should_restart = config_update_required or certificate_update_required
        self._configure_pebble(restart=should_restart)
```

We will need the following methods to handle pulling, pushing and comparing certificates:

```python

class TlsCertificatesInterfaceDemoCharm(ops.CharmBase):

    def _relation_created(self, relation_name: str) -> bool:
        return bool(self.model.relations.get(relation_name))

    def _certificate_is_available(self) -> bool:
        cert, key = self.certificates.get_assigned_certificate(
            certificate_request=self._get_certificate_request_attributes()
        )
        return bool(cert and key)

    def _check_and_update_certificate(self) -> bool:
        """Check if the certificate or private key needs an update and perform the update.

        This method retrieves the currently assigned certificate and private key associated with
        the charm's TLS relation. It checks whether the certificate or private key has changed
        or needs to be updated. If an update is necessary, the new certificate or private key is
        stored.

        Returns:
            bool: True if either the certificate or the private key was updated, False otherwise.
        """
        provider_certificate, private_key = self.certificates.get_assigned_certificate(
            certificate_request=self._get_certificate_request_attributes()
        )
        if not provider_certificate or not private_key:
            logger.debug("Certificate or private key is not available")
            return False
        if certificate_update_required := self._is_certificate_update_required(
            provider_certificate.certificate
        ):
            self._store_certificate(certificate=provider_certificate.certificate)
        if private_key_update_required := self._is_private_key_update_required(private_key):
            self._store_private_key(private_key=private_key)
        return certificate_update_required or private_key_update_required

    def _is_certificate_update_required(self, certificate: Certificate) -> bool:
        return self._get_existing_certificate() != certificate

    def _is_private_key_update_required(self, private_key: PrivateKey) -> bool:
        return self._get_existing_private_key() != private_key

    def _get_existing_certificate(self) -> Optional[Certificate]:
        return self._get_stored_certificate() if self._certificate_is_stored() else None

    def _get_existing_private_key(self) -> Optional[PrivateKey]:
        return self._get_stored_private_key() if self._private_key_is_stored() else None

    def _certificate_is_stored(self) -> bool:
        return self.container.exists(path=f"{CERTS_DIR_PATH}/{CERTIFICATE_NAME}")

    def _private_key_is_stored(self) -> bool:
        return self.container.exists(path=f"{CERTS_DIR_PATH}/{PRIVATE_KEY_NAME}")

    def _get_stored_certificate(self) -> Certificate:
        cert_string = str(self.container.pull(path=f"{CERTS_DIR_PATH}/{CERTIFICATE_NAME}").read())
        return Certificate.from_string(cert_string)

    def _get_stored_private_key(self) -> PrivateKey:
        key_string = str(self.container.pull(path=f"{CERTS_DIR_PATH}/{PRIVATE_KEY_NAME}").read())
        return PrivateKey.from_string(key_string)

    def _store_certificate(self, certificate: Certificate) -> None:
        """Store certificate in workload."""
        self.container.push(path=f"{CERTS_DIR_PATH}/{CERTIFICATE_NAME}", source=str(certificate))
        logger.info("Pushed certificate pushed to workload")

    def _store_private_key(self, private_key: PrivateKey) -> None:
        """Store private key in workload."""
        self.container.push(
            path=f"{CERTS_DIR_PATH}/{PRIVATE_KEY_NAME}",
            source=str(private_key),
        )
        logger.info("Pushed private key to workload")

```

## 3. Handle attribute changes

The `CertificateRequestAttributes` can change. For the library to pick up the changes and generate new CSRs, you can register `refresh_events` when instantiating `TLSCertificatesRequiresV4`:

```python

class TlsCertificatesInterfaceDemoCharm(ops.CharmBase):
    """Charm the service."""

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        ...
        self.certificates = TLSCertificatesRequiresV4(
            charm=self,
            relationship_name="certificates",
            certificate_requests=[self._get_certificate_request_attributes()],
            mode=Mode.UNIT,
            refresh_events=[self.on.config_changed]
        )
        ...
        framework.observe(
            self.certificates.on.certificate_available, self._configure
        )
        ...
```
Or you can use the public `sync` function of the library to trigger the same refresh process:

```python
self.certificates.sync()
```


## 4. Deploy the nginx charm and integrate it with a TLS provider

Deploy the new nginx charm:

```
juju deploy ./tls-certificates-interface-demo_amd64.charm nginx-https --resource nginx-image=nginx:1.27.1
```

Wait for the charm to go to the Blocked/idle status:

```shell
> juju status
Model  Controller          Cloud/Region        Version  SLA          Timestamp
demo   microk8s-localhost  microk8s/localhost  3.5.3    unsupported  15:15:22-04:00

App          Version  Status   Scale  Charm                            Channel  Rev  Address         Exposed  Message
nginx-http            active       1  tls-certificates-interface-demo             0  10.152.183.199  no
nginx-https           blocked      1  tls-certificates-interface-demo             1  10.152.183.188  no       certificates integration not created

Unit            Workload  Agent  Address      Ports  Message
nginx-http/0*   active    idle   10.1.19.158
nginx-https/0*  blocked   idle   10.1.19.145         certificates integration not created
```

Deploy [Self Signed Certificates](https://charmhub.io/self-signed-certificates) (a TLS Certificates provider), and integrate it with the nginx charm

```shell
juju deploy self-signed-certificates --channel=1/stable
juju integrate self-signed-certificates:certificates nginx-https:certificates
```

Wait for the `nginx-https` charm to go to the Active/Idle status:

```shell
> juju status
Model  Controller          Cloud/Region        Version  SLA          Timestamp
demo   microk8s-localhost  microk8s/localhost  3.5.3    unsupported  15:17:13-04:00

App                       Version  Status   Scale  Charm                            Channel        Rev  Address         Exposed  Message
nginx-http                         active       1  tls-certificates-interface-demo                   0  10.152.183.199  no
nginx-https                        waiting      1  tls-certificates-interface-demo                   1  10.152.183.188  no       installing agent
self-signed-certificates           active       1  self-signed-certificates         latest/stable  155  10.152.183.242  no

Unit                         Workload  Agent  Address      Ports  Message
nginx-http/0*                active    idle   10.1.19.158
nginx-https/0*               active    idle   10.1.19.145
self-signed-certificates/0*  active    idle   10.1.19.146
```

Using your browser, navigate to the application address on port 8080 using the HTTPS scheme. Here this would be `https://10.152.183.188:8080`.

You should see the browser's standard "Your connection is not private" warning page (in Chrome the error code is `NET::ERR_CERT_AUTHORITY_INVALID`), telling you that the HTTPS certificate is not valid.

Don't worry, this message is expected since the certificate we received is self-signed.

Click on Advanced -> Proceed and you should now see the same Nginx page as in step 1 -- the default Nginx landing page, this time served over HTTPS.

You can inspect the certificate from your browser's address bar. You should see a leaf certificate issued for `example.com` by `Self Signed Certificates`, with a chain that ends at the self-signed CA certificate generated by the `self-signed-certificates` charm. The Subject Alternative Name (SAN) section will list `DNS Name=example.com`.

Congratulations, you added the TLS integration to your charm.
