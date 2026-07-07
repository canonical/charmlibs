.. meta::
   :description: Step-by-step tutorial on how to set up Hydra on MicroK8s with Juju, PostgreSQL database, Traefik ingress, and Canonical Observability Stack.

Getting started
===============

This tutorial shows how to set up a fully working Hydra server using the Hydra charm, MicroK8s, and Juju.

Set things up
-------------

Bootstrap a `microk8s controller <https://juju.is/docs/juju/set-up--tear-down-your-test-environment#heading--set-up-automatically>`_ using juju ``3.4`` and create a new Juju model:

.. code-block:: shell

   $ juju add-model hydra
   Added 'hydra' model on microk8s/localhost with credential 'microk8s' for user 'admin'

See more: `Set up your test environment automatically <https://juju.is/docs/juju/set-up--tear-down-your-test-environment#heading--set-up-automatically>`_


Deploy, configure, integrate, and manage Hydra
----------------------------------------------

Hydra requires a way to persist data; in the case of our charm, we enforce the usage of a ``postgreSQL`` database.

We are going to be using the `postgresql-k8s charm <https://charmhub.io/postgresql-k8s>`_.

.. code-block:: shell

   $ juju deploy postgresql-k8s --channel 14/stable --trust postgresql
   Deployed "postgresql" from charm-hub charm "postgresql-k8s", revision 193 in channel 14/stable on ubuntu@22.04/stable

Once that is done (no need to wait for it to be ready), we can proceed with deploying ``hydra`` and integrating the two charms.

.. code-block:: shell

   $ juju deploy hydra --channel 0.2/stable
   Deployed "hydra" from charm-hub charm "hydra", revision 278 in channel 0.2/stable on ubuntu@22.04/stable

Integrate with PostgreSQL
^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: shell

   $ juju integrate postgresql:database hydra

After some time, we should be able to inspect that all has been successfully deployed and connected:

.. code-block:: shell

   $ juju status --relations                           

   Model  Controller          Cloud/Region        Version  SLA          Timestamp
   hydra  microk8s-localhost  microk8s/localhost  3.4.2    unsupported  15:57:02+01:00

   App         Version  Status   Scale Charm          Channel       Rev  Address         Exposed  Message
   hydra       v2.3.0   waiting      1 hydra          latest/stable 395  10.152.183.141  no       installing agent
   postgresql  14.10    active       1 postgresql-k8s 14/stable     925  10.152.183.100  no       Primary

   Unit           Workload  Agent  Address       Ports  Message
   hydra/0*       blocked   idle   10.1.245.156         Missing required relation with ingress
   postgresql/0*  active    idle   10.1.245.160         Primary

   Integration provider       Requirer                   Interface          Type     Message
   hydra:hydra                hydra:hydra                hydra_peers        peer     
   postgresql:database        hydra:pg-database          postgresql_client  regular  
   postgresql:database-peers  postgresql:database-peers  postgresql_peers   peer     
   postgresql:restart         postgresql:restart         rolling_op         peer     
   postgresql:upgrade         postgresql:upgrade         upgrade            peer

You will notice that ``hydra`` is in a blocked status now. The reason is that we need to expose it via an ingress to keep moving forward with the deployment.


Integrate with an Ingress
^^^^^^^^^^^^^^^^^^^^^^^^^

``Hydra`` requires an ``ingress`` relation to be healthy; this is because its APIs need to be publicly available to be a useful component.

`Traefik <https://charmhub.io/traefik-k8s>`_ is the charm of choice to make this happen.

.. code-block:: shell

   $ juju deploy traefik-k8s --channel stable
   Deployed "traefik-k8s" from charm-hub charm "traefik-k8s", revision 176 in channel latest/stable on ubuntu@20.04/stable

We can now proceed with the integration to expose ``Hydra`` public APIs via the ``public-ingress`` relation:

.. code-block:: shell

   $ juju integrate hydra:public-ingress traefik-k8s

After some time, we should be able to inspect that all has been successfully deployed and connected:

.. code-block:: shell

   $ juju status --relations                           

   Model  Controller          Cloud/Region        Version  SLA          Timestamp
   hydra  microk8s-localhost  microk8s/localhost  3.6.2    unsupported  16:02:36+01:00

   App          Version  Status   Scale  Charm           Channel        Rev  Address         Exposed  Message
   hydra        v2.3.0   waiting      1  hydra           latest/stable  395  10.152.183.141  no       installing agent
   postgresql   14.10    active       1  postgresql-k8s  14/stable      925  10.152.183.100  no       Primary
   traefik-k8s  v2.11.0  active       1  traefik-k8s     latest/stable  342  10.64.140.0     no

   Unit            Workload  Agent  Address       Ports  Message
   hydra/0*        active    idle   10.1.245.156         
   postgresql/0*   active    idle   10.1.245.160         Primary
   traefik-k8s/0*  active    idle   10.1.245.159         

   Integration provider       Requirer                   Interface          Type     Message
   hydra:hydra                hydra:hydra                hydra_peers        peer     
   postgresql:database        hydra:pg-database          postgresql_client  regular  
   postgresql:database-peers  postgresql:database-peers  postgresql_peers   peer     
   postgresql:restart         postgresql:restart         rolling_op         peer     
   postgresql:upgrade         postgresql:upgrade         upgrade            peer     
   traefik-k8s:ingress        hydra:public-ingress       ingress            regular  
   traefik-k8s:peers          traefik-k8s:peers          traefik_peers      peer


Grafana, Loki, and Prometheus
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The Hydra operator integrates with the `Canonical Observability Stack <https://charmhub.io/topics/canonical-observability-stack>`_ (COS) bundle.
It comes with a Grafana dashboard as well as Loki and Prometheus alert rules for basic common scenarios.
To integrate with the COS bundle, after you `deploy it <https://charmhub.io/topics/canonical-observability-stack/tutorials/install-microk8s#heading--deploy-the-cos-lite-bundle>`_, run:

.. code-block:: shell

   $ juju integrate hydra:grafana-dashboard grafana:grafana-dashboard
   $ juju integrate hydra:metrics-endpoint prometheus:metrics-endpoint
   $ juju integrate loki:logging hydra:log-proxy


Tear things down
----------------

To tear things down, remove the entire ``hydra`` model in Juju with:

.. code-block:: shell

   juju destroy-model hydra
