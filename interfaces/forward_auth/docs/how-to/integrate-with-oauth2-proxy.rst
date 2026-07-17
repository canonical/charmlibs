.. meta::
   :description: Integrate your charm and ingress provider with Identity and Access Proxy using the `forward-auth` interface.

.. _integrate-with-oauth2-proxy:

Integrate your charm with Identity and Access Proxy
===================================================

Applications that do not conform to OAuth/OIDC standards or don't offer built-in access control
can be secured using the Identity and Access Proxy (IAP) solution. This approach allows you to protect application endpoints
by intercepting incoming requests and delegating the authentication and authorization (authn/authz) process to the relevant components of the `Identity Platform <https://charmhub.io/identity-platform>`_.

OAuth2 Proxy is the main entrypoint to plug the Identity and Access Proxy to your charmed operator. This is achieved through the power of Juju relations.

This guide explains how to extend the Identity Platform with the Identity and Access Proxy solution
and integrate it with your charm, allowing you to restrict access to your application to authenticated users only.

Prerequisites
-------------

We are going to assume that:

1. Your charmed application does not support the OAuth 2.0/OIDC protocols (otherwise, refer to `this guide <https://charmhub.io/topics/canonical-identity-platform/how-to/integrate-oidc-compatible-charms>`_ instead).
2. Your charmed application supports integration with Charmed Traefik via the ``ingress-per-app`` or ``ingress-per-unit`` interface and provides Charmed OAuth2 Proxy with necessary data by supporting the ``auth_proxy`` interface.
3. You have deployed the Identity Platform, see `tutorial <https://charmhub.io/topics/canonical-identity-platform/tutorials/e2e-tutorial>`_.
4. You have deployed your charmed application on Kubernetes.

Initial Deployment State
~~~~~~~~~~~~~~~~~~~~~~~~

This deployment should be your starting point:

.. code:: text

    Model  Controller     Cloud/Region        Version  SLA          Timestamp
    iam    my-controller  microk8s/localhost  3.6.13   unsupported  16:37:26+01:00

    SAAS           Status  Store  URL
    ingress        active  local  admin/core.ingress
    postgresql     active  local  admin/core.postgresql
    traefik-route  active  local  admin/core.traefik-route

    App       Version  Status  Scale  Charm                                Channel        Rev  Address         Exposed  Message
    hydra     v2.3.0   active      1  hydra                                latest/stable  395  10.152.183.127  no
    kratos    v1.3.1   active      1  kratos                               latest/stable  565  10.152.183.75   no
    login-ui  0.24.2   active      1  identity-platform-login-ui-operator  latest/stable  197  10.152.183.135  no

    Unit         Workload  Agent  Address      Ports  Message
    hydra/0* active    idle   10.1.57.184
    kratos/0* active    idle   10.1.57.183
    login-ui/0* active    idle   10.1.57.185

    Offer              Application  Charm   Rev  Connected  Endpoint     Interface    Role
    kratos-info-offer  kratos       kratos  565  0/0        kratos-info  kratos_info  provider
    oauth-offer        hydra        hydra   395  0/0        oauth        oauth        provider

In this guide, we assume you also deployed your charmed application in the ``iam`` model.

Step 1: Configure Ingress and Forward Auth
------------------------------------------

In order to set up the proxy, you first need to expose the ``forward-auth`` offer, enable the feature in Charmed Traefik, and integrate it with your charm via the ingress relation.

.. code-block:: shell

    juju config traefik-public enable_experimental_forward_auth=True -m core
    juju offer traefik-public:experimental-forward-auth forward-auth -m core
    juju integrate your-charm admin/core.ingress -m iam

Step 2: Deploy and Integrate OAuth2 Proxy
-----------------------------------------

The next step is to deploy Charmed OAuth2 Proxy and integrate it with Charmed Traefik using the exposed offer:

.. code-block:: shell

    juju deploy oauth2-proxy-k8s --channel latest/stable --trust -m iam
    juju integrate oauth2-proxy:forward-auth admin/core.forward-auth -m iam

You can follow the deployment status with ``watch -c juju status --color``.

Step 3: Integrate Your Application with the Proxy
-------------------------------------------------

Then, integrate your charm with the proxy by running:

.. code-block:: shell

    juju integrate oauth2-proxy-k8s your-charm:auth-proxy -m iam

Step 4: Connect to the Identity Provider
----------------------------------------

Finally, integrate the proxy with the Identity Platform's OIDC provider—Charmed Hydra:

.. code-block:: shell

    juju integrate oauth2-proxy-k8s:oauth hydra -m iam

Authentication Flow
-------------------

When you access your application, Charmed Traefik will ask OAuth2 Proxy whether access to the endpoint is protected.
If it is, the proxy will check for a valid session. If no valid session is found, it will redirect you to the Identity Platform login page.
Upon successful authentication, you will be redirected back to your application.

.. note::
    See more: `Charmhub | OAuth2 Proxy > Integrations <https://charmhub.io/oauth2-proxy-k8s/integrations>`_
